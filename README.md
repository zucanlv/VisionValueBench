# VisionValueBench

Benchmark, construction and evaluation materials for studying visual value
leakage in multilingual text-to-image generation.

[Project homepage](https://zucanlv.github.io/VisionValueBench/) ·
[Paper PDF](https://zucanlv.github.io/VisionValueBench/paper.pdf) ·
[Dataset](https://huggingface.co/datasets/ZucanLyu/VisionValueBench)

VisionValueBench asks whether a text-to-image system renders a cultural value
orientation that the prompt did not specify. The release contains 2,773
scenarios derived from CDEval (960 in the evaluation set), the construction and
screening prompts, the six human-readable decision cards, the executed SAE/IAE
prompts and JSON schemas, frozen automatic votes for 68,764 image records,
numerical reproduction, and a runnable reference implementation of the
two-layer evaluation.

> Generated images are **not** redistributed in this repository. The
> [dataset](https://huggingface.co/datasets/ZucanLyu/VisionValueBench) hosts the
> benchmark scenarios; the frozen votes here support numerical replay without
> the image collection.

## Contents

| Path | Contents |
| --- | --- |
| `data/` | 2,773 retained scenarios with Chinese/Thai/Hindi translations and 14 rendered prompt conditions; 180 filtered scenarios; the 960 evaluation IDs |
| `materials/construction/` | Concept, scenario and translation prompts; language/country rendering templates; original template source excerpts |
| `materials/filtering/` | Fixed-orientation screening prompt and six-dimensional rubric |
| `materials/annotation/` | Four executed SAE/IAE proposal and verification prompts, JSON schemas, shared attribution rules and six decision cards |
| `materials/human/` | Human-readable decision cards and worked examples with six images |
| `evaluation/` | Reference SAE/IAE runner, OpenAI-compatible transport, offline mock demo, configs and tests |
| `analysis/` | Frozen automatic votes, sample metadata, reference tables and the standalone numerical replay script |
| `scripts/` | Count-to-score helper and release-file verification |
| `docs/workflow.md` | Inputs, outputs, pooling, voting and score definitions |
| `docs/release_scope.md` | What is included and what is outside the release |

The manuscript uses **Scenario-Anticipated Evaluation (SAE)** and
**Image-Adaptive Evaluation (IAE)**. Archived execution files retain their
original `scenario` / `image` method keys and `endpoint` vocabulary so their
hashes remain valid. IAE is the primary downstream analysis; SAE is an
independently evaluated comparison.

## Start here

Read the [workflow](docs/workflow.md), then the [decision cards](materials/annotation/cards/).
The complete prompts are in `materials/annotation/`; the paper's shortened
prompt displays are editorial summaries.

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

The replay writes to `analysis/recomputed/` and preserves reference inputs. It
recomputes profiles, paired effects, refinement comparisons, coverage and
verifier sensitivities, including the joint 5,000-replicate source-scenario
bootstrap. See [validation](docs/validation.md) for the completed replay
checks.

## Reference evaluation

`evaluation/` implements the two-layer protocol end to end: three proposers per
layer, content-hash candidate pooling, three independent verifiers, per-layer
majority and endpoint OR. The frozen prompts and schemas are read from
`materials/annotation/` and checked against `materials/manifest.json`.

Offline smoke test (no credentials, deterministic mock responses):

```sh
python3 evaluation/run_eval.py \
  --manifest evaluation/examples/manifest.jsonl \
  --out runs/smoke \
  --mock
python3 scripts/score.py runs/smoke/counts.csv
```

Prepare a run without calling a model:

```sh
python3 evaluation/run_eval.py \
  --manifest evaluation/examples/manifest.jsonl \
  --out runs/prepared
```

Real model calls need the OpenAI-compatible client and credentials named by the
config:

```sh
python3 -m pip install -r evaluation/requirements.txt
python3 evaluation/run_eval.py \
  --manifest path/to/manifest.jsonl \
  --out runs/my-eval \
  --config evaluation/configs/paper.json \
  --execute \
  --max-calls 2000
```

See [evaluation/README.md](evaluation/README.md) for the manifest format,
output files, cost warning and the exact scope of the reference runner.

## Data

`data/scenarios.jsonl` has one record per retained scenario with the source
CDEval item, concept, English scenario, three translations and all 14 rendered
prompts. `data/filtered_out.jsonl` records the 180 scenarios removed by
fixed-orientation screening, with the quoted evidence. `data/eval_960.txt` lists
the 960 evaluation-set IDs. The count derivation (2,953 → 2,773 → 960) and the
field descriptions are in [data/README.md](data/README.md).

The frozen vote snapshot in `analysis/votes.json.gz` contains 68,764 completed
image records across eight configurations and all recorded conditions. Main
profile families use six configurations; bare FLUX.2 and HiDream remain
refinement controls. The primary shared settings are English/Chinese crossed
with no cue, US cue and China cue. This snapshot supplies binary automatic
votes, not the full image dataset or full evidence responses.

## Provenance and scope

`materials/manifest.json` records the 33 original material hashes and extraction
steps. `RELEASE_MANIFEST.json` covers packaged source assets. Annotation prompts
and schemas are byte-preserved; construction templates use the documented
named-placeholder substitutions, with original source expressions retained
alongside them.

The reference implementation in `evaluation/` covers evaluation end to end. The
internal production runner's provider-specific batch jobs, budget ledger,
human-review bundle exporter and operational deployment code are outside this
release. The original UI/annotation application and participant data are also
outside it.

## Citation

```bibtex
@misc{lyu2026visionvaluebench,
  title        = {Whose Values Are Generated? Measuring Visual Value Leakage in Multilingual Text-to-Image Generation},
  author       = {Lyu, Zucan and Yao, Binwei and Uppaal, Rheeya and Yao, Jing and Yi, Xiaoyuan and Hu, Junjie},
  year         = {2026},
  howpublished = {arXiv preprint},
  note         = {VisionValueBench. Code: https://github.com/zucanlv/VisionValueBench},
  url          = {https://github.com/zucanlv/VisionValueBench}
}
```

See [CITATION.cff](CITATION.cff) for the machine-readable entry.

## License

Code is released under the MIT License ([LICENSE](LICENSE)). Benchmark data and
prompts (`data/`, `materials/`, derived tables in `analysis/`) are released
under CC BY 4.0 ([LICENSE-DATA](LICENSE-DATA)). The scenario set is derived
from CDEval (Wang et al., 2023); please cite both. Paper text and figures are
copyright the authors.