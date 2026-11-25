# Release scope

## Included in this release

- The full benchmark scenario set: 2,773 retained scenarios with Chinese, Thai
  and Hindi translations and 14 rendered prompt conditions, plus the 180
  scenarios removed by fixed-orientation screening and the 960 evaluation IDs.
- Full historical execution materials, with their original provenance manifest.
- Six illustrative human-review examples and cards; participant answers and
  identifiers are excluded.
- A reference implementation of the two-layer SAE/IAE evaluation: executed
  prompts and schemas, semantic validation, content-hash candidate pooling,
  short-ID blinding, per-layer majority, endpoint OR and four-state scoring.
- Frozen binary automatic-verifier votes and the numerical inputs needed by the
  standalone replay.
- The original numerical script with its 5,000-replicate bootstrap, plus a newly
  written standard-library score helper.
- Workflow, file integrity checks and explicit release boundaries.

## Reference implementation and the production runner

`evaluation/` is a runnable reference implementation, not the internal
production runner. It preserves the frozen `pooled-two-layer-v2.1` prompts,
schemas, validation rules, bank construction, majority rule and endpoint OR. It
uses one OpenAI-compatible transport so it can run against any compatible
endpoint.

The original production runner's provider-specific batch submission, budget
ledger, usage accounting, human-review bundle exporter and operational
deployment code are not included. The old CLI entry point was
`python -m scripts.data_generation.value.pooled_annotation.run`; it is
documented here as provenance, not as a runnable command in this release.

## Release boundaries

Generated images are not redistributed in this repository. The
[Hugging Face dataset](https://huggingface.co/datasets/ZucanLyu/VisionValueBench)
hosts the benchmark scenarios; the frozen automatic votes in `analysis/` allow
numerical replay without distributing the image collection. Full machine
evidence responses and the human-study database are outside this release.

## Release metadata

- Repository: [zucanlv/VisionValueBench](https://github.com/zucanlv/VisionValueBench)
- Dataset: [ZucanLyu/VisionValueBench](https://huggingface.co/datasets/ZucanLyu/VisionValueBench)
- Code license: MIT (`LICENSE`)
- Data and prompt license: CC BY 4.0 (`LICENSE-DATA`)
- Citation: `CITATION.cff` and `CITATION.bib`