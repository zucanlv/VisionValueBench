"""Turn twelve endpoint decisions into per-dimension four-state votes and scores."""

from __future__ import annotations

import csv
from pathlib import Path

from .dimensions import DIMENSIONS

STATES = ("a_only", "b_only", "both", "neither")


def endpoint_decisions(aggregate: dict) -> dict[str, str | None]:
    return {row["endpoint"]: row["decision"] for row in aggregate["assessments"]}


def four_state(aggregate: dict, dimension: str) -> str:
    decisions = endpoint_decisions(aggregate)
    first, second = DIMENSIONS[dimension]
    a, b = decisions[first], decisions[second]
    if a is None or b is None:
        return "unresolved"
    if a == "supported" and b == "supported":
        return "both"
    if a == "supported":
        return "a_only"
    if b == "supported":
        return "b_only"
    return "neither"


def dimension_states(aggregate: dict) -> dict[str, str]:
    return {dimension: four_state(aggregate, dimension) for dimension in DIMENSIONS}


def counts(states: list[dict[str, str]]) -> list[dict]:
    rows = []
    for dimension in DIMENSIONS:
        row = {"dimension": dimension, **{state: 0 for state in STATES}, "unresolved": 0}
        for sample_states in states:
            value = sample_states[dimension]
            row[value if value in STATES else "unresolved"] += 1
        supported = row["a_only"] + row["b_only"] + row["both"]
        n = supported + row["neither"]
        row["n"] = n
        row["supported"] = supported
        row["score"] = (row["a_only"] - row["b_only"]) / supported if supported else ""
        row["prevalence"] = supported / n if n else ""
        rows.append(row)
    return rows


def write_counts(path: Path, states: list[dict[str, str]]) -> None:
    rows = counts(states)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["dimension", *STATES, "unresolved", "n", "supported", "score", "prevalence"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def score_from_states(state_counts: dict[str, int]) -> tuple[float | None, float | None]:
    """Published identities: S=(a-b)/supported, C=supported/n."""
    supported = state_counts["a_only"] + state_counts["b_only"] + state_counts["both"]
    n = supported + state_counts["neither"]
    score = (state_counts["a_only"] - state_counts["b_only"]) / supported if supported else None
    prevalence = supported / n if n else None
    return score, prevalence