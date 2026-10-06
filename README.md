# VisionValueBench

Full execution prompts and decision materials for studying visual value leakage in text-to-image generation, with an offline replay of the frozen automatic-verifier votes.

This repository contains two usable parts: the frozen `pooled-two-layer-v2.1` materials and numerical reproduction. The complete generation and annotation API runner is still to be recovered from the original project backup.

## Contents

| Path | Contents |
| --- | --- |
| `materials/construction/` | Concept, scenario and translation prompts; language/country rendering templates; original template source excerpts |
| `materials/filtering/` | Fixed-orientation filtering prompt and six-dimensional rubric |
| `materials/annotation/` | Four SAE/IAE proposal and verification prompts, JSON schemas, shared rules and six decision cards |
| `materials/human/` | Human-readable decision cards and worked examples with six images |
| `analysis/` | Frozen automatic votes, sample metadata, reference tables and the original standalone numerical replay script |
| `scripts/` | A small count-to-score helper and release-file verification |
| `docs/workflow.md` | Inputs, outputs, pooling, voting and score definitions |
| `docs/release_scope.md` | What is ready and what remains to recover |

The manuscript uses **Scenario-Anticipated Evaluation (SAE)** and **Image-Adaptive Evaluation (IAE)**. Archived execution files retain their original `scenario` / `image` method keys and `endpoint` vocabulary so their hashes remain valid. IAE is the primary downstream analysis; SAE is an independently evaluated comparison.

## Start here

Read the [workflow](docs/workflow.md), then the [decision cards](materials/annotation/cards/). The complete prompts are in `materials/annotation/`; the paper's shortened prompt displays are editorial summaries.

Verify the packaged files using Python 3:

```sh
python3 scripts/verify_manifest.py
```

Calculate scores from four-state counts using the standard library:

```sh
python3 scripts/score.py examples/counts.csv
python3 scripts/score.py analysis/profiles.csv --check
```

To regenerate numerical tables from frozen votes:

```sh
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 analysis/reproduce_numeric.py
```

The replay writes to `analysis/recomputed/` and preserves reference inputs. It recomputes profiles, paired effects, refinement comparisons, coverage and verifier sensitivities, including the joint 5,000-replicate source-scenario bootstrap. See [validation](docs/validation.md) for the completed replay checks. These calculations use saved votes; new generation and model annotation require the original API runner and credentials supplied outside this repository.

## Provenance and scope

`materials/manifest.json` records the 33 original material hashes and extraction steps. `RELEASE_MANIFEST.json` covers packaged source assets. Annotation prompts and schemas are byte-preserved; construction templates use the documented named-placeholder substitutions, with original source expressions retained alongside them.

The vote snapshot contains 68,764 completed image records across eight configurations and all recorded conditions. Main profile families use six configurations; bare FLUX.2 and HiDream remain refinement controls. The primary shared settings are English/Chinese crossed with no cue, US cue and China cue. This snapshot supplies binary automatic votes, not the full image dataset or full evidence responses.

Repository: [zucanlv/VisionValueBench](https://github.com/zucanlv/VisionValueBench). Paper citation, dataset link and licensing information will be added separately.
