from __future__ import annotations

import glob
import json
import random
from pathlib import Path
from typing import Any

from .errors import PipelineError
from .io import normalize_text, stable_id


CDEVAL_DIMENSIONS = {
    "PDI": (
        "power_distance",
        "high_power_distance",
        "low_power_distance",
    ),
    "IDV": (
        "individualism_collectivism",
        "individualism",
        "collectivism",
    ),
    "MAS": (
        "masculinity_femininity",
        "achievement_and_competition_orientation",
        "care_and_quality_of_life_orientation",
    ),
    "UAI": (
        "uncertainty_avoidance",
        "high_uncertainty_avoidance",
        "low_uncertainty_avoidance",
    ),
    "LTO": (
        "long_term_orientation",
        "long_term_orientation",
        "short_term_orientation",
    ),
    "IVR": (
        "indulgence_restraint",
        "indulgence",
        "restraint",
    ),
}

CDEVAL_ENDPOINT_DESCRIPTIONS = {
    "high_power_distance": (
        "Accepts hierarchical order, unequal authority, centralized decisions, "
        "and deference to people in higher-status roles as legitimate or expected."
    ),
    "low_power_distance": (
        "Prefers more equal power relations, consultative or participatory "
        "decisions, and greater freedom to question people in authority."
    ),
    "individualism": (
        "Prioritizes personal autonomy, individual goals, self-reliance, and "
        "personal responsibility when making choices or taking action."
    ),
    "collectivism": (
        "Prioritizes group belonging, shared goals, mutual obligations, harmony, "
        "and the needs of close relationships when making choices or taking action."
    ),
    "achievement_and_competition_orientation": (
        "Prioritizes achievement, competition, recognition, assertiveness, and "
        "demonstrable performance as important signs of success."
    ),
    "care_and_quality_of_life_orientation": (
        "Prioritizes cooperation, care for others, work-life balance, well-being, "
        "and the quality of relationships over competitive success."
    ),
    "high_uncertainty_avoidance": (
        "Prefers clear rules, planning, predictability, and safeguards that reduce "
        "ambiguity, unfamiliarity, and perceived risk."
    ),
    "low_uncertainty_avoidance": (
        "Accepts ambiguity and unfamiliar situations more readily, favoring "
        "flexibility, experimentation, and adaptation over extensive safeguards."
    ),
    "long_term_orientation": (
        "Prioritizes future rewards, perseverance, adaptation, sustained effort, "
        "and investments whose benefits may emerge over a long period."
    ),
    "short_term_orientation": (
        "Prioritizes nearer-term results, present obligations, established norms, "
        "and outcomes whose benefits are visible relatively soon."
    ),
    "indulgence": (
        "Allows relatively free gratification of desires related to enjoyment, "
        "leisure, pleasure, and personal expression."
    ),
    "restraint": (
        "Regulates gratification through self-discipline, duty, social norms, and "
        "limits on leisure, pleasure, or personal desires."
    ),
}

CDEVAL_FIELDS = ("Question", "Option 1", "Option 2", "Domain")
CDEVAL_SELECTION_MODES = frozenset({"all", "random", "range"})


def resolve_cdeval_selection(source: dict[str, Any]) -> dict[str, Any]:
    """Normalize the new selection block and the legacy random fields."""
    selection = source.get("selection")
    if selection is None:
        count = source.get("samples_per_dimension")
        if count is None:
            return {"mode": "all"}
        return {
            "mode": "random",
            "count": _require_integer(
                count,
                "source.samples_per_dimension",
                minimum=1,
            ),
            "seed": _require_integer(
                source.get("sample_seed", 0),
                "source.sample_seed",
            ),
        }

    if not isinstance(selection, dict):
        raise PipelineError("source.selection must be a YAML object")
    if "samples_per_dimension" in source or "sample_seed" in source:
        raise PipelineError(
            "Do not mix source.selection with legacy "
            "source.samples_per_dimension/source.sample_seed fields"
        )
    unknown_fields = set(selection) - {"mode", "count", "seed", "start", "end"}
    if unknown_fields:
        raise PipelineError(
            f"Unknown source.selection fields: {sorted(unknown_fields)}"
        )

    mode = selection.get("mode")
    if mode not in CDEVAL_SELECTION_MODES:
        raise PipelineError(
            "source.selection.mode must be all, random, or range"
        )
    if mode == "all":
        _reject_selection_fields(
            selection,
            mode,
            {"count", "seed", "start", "end"},
        )
        return {"mode": mode}
    if mode == "random":
        _reject_selection_fields(selection, mode, {"start", "end"})
        if "count" not in selection:
            raise PipelineError(
                "source.selection.count is required for random mode"
            )
        return {
            "mode": mode,
            "count": _require_integer(
                selection["count"],
                "source.selection.count",
                minimum=1,
            ),
            "seed": _require_integer(
                selection.get("seed", 0),
                "source.selection.seed",
            ),
        }

    _reject_selection_fields(selection, mode, {"count", "seed"})
    for field in ("start", "end"):
        if field not in selection:
            raise PipelineError(
                f"source.selection.{field} is required for range mode"
            )
    start = _require_integer(
        selection["start"],
        "source.selection.start",
        minimum=0,
    )
    end = _require_integer(
        selection["end"],
        "source.selection.end",
        minimum=1,
    )
    if start >= end:
        raise PipelineError(
            "source.selection range must satisfy start < end"
        )
    return {"mode": mode, "start": start, "end": end}


