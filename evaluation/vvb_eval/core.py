"""Deterministic validation, candidate banking and vote aggregation for the v2.1 protocol.

This module is adapted from the frozen ``pooled-two-layer-v2.1`` production
implementation.  The contracts, content-hash bank IDs, short model-facing
candidate IDs, majority rule and endpoint OR are preserved.  The production
transport, budget ledger, batch submission and human-bundle exporter are not
part of this reference release.

Stored records, banks and annotations use internal dimension keys and bank
candidate IDs.  Prompts and schemas show model-facing dimension keys and short
per-call candidate IDs (``C1``, ``C2``, ...); the contracts translate both ways.
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
from pathlib import Path

from .dimensions import DIMENSIONS, model_key, internal_key

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parent.parent
MATERIALS_DIR = Path(os.environ.get("VVB_MATERIALS", REPO_ROOT / "materials")).resolve()

PROTOCOL = "pooled-two-layer-v2.1"
STAGES = (
    "scenario_proposal",
    "image_proposal",
    "scenario_verification",
    "image_verification",
)
EVIDENCE_FIELD = {"scenario": "potential_evidence", "image": "visual_basis"}
REVIEW_FIELDS = (
    "candidate_id",
    "core",
    "in_image",
    "observation_assessment",
    "interpretation_check",
    "interpretation_assessment",
    "decision",
)


def digest(value) -> str:
    raw = (
        value
        if isinstance(value, bytes)
        else json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    )
    return hashlib.sha256(raw).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def fields(value, names) -> None:
    require(isinstance(value, dict) and set(value) == set(names), f"Expected fields: {list(names)}")


def validate_proposal(value: dict, layer: str) -> dict:
    """Check one proposer output and return it with internal dimension keys."""
    require(layer in EVIDENCE_FIELD, "Unknown layer")
    fields(
        value,
        ("focal_situation", "ranking", "dimensions") if layer == "scenario" else ("ranking", "dimensions"),
    )
    if layer == "scenario":
        require(text(value["focal_situation"]), "Empty focal situation")

    ranks = value["ranking"]
    require(isinstance(ranks, list) and len(ranks) == 6, "Ranking coverage")
    relevance = {}
    for row in ranks:
        fields(row, ("dimension", "rank", "relevance", "reason"))
        require(
            type(row["rank"]) is int
            and row["relevance"] in ("related", "unrelated")
            and text(row["reason"]),
            "Invalid ranking fields",
        )
        dimension = internal_key(row["dimension"])
        require(dimension not in relevance, "Repeated ranking dimension")
        relevance[dimension] = row["relevance"]
    require(set(relevance) == set(DIMENSIONS), "Ranking coverage")
    order = [row["rank"] for row in ranks]
    require(
        order == sorted(order) and order[0] == 1 and all(1 <= x <= 6 for x in order),
        "Ranks must be sorted, start at 1 and stay within 1..6; ties are allowed",
    )

    fields(value["dimensions"], [model_key(d) for d in DIMENSIONS])
    dimensions, ids = {}, []
    for dimension, endpoints in DIMENSIONS.items():
        block = value["dimensions"][model_key(dimension)]
        fields(block, endpoints)
        dimensions[dimension] = {}
        for endpoint in endpoints:
            require(isinstance(block[endpoint], list), "Expected proposal array")
            require(
                relevance[dimension] == "related" or not block[endpoint],
                "An unrelated dimension must have empty endpoint lists",
            )
            for candidate in block[endpoint]:
                fields(candidate, ("id", EVIDENCE_FIELD[layer], "interpretation"))
                require(all(text(v) for v in candidate.values()), "Empty proposal field")
                ids.append(candidate["id"])
            dimensions[dimension][endpoint] = [dict(c) for c in block[endpoint]]
    require(len(ids) == len(set(ids)), "Duplicate proposal ID")

    out = {
        "ranking": [{**row, "dimension": internal_key(row["dimension"])} for row in ranks],
        "dimensions": dimensions,
    }
    if layer == "scenario":
        out["focal_situation"] = value["focal_situation"]
    return out


def bank(proposals: dict, layer: str, members) -> dict:
    """Pool internal-key proposals; only byte-identical candidate content merges."""
    members = tuple(members)
    require(
        bool(members) and set(proposals) == set(members) and len(set(members)) == len(members),
        "Bank requires every selected proposer",
    )
    dimensions = {d: {ep: [] for ep in eps} for d, eps in DIMENSIONS.items()}
    origins = {}
    for dimension, endpoints in DIMENSIONS.items():
        for endpoint in endpoints:
            unique = {}
            for model in sorted(members):
                for candidate in proposals[model]["dimensions"][dimension][endpoint]:
                    content = {k: v for k, v in candidate.items() if k != "id"}
                    cid = ("S-" if layer == "scenario" else "E-") + digest(
                        [layer, dimension, endpoint, content]
                    )[:24]
                    unique[cid] = {"id": cid, **content}
                    origins.setdefault(cid, []).append(
                        {"model": model, "source_id": candidate["id"]}
                    )
            dimensions[dimension][endpoint] = [unique[cid] for cid in sorted(unique)]
    return {
        "layer": layer,
        "dimensions": dimensions,
        "origins": origins,
        "members": list(members),
    }


def model_candidates(dimensions: dict, layer: str):
    """Bank candidates as a model sees them: model-facing keys and C1, C2, ... in bank order."""
    field = EVIDENCE_FIELD[layer]
    shown, mapping, n = {}, {}, 0
    for dimension, endpoints in DIMENSIONS.items():
        shown[model_key(dimension)] = {}
        for endpoint in endpoints:
            items = []
            for candidate in dimensions[dimension][endpoint]:
                n += 1
                mapping[f"C{n}"] = candidate["id"]
                items.append(
                    {
                        "id": f"C{n}",
                        field: candidate[field],
                        "interpretation": candidate["interpretation"],
                    }
                )
            shown[model_key(dimension)][endpoint] = items
    return shown, mapping


def validate_verification(value: dict, dimensions: dict, layer: str) -> dict:
    """Check one verifier output and return it with internal keys and bank candidate IDs."""
    require(layer in EVIDENCE_FIELD, "Unknown layer")
    shown, mapping = model_candidates(dimensions, layer)
    fields(value, ("scene", "assessments"))
    require(text(value["scene"]), "Empty scene description")

    rows = value["assessments"]
    require(isinstance(rows, list) and len(rows) == 12, "Expected twelve endpoint assessments")
    row_fields = (
        ["dimension", "endpoint", "candidate_reviews"]
        + (["additional_evidence"] if layer == "image" else [])
        + ["decision", "explanation"]
    )
    seen, normalized = set(), []
    for row in rows:
        fields(row, row_fields)
        dimension = internal_key(row["dimension"])
        endpoint = row["endpoint"]
        require(endpoint in DIMENSIONS[dimension], "Endpoint/dimension mismatch")
        require((dimension, endpoint) not in seen, "Repeated endpoint")
        seen.add((dimension, endpoint))

        expected = [c["id"] for c in shown[row["dimension"]][endpoint]]
        require(isinstance(row["candidate_reviews"], list), "Candidate reviews must be an array")
        reviewed, accepted, reviews = set(), 0, []
        for review in row["candidate_reviews"]:
            fields(review, REVIEW_FIELDS)
            candidate_id = review["candidate_id"]
            require(
                candidate_id in expected and candidate_id not in reviewed,
                "Missing, foreign or duplicate candidate review ID",
            )
            reviewed.add(candidate_id)
            require(
                all(text(review[k]) for k in ("core", "in_image", "interpretation_check")),
                "Empty review text",
            )
            observation = review["observation_assessment"]
            interpretation = review["interpretation_assessment"]
            decision = review["decision"]
            require(observation in ("grounded", "not_grounded", "unclear"), "Invalid observation assessment")
            require(
                interpretation in ("warranted", "not_warranted", "unclear", "not_assessed"),
                "Invalid interpretation assessment",
            )
            # Once the observation is not grounded the interpretation is moot:
            # any value is accepted and stored as not_assessed.
            if observation != "grounded":
                interpretation = "not_assessed"
            require(
                observation != "grounded" or interpretation != "not_assessed",
                "A grounded observation needs an interpretation assessment",
            )
            require(decision in ("accept", "reject"), "Invalid candidate decision")
            require(
                (decision == "accept") == (observation == "grounded" and interpretation == "warranted"),
                "Accept requires a grounded observation and a warranted interpretation",
            )
            accepted += decision == "accept"
            reviews.append(
                {
                    **review,
                    "interpretation_assessment": interpretation,
                    "candidate_id": mapping[candidate_id],
                    "display_id": candidate_id,
                }
            )
        require(reviewed == set(expected), "Every supplied candidate must be reviewed exactly once")

        additional = []
        if layer == "image":
            require(isinstance(row["additional_evidence"], list), "Additional evidence must be an array")
            for item in row["additional_evidence"]:
                fields(item, ("visual_basis", "interpretation"))
                require(
                    text(item["visual_basis"]) and text(item["interpretation"]),
                    "Empty additional evidence field",
                )
                additional.append(dict(item))
        require(
            row["decision"] in ("supported", "not_supported") and text(row["explanation"]),
            "Invalid endpoint decision/explanation",
        )
        require(
            (row["decision"] == "supported") == bool(accepted or additional),
            "Decision must be supported exactly when a candidate is accepted or evidence is added",
        )
        out = {
            "dimension": dimension,
            "endpoint": endpoint,
            "candidate_reviews": reviews,
            "decision": row["decision"],
            "explanation": row["explanation"],
        }
        if layer == "image":
            out["additional_evidence"] = additional
        normalized.append(out)
    return {"scene": value["scene"], "assessments": normalized}


def majority(decisions: dict, members) -> str | None:
    members = tuple(members)
    require(
        len(members) == 3 and len(set(members)) == 3 and not (set(decisions) - set(members)),
        "Invalid voter set",
    )
    require(
        all(v in ("supported", "not_supported", None) for v in decisions.values()),
        "Invalid vote",
    )
    # A failed or absent model is not a negative; a complete layer requires all three.
    if any(decisions.get(m) is None for m in members):
        return None
    return "supported" if sum(decisions[m] == "supported" for m in members) >= 2 else "not_supported"


def endpoint_or(scenario: str | None, image: str | None) -> str | None:
    require(
        all(v in ("supported", "not_supported", None) for v in (scenario, image)),
        "Invalid layer decision",
    )
    if "supported" in (scenario, image):
        return "supported"
    if scenario == image == "not_supported":
        return "not_supported"
    return None


def aggregate(results: dict, members) -> dict:
    """Majority within each layer, then endpoint OR; ``results`` holds normalized verifier outputs."""
    require(not (set(results) - {"scenario", "image"}), "Unknown aggregation layer")
    members = tuple(members)
    rows = []
    for dimension, endpoints in DIMENSIONS.items():
        for endpoint in endpoints:
            layers = {}
            for layer in ("scenario", "image"):
                votes = {}
                for model in members:
                    value = results.get(layer, {}).get(model)
                    votes[model] = (
                        None
                        if value is None
                        else next(
                            x["decision"]
                            for x in value["assessments"]
                            if x["dimension"] == dimension and x["endpoint"] == endpoint
                        )
                    )
                layers[layer] = {"votes": votes, "decision": majority(votes, members)}
            rows.append(
                {
                    "dimension": dimension,
                    "endpoint": endpoint,
                    "layers": layers,
                    "decision": endpoint_or(
                        layers["scenario"]["decision"], layers["image"]["decision"]
                    ),
                    "complete": all(z["decision"] is not None for z in layers.values()),
                }
            )
    return {"complete": all(x["complete"] for x in rows), "assessments": rows}


def stage_schema(stage: str, candidates: dict | None = None) -> dict:
    """The stage's frozen schema; verification candidate IDs are limited to the IDs this call shows."""
    require(stage in STAGES, "Unknown stage")
    schema = json.loads(asset_text(f"{stage}.schema.json"))
    if stage.endswith("verification"):
        require(candidates is not None, "Verification requires its own bank")
        _, mapping = model_candidates(candidates, stage.split("_")[0])
        if mapping:
            schema["properties"]["assessments"]["items"]["properties"]["candidate_reviews"]["items"][
                "properties"
            ]["candidate_id"]["enum"] = sorted(mapping, key=lambda x: int(x[1:]))
    return schema


