from __future__ import annotations

import json
from typing import Any, Mapping

from .adapters import StructuredModel
from .base_contracts import StageContext
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


TRANSLATION_PROMPT_VERSION = "joint-v3"
TARGET_LOCALES = ("zh-CN", "th-TH", "hi-IN")
TRANSLATION_PROMPT_TEMPLATE = """# Role

You translate one finalized English scenario prompt into three natural-language prompts for a controlled multilingual text-to-image research dataset.

# Input

You will receive one finalized English scenario prompt. The English prompt will be used directly by an image-generation model and is the source of truth. Translate it without revising or redesigning the scenario.

# Output

Return one natural translation of the input prompt in each of the following languages:

- `zh-CN`: Simplified Chinese as used in mainland China;
- `th-TH`: Thai as used in Thailand; and
- `hi-IN`: Hindi in Devanagari as used in India.

All four prompts must describe exactly the same scenario. Use natural wording and syntax in each language.

# Translation Requirements

- Translate the meaning of the prompt as a whole rather than mapping English phrases one by one. Reorganize the sentence as needed so that each translation reads as if it were originally written in that language.
- Preserve the same scenario information, including its level of detail, event status, explicit alternatives, and anything intentionally left unspecified.
- Do not culturally adapt the scenario or introduce details that are absent from the English prompt.

# Few-Shot Examples

The examples demonstrate semantic equivalence with natural language-specific wording. They are not sentence templates to copy mechanically.

## Example 1: A reaction occurs, but its direction remains open

English prompt:

`a visitor reacting to a provocative artwork that challenges traditional views`

Translations:

{
  "zh-CN": "一名参观者面对一件挑战传统观念、引发争议的艺术作品时的反应",
  "th-TH": "ผู้เข้าชมกำลังแสดงปฏิกิริยาต่อผลงานศิลปะที่ชวนให้ถกเถียงและท้าทายมุมมองแบบดั้งเดิม",
  "hi-IN": "एक दर्शक ऐसी विवादास्पद कलाकृति पर प्रतिक्रिया दे रहा है जो पारंपरिक सोच को चुनौती देती है"
}

## Example 2: A completed choice retains alternatives that cannot be safely omitted

English prompt:

`a person following through on the choice they made between attending a family gathering and taking a long-awaited personal vacation`

Translations:

{
  "zh-CN": "一个人正按照自己已经作出的选择行动：参加家庭聚会，或开始期待已久的个人假期",
  "th-TH": "บุคคลหนึ่งกำลังลงมือทำตามการตัดสินใจของตน หลังจากเลือกระหว่างการไปร่วมงานรวมญาติกับการไปเที่ยวพักผ่อนส่วนตัวที่รอคอยมานาน",
  "hi-IN": "एक व्यक्ति अपने फैसले के मुताबिक आगे बढ़ रहा है: परिवार के कार्यक्रम में शामिल होना या उस निजी छुट्टी पर जाना जिसका उसे लंबे समय से इंतज़ार था"
}

## Example 3: A completed choice is represented by its unspecified result

English prompt:

`a person with the car they chose to buy`

Translations:

{
  "zh-CN": "一个人和自己选购的汽车",
  "th-TH": "บุคคลหนึ่งอยู่กับรถยนต์ที่ตนเลือกซื้อ",
  "hi-IN": "एक व्यक्ति अपनी खरीदी हुई कार के साथ"
}

## Example 4: A relevant relationship is available without prescribing the interaction

English prompt:

`a child working on a school assignment while a parent is nearby`

Translations:

{
  "zh-CN": "一个孩子正在做作业，一位家长就在旁边",
  "th-TH": "เด็กคนหนึ่งกำลังทำการบ้าน โดยมีพ่อหรือแม่อยู่ใกล้ ๆ",
  "hi-IN": "एक बच्चा स्कूल का काम कर रहा है और उसकी माँ या उसके पिता पास में हैं"
}

# Your Task

Translate the following finalized English scenario prompt into all three target languages.

# English Scenario Prompt

<ENGLISH_SCENARIO_PROMPT>

# Final Check

Before answering, silently verify that the English prompt and all three translations describe exactly the same scenario and leave the same information unspecified. Then read each translation on its own and revise any wording that sounds translated or grammatically unnatural, without changing the scenario.

# Output Format

Return exactly one valid JSON object with this shape:

{
  "translations": {
    "zh-CN": "one natural Simplified Chinese translation",
    "th-TH": "one natural Thai translation",
    "hi-IN": "one natural Hindi translation"
  }
}

Return JSON only. Do not use Markdown fences or add commentary.
"""


