"""Frozen six-dimension / twelve-endpoint order for the v2.1 annotation protocol.

The order is the one used by the released automatic votes
(``analysis/votes.json.gz`` -> ``endpoint_order``) and by the decision cards in
``materials/annotation/cards``.  Internal keys follow the manuscript; model-facing
keys are the two names that were changed to avoid priming the judge models.
"""

from __future__ import annotations

DIMENSIONS: dict[str, tuple[str, str]] = {
    "power_distance": ("high_power_distance", "low_power_distance"),
    "individualism_collectivism": ("individualism", "collectivism"),
    "masculinity_femininity": (
        "achievement_and_competition_orientation",
        "care_and_quality_of_life_orientation",
    ),
    "uncertainty_avoidance": ("high_uncertainty_avoidance", "low_uncertainty_avoidance"),
    "long_term_orientation": ("long_term_orientation", "short_term_orientation"),
    "indulgence_restraint": ("indulgence", "restraint"),
}

# The two internal keys that are not shown to a judge model verbatim.
MODEL_KEYS = {
    "masculinity_femininity": "motivation_achievement_success",
    "long_term_orientation": "long_short_term_orientation",
}
INTERNAL_KEYS = {model: internal for internal, model in MODEL_KEYS.items()}

DIMENSION_CODES = {
    "PDI": "power_distance",
    "IDV": "individualism_collectivism",
    "MAS": "masculinity_femininity",
    "UAI": "uncertainty_avoidance",
    "LTO": "long_term_orientation",
    "IVR": "indulgence_restraint",
}


def model_key(dimension: str) -> str:
    return MODEL_KEYS.get(dimension, dimension)


def internal_key(dimension: str) -> str:
    if dimension not in {model_key(d) for d in DIMENSIONS}:
        raise ValueError(f"Unknown model-facing dimension: {dimension}")
    return INTERNAL_KEYS.get(dimension, dimension)