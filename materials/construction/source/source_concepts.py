from __future__ import annotations

import glob
import json
from pathlib import Path
from typing import Any

from .adapters import StructuredModel
from .cdeval_source import load_cdeval_items
from .base_contracts import StageContext, validate_concept_record
from .errors import PipelineError
from .io import (
    artifact_filename,
    atomic_write_json,
    atomic_write_jsonl,
    iter_jsonl,
    materialize_artifacts,
    normalize_text,
    normalized_key,
    parallel_map,
    require_complete_records,
    stable_id,
    utc_now,
)


CONCEPT_WORD_SAFETY_LIMIT = 30


def run_concepts(context: StageContext) -> list[dict[str, Any]]:
    source_items = load_source_items(context.config["source"])
    if context.limit is not None:
        source_items = source_items[: context.limit]
    stage_dir = context.stage_dir("concepts")
    stage_dir.mkdir(parents=True, exist_ok=True)
    extraction = context.config["concept_extraction"]
    model = StructuredModel(
        extraction["model"],
        usage_context={
            "root": context.run_dir / "usage" / "openai_compatible",
            "run_id": f"{context.run_dir.name}-concepts",
            "purpose": "concept_extraction",
        },
    )
    def worker(item: dict[str, Any]) -> dict[str, Any]:
        artifact_path = stage_dir / artifact_filename(
            item["lineage_id"], "concept"
        )
        if context.resume and artifact_path.exists():
            cached = json.loads(artifact_path.read_text(encoding="utf-8"))
            cached.setdefault("lineage_id", item["lineage_id"])
            return cached
        legacy_path = stage_dir / f"{item['source_record_id']}.json"
        if context.resume and legacy_path.exists():
            cached = json.loads(legacy_path.read_text(encoding="utf-8"))
            cached.setdefault("lineage_id", item["lineage_id"])
            return cached
        record = extract_concept(
            item,
            extraction,
            model,
            source=str(context.config["source"]["adapter"]),
        )
        validate_concept_record(record)
        if not context.dry_run:
            atomic_write_json(artifact_path, record)
        return record

    records = parallel_map(
        source_items,
        worker,
        int(extraction.get("concurrency", context.config["experiment"]["max_workers"])),
        "concept extraction",
        None
        if context.dry_run
        else context.manifest_path("concept_extraction_failures"),
    )
    if not context.dry_run:
        atomic_write_jsonl(context.manifest_path("concepts"), records)
    model.summarize_usage()
    require_complete_records("concept extraction", len(records), len(source_items))
    return records