def run_translations(
    context: StageContext,
    scenarios: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    config = context.config["translation"]
    languages = context.config["languages"]
    source_language = config["source_language"]
    model = StructuredModel(
        config["model"],
        usage_context={
            "run_id": context.run_dir.name,
            "purpose": "translations",
        },
    )
    stage_dir = context.stage_dir("translations")
    stage_dir.mkdir(parents=True, exist_ok=True)
    target_locales = set(languages) - {source_language}
    unsupported_locales = target_locales - set(TARGET_LOCALES)
    if unsupported_locales:
        raise PipelineError(
            "Joint translation supports only zh-CN, th-TH, and hi-IN; "
            f"unsupported locales: {sorted(unsupported_locales)}"
        )

    def worker(scenario: dict[str, Any]) -> list[dict[str, Any]]:
        source_prompt = normalize_text(scenario["canonical_prompt_core"])
        completed: dict[str, dict[str, Any]] = {}
        pending_locales: list[str] = []
        for locale in languages:
            artifact_path = stage_dir / artifact_filename(
                scenario["lineage_id"],
                f"scenario_{scenario['scenario_index']:02d}",
                locale,
                "translation",
            )
            if context.resume and artifact_path.exists():
                cached = json.loads(artifact_path.read_text(encoding="utf-8"))
                if _uses_current_translation(
                    cached,
                    locale,
                    model.model,
                    source_prompt,
                ):
                    completed[locale] = cached
                    continue
            if locale != source_language:
                pending_locales.append(locale)

        joint_translations: dict[str, str] = {}
        joint_provenance: dict[str, Any] = {}
        if pending_locales:
            joint_translations, joint_provenance = translate_prompt_cores(
                source_prompt,
                model,
            )

        for locale, language in languages.items():
            if locale in completed:
                continue
            if locale == source_language:
                translated = source_prompt
                provenance = {
                    "model": "identity",
                    "raw_content": source_prompt,
                    "usage": {},
                }
            else:
                translated = joint_translations[locale]
                provenance = dict(joint_provenance)
            translation_id = stable_id(
                "translation",
                scenario["scenario_id"],
                locale,
                source_prompt,
                (
                    f"{model.model}:{TRANSLATION_PROMPT_VERSION}"
                    if locale != source_language
                    else "identity"
                ),
            )
            record = {
                "lineage_id": scenario["lineage_id"],
                "scenario_index": scenario["scenario_index"],
                "translation_id": translation_id,
                "scenario_id": scenario["scenario_id"],
                "source_language": source_language,
                "language": locale,
                "language_name": language["name"],
                "source_prompt_core": source_prompt,
                "prompt_core": translated,
                "provenance": {**provenance, "created_at": utc_now()},
            }
            validate_translation_record(record)
            if not context.dry_run:
                artifact_path = stage_dir / artifact_filename(
                    scenario["lineage_id"],
                    f"scenario_{scenario['scenario_index']:02d}",
                    locale,
                    "translation",
                )
                atomic_write_json(artifact_path, record)
            completed[locale] = record
        return [completed[locale] for locale in languages]

    kept = [scenario for scenario in scenarios if scenario["decision"] == "keep"]
    nested = parallel_map(
        kept,
        worker,
        int(
            config.get(
                "concurrency",
                context.config["experiment"]["max_workers"],
            )
        ),
        "prompt translation",
        None
        if context.dry_run
        else context.manifest_path("translation_failures"),
    )
    records = [record for group in nested for record in group]
    if not context.dry_run:
        atomic_write_jsonl(context.manifest_path("translations"), records)
    require_complete_records(
        "prompt translation",
        len(records),
        len(kept) * len(languages),
    )
    return records


def validate_translation_record(record: Mapping[str, Any]) -> None:
    for field in (
        "translation_id",
        "scenario_id",
        "source_language",
        "language",
        "language_name",
        "source_prompt_core",
        "prompt_core",
        "provenance",
    ):
        if field not in record:
            raise PipelineError(
                f"TranslationRecord is missing required field {field}"
            )
    if not normalize_text(record["prompt_core"]):
        raise PipelineError("TranslationRecord.prompt_core must be non-empty")


def _uses_current_translation(
    record: Any,
    locale: str,
    model: str,
    source_prompt: str,
) -> bool:
    if not isinstance(record, Mapping):
        return False
    provenance = record.get("provenance")
    if not isinstance(provenance, Mapping):
        return False
    expected_model = (
        "identity" if locale == record.get("source_language") else model
    )
    current_prompt = (
        locale == record.get("source_language")
        or provenance.get("prompt_version") == TRANSLATION_PROMPT_VERSION
    )
    return (
        record.get("language") == locale
        and provenance.get("model") == expected_model
        and current_prompt
        and normalize_text(record.get("source_prompt_core")) == source_prompt
        and bool(normalize_text(record.get("prompt_core")))
    )


def translate_prompt_cores(
    prompt_core: str,
    model: StructuredModel,
) -> tuple[dict[str, str], dict[str, Any]]:
    source_prompt = normalize_text(prompt_core)
    if not source_prompt:
        raise PipelineError("English scenario prompt must be non-empty")
    complete_prompt = TRANSLATION_PROMPT_TEMPLATE.replace(
        "<ENGLISH_SCENARIO_PROMPT>",
        source_prompt,
    )
    response = model.complete(
        complete_prompt,
        mock_factory=lambda: {
            "translations": {
                locale: f"{source_prompt} ({locale})"
                for locale in TARGET_LOCALES
            }
        },
    )
    raw_translations = response.parsed.get("translations")
    if (
        not isinstance(raw_translations, Mapping)
        or set(raw_translations) != set(TARGET_LOCALES)
    ):
        raise PipelineError(
            "Translator must return exactly zh-CN, th-TH, and hi-IN"
        )
    translations = {
        locale: normalize_text(raw_translations.get(locale))
        for locale in TARGET_LOCALES
    }
    if not all(translations.values()):
        raise PipelineError("Translator returned an empty translation")
    return translations, {
        "model": response.model,
        "raw_content": response.raw_content,
        "usage": response.usage,
        "prompt_version": TRANSLATION_PROMPT_VERSION,
    }