def _reject_selection_fields(
    selection: dict[str, Any],
    mode: str,
    forbidden: set[str],
) -> None:
    present = sorted(forbidden.intersection(selection))
    if present:
        raise PipelineError(
            f"source.selection fields {present} do not apply to {mode} mode"
        )


def _require_integer(value: Any, label: str, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PipelineError(f"{label} must be an integer")
    if minimum is not None and value < minimum:
        raise PipelineError(f"{label} must be at least {minimum}")
    return value


def load_cdeval_items(source: dict[str, Any]) -> list[dict[str, Any]]:
    pattern = source.get("questions_glob")
    if not pattern:
        raise PipelineError("source.questions_glob is required for cdeval")
    paths = [Path(path) for path in sorted(glob.glob(str(pattern)))]
    if not paths:
        raise PipelineError(f"No CDEval question files matched: {pattern}")

    selected = {
        str(code).upper()
        for code in source.get("dimensions", CDEVAL_DIMENSIONS)
    }
    unknown = selected - CDEVAL_DIMENSIONS.keys()
    if unknown:
        raise PipelineError(f"Unknown CDEval dimensions: {sorted(unknown)}")

    dataset_name = str(source.get("dataset_name", "CDEval"))
    selection = resolve_cdeval_selection(source)

    items: list[dict[str, Any]] = []
    for path in paths:
        dimension_code = path.stem.upper()
        if dimension_code not in selected:
            continue
        indexed_rows = list(enumerate(_load_rows(path), start=1))
        if selection["mode"] == "random":
            count = selection["count"]
            if len(indexed_rows) < count:
                raise PipelineError(
                    f"CDEval dimension {dimension_code} contains "
                    f"{len(indexed_rows)} rows; cannot sample "
                    f"{count}"
                )
            rng = random.Random(f"{selection['seed']}:{dimension_code}")
            indexed_rows = sorted(rng.sample(indexed_rows, count))
        elif selection["mode"] == "range":
            start = selection["start"]
            end = selection["end"]
            if end > len(indexed_rows):
                raise PipelineError(
                    f"CDEval dimension {dimension_code} contains "
                    f"{len(indexed_rows)} rows; range end {end} is out of bounds"
                )
            indexed_rows = indexed_rows[start:end]
        items.extend(
            _build_item(
                row,
                path=path,
                index=index,
                dataset_name=dataset_name,
                dimension_code=dimension_code,
            )
            for index, row in indexed_rows
        )
    return items


def _load_rows(path: Path) -> list[dict[str, Any]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PipelineError(
            f"Could not load CDEval file {path}: {error}"
        ) from error
    if not isinstance(value, list):
        raise PipelineError(f"Expected a JSON list in {path}")
    return value


def _build_item(
    row: dict[str, Any],
    *,
    path: Path,
    index: int,
    dataset_name: str,
    dimension_code: str,
) -> dict[str, Any]:
    if not isinstance(row, dict):
        raise PipelineError(f"Expected an object at {path}:{index}")

    fields = {field: normalize_text(row.get(field)) for field in CDEVAL_FIELDS}
    missing = [field for field, value in fields.items() if not value]
    if missing:
        raise PipelineError(
            f"Missing CDEval fields {missing} at {path}:{index}"
        )

    question = fields["Question"]
    option_1 = fields["Option 1"]
    option_2 = fields["Option 2"]
    domain = fields["Domain"]
    dimension, endpoint_1, endpoint_2 = (
        CDEVAL_DIMENSIONS[dimension_code]
    )

    return {
        "lineage_id": f"cdeval_{dimension_code.casefold()}_{index:04d}",
        "source_record_id": stable_id(
            "source",
            dataset_name,
            dimension_code,
            index,
            question,
        ),
        "source_dataset": dataset_name,
        "source_text": (
            f"Domain: {domain}\n"
            f"Question: {question}\n"
            f"Option 1: {option_1}\n"
            f"Option 2: {option_2}"
        ),
        "source_payload": {
            **row,
            "source_item_index": index,
            "value_framework": "Hofstede",
            "value_dimension": dimension,
            # These are the dimension's two unassigned poles. CDEval's answer
            # options remain source evidence above; this does not assert that
            # Option 1/2 is an authoritative mapping to pole 1/2.
            "value_endpoints": [
                _build_endpoint(endpoint_1),
                _build_endpoint(endpoint_2),
            ],
        },
    }


def _build_endpoint(endpoint_id: str) -> dict[str, str]:
    return {
        "id": endpoint_id,
        "description": CDEVAL_ENDPOINT_DESCRIPTIONS[endpoint_id],
    }
