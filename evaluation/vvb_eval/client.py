"""Model transports for the reference evaluation runner.

The real transport speaks the OpenAI Chat Completions protocol, so any
OpenAI-compatible endpoint can be used (OpenAI, OpenRouter, Google's
OpenAI-compatible endpoint, a local vLLM server, ...).  ``MockClient`` produces
deterministic, schema-valid responses for the offline smoke test; it is not a
scientific baseline and its outputs must not be interpreted as measurements.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .dimensions import DIMENSIONS, model_key


class ClientError(RuntimeError):
    pass


@dataclass
class CallContext:
    """Everything the transport may need beyond the rendered prompt."""

    stage: str
    role: str
    model: str
    scenario: str
    sample_id: str
    image_path: Path | None
    bank: dict | None
    shown_candidates: dict | None


def extract_text(message: Any) -> str:
    content = getattr(message, "content", None)
    if isinstance(content, str) and content.strip():
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            text = part.get("text") if isinstance(part, dict) else getattr(part, "text", None)
            if text:
                parts.append(text)
        if parts:
            return "".join(parts)
    raise ClientError("Model response did not contain text content")


def parse_json_object(content: str) -> dict:
    if not isinstance(content, str) or not content.strip():
        raise ClientError("Model output was empty")
    stripped = content.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        start, end = stripped.find("{"), stripped.rfind("}")
        if start < 0 or end <= start:
            raise ClientError("Model output did not contain a JSON object") from None
        try:
            value = json.loads(stripped[start : end + 1])
        except json.JSONDecodeError as error:
            raise ClientError(f"Could not parse model JSON: {error}") from None
    if not isinstance(value, dict):
        raise ClientError("Model output must be a JSON object")
    return value


def image_data_url(path: Path) -> str:
    mime, _ = mimetypes.guess_type(path.name)
    mime = mime or "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _unsupported_format_error(error: Exception) -> bool:
    message = str(error).lower()
    return any(
        marker in message
        for marker in (
            "response_format",
            "json_schema",
            "json schema",
            "unknown parameter",
            "unsupported parameter",
            "invalid parameter",
        )
    )


class OpenAIClient:
    """One OpenAI-compatible chat client for a configured role."""

    def __init__(self, config: dict):
        try:
            from openai import OpenAI
        except ImportError as error:  # pragma: no cover - only in execute mode
            raise ClientError(
                "The execute mode needs the 'openai' package: pip install -r evaluation/requirements.txt"
            ) from error
        self.config = dict(config)
        self.model = self.config["model"]
        self.api_key_env = self.config.get("api_key_env", "OPENAI_API_KEY")
        key = os.environ.get(self.api_key_env)
        if not key:
            raise ClientError(f"Missing configured credential: {self.api_key_env}")
        self.client = OpenAI(
            api_key=key,
            base_url=self.config.get("base_url"),
            timeout=self.config.get("timeout_seconds", 600),
        )
        self.response_format = self.config.get("response_format", "json_schema")

    def _request_kwargs(self, prompt: str, image_paths: list[Path], schema: dict | None) -> dict:
        content: list[dict] = [{"type": "text", "text": prompt}]
        for path in image_paths:
            content.append({"type": "image_url", "image_url": {"url": image_data_url(path)}})
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": content}],
        }
        if self.config.get("temperature") is not None:
            kwargs["temperature"] = self.config["temperature"]
        max_tokens = self.config.get("max_tokens")
        if max_tokens:
            kwargs[self.config.get("max_tokens_field", "max_tokens")] = max_tokens
        if self.config.get("reasoning_effort"):
            kwargs["reasoning_effort"] = self.config["reasoning_effort"]
        if self.config.get("extra_body"):
            kwargs["extra_body"] = self.config["extra_body"]
        if self.response_format == "json_schema" and schema is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": self.config.get("schema_name", "visionvaluebench"),
                    "strict": True,
                    "schema": schema,
                },
            }
        elif self.response_format == "json_object":
            kwargs["response_format"] = {"type": "json_object"}
        return kwargs

    def complete(
        self,
        prompt: str,
        image_paths: list[Path],
        context: CallContext,
        schema: dict | None = None,
    ) -> dict:
        kwargs = self._request_kwargs(prompt, image_paths, schema)
        used = kwargs.get("response_format", {}).get("type", "none")
        try:
            response = self.client.chat.completions.create(**kwargs)
        except Exception as error:
            if used != "json_schema" or not _unsupported_format_error(error):
                raise
            # Some OpenAI-compatible providers do not implement json_schema.
            # Fall back to JSON mode, then to prompt-only JSON, and record which one ran.
            self.response_format = "json_object"
            kwargs = self._request_kwargs(prompt, image_paths, schema)
            used = "json_object"
            try:
                response = self.client.chat.completions.create(**kwargs)
            except Exception as second:
                if not _unsupported_format_error(second):
                    raise
                self.response_format = "none"
                kwargs = self._request_kwargs(prompt, image_paths, schema)
                used = "none"
                response = self.client.chat.completions.create(**kwargs)
        message = response.choices[0].message
        raw = extract_text(message)
        parsed = parse_json_object(raw)
        usage = response.usage.model_dump() if getattr(response, "usage", None) else None
        return {
            "raw": raw,
            "parsed": parsed,
            "usage": usage,
            "model": getattr(response, "model", None) or self.model,
            "response_format": used,
        }


def _source_dimension(sample_id: str) -> str | None:
    codes = {
        "pdi": "power_distance",
        "idv": "individualism_collectivism",
        "mas": "masculinity_femininity",
        "uai": "uncertainty_avoidance",
        "lto": "long_term_orientation",
        "ivr": "indulgence_restraint",
    }
    match = re.search(r"cdeval_(pdi|idv|mas|uai|lto|ivr)_", sample_id)
    return codes[match.group(1)] if match else None


def _mock_proposal(context: CallContext) -> dict:
    layer = context.stage.split("_")[0]
    evidence = "potential_evidence" if layer == "scenario" else "visual_basis"
    ranking = [
        {
            "dimension": model_key(dimension),
            "rank": rank,
            "relevance": "related",
            "reason": f"Mock relevance for {dimension}.",
        }
        for rank, dimension in enumerate(DIMENSIONS, 1)
    ]
    dimensions = {}
    for dimension, endpoints in DIMENSIONS.items():
        dimensions[model_key(dimension)] = {}
        for endpoint in endpoints:
            dimensions[model_key(dimension)][endpoint] = [
                {
                    "id": f"{context.role}-{dimension}-{endpoint}",
                    evidence: f"Mock {evidence} for {endpoint} from {context.role}.",
                    "interpretation": f"Mock interpretation of {endpoint} from {context.role}.",
                }
            ]
    out = {"ranking": ranking, "dimensions": dimensions}
    if layer == "scenario":
        out["focal_situation"] = f"Mock focal situation for {context.sample_id}."
    return out


def _mock_verification(context: CallContext) -> dict:
    layer = context.stage.split("_")[0]
    shown = context.shown_candidates or {}
    source = _source_dimension(context.sample_id)
    variant = sum(ord(char) for char in context.sample_id) % 3
    supported: set[str] = set()
    if source:
        first, second = DIMENSIONS[source]
        if variant == 0:
            supported.add(first)
        elif variant == 1:
            supported.add(second)
        else:
            supported.update((first, second))

    assessments = []
    for dimension, endpoints in DIMENSIONS.items():
        for endpoint in endpoints:
            candidates = shown.get(model_key(dimension), {}).get(endpoint, [])
            should_accept = endpoint in supported and layer == "scenario"
            accepted = False
            reviews = []
            for index, candidate in enumerate(candidates):
                if should_accept and index == 0:
                    reviews.append(
                        {
                            "candidate_id": candidate["id"],
                            "core": "Mock core scene.",
                            "in_image": "Mock observation in the image.",
                            "observation_assessment": "grounded",
                            "interpretation_check": "Mock interpretation check.",
                            "interpretation_assessment": "warranted",
                            "decision": "accept",
                        }
                    )
                    accepted = True
                else:
                    reviews.append(
                        {
                            "candidate_id": candidate["id"],
                            "core": "Mock core scene.",
                            "in_image": "Mock observation not found in the image.",
                            "observation_assessment": "not_grounded",
                            "interpretation_check": "Mock interpretation is moot.",
                            "interpretation_assessment": "not_assessed",
                            "decision": "reject",
                        }
                    )
            additional = []
            if layer == "image" and endpoint in supported:
                # Exercise the IAE addition path for one supported endpoint.
                additional.append(
                    {
                        "visual_basis": f"Mock additional visible evidence for {endpoint}.",
                        "interpretation": f"Mock additional interpretation of {endpoint}.",
                    }
                )
            assessments.append(
                {
                    "dimension": model_key(dimension),
                    "endpoint": endpoint,
                    "candidate_reviews": reviews,
                    "additional_evidence": additional,
                    "decision": "supported" if (accepted or additional) else "not_supported",
                    "explanation": "Mock verification decision.",
                }
            )
    if layer == "scenario":
        for row in assessments:
            row.pop("additional_evidence", None)
    return {"scene": "Mock scene description.", "assessments": assessments}


class MockClient:
    """Deterministic schema-valid responses for offline smoke tests."""

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    def complete(
        self,
        prompt: str,
        image_paths: list[Path],
        context: CallContext,
        schema: dict | None = None,
    ) -> dict:
        parsed = (
            _mock_proposal(context)
            if context.stage.endswith("_proposal")
            else _mock_verification(context)
        )
        return {
            "raw": json.dumps(parsed, ensure_ascii=False),
            "parsed": parsed,
            "usage": None,
            "model": "mock",
            "response_format": "mock",
        }