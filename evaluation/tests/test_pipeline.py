from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

EVALUATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EVALUATION))

from vvb_eval import core  # noqa: E402
from vvb_eval.dimensions import DIMENSIONS, model_key  # noqa: E402
from vvb_eval.runner import MOCK_CONFIG, Runner, load_manifest  # noqa: E402
from vvb_eval.scoring import four_state  # noqa: E402

ENDPOINT_ORDER = [
    "high_power_distance",
    "low_power_distance",
    "individualism",
    "collectivism",
    "achievement_and_competition_orientation",
    "care_and_quality_of_life_orientation",
    "high_uncertainty_avoidance",
    "low_uncertainty_avoidance",
    "long_term_orientation",
    "short_term_orientation",
    "indulgence",
    "restraint",
]


class CoreTests(unittest.TestCase):
    def test_endpoint_order_matches_frozen_votes(self):
        self.assertEqual([ep for eps in DIMENSIONS.values() for ep in eps], ENDPOINT_ORDER)

    def test_majority_and_missing_vote(self):
        members = ("a", "b", "c")
        self.assertEqual(core.majority({"a": "supported", "b": "supported", "c": "not_supported"}, members), "supported")
        self.assertEqual(core.majority({"a": "supported", "b": "not_supported", "c": "not_supported"}, members), "not_supported")
        self.assertIsNone(core.majority({"a": "supported", "b": None, "c": "supported"}, members))

    def test_endpoint_or(self):
        self.assertEqual(core.endpoint_or("supported", "not_supported"), "supported")
        self.assertEqual(core.endpoint_or("not_supported", "supported"), "supported")
        self.assertEqual(core.endpoint_or("not_supported", "not_supported"), "not_supported")
        self.assertIsNone(core.endpoint_or("not_supported", None))

    def test_bank_deduplicates_only_identical_content(self):
        def proposal(role, evidence):
            dimensions = {}
            for dimension, endpoints in DIMENSIONS.items():
                dimensions[model_key(dimension)] = {}
                for endpoint in endpoints:
                    dimensions[model_key(dimension)][endpoint] = [
                        {"id": f"{role}-{endpoint}", "potential_evidence": evidence, "interpretation": "same"}
                    ]
            return {
                "focal_situation": "s",
                "ranking": [
                    {"dimension": model_key(d), "rank": i, "relevance": "related", "reason": "r"}
                    for i, d in enumerate(DIMENSIONS, 1)
                ],
                "dimensions": dimensions,
            }

        members = ("a", "b", "c")
        proposals = {
            "a": core.validate_proposal(proposal("a", "same evidence"), "scenario"),
            "b": core.validate_proposal(proposal("b", "same evidence"), "scenario"),
            "c": core.validate_proposal(proposal("c", "different evidence"), "scenario"),
        }
        bank = core.bank(proposals, "scenario", members)
        for dimension, endpoints in DIMENSIONS.items():
            for endpoint in endpoints:
                self.assertEqual(len(bank["dimensions"][dimension][endpoint]), 2)

    def test_four_state(self):
        def aggregate_for(states):
            rows = []
            for dimension, endpoints in DIMENSIONS.items():
                for endpoint in endpoints:
                    rows.append(
                        {
                            "dimension": dimension,
                            "endpoint": endpoint,
                            "decision": states[dimension][endpoint],
                            "layers": {},
                            "complete": True,
                        }
                    )
            return {"assessments": rows, "complete": True}

        states = {d: {ep: "not_supported" for ep in eps} for d, eps in DIMENSIONS.items()}
        states["power_distance"]["high_power_distance"] = "supported"
        self.assertEqual(four_state(aggregate_for(states), "power_distance"), "a_only")
        states["power_distance"]["low_power_distance"] = "supported"
        self.assertEqual(four_state(aggregate_for(states), "power_distance"), "both")
        states["power_distance"]["high_power_distance"] = "not_supported"
        self.assertEqual(four_state(aggregate_for(states), "power_distance"), "b_only")
        states["power_distance"]["low_power_distance"] = None
        self.assertEqual(four_state(aggregate_for(states), "power_distance"), "unresolved")

    def test_assets_verify(self):
        assets = core.verify_assets()
        self.assertEqual(len(assets["files"]), 8)


class PipelineTests(unittest.TestCase):
    def test_manifest_rejects_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.jsonl"
            row = {"sample_id": "x", "scenario": "s", "image": "missing.jpg"}
            path.write_text(json.dumps(row) + "\n" + json.dumps(row) + "\n")
            with self.assertRaises(ValueError):
                load_manifest(path)

    def test_mock_end_to_end_and_resume(self):
        manifest = EVALUATION / "examples" / "manifest.jsonl"
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "run"
            runner = Runner(
                manifest=manifest,
                out=out,
                config=json.loads(json.dumps(MOCK_CONFIG)),
                mock=True,
                max_calls=100,
            )
            status = runner.run("mock")
            self.assertTrue(status["complete"], status["failures"])
            self.assertEqual(status["calls"], 24)
            self.assertEqual(status["complete_annotations"], 2)
            self.assertTrue((out / "counts.csv").is_file())
            self.assertEqual(len((out / "votes.jsonl").read_text().strip().splitlines()), 2)
            annotation = json.loads((out / "annotations" / "flux2__cdeval_ivr_0109__en_us__none.json").read_text())
            self.assertTrue(annotation["complete"])
            self.assertEqual(len(annotation["assessments"]), 12)

            # A second run must reuse every valid record and make no model calls.
            resumed = Runner(
                manifest=manifest,
                out=out,
                config=json.loads(json.dumps(MOCK_CONFIG)),
                mock=True,
                max_calls=100,
            )
            status = resumed.run("mock")
            self.assertTrue(status["complete"], status["failures"])
            self.assertEqual(status["calls"], 0)


if __name__ == "__main__":
    unittest.main()