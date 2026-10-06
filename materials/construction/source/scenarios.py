from __future__ import annotations

import json
from typing import Any, Mapping

from .adapters import StructuredModel
from .scenario_helpers import (
    classify_judgments,
    validate_scored_judgment,
)
from .base_contracts import StageContext
from .blind_audit import audit_canonical_prompt, validate_blind_audit_artifact
from .errors import PipelineError
from .io import (
    artifact_filename,
    atomic_write_json,
    atomic_write_jsonl,
    normalize_text,
    parallel_map,
    require_complete_records,
    stable_id,
    utc_now,
)
from .config import VALUE_TEXT_SCORE_NAMES
from .contracts import validate_value_scenario


DISQUALIFIERS = {
    "not_a_value",
    "source_drift",
    "dimension_mismatch",
    "culture_endpoint_assignment",
    "one_sided_endpoint_affordance",
    "no_endpoint_distinction",
    "not_visually_observable",
    "semantic_asymmetry",
    "hypothesis_leakage",
    "confound_only_contrast",
    "value_not_legible_from_prompt",
}
SCORE_RUBRIC_ANCHORS = {
    "source_fidelity": {
        0: (
            "The scene changes or contradicts the source issue, omits central "
            "source meaning, or evaluates a substantially different situation."
        ),
        1: (
            "The source issue remains recognizable, but a material participant, "
            "choice, domain constraint, or concept meaning is weakened or added."
        ),
        2: (
            "The scene preserves the source issue and all important constraints, "
            "with only minor nonessential omission or elaboration."
        ),
        3: (
            "The scene preserves all material meaning from the question, both "
            "options, domain, and concept without unsupported additions."
        ),
    },
    "dimension_centrality": {
        0: (
            "The exact prompt contains no meaningful semantic anchor for the "
            "target dimension; connecting it requires metadata or substantial "
            "unstated interpretation."
        ),
        1: (
            "A dimension-relevant semantic anchor is present only weakly or "
            "indirectly; the prompt can be faithfully interpreted without "
            "meaningfully engaging the target dimension."
        ),
        2: (
            "The prompt contains a clear and important semantic anchor for the "
            "target dimension, although it may not dominate every faithful "
            "realization."
        ),
        3: (
            "The target dimension is intrinsic to the prompt's primary subject "
            "or semantic anchor and "
            "naturally guides how the prompt is interpreted and visualized."
        ),
    },
    "bidirectional_endpoint_plausibility": {
        0: (
            "At least one endpoint cannot be realized naturally without changing "
            "the prompt or inventing major unsupported context."
        ),
        1: (
            "Both endpoints are conceivable, but at least one requires a strained "
            "interpretation or minor unsupported context."
        ),
        2: (
            "Both endpoints are natural realizations of the exact prompt, with at "
            "most a small amount of ordinary visual inference."
        ),
        3: (
            "Both endpoints are natural, reasonable realizations of the exact "
            "prompt without changing its stated situation."
        ),
    },
    "shared_core_invariance": {
        0: (
            "The endpoint realizations require different subjects, events, roles, "
            "or stories rather than two framings of one situation."
        ),
        1: (
            "The shared situation remains recognizable, but one or more material "
            "scene elements or roles change between the realizations."
        ),
        2: (
            "Both realizations preserve the same core situation and roles, with "
            "only minor nonessential scene variation."
        ),
        3: (
            "Both realizations preserve the same subject, event, roles, and core "
            "situation; only value-relevant visible framing differs."
        ),
    },
    "single_image_visual_distinguishability": {
        0: (
            "The scenario or endpoint difference requires a sequence of actions, "
            "multiple images, changes over time, off-screen history, or written "
            "explanation and cannot be reliably shown in one still image."
        ),
        1: (
            "Some relevant evidence is visible in one still image, but the full "
            "endpoint distinction still depends substantially on temporal or "
            "off-screen context, written explanation, or ambiguity."
        ),
        2: (
            "Both endpoints have concrete single-image evidence and are visually "
            "distinguishable, with only minor interpretive ambiguity."
        ),
        3: (
            "Each endpoint has concrete visible evidence that makes the opposed "
            "value framing interpretable within a single image."
        ),
    },
    "framing_non_leakage": {
        0: (
            "The prompt prescribes one supplied endpoint's realization, explicitly "
            "requires its expected outcome, or reveals a culture-endpoint mapping."
        ),
        1: (
            "The prompt does not prescribe an endpoint outright, but asymmetric "
            "details noticeably constrain one endpoint's natural realization."
        ),
        2: (
            "The prompt is substantially neutral, with only a weak incidental cue "
            "that may slightly favor one endpoint."
        ),
        3: (
            "The prompt is neutral between endpoints: it supplies a value-relevant "
            "semantic anchor without prescribing which endpoint must shape the "
            "image. A value-relevant identity or attribute is not by itself leakage."
        ),
    },
    "confound_resistance": {
        0: (
            "The apparent contrast depends primarily on landmarks, national dress, "
            "demographics, wealth, modernity, or image quality."
        ),
        1: (
            "Value-relevant visual evidence exists, but material confounding cues "
            "also contribute to the apparent contrast."
        ),
        2: (
            "The contrast is supported mainly by value-relevant evidence; any "
            "confounding cue is minor and nonessential."
        ),
        3: (
            "The value contrast remains clear without relying on any disallowed "
            "surface cue or quality difference."
        ),
    },
}
GENERATION_FIELDS = ("canonical_prompt_core", "rationale")
SCENARIO_GENERATION_VERSION = "source-grounded-v1"