def load_source_items(source: dict[str, Any]) -> list[dict[str, Any]]:
    adapter = source["adapter"]
    if adapter == "mock":
        concepts = source.get("concepts") or ["greeting customs"]
        return [
            {
                "lineage_id": f"mock_{index:04d}",
                "source_record_id": stable_id("source", "mock", index, concept),
                "source_dataset": str(source.get("dataset_name", "mock")),
                "source_text": normalize_text(concept),
                "source_payload": {
                    "concept": normalize_text(concept),
                    "value_dimension": source.get("value_dimension"),
                    "value_endpoints": source.get("value_endpoints"),
                },
                "preextracted_concept": normalize_text(concept),
            }
            for index, concept in enumerate(concepts, start=1)
        ]
    if adapter == "cdeval":
        return load_cdeval_items(source)
    if adapter == "concept_jsonl":
        path = source.get("path")
        if not path:
            raise PipelineError("source.path is required for concept_jsonl")
        concept_field = str(source.get("concept_field", "concept"))
        id_field = source.get("id_field")
        dataset_name = str(source.get("dataset_name") or Path(path).stem)
        items: list[dict[str, Any]] = []
        for index, row in enumerate(iter_jsonl(path), start=1):
            concept = normalize_text(row.get(concept_field))
            if not concept:
                continue
            raw_id = row.get(id_field) if id_field else index
            items.append(
                {
                    "lineage_id": stable_id("case", dataset_name, raw_id),
                    "source_record_id": stable_id(
                        "source", dataset_name, raw_id, concept
                    ),
                    "source_dataset": dataset_name,
                    "source_text": concept,
                    "source_payload": row,
                    "preextracted_concept": concept,
                }
            )
        return items
    if adapter == "blend":
        pattern = source.get("questions_glob")
        if not pattern:
            raise PipelineError("source.questions_glob is required for blend")
        paths = [Path(path) for path in sorted(glob.glob(str(pattern)))]
        if not paths:
            raise PipelineError(f"No BLEnD question files matched: {pattern}")
        grouped: dict[str, dict[str, Any]] = {}
        for path in paths:
            culture = path.stem.removesuffix("_questions")
            rows = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(rows, list):
                raise PipelineError(f"Expected a JSON list in {path}")
            for index, row in enumerate(rows, start=1):
                if not isinstance(row, dict):
                    raise PipelineError(f"Expected an object at {path}:{index}")
                question_id = normalize_text(row.get("ID"))
                translation = normalize_text(row.get("Translation"))
                if not question_id or not translation:
                    raise PipelineError(f"Missing BLEnD fields at {path}:{index}")
                item = grouped.setdefault(
                    question_id,
                    {
                        "lineage_id": stable_id("case", "blend", question_id),
                        "source_record_id": stable_id(
                            "source", "BLEnD", question_id
                        ),
                        "source_dataset": "BLEnD",
                        "question_id": question_id,
                        "topic": normalize_text(row.get("Topic")),
                        "variants": [],
                    },
                )
                item["variants"].append(
                    {"culture": culture, "translation": translation}
                )
        expected = len(paths)
        result: list[dict[str, Any]] = []
        for item in grouped.values():
            if len(item["variants"]) != expected:
                raise PipelineError(
                    f"BLEnD question {item['question_id']} has "
                    f"{len(item['variants'])}/{expected} variants"
                )
            variants = "\n".join(
                f"- {variant['culture']}: {variant['translation']}"
                for variant in item["variants"]
            )
            result.append(
                {
                    **item,
                    "source_text": variants,
                    "source_payload": {
                        "question_id": item["question_id"],
                        "topic": item["topic"],
                        "variants": item["variants"],
                    },
                }
            )
        return result
    raise PipelineError(f"Unsupported source adapter: {adapter}")


def extract_concept(
    item: dict[str, Any],
    config: dict[str, Any],
    model: StructuredModel,
    *,
    source: str,
) -> dict[str, Any]:
    maximum_words = min(
        int(config.get("max_concept_words", CONCEPT_WORD_SAFETY_LIMIT)),
        CONCEPT_WORD_SAFETY_LIMIT,
    )
    preextracted = item.get("preextracted_concept")
    rationale = ""
    if preextracted and not config.get("force_model", False):
        concept = validate_concept(str(preextracted), maximum_words)
        response_meta = {
            "model": "source",
            "raw_content": "",
            "usage": {},
        }
    else:
        prompt = build_prompt(item, maximum_words, source)
        response = model.complete(
            prompt,
            mock_factory=lambda: {
                "concept": mock_concept(item["source_text"], maximum_words),
                "rationale": "Mock extraction for pipeline verification.",
            },
        )
        concept = validate_concept(response.parsed.get("concept"), maximum_words)
        rationale = normalize_text(response.parsed.get("rationale"))
        if source == "cdeval" and not rationale:
            raise PipelineError("CDEval concept rationale is empty")
        response_meta = {
            "model": response.model,
            "raw_content": response.raw_content,
            "usage": response.usage,
        }
    record = {
        "lineage_id": item["lineage_id"],
        "concept_id": stable_id(
            "concept",
            item["source_dataset"],
            item["lineage_id"],
            normalized_key(concept),
        ),
        "concept": concept,
        "source_dataset": item["source_dataset"],
        "source_record_id": item["source_record_id"],
        "source_payload": item["source_payload"],
        "provenance": {**response_meta, "created_at": utc_now()},
    }
    if rationale:
        record["rationale"] = rationale
    return record


def build_prompt(
    item: dict[str, Any],
    maximum_words: int,
    source: str,
) -> str:
    if source == "cdeval":
        return build_cdeval_prompt(item)
    descriptions = {
        "concept_jsonl": (
            "Normalize one supplied concept for a culture-value data-generation "
            "pipeline. Preserve its meaning and do not add outside facts."
        ),
        "blend": (
            "Extract one source-grounded concept shared across the supplied BLEnD "
            "question variants. Do not answer the questions or add outside "
            "cultural claims."
        ),
        "mock": (
            "Normalize one supplied mock concept for pipeline verification. "
            "Preserve its meaning."
        ),
    }
    description = descriptions.get(source)
    if description is None:
        raise PipelineError(f"Unsupported source adapter for concept prompt: {source}")
    return f"""# Task

{description}

{build_generic_prompt(item, maximum_words)}

Return one JSON object only."""


def build_cdeval_prompt(item: dict[str, Any]) -> str:
    payload = item.get("source_payload")
    if not isinstance(payload, dict):
        raise PipelineError("CDEval concept extraction requires source_payload")

    question = normalize_text(payload.get("Question"))
    option_1 = normalize_text(payload.get("Option 1"))
    option_2 = normalize_text(payload.get("Option 2"))
    domain = normalize_text(payload.get("Domain"))
    dimension = normalize_text(payload.get("value_dimension"))
    endpoints = payload.get("value_endpoints")
    fields = {
        "Question": question,
        "Option 1": option_1,
        "Option 2": option_2,
        "Domain": domain,
        "Hofstede dimension": dimension,
    }
    missing = [name for name, value in fields.items() if not value]
    if missing:
        raise PipelineError(
            f"CDEval concept prompt is missing fields: {missing}"
        )

    if not isinstance(endpoints, list) or len(endpoints) != 2:
        raise PipelineError(
            "CDEval concept prompt requires exactly two value endpoints"
        )
    normalized_endpoints = []
    for endpoint in endpoints:
        if not isinstance(endpoint, dict):
            raise PipelineError("CDEval value endpoints must be objects")
        endpoint_id = normalize_text(endpoint.get("id"))
        description = normalize_text(endpoint.get("description"))
        if not endpoint_id or not description:
            raise PipelineError(
                "CDEval value endpoints require id and description"
            )
        normalized_endpoints.append(
            f"- {endpoint_id}: {description}"
        )
    endpoint_evidence = "\n".join(normalized_endpoints)

    return f"""# Role

You extract one source-grounded concept from a question and two contrasting response options.

# Task Context

## Input

Each input contains:

- a question and two contrasting response options about the same underlying situation;
- a domain that bounds the situation;
- a value dimension; and
- exactly two unassigned value endpoints with descriptions.

The question and options determine the content of the concept. The domain helps disambiguate and bound the situation. The value dimension and endpoint descriptions help identify which part of the source situation is value-sensitive; they must not replace the source situation or introduce information not stated in the question and options.

## Output

Return one `concept` and one `rationale`.

The concept is a concise English noun phrase or gerund phrase that names the specific situation, decision, behavior, or social issue jointly expressed by the question and both options. It identifies their shared source-specific context rather than answering the question, endorsing an option, or naming an abstract cultural value.

The rationale briefly explains how the question establishes the shared situation and how the two options represent contrasting responses within that situation.

# Few-Shot Examples

## Example 1

### Input

Domain: Arts

Question: How do you react when viewing a provocative art piece that challenges your traditional views?

Option 1: I prefer art that conforms to my traditional views. Provocative art makes me uncomfortable.

Option 2: I enjoy provocative art that challenges my views. It opens new perspectives for me.

Value dimension: uncertainty_avoidance

Value endpoints:

- high_uncertainty_avoidance: Prefers clear rules, planning, predictability, and safeguards that reduce ambiguity, unfamiliarity, and perceived risk.
- low_uncertainty_avoidance: Accepts ambiguity and unfamiliar situations more readily, favoring flexibility, experimentation, and adaptation over extensive safeguards.

### Output

{{
  "concept": "reacting to provocative art that challenges traditional views",
  "rationale": "The question establishes a situation in which a person encounters provocative art that challenges existing views. The options contrast discomfort and preference for familiar perspectives with enjoyment of the challenge and openness to new perspectives."
}}

## Example 2

### Input

Domain: Work

Question: What do you mostly seek at work?

Option 1: I look for opportunities that would allow me to develop new skills and competencies over the long term.

Option 2: I seek immediate job satisfaction, such as enjoying what I do daily or having a friendly working environment.

Value dimension: long_term_orientation

Value endpoints:

- long_term_orientation: Prioritizes future rewards, perseverance, adaptation, sustained effort, and investments whose benefits may emerge over a long period.
- short_term_orientation: Prioritizes nearer-term results, present obligations, established norms, and outcomes whose benefits are visible relatively soon.

### Output

{{
  "concept": "choosing between long-term skill growth and immediate job satisfaction",
  "rationale": "The question establishes a decision about what a person prioritizes in their work. The options contrast investing in future skills with seeking present-day enjoyment and a supportive work environment."
}}

# Your Task

Extract exactly one concept from the following input.

Domain: {domain}

Question: {question}

Option 1: {option_1}

Option 2: {option_2}

Value dimension: {dimension}

Value endpoints:

{endpoint_evidence}

# Concept Extraction Guidance

Use only the supplied question, options, domain, value dimension, and endpoint descriptions.

The concept must:

- be one concise English noun phrase or gerund phrase;
- name the specific situation, decision, behavior, or social issue shared by the question and both options;
- identify the common decision context underlying the contrasting responses;
- be grounded primarily in the question and options;
- use the value dimension and endpoint descriptions only to disambiguate the value-sensitive part of the source situation;
- avoid restating either option as the preferred response;
- avoid abstract dimension labels or generic value conflicts, such as “individualism versus collectivism”;
- avoid countries, nationalities, languages, cultural-group claims, and unsupported details.

The rationale must:

- briefly explain how the question establishes the situation;
- explain how the two options represent contrasting responses within that situation; and
- avoid deciding which option is better or associating either option with a value endpoint.

# Output Format

Return exactly one valid JSON object with this shape:

{{
  "concept": "concise source-specific noun phrase or gerund phrase",
  "rationale": "brief source-grounded explanation"
}}

Return JSON only. Do not use Markdown fences or add commentary."""


def build_generic_prompt(item: dict[str, Any], maximum_words: int) -> str:
    return f"""Extract exactly one culture-neutral concept noun phrase.

Source dataset: {item["source_dataset"]}
Source record:
{item["source_text"]}

Requirements:
- describe what the record asks about, not its answer;
- use at most {maximum_words} English words;
- omit culture, country, nationality and language names;
- preserve essential social participants or setting.

Return:
{{"concept":"short noun phrase","rationale":"brief source-grounded reason"}}"""


def validate_concept(value: Any, maximum_words: int) -> str:
    concept = normalize_text(value)
    if not concept:
        raise PipelineError("Extracted concept is empty")
    if len(concept.split()) > maximum_words:
        raise PipelineError(
            f"Extracted concept exceeds {maximum_words} words: {concept}"
        )
    return concept


def mock_concept(source_text: str, maximum_words: int) -> str:
    words = normalize_text(source_text).replace("-", " ").split()
    return " ".join(words[:maximum_words]) or "cultural practice"


def load_concept_artifacts(context: StageContext) -> list[dict[str, Any]]:
    return materialize_artifacts(context.stage_dir("concepts"))
