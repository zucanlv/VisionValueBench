"""Reference runner for the two-layer SAE/IAE evaluation."""

from __future__ import annotations

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import core
from .client import CallContext, MockClient, OpenAIClient
from .dimensions import DIMENSIONS
from .scoring import dimension_states, write_counts

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


class StageError(RuntimeError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    return core.digest(path.read_bytes())


def sha256_text(value: str) -> str:
    return core.digest(value)


def sha256_json(value) -> str:
    return core.digest(value)


def read_json(path: Path):
    return json.loads(path.read_text())


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f".{threading.get_ident()}.tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temp.replace(path)


@dataclass(frozen=True)
class Sample:
    sample_id: str
    scenario: str
    image: Path
    scenario_sha256: str
    image_sha256: str


def _valid_image(path: Path) -> bool:
    if path.suffix.lower() not in IMAGE_SUFFIXES or not path.is_file():
        return False
    with path.open("rb") as handle:
        head = handle.read(12)
    return (
        head.startswith(b"\xff\xd8\xff")
        or head.startswith(b"\x89PNG\r\n\x1a\n")
        or (head[:4] == b"RIFF" and head[8:12] == b"WEBP")
    )


def load_manifest(path: Path) -> list[Sample]:
    path = path.resolve()
    samples, seen = [], set()
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"Manifest line {number}: {error}") from None
            if set(row) != {"sample_id", "scenario", "image"}:
                raise ValueError(
                    f"Manifest line {number}: expected exactly sample_id, scenario, image"
                )
            sample_id, scenario, image = row["sample_id"], row["scenario"], row["image"]
            if not (
                isinstance(sample_id, str)
                and sample_id
                and all(char.isalnum() or char in "-_" for char in sample_id)
            ):
                raise ValueError(f"Manifest line {number}: unsafe sample_id")
            if sample_id in seen:
                raise ValueError(f"Manifest line {number}: duplicate sample_id {sample_id}")
            if not isinstance(scenario, str) or not scenario.strip():
                raise ValueError(f"Manifest line {number}: empty scenario")
            image_path = (path.parent / image).resolve()
            if not _valid_image(image_path):
                raise ValueError(f"Manifest line {number}: missing or unsupported image {image_path}")
            seen.add(sample_id)
            samples.append(
                Sample(
                    sample_id=sample_id,
                    scenario=scenario,
                    image=image_path,
                    scenario_sha256=sha256_text(scenario),
                    image_sha256=sha256_file(image_path),
                )
            )
    if not samples:
        raise ValueError("Manifest is empty")
    return samples


MOCK_CONFIG = {
    "proposers": ["model_a", "model_b", "model_c"],
    "verifiers": ["model_a", "model_b", "model_c"],
    "models": {
        "model_a": {"model": "mock"},
        "model_b": {"model": "mock"},
        "model_c": {"model": "mock"},
    },
}


def load_config(path: Path | None) -> dict:
    if path is None:
        return json.loads(json.dumps(MOCK_CONFIG))
    config = read_json(path)
    proposers, verifiers, models = config.get("proposers"), config.get("verifiers"), config.get("models")
    if not isinstance(proposers, list) or len(proposers) != 3 or len(set(proposers)) != 3:
        raise ValueError("config.proposers must contain exactly three unique roles")
    if not isinstance(verifiers, list) or len(verifiers) != 3 or len(set(verifiers)) != 3:
        raise ValueError("config.verifiers must contain exactly three unique roles")
    if not isinstance(models, dict) or not set(models) >= set(proposers) | set(verifiers):
        raise ValueError("config.models must define every proposer and verifier role")
    for role in set(proposers) | set(verifiers):
        if not isinstance(models[role].get("model"), str) or not models[role]["model"].strip():
            raise ValueError(f"config.models.{role}.model is required")
    return config


@dataclass(frozen=True)
class Job:
    key: str
    stage: str
    role: str
    sample: Sample
    bank: dict | None