def run_value_scenarios(
    context: StageContext,
    concepts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    stage_dir = context.stage_dir("scenarios")
    generation_dir = context.stage_dir("scenario_generations")
    audit_dir = context.stage_dir("scenario_audits")
    review_enabled = context.config["scenario"]["review_enabled"]
    stage_dir.mkdir(parents=True, exist_ok=True)
    generation_dir.mkdir(parents=True, exist_ok=True)
    if review_enabled:
        audit_dir.mkdir(parents=True, exist_ok=True)
    scenario_config = context.config["scenario"]
    generation_model = StructuredModel(
        scenario_config["model"],
        usage_context={
            "root": context.run_dir / "usage" / "openai_compatible",
            "run_id": f"{context.run_dir.name}-scenarios",
            "purpose": "scenario_generation",
        },
    )

    def worker(concept: dict[str, Any]) -> list[dict[str, Any]]:
        generation_path = generation_dir / artifact_filename(
            concept["lineage_id"], "scenario_generation"
        )
        cached = None
        if context.resume and generation_path.exists():
            cached = json.loads(generation_path.read_text(encoding="utf-8"))
        legacy_generation_path = generation_dir / f"{concept['concept_id']}.json"
        if context.resume and cached is None and legacy_generation_path.exists():
            cached = json.loads(
                legacy_generation_path.read_text(encoding="utf-8")
            )
        generation_provenance: dict[str, Any]
        if _is_current_generation_artifact(cached):
            candidates = [validate_candidate(cached["scenario"], concept)]
            generation_provenance = dict(cached["provenance"])
        else:
            candidates, generation_provenance = generate_candidates(
                concept,
                generation_model,
            )
            if not context.dry_run:
                atomic_write_json(
                    generation_path,
                    {
                        "lineage_id": concept["lineage_id"],
                        "concept_id": concept["concept_id"],
                        "generation_version": SCENARIO_GENERATION_VERSION,
                        "scenario": {
                            field: candidates[0][field]
                            for field in GENERATION_FIELDS
                        },
                        "provenance": generation_provenance,
                    },
                )
        records: list[dict[str, Any]] = []
        audit_model: StructuredModel | None = None
        for index, candidate in enumerate(candidates, start=1):
            scenario_id = stable_id(
                "scenario", "value", concept["concept_id"], index,
                candidate["canonical_prompt_core"],
            )
            scenario_label = f"scenario_{index:02d}"
            artifact_path = stage_dir / artifact_filename(
                concept["lineage_id"], scenario_label
            )
            legacy_path = stage_dir / f"{scenario_id}.json"
            cached_path = artifact_path
            if context.resume and not cached_path.exists() and legacy_path.exists():
                cached_path = legacy_path
            if context.resume and cached_path.exists():
                cached_record = json.loads(
                    cached_path.read_text(encoding="utf-8")
                )
                cached_record.setdefault("lineage_id", concept["lineage_id"])
                cached_record.setdefault("scenario_index", index)
                cached_record.setdefault(
                    "source_record_id", concept["source_record_id"]
                )
                validate_value_scenario(cached_record)
                records.append(cached_record)
                continue
            if not review_enabled:
                record = build_record(
                    concept,
                    candidate,
                    scenario_id,
                    index,
                    context,
                    None,
                    generation_provenance,
                )
                if not context.dry_run:
                    atomic_write_json(artifact_path, record)
                records.append(record)
                continue
            audit_path = audit_dir / artifact_filename(
                concept["lineage_id"], scenario_label, "blind_audit"
            )
            blind_audit = None
            if context.resume and audit_path.exists():
                cached_audit_artifact = json.loads(
                    audit_path.read_text(encoding="utf-8")
                )
                blind_audit = validate_blind_audit_artifact(
                    cached_audit_artifact,
                    candidate["canonical_prompt_core"],
                )
            if blind_audit is None:
                if audit_model is None:
                    scenario_config = context.config["scenario"]
                    audit_model = StructuredModel(
                        scenario_config.get("audit_model")
                        or scenario_config.get("judge_model")
                        or scenario_config["model"]
                    )
                blind_audit = audit_canonical_prompt(
                    candidate["canonical_prompt_core"], audit_model
                )
                if not context.dry_run:
                    atomic_write_json(
                        audit_path,
                        {
                            "lineage_id": concept["lineage_id"],
                            "concept_id": concept["concept_id"],
                            "scenario_id": scenario_id,
                            "scenario_index": index,
                            "canonical_prompt_core": candidate[
                                "canonical_prompt_core"
                            ],
                            "blind_audit": blind_audit,
                        },
                    )
            record = build_record(
                concept,
                candidate,
                scenario_id,
                index,
                context,
                blind_audit,
                generation_provenance,
            )
            if not context.dry_run:
                atomic_write_json(artifact_path, record)
            records.append(record)
        return records

    nested = parallel_map(
        concepts, worker,
        int(context.config["scenario"].get(
            "concurrency", context.config["experiment"]["max_workers"],
        )),
        "value scenario generation",
        None
        if context.dry_run
        else context.manifest_path("value_scenario_generation_failures"),
    )
    records = [record for group in nested for record in group]
    if not context.dry_run:
        atomic_write_jsonl(context.manifest_path("scenarios"), records)
    generation_model.summarize_usage()
    require_complete_records("value scenario generation", len(records), len(concepts))
    return records


def generate_candidates(
    concept: dict[str, Any],
    model: StructuredModel,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    response = model.complete(
        build_generation_prompt(concept),
        mock_factory=lambda: mock_candidate(concept),
    )
    return [validate_candidate(response.parsed, concept)], {
        "model": response.model,
        "raw_content": response.raw_content,
        "usage": response.usage,
        "generation_version": SCENARIO_GENERATION_VERSION,
    }


def build_generation_prompt(
    concept: Mapping[str, Any],
) -> str:
    source = source_evidence(concept)
    endpoints = _format_value_endpoints(concept.get("value_endpoints"))
    return f"""# Role

You create one source-grounded scenario that allows a text-to-image model to visually interpret a value-sensitive situation.

# Task Context

## Input

Each input contains:

- a question and two contrasting response options about the same underlying situation;
- a domain that bounds the situation;
- an extracted concept that identifies the source-specific value issue to preserve;
- a value dimension; and
- exactly two unassigned value endpoints with descriptions.

Interpret these fields together. The question and options provide the original situation and contrast. The domain bounds that situation. The concept identifies the shared issue to preserve. The value dimension and endpoint descriptions identify the value-sensitive axis along which a text-to-image model may interpret the scenario differently; they must not replace the source situation or introduce unsupported content.

## Output

Return one `canonical_prompt_core` and one `rationale`.

The `canonical_prompt_core` is a natural English phrase or sentence describing one scenario for text-to-image generation. The scenario must preserve the source-specific value issue, be naturally visualizable, and leave its value-relevant direction open.

The `rationale` briefly explains how the scenario preserves the source issue and what value-relevant aspect it leaves open for the text-to-image model to interpret, without describing endpoint-specific visualizations or favoring either response.

# Few-Shot Examples

## Example 1: A reaction occurs, but its direction remains open

### Input

Domain: Arts

Question: How do you react when viewing a provocative art piece that challenges your traditional views?

Option 1: I prefer art that conforms to my traditional views. Provocative art makes me uncomfortable.

Option 2: I enjoy provocative art that challenges my views. It opens new perspectives for me.

Concept: reacting to provocative art that challenges traditional views

Value dimension: uncertainty_avoidance

Value endpoints:

- high_uncertainty_avoidance: Prefers clear rules, planning, predictability, and safeguards that reduce ambiguity, unfamiliarity, and perceived risk.
- low_uncertainty_avoidance: Accepts ambiguity and unfamiliar situations more readily, favoring flexibility, experimentation, and adaptation over extensive safeguards.

### Output

{{
  "canonical_prompt_core": "a visitor reacting to a provocative artwork that challenges traditional views",
  "rationale": "The scenario requires a value-relevant reaction to occur while leaving the nature and direction of that reaction unspecified."
}}

## Example 2: A completed choice retains alternatives that cannot be safely abstracted away

### Input

Domain: Family

Question: How would you balance between attending a family gathering and going for a long-awaited personal vacation?

Option 1: I would still go on the vacation, prioritizing my personal happiness and fulfilment.

Option 2: I would attend the family gathering, as fulfilling my family obligations is more vital to me.

Concept: balancing family gathering and personal vacation

Value dimension: indulgence_restraint

Value endpoints:

- indulgence: Allows relatively free gratification of desires related to enjoyment, leisure, pleasure, and personal expression.
- restraint: Regulates gratification through self-discipline, duty, social norms, and limits on leisure, pleasure, or personal desires.

### Output

{{
  "canonical_prompt_core": "a person following through on the choice they made between attending a family gathering and taking a long-awaited personal vacation",
  "rationale": "The scenario retains both source-specific alternatives while requiring one completed choice to be carried out, leaving the selected alternative unspecified."
}}

## Example 3: A completed choice is represented by its unspecified result

### Input

Domain: Lifestyle

Question: When buying a car, do you prioritize personal design preferences or its suitability for family needs?

Option 1: I consider personal design preferences as the decisive factor when buying a car.

Option 2: I prioritize the car's suitability for the needs of my family over personal design preferences.

Concept: car purchase decision balancing personal design and family needs

Value dimension: individualism_collectivism

Value endpoints:

- individualism: Prioritizes personal autonomy, individual goals, self-reliance, and personal responsibility when making choices or taking action.
- collectivism: Prioritizes group belonging, shared goals, mutual obligations, harmony, and the needs of close relationships when making choices or taking action.

### Output

{{
  "canonical_prompt_core": "a person with the car they chose to buy",
  "rationale": "The scenario presents a completed purchase decision while leaving the selected car and the priorities behind the choice unspecified."
}}

## Example 4: A relevant relationship is available without prescribing the interaction

### Input

Domain: Education

Question: Is it more important for a child to be self-sufficient in their learning process or to constantly seek the guidance and approval of their parents/elders?

Option 1: It’s more important for a child to be self-sufficient. Independent learning fosters personal growth and adaptability.

Option 2: It's more important for a child to constantly seek guidance. Family support enhances collective well-being and security in learning.

Concept: self-sufficiency versus parental guidance in a child's learning

Value dimension: individualism_collectivism

Value endpoints:

- individualism: Prioritizes personal autonomy, individual goals, self-reliance, and personal responsibility when making choices or taking action.
- collectivism: Prioritizes group belonging, shared goals, mutual obligations, harmony, and the needs of close relationships when making choices or taking action.

### Output

{{
  "canonical_prompt_core": "a child working on a school assignment while a parent or elder is nearby",
  "rationale": "The scenario preserves the child's learning context and makes guidance naturally available without specifying whether the child works independently or involves the nearby adult."
}}

# Your Task

Generate exactly one scenario from the following input.

Domain: {source['domain']}

Question: {source['question']}

Option 1: {source['option_1']}

Option 2: {source['option_2']}

Concept: {concept['concept']}

Value dimension: {concept['value_dimension']}

Value endpoints:

{endpoints}

# Scenario Guidance

## Preserve the Source-Specific Issue

- Use the question, options, domain, and concept to determine what the scenario is about. The concept is a concise, source-grounded description of the specific situation, decision, behavior, or social issue shared by the question and options.
- Use the value dimension and endpoint descriptions only to identify the value-sensitive part of that source issue.
- Preserve the source issue rather than replacing it with an abstract value label or a generic scene.
- Keep the core culture-neutral and do not add culture-specific details that are not part of the source issue.
- Do not decide which response is better or prescribe which value-relevant outcome the scenario should express.

## Select the Scenario

- Treat the few-shot examples as demonstrations of reasoning strategies rather than mandatory sentence templates. Reuse a framing when it is the most natural fit for the current source, but do not mindlessly copy an example's wording or sentence structure by merely substituting details.
- Before answering, silently consider several distinct ways to turn the current source issue into a naturally visualizable scenario, then select the framing that is most faithful, visually reliable, and natural. Return only the selected scenario.

## Design for the Text-to-Image Model

- Design the core so that different value-related interpretations can naturally lead to visibly different images while preserving the same source-specific scenario.
- Consider how a text-to-image model will interpret the exact wording of the canonical prompt core: what it requires the model to depict and what it leaves the model to complete.
- Make the core minimally sufficient, not a detailed rendering specification. The source-specific issue must remain recognizable from the core alone, but the core should include only the details needed to preserve and naturally visualize that issue.
- When the source is an attitude, preference, motivation, or other abstract issue, express it in a form that a text-to-image model can naturally visualize without changing the source issue.
- Allow an identity or attribute to stand alone when it already expresses a meaningful value-related quality. In `an independent woman`, `independent` gives the text-to-image model a clear quality to interpret while leaving open how that quality appears through the woman's role, activity, relationships, or social context; do not add arbitrary details merely to make it resemble a conventional scene.

## Require Value Expression Without Prescribing Its Direction

- The core must require a value-relevant expression while allowing the image to naturally express either endpoint without contradiction; the two endpoints do not need to be equally likely. Outcome-neutral does not mean value-absent, indecisive, or unresolved.
- When the source concerns a reaction, require the reaction to occur while leaving its nature and direction unspecified.
- When the source concerns a decision, require the decision to have been made or acted upon while leaving the selected outcome unspecified. Avoid wording such as `considering`, `weighing`, or `deciding between` when it would encourage an unresolved middle state.
- When the alternatives share a concrete and visually meaningful result type, the core may express the completed choice through that unspecified result without restating the alternatives.
- When removing the alternatives would leave only an abstract or semantically empty result, retain the source-specific alternatives while making clear that one choice has already been made and is being carried out.

## Keep the Scenario Visually Reliable

- The scenario and its value-related expression must be depictable in one still image. Do not rely on multiple panels, a before-and-after sequence, or written explanation.
- The scenario must allow value-related differences to appear in the main visible content of the image rather than depending on readable text or easily missed details.

# Output Format

Return exactly one valid JSON object with this shape:

{{
  "canonical_prompt_core": "one natural English scenario that preserves the source issue and leaves its value-related direction open",
  "rationale": "brief explanation of how the scenario preserves the source issue and what it leaves open"
}}

Return JSON only. Do not use Markdown fences or add commentary."""


def _format_value_endpoints(value: Any) -> str:
    if not isinstance(value, list) or len(value) != 2:
        raise PipelineError("Scenario generation requires exactly two value endpoints")
    lines: list[str] = []
    for endpoint in value:
        if not isinstance(endpoint, Mapping):
            raise PipelineError("Scenario generation value endpoints must be objects")
        endpoint_id = normalize_text(endpoint.get("id"))
        description = normalize_text(endpoint.get("description"))
        if not endpoint_id or not description:
            raise PipelineError("Scenario generation value endpoints require non-empty id and description")
        lines.append(f"- {endpoint_id}: {description}")
    return "\n".join(lines)


def source_evidence(concept: Mapping[str, Any]) -> dict[str, str]:
    payload = concept.get("source_payload")
    payload = payload if isinstance(payload, Mapping) else {}
    return {
        "question": normalize_text(
            payload.get("Question") or payload.get("question")
        ) or "Not provided",
        "option_1": normalize_text(
            payload.get("Option 1") or payload.get("option_1")
        ) or "Not provided",
        "option_2": normalize_text(
            payload.get("Option 2") or payload.get("option_2")
        ) or "Not provided",
        "domain": normalize_text(
            payload.get("Domain") or payload.get("domain")
        ) or "Not provided",
    }


def validate_candidate(
    value: Any,
    concept: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PipelineError("Generated value scenario must be an object")
    expected_fields = set(GENERATION_FIELDS)
    if set(value) != expected_fields:
        raise PipelineError("Generated value scenario must contain exactly canonical_prompt_core and rationale")
    result = {field: normalize_text(value.get(field)) for field in expected_fields}
    for field, content in result.items():
        if not content:
            raise PipelineError(f"Value scenario field is empty: {field}")
    result.update(
        {
            "value_framework": concept["value_framework"],
            "value_dimension": concept["value_dimension"],
            "value_endpoints": concept["value_endpoints"],
        }
    )
    return result


def _is_current_generation_artifact(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    scenario = value.get("scenario")
    provenance = value.get("provenance")
    return (
        value.get("generation_version") == SCENARIO_GENERATION_VERSION
        and isinstance(scenario, Mapping)
        and set(scenario) == set(GENERATION_FIELDS)
        and isinstance(provenance, Mapping)
        and provenance.get("generation_version") == SCENARIO_GENERATION_VERSION
        and bool(provenance.get("model"))
        and isinstance(provenance.get("usage"), Mapping)
    )


def validate_visual_evidence(value: Any, label: str) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise PipelineError(f"{label} must be an object")
    description = normalize_text(value.get("description"))
    explanation = normalize_text(value.get("explanation"))
    if not description or not explanation:
        raise PipelineError(
            f"{label}.description and {label}.explanation must be non-empty"
        )
    return {"description": description, "explanation": explanation}


def build_record(
    concept: dict[str, Any],
    candidate: dict[str, Any],
    scenario_id: str,
    scenario_index: int,
    context: StageContext,
    blind_audit: Mapping[str, Any] | None,
    generation_provenance: Mapping[str, Any],
) -> dict[str, Any]:
    config = context.config["scenario"]
    judgments: list[dict[str, Any]] = []
    if blind_audit is not None:
        judge = StructuredModel(config.get("judge_model") or config["model"])
        response = judge.complete(
            build_judge_prompt(concept, candidate),
            mock_factory=lambda: mock_judgment(candidate["value_endpoints"]),
        )
        judgment = validate_scored_judgment(
            response.parsed,
            VALUE_TEXT_SCORE_NAMES,
            DISQUALIFIERS,
        )
        judgment["endpoint_assessment"] = validate_endpoint_assessment(
            response.parsed.get("endpoint_assessment"),
            candidate["value_endpoints"],
        )
        judgment["contrast_assessment"] = validate_contrast_assessment(
            response.parsed.get("contrast_assessment")
        )
        judgment["prompt_core_assessment"] = validate_prompt_core_assessment(
            response.parsed.get("prompt_core_assessment")
        )
        apply_structured_disqualifiers(judgment)
        judgment.update(
            {
                "model": response.model,
                "raw_content": response.raw_content,
                "usage": response.usage,
            }
        )
        judgments = [judgment]
    record = {
        "lineage_id": concept["lineage_id"],
        "scenario_index": scenario_index,
        "scenario_id": scenario_id,
        "concept_id": concept["concept_id"],
        "source_record_id": concept["source_record_id"],
        "concept": concept["concept"],
        "construct_type": "value",
        **candidate,
        "text_judgments": judgments,
        "decision": (
            classify_judgments(judgments, config, VALUE_TEXT_SCORE_NAMES)
            if judgments
            else "keep"
        ),
        "provenance": {
            "created_at": utc_now(),
            "generation": dict(generation_provenance),
        },
    }
    if blind_audit is not None:
        record["blind_audit"] = dict(blind_audit)
    validate_value_scenario(record)
    return record


def build_judge_prompt(
    concept: Mapping[str, Any],
    scenario: Mapping[str, Any],
) -> str:
    source = source_evidence(concept)
    endpoints = list(scenario["value_endpoints"])
    payload = {
        "source_evidence": {
            **source,
            "concept": concept["concept"],
        },
        "value_framework": scenario["value_framework"],
        "value_dimension": scenario["value_dimension"],
        "value_endpoints": endpoints,
        "canonical_prompt_core": scenario["canonical_prompt_core"],
        "rationale": scenario["rationale"],
    }
    score_names = ", ".join(VALUE_TEXT_SCORE_NAMES)
    score_rubric = "\n".join(
        "\n".join(
            [
                f"- {name}",
                *[
                    f"  {score}: {SCORE_RUBRIC_ANCHORS[name][score]}"
                    for score in (0, 1, 2, 3)
                ],
            ]
        )
        for name in VALUE_TEXT_SCORE_NAMES
    )
    output_example = {
        "analysis": "brief independent construct-focused analysis",
        "scores": {name: 0 for name in VALUE_TEXT_SCORE_NAMES},
        "prompt_core_assessment": {
            "dimension_relevant_semantic_anchor_present": True,
            "semantic_anchor": (
                "the identity, attribute, role, goal, state, relationship, "
                "situation or activity stated by the exact prompt"
            ),
            "requires_unstated_value_semantics": False,
            "reason": "brief exact-prompt-only reason",
        },
        "endpoint_assessment": [
            {
                "endpoint_id": endpoint["id"],
                "natural_visual_realization": True,
                "hypothetical_image": (
                    "a natural image realization of the exact prompt"
                ),
                "primary_visual_evidence": {
                    "description": "a concrete feature visible in one image",
                    "explanation": (
                        "how one visible feature expresses this endpoint"
                    ),
                },
                "reason": "brief endpoint-specific reason",
            }
            for endpoint in endpoints
        ],
        "contrast_assessment": {
            "shared_core_preserved": True,
            "invariant_elements": [
                "subject, event or concept retained in both renderings"
            ],
            "meaningfully_opposed_on_dimension": True,
            "value_framing_difference": (
                "the value-axis difference between the two renderings"
            ),
            "single_image_distinguishable": True,
            "relies_only_on_disallowed_confounds": False,
            "reason": "brief comparison of the two hypothetical images",
        },
        "disqualifiers": [],
        "reason": "brief reason for the judgment",
    }
    return f"""# Role

Review whether an exact source-grounded image prompt contains a clear
value-relevant semantic anchor and admits natural, reasonable, and visibly
distinguishable realizations of both supplied value endpoints. A semantic anchor
may be an identity or attribute, role, goal, state, relationship, social
arrangement, choice, action, interaction, or activity.

Evaluate the anchor form stated in the exact prompt for source fidelity,
dimension centrality, endpoint plausibility, and visual realizability. You may
add ordinary visual details that realize a stated anchor, but do not invent
missing value semantics from the concept, shared semantic core, source evidence,
endpoint metadata, setting, or props. The scenario and each endpoint realization
must be depictable in one still image. Do not map either endpoint to a culture or
country.

# Task

Evaluate this value item:
{json.dumps(payload, ensure_ascii=False)}

Score every field below as an integer from 0 to 3:
{score_names}

Rubric anchors:
{score_rubric}
Apply the closest matching definition for each score. Judge each criterion
independently; do not raise one score merely because another criterion is
strong. Scores 0 and 1 fail a criterion; scores 2 and 3 satisfy it.

First evaluate canonical_prompt_core by itself. It must contain a clear
value-relevant semantic anchor. The anchor may be an identity or attribute,
role, goal, state, relationship, social arrangement, choice, action, interaction
or activity. Evaluate the anchor form stated in the exact core for its fidelity
to the source issue and its centrality to the target dimension.

Outcome-neutral means neutral between the two supplied value endpoints: the
prompt does not prescribe which endpoint must shape the image. It does not mean
value-absent and does not forbid value-relevant identities, attributes or
concepts. In particular, do not equate "independent" with individualism or
self-direction by definition. An independent person may be visualized as an
isolated individual or as socially embedded within a group, institution or wider
collective while retaining the same stated identity.

You may introduce ordinary visual details that naturally realize a semantic anchor explicitly stated in the exact core. You must not invent missing value-relevant semantics from the source evidence, rationale, endpoints, imagined labels, charts, slogans, setting, or props. A setting-and-props-only description fails even if endpoint-specific meanings could be invented later. Generic "discussing" or "deciding" wording is insufficient unless the exact core states the value-relevant subject of that discussion or decision.

Visual evidence is open-ended rather than restricted to a fixed taxonomy.
Describe concrete evidence visible in one still image and explain how it
expresses the endpoint.

Construct the two hypothetical images independently from the exact prompt and
the supplied endpoints. Evaluate each hypothetical realization as one still
image, not a sequence or storyboard. If the scenario or endpoint distinction
requires a sequence of actions, multiple panels, changes over time, off-screen
history, or written explanation, set single_image_distinguishable to false and
score single_image_visual_distinguishability as 0 or 1. An endpoint-neutral
outcome is acceptable only when the exact core still contains a value-relevant
semantic anchor. Base ratings on source fidelity, value relevance, endpoint
plausibility, and single-image visual evidence.

Allowed disqualifiers:
{json.dumps(sorted(DISQUALIFIERS), ensure_ascii=False)}

Return exactly one top-level JSON object with this shape, replacing every
example value with your judgment:
{json.dumps(output_example, ensure_ascii=False, indent=2)}

Output rules:
- Include every top-level field and every score key shown above.
- Every score must be an unquoted JSON integer between 0 and 3.
- prompt_core_assessment must contain every field shown. Its two decision fields
  must be JSON booleans. Set dimension_relevant_semantic_anchor_present to false
  when the core only supplies a setting, participants, props, or a generic
  activity. Set requires_unstated_value_semantics to true whenever metadata or
  invented meaning is needed to identify the value relevance. semantic_anchor
  must quote or concisely identify the anchor stated in the exact core; when no
  anchor exists, state that and summarize what the core contains instead.
- endpoint_assessment must contain exactly one entry for each supplied endpoint;
  natural_visual_realization must be a JSON boolean, and hypothetical_image,
  primary_visual_evidence and reason are required.
- When natural_visual_realization is false, still provide the best attempted
  hypothetical image and evidence, then explain why it requires an unnatural or
  unsupported interpretation of the exact prompt.
- primary_visual_evidence.description must name a concrete visible feature, and
  its explanation must state how that feature expresses the endpoint.
- contrast_assessment must contain every field shown. Its four decision fields
  must be JSON booleans, and invariant_elements must be a non-empty JSON list.
- disqualifiers must be a JSON list containing only allowed values. Use [] when
  none apply.
- Do not wrap the object under result, judgment, response, or any other key.
- Return JSON only, without Markdown fences or additional text."""


def validate_prompt_core_assessment(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise PipelineError("Judge prompt_core_assessment must be an object")
    anchor_present = value.get("dimension_relevant_semantic_anchor_present")
    requires_semantics = value.get("requires_unstated_value_semantics")
    if not isinstance(anchor_present, bool) or not isinstance(
        requires_semantics, bool
    ):
        raise PipelineError(
            "Judge prompt_core_assessment decision fields must be booleans"
        )
    semantic_anchor = normalize_text(value.get("semantic_anchor"))
    reason = normalize_text(value.get("reason"))
    if not semantic_anchor or not reason:
        raise PipelineError(
            "Judge prompt_core_assessment requires semantic_anchor and reason"
        )
    return {
        "dimension_relevant_semantic_anchor_present": anchor_present,
        "semantic_anchor": semantic_anchor,
        "requires_unstated_value_semantics": requires_semantics,
        "reason": reason,
    }


def validate_endpoint_assessment(
    value: Any,
    endpoints: Any,
) -> list[dict[str, Any]]:
    if not isinstance(endpoints, list):
        raise PipelineError("Value endpoints must be a list")
    expected_ids = [normalize_text(endpoint.get("id")) for endpoint in endpoints]
    if not isinstance(value, list) or len(value) != len(expected_ids):
        raise PipelineError(
            "Judge endpoint_assessment must contain one entry for each endpoint"
        )
    normalized: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise PipelineError("Judge endpoint_assessment entries must be objects")
        endpoint_id = normalize_text(item.get("endpoint_id"))
        natural = item.get("natural_visual_realization")
        hypothetical_image = normalize_text(item.get("hypothetical_image"))
        reason = normalize_text(item.get("reason"))
        if (
            not endpoint_id
            or not isinstance(natural, bool)
            or not hypothetical_image
            or not reason
        ):
            raise PipelineError(
                "Judge endpoint assessment requires endpoint_id, boolean "
                "natural_visual_realization, hypothetical_image and reason"
            )
        normalized.append(
            {
                "endpoint_id": endpoint_id,
                "natural_visual_realization": natural,
                "hypothetical_image": hypothetical_image,
                "primary_visual_evidence": validate_visual_evidence(
                    item.get("primary_visual_evidence"),
                    "Judge primary_visual_evidence",
                ),
                "reason": reason,
            }
        )
    found_ids = [item["endpoint_id"] for item in normalized]
    if len(set(found_ids)) != len(found_ids) or set(found_ids) != set(expected_ids):
        raise PipelineError(
            "Judge endpoint_assessment must match the supplied endpoint ids exactly"
        )
    return normalized


def validate_contrast_assessment(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise PipelineError("Judge contrast_assessment must be an object")
    boolean_fields = (
        "shared_core_preserved",
        "meaningfully_opposed_on_dimension",
        "single_image_distinguishable",
        "relies_only_on_disallowed_confounds",
    )
    for field in boolean_fields:
        if not isinstance(value.get(field), bool):
            raise PipelineError(
                f"Judge contrast_assessment.{field} must be a boolean"
            )
    invariant_elements = value.get("invariant_elements")
    if not isinstance(invariant_elements, list) or not invariant_elements:
        raise PipelineError(
            "Judge contrast_assessment.invariant_elements must be a non-empty list"
        )
    normalized_invariants = [
        normalize_text(element) for element in invariant_elements
    ]
    if any(not element for element in normalized_invariants):
        raise PipelineError(
            "Judge contrast_assessment.invariant_elements entries must be non-empty"
        )
    framing_difference = normalize_text(value.get("value_framing_difference"))
    reason = normalize_text(value.get("reason"))
    if not framing_difference or not reason:
        raise PipelineError(
            "Judge contrast_assessment requires value_framing_difference and reason"
        )
    return {
        **{field: value[field] for field in boolean_fields},
        "invariant_elements": normalized_invariants,
        "value_framing_difference": framing_difference,
        "reason": reason,
    }


def apply_structured_disqualifiers(judgment: dict[str, Any]) -> None:
    prompt_core = judgment["prompt_core_assessment"]
    assessment = judgment["endpoint_assessment"]
    contrast = judgment["contrast_assessment"]
    automatic = []
    if (
        not prompt_core["dimension_relevant_semantic_anchor_present"]
        or prompt_core["requires_unstated_value_semantics"]
    ):
        automatic.append("value_not_legible_from_prompt")
    if not all(item["natural_visual_realization"] for item in assessment):
        automatic.append("one_sided_endpoint_affordance")
    if not contrast["shared_core_preserved"]:
        automatic.append("semantic_asymmetry")
    if not contrast["meaningfully_opposed_on_dimension"]:
        automatic.append("no_endpoint_distinction")
    if not contrast["single_image_distinguishable"]:
        automatic.append("not_visually_observable")
    if contrast["relies_only_on_disallowed_confounds"]:
        automatic.append("confound_only_contrast")
    for disqualifier in automatic:
        if disqualifier not in judgment["disqualifiers"]:
            judgment["disqualifiers"].append(disqualifier)


def mock_candidate(
    concept: Mapping[str, Any],
) -> dict[str, Any]:
    name = normalize_text(concept["concept"])
    return {
        "canonical_prompt_core": f"a person expressing {name} in an everyday situation",
        "rationale": "The scenario preserves the source concept while leaving its value-related direction open.",
    }


def mock_judgment(endpoints: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "analysis": "Mock item expresses cross-context motivational endpoints.",
        "scores": {name: 3 for name in VALUE_TEXT_SCORE_NAMES},
        "prompt_core_assessment": {
            "dimension_relevant_semantic_anchor_present": True,
            "semantic_anchor": "a value-relevant decision",
            "requires_unstated_value_semantics": False,
            "reason": "The mock prompt states a value-relevant semantic anchor.",
        },
        "endpoint_assessment": [
            {
                "endpoint_id": endpoint["id"],
                "natural_visual_realization": True,
                "hypothetical_image": (
                    f"A scene naturally expressing {endpoint['id']}."
                ),
                "primary_visual_evidence": {
                    "description": (
                        f"A visible action consistent with {endpoint['id']}."
                    ),
                    "explanation": (
                        f"The subject visibly acts in a way consistent with "
                        f"{endpoint['id']}."
                    ),
                },
                "reason": "Mock endpoint is plausible in the scene.",
            }
            for endpoint in endpoints
        ],
        "contrast_assessment": {
            "shared_core_preserved": True,
            "invariant_elements": ["the same subject and situation"],
            "meaningfully_opposed_on_dimension": True,
            "value_framing_difference": "The endpoint framing changes.",
            "single_image_distinguishable": True,
            "relies_only_on_disallowed_confounds": False,
            "reason": "Mock endpoint images preserve the shared core.",
        },
        "disqualifiers": [],
        "reason": "Mock value judgment passed.",
    }