def render(stage: str, scenario: str, candidates: dict | None = None) -> str:
    """Fill a prompt; verification prompts receive the bank as ``model_candidates`` shows it."""
    require(stage in STAGES and isinstance(scenario, str) and scenario.strip(), "Invalid prompt input")
    prompt = asset_text(f"{stage}.prompt.md").replace("{{CANONICAL_PROMPT_CORE}}", scenario)
    if stage.endswith("verification"):
        require(candidates is not None, "Verification requires its own bank")
        layer = stage.split("_")[0]
        shown, _ = model_candidates(candidates, layer)
        token = "{{SCENARIO_CANDIDATES}}" if layer == "scenario" else "{{IMAGE_CANDIDATES}}"
        prompt = prompt.replace(token, json.dumps(shown, ensure_ascii=False, indent=2))
    require("{{" not in prompt, "Unfilled prompt field")
    return prompt


@functools.lru_cache(maxsize=None)
def asset_text(name: str) -> str:
    """Read a frozen prompt or schema from ``materials/annotation`` once per process."""
    path = MATERIALS_DIR / "annotation" / name
    if not path.is_file():
        raise FileNotFoundError(
            f"Missing frozen material {path}. Set VVB_MATERIALS to the repository "
            "materials directory if the evaluation package was moved."
        )
    return path.read_text()


def verify_assets() -> dict:
    """Check the eight executed prompt/schema files against ``materials/manifest.json``."""
    manifest_path = MATERIALS_DIR / "manifest.json"
    require(manifest_path.is_file(), f"Missing materials manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text())
    stage_assets = {
        f"{stage}.{suffix}" for stage in STAGES for suffix in ("prompt.md", "schema.json")
    }
    checked = {}
    for entry in manifest["files"]:
        relative = entry["file"]
        if not relative.startswith("annotation/"):
            continue
        if Path(relative).name not in stage_assets:
            continue
        path = MATERIALS_DIR / relative
        require(path.is_file(), f"Missing frozen material: {path}")
        require(
            digest(path.read_bytes()) == entry["sha256"],
            f"Frozen material changed: {relative}",
        )
        checked[relative] = entry["sha256"]
    require(len(checked) == 8, f"Expected eight annotation materials, checked {len(checked)}")
    return {
        "protocol": manifest.get("annotation_freeze", PROTOCOL),
        "annotation_freeze_verification": manifest.get("annotation_freeze_verification"),
        "files": checked,
    }