class Runner:
    def __init__(
        self,
        manifest: Path,
        out: Path,
        config: dict,
        mock: bool = False,
        workers: int | None = None,
        max_calls: int = 200,
        retry_failed: bool = False,
        resume: bool = True,
        limit: int | None = None,
    ):
        self.manifest_path = manifest.resolve()
        self.out = out.resolve()
        self.out.mkdir(parents=True, exist_ok=True)
        self.config = config
        self.mock = mock
        self.proposers = tuple(config["proposers"])
        self.verifiers = tuple(config["verifiers"])
        self.workers = workers or int(config.get("workers", 8))
        self.max_calls = max_calls
        self.retry_failed = retry_failed
        self.resume = resume
        self.samples = load_manifest(self.manifest_path)
        if limit is not None:
            self.samples = self.samples[:limit]
        self.calls = 0
        self.failures: list[dict] = []
        self.lock = threading.Lock()
        self.clients = {}

    # -- planning ---------------------------------------------------------
    def unique_scenarios(self) -> dict[str, Sample]:
        unique = {}
        for sample in self.samples:
            unique.setdefault(sample.scenario_sha256, sample)
        return unique

    def planned_calls(self) -> int:
        scenarios = len(self.unique_scenarios())
        return (
            scenarios * len(self.proposers)
            + len(self.samples) * len(self.proposers)
            + len(self.samples) * len(self.verifiers) * 2
        )

    # -- records ----------------------------------------------------------
    def _identity(self, stage: str, role: str, sample: Sample, prompt: str, bank: dict | None) -> dict:
        return {
            "stage": stage,
            "role": role,
            "model": self.config["models"][role]["model"],
            "scenario_sha256": sample.scenario_sha256,
            "image_sha256": None if stage == "scenario_proposal" else sample.image_sha256,
            "prompt_sha256": sha256_text(prompt),
            "bank_sha256": None if bank is None else sha256_json(bank),
        }

    def _record_path(self, stage: str, role: str, key: str) -> Path:
        return self.out / "records" / stage / role / f"{key}.json"

    def _record_key(self, stage: str, sample: Sample) -> str:
        return sample.scenario_sha256 if stage == "scenario_proposal" else sample.sample_id

    def _cached(self, path: Path, identity: dict):
        if not self.resume or not path.exists():
            return None
        record = read_json(path)
        if record.get("state") == "valid" and record.get("identity") == identity:
            return record["validated"]
        if record.get("state") == "invalid" and not self.retry_failed:
            raise StageError(
                f"Cached call failed: {path}. Use --retry-failed to run it again."
            )
        return None

    def _bump(self) -> None:
        with self.lock:
            self.calls += 1
            if self.calls > self.max_calls:
                raise StageError(f"Call budget exceeded (--max-calls {self.max_calls})")

    def _fail(self, job: Job, error: Exception) -> None:
        with self.lock:
            self.failures.append(
                {
                    "key": job.key,
                    "stage": job.stage,
                    "role": job.role,
                    "sample_id": job.sample.sample_id,
                    "error": str(error)[:2000],
                }
            )

    # -- one call ---------------------------------------------------------
    def _call_one(self, job: Job):
        layer = job.stage.split("_")[0]
        prompt = core.render(
            job.stage,
            job.sample.scenario,
            job.bank["dimensions"] if job.bank is not None else None,
        )
        identity = self._identity(job.stage, job.role, job.sample, prompt, job.bank)
        key = self._record_key(job.stage, job.sample)
        path = self._record_path(job.stage, job.role, key)
        cached = self._cached(path, identity)
        if cached is not None:
            return cached

        shown = (
            core.model_candidates(job.bank["dimensions"], layer)[0]
            if job.bank is not None
            else None
        )
        context = CallContext(
            stage=job.stage,
            role=job.role,
            model=self.config["models"][job.role]["model"],
            scenario=job.sample.scenario,
            sample_id=job.sample.sample_id,
            image_path=None if job.stage == "scenario_proposal" else job.sample.image,
            bank=job.bank,
            shown_candidates=shown,
        )
        schema = core.stage_schema(
            job.stage, job.bank["dimensions"] if job.bank is not None else None
        )
        images = [] if job.stage == "scenario_proposal" else [job.sample.image]
        retries = int(self.config.get("retries", 1))
        last_error = None
        for attempt in range(retries + 1):
            self._bump()
            record = {
                "identity": identity,
                "stage": job.stage,
                "role": job.role,
                "sample_id": job.sample.sample_id,
                "attempt": attempt,
                "prompt": prompt,
                "created_at": now(),
                "state": "pending",
            }
            try:
                response = self.clients[job.role].complete(prompt, images, context, schema=schema)
                parsed = response["parsed"]
                validated = (
                    core.validate_proposal(parsed, layer)
                    if job.stage.endswith("proposal")
                    else core.validate_verification(parsed, job.bank["dimensions"], layer)
                )
                record.update(
                    state="valid",
                    raw=response["raw"],
                    parsed=parsed,
                    validated=validated,
                    usage=response.get("usage"),
                    resolved_model=response.get("model"),
                    response_format=response.get("response_format"),
                    completed_at=now(),
                )
                write_json(path, record)
                return validated
            except Exception as error:  # noqa: BLE001 - each failed call is recorded
                last_error = error
                record.update(
                    state="invalid",
                    error=str(error)[:2000],
                    completed_at=now(),
                )
                write_json(path, record)
                if attempt < retries:
                    continue
        raise StageError(str(last_error))

    # -- stages -----------------------------------------------------------
    def _run_jobs(self, jobs: list[Job]) -> dict[str, dict]:
        results = {}
        if not jobs:
            return results
        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            futures = {executor.submit(self._call_one, job): job for job in jobs}
            for future in as_completed(futures):
                job = futures[future]
                try:
                    results[job.key] = future.result()
                except Exception as error:  # noqa: BLE001
                    self._fail(job, error)
        return results

    def _job_key(self, stage: str, role: str, sample: Sample, bank: dict | None = None) -> str:
        suffix = sample.scenario_sha256 if stage == "scenario_proposal" else sample.sample_id
        extra = "" if bank is None else f"|{sha256_json(bank)[:16]}"
        return f"{stage}|{role}|{suffix}{extra}"

    def run(self, mode: str) -> dict:
        assets = core.verify_assets()
        planned = self.planned_calls()
        if mode != "prepare" and planned > self.max_calls:
            raise StageError(
                f"Planned {planned} calls exceeds --max-calls {self.max_calls}; "
                "raise the cap deliberately if this is intended."
            )
        self._write_run(mode, assets, planned)
        if mode == "prepare":
            return {
                "prepared": True,
                "mode": mode,
                "samples": len(self.samples),
                "unique_scenarios": len(self.unique_scenarios()),
                "planned_calls": planned,
                "out": str(self.out),
            }

        client_class = MockClient if self.mock else OpenAIClient
        self.clients = {
            role: client_class(self.config["models"][role])
            for role in set(self.proposers) | set(self.verifiers)
        }

        scenarios = self.unique_scenarios()

        # 1. Scenario proposals: one per unique canonical scenario and proposer.
        jobs = [
            Job(self._job_key("scenario_proposal", role, sample), "scenario_proposal", role, sample, None)
            for role in self.proposers
            for sample in scenarios.values()
        ]
        scenario_proposals = self._run_jobs(jobs)

        scenario_banks = {}
        for scenario_hash, sample in scenarios.items():
            proposals = {
                role: scenario_proposals.get(
                    self._job_key("scenario_proposal", role, sample)
                )
                for role in self.proposers
            }
            if any(value is None for value in proposals.values()):
                self._fail(
                    Job("scenario_bank", "scenario_bank", "-", sample, None),
                    StageError("Missing scenario proposal; bank not built"),
                )
                continue
            scenario_banks[scenario_hash] = core.bank(proposals, "scenario", self.proposers)
            write_json(self.out / "banks" / "scenario" / f"{scenario_hash}.json", scenario_banks[scenario_hash])

        # 2. Image proposals: one per sample and proposer.
        jobs = [
            Job(self._job_key("image_proposal", role, sample), "image_proposal", role, sample, None)
            for role in self.proposers
            for sample in self.samples
        ]
        image_proposals = self._run_jobs(jobs)

        image_banks = {}
        for sample in self.samples:
            proposals = {
                role: image_proposals.get(self._job_key("image_proposal", role, sample))
                for role in self.proposers
            }
            if any(value is None for value in proposals.values()):
                self._fail(
                    Job("image_bank", "image_bank", "-", sample, None),
                    StageError("Missing image proposal; bank not built"),
                )
                continue
            image_banks[sample.sample_id] = core.bank(proposals, "image", self.proposers)
            write_json(
                self.out / "banks" / "image" / f"{sample.sample_id}.json",
                image_banks[sample.sample_id],
            )

        # 3. Scenario verification and image verification.
        scenario_jobs, image_jobs = [], []
        for sample in self.samples:
            bank = scenario_banks.get(sample.scenario_sha256)
            if bank is not None:
                for role in self.verifiers:
                    scenario_jobs.append(
                        Job(
                            self._job_key("scenario_verification", role, sample, bank),
                            "scenario_verification",
                            role,
                            sample,
                            bank,
                        )
                    )
            bank = image_banks.get(sample.sample_id)
            if bank is not None:
                for role in self.verifiers:
                    image_jobs.append(
                        Job(
                            self._job_key("image_verification", role, sample, bank),
                            "image_verification",
                            role,
                            sample,
                            bank,
                        )
                    )
        scenario_verification = self._run_jobs(scenario_jobs)
        image_verification = self._run_jobs(image_jobs)

        # 4. Aggregate and write per-sample annotations, votes and counts.
        states = []
        votes_path = self.out / "votes.jsonl"
        with votes_path.open("w", encoding="utf-8") as votes:
            for sample in self.samples:
                results = {"scenario": {}, "image": {}}
                scenario_bank = scenario_banks.get(sample.scenario_sha256)
                image_bank = image_banks.get(sample.sample_id)
                if scenario_bank is not None:
                    for role in self.verifiers:
                        value = scenario_verification.get(
                            self._job_key("scenario_verification", role, sample, scenario_bank)
                        )
                        if value is not None:
                            results["scenario"][role] = value
                if image_bank is not None:
                    for role in self.verifiers:
                        value = image_verification.get(
                            self._job_key("image_verification", role, sample, image_bank)
                        )
                        if value is not None:
                            results["image"][role] = value
                aggregate = core.aggregate(results, self.verifiers)
                annotation = {
                    "sample_id": sample.sample_id,
                    "scenario": sample.scenario,
                    "image": sample.image.name,
                    "aggregation": "majority within each layer, then endpoint OR",
                    **aggregate,
                }
                write_json(self.out / "annotations" / f"{sample.sample_id}.json", annotation)
                if aggregate["complete"]:
                    states.append(dimension_states(aggregate))
                votes.write(
                    json.dumps(
                        {
                            "sample_id": sample.sample_id,
                            "complete": aggregate["complete"],
                            "endpoints": {
                                row["endpoint"]: {
                                    "scenario": row["layers"]["scenario"]["decision"],
                                    "image": row["layers"]["image"]["decision"],
                                    "final": row["decision"],
                                }
                                for row in aggregate["assessments"]
                            },
                            "dimensions": dimension_states(aggregate),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        write_counts(self.out / "counts.csv", states)

        complete = not self.failures and len(states) == len(self.samples)
        status = {
            "complete": complete,
            "mode": mode,
            "samples": len(self.samples),
            "complete_annotations": len(states),
            "calls": self.calls,
            "failures": self.failures,
            "finished_at": now(),
            "out": str(self.out),
        }
        write_json(self.out / "status.json", status)
        return status

    def _write_run(self, mode: str, assets: dict, planned: int) -> None:
        metadata = {
            "protocol": core.PROTOCOL,
            "created_at": now(),
            "mode": mode,
            "manifest": str(self.manifest_path),
            "manifest_sha256": sha256_file(self.manifest_path),
            "samples": len(self.samples),
            "unique_scenarios": len(self.unique_scenarios()),
            "proposers": list(self.proposers),
            "verifiers": list(self.verifiers),
            "models": {
                role: {
                    key: value
                    for key, value in self.config["models"][role].items()
                    if key not in {"api_key", "token"}
                }
                for role in sorted(set(self.proposers) | set(self.verifiers))
            },
            "planned_calls": planned,
            "assets": assets,
            "aggregation": "within each layer, a verifier supports an endpoint exactly when it accepts a candidate (Image layer: or adds evidence); majority of the three verifiers per layer, then endpoint OR",
            "scope": "proposers mark each dimension related or unrelated and write candidates only for related dimensions; verifiers assess all twelve endpoints",
            "model_view": "prompts show model-facing dimension keys and short per-call candidate IDs; records keep the model output, validation maps it back to internal keys and bank IDs",
            "scenario_reuse": "one proposal per model and exact canonical scenario in this run",
        }
        write_json(self.out / "run.json", metadata)