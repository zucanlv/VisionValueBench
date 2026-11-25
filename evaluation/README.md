# Reference evaluation implementation

This directory contains a runnable reference implementation of the two-layer
evaluation used in the paper:

- **SAE** (Scenario-Anticipated Evaluation): three proposers read the canonical
  scenario without the image; their candidate banks are pooled and three
  verifiers check each candidate against the image.
- **IAE** (Image-Adaptive Evaluation): three proposers read the scenario and the
  image; the image-layer verifier may also add evidence that no proposer listed.

Each layer uses a majority of its three verifiers per orientation, and the final
orientation decision is the OR of the two layers. Inputs, prompts, schemas,
validation rules and aggregation follow the frozen `pooled-two-layer-v2.1`
materials in `materials/annotation/`.

The implementation is a **reference runner**, not the internal production
runner. It keeps the frozen contracts and aggregation, but uses one
OpenAI-compatible transport instead of the original multi-provider batch/budget
stack. See [Scope](#scope) below.

## Install

The prepare and mock modes use only the Python standard library. Real model
calls need the OpenAI client:

```sh
python3 -m pip install -r evaluation/requirements.txt
```

## Offline smoke test

```sh
python3 evaluation/run_eval.py \
  --manifest evaluation/examples/manifest.jsonl \
  --out runs/smoke \
  --mock
```

This runs all 24 calls (2 samples × 3 proposers × 2 layers, plus 3 verifiers ×
2 layers × 2 samples) with deterministic mock responses. It is a plumbing test,
**not** a scientific measurement. The output is:

```text
runs/smoke/
├── run.json                    # protocol, manifest, model config, asset hashes
├── records/                    # every prompt, raw response, validation result
├── banks/                      # scenario and image candidate banks
├── annotations/<sample>.json   # 12 endpoint decisions per sample
├── votes.jsonl                 # per-sample endpoint votes and dimension states
├── counts.csv                  # four-state counts, readable by scripts/score.py
└── status.json
```

Score the counts with the repository helper:

```sh
python3 scripts/score.py runs/smoke/counts.csv
```

Prepare a run without calling a model (validates the manifest, images, prompts
and asset hashes; prints the number of calls that a full run would make):

```sh
python3 evaluation/run_eval.py \
  --manifest evaluation/examples/manifest.jsonl \
  --out runs/prepared
```

## Real model calls

Copy a config and set the credentials named by `api_key_env`:

```sh
export OPENAI_API_KEY=...
export GOOGLE_API_KEY=...
export OPENROUTER_API_KEY=...

python3 evaluation/run_eval.py \
  --manifest path/to/manifest.jsonl \
  --out runs/my-eval \
  --config evaluation/configs/paper.json \
  --execute \
  --max-calls 2000
```

`evaluation/configs/paper.json` records the three judge models used in the
paper (`luna`, `gemini`, `muse`). Those deployments may not be available to
you; `evaluation/configs/example.openai.json` is a runnable OpenAI example.
Any OpenAI-compatible endpoint can be used by setting `base_url`.

**Cost warning.** A full run is large: 960 unique scenarios and 68,764 images
require roughly 615k model calls across the two layers. `--max-calls` is a hard
safety cap (default 200); raise it deliberately. A failed call is recorded and
does not become a negative vote. Use `--limit N` for a pilot.

`--execute` needs all three proposer and verifier roles configured. If a model
does not implement `response_format=json_schema`, the client falls back to JSON
mode and then to prompt-only JSON; the response format actually used is stored
in each record.

## Manifest

One JSON object per line:

```json
{"sample_id": "flux2__cdeval_ivr_0109__en_us__none", "scenario": "a traveler at the vacation destination they chose for either its exciting recreational activities or its quiet serenity", "image": "images/flux2__cdeval_ivr_0109__en_us__none.jpg"}
```

- `sample_id`: letters, digits, `_`, `-`; unique.
- `scenario`: the **canonical** scenario shown to the judges, not the rendered
  text-to-image prompt.
- `image`: path relative to the manifest file; JPEG, PNG or WebP.

Proposer outputs for identical canonical scenario text are cached and reused
within a run, so a 68,764-image manifest still makes only 960 × 3 scenario
proposal calls.

## Output semantics

For each image and each of the twelve orientations, `annotations/` stores the
three verifier votes per layer, the layer majority decision, and the final
endpoint decision. A sample is `complete` only when all twelve endpoint
decisions are resolved in both layers; missing or failed calls stay unresolved
and are never imputed as negative.

`votes.jsonl` converts the twelve endpoint decisions into the four states per
dimension (`a_only`, `b_only`, `both`, `neither`). `counts.csv` aggregates them
and applies the published identities:

```text
n         = a_only + b_only + both + neither
supported = a_only + b_only + both
S         = (a_only - b_only) / supported
C         = supported / n
```

The first endpoint listed in `vvb_eval/dimensions.py` is the A orientation, in
the same order as `analysis/votes.json.gz` (`endpoint_order`).

## Scope

Included: the four executed prompt templates, their JSON schemas, semantic
validation, content-hash candidate pooling, short-ID blinding, per-layer
majority, endpoint OR, four-state scoring, resumable records, and a mock
transport.

Not included: the internal production runner's provider-specific batch jobs,
budget ledger, human-review bundle exporter and operational deployment code.
The original UI/annotation app and participant data are outside this release.

The prompts and schemas are read from `materials/annotation/` and checked
against `materials/manifest.json` at the start of every run. Set `VVB_MATERIALS`
if you move the evaluation package away from the repository root.

## Tests

```sh
python3 evaluation/tests/test_pipeline.py -v
```

The tests cover the frozen endpoint order, exact-content bank deduplication,
majority and OR rules, four-state scoring, asset hashes, and a full mock run
including zero-call resume.