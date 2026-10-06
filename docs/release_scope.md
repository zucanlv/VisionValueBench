# Release scope

## Included in this release

- Full historical execution materials, with their original provenance manifest.
- Six illustrative human-review examples and cards; participant answers and identifiers are excluded.
- Frozen binary automatic-verifier votes and the numerical inputs needed by the standalone replay.
- Original numerical script with its 5,000-replicate bootstrap, plus a newly written standard-library score helper.
- Workflow, file integrity checks and explicit release boundaries.

## Required for end-to-end execution

Recover the original `pooled-two-layer-v2.1` `run.py`, `core.py`, `batch.py`, semantic contracts/validators and model adapters from the project backup. Recover the source-data import, sampling/filtering executors, generation wrappers and sanitized configuration. The old CLI entry point was `python -m scripts.data_generation.value.pooled_annotation.run`; it is documented here as a recovery target, not as a runnable command in this candidate.

Validate those recovered pieces against the executed prompt/schema hashes and recorded run configurations. The core semantics to preserve are separate SAE/IAE candidate pools, canonical-text caching, exact-field deduplication, image-grounded verification, IAE additions, complete twelve-orientation output and independent majority voting. Include a small input/output example before advertising new API execution.

The four `materials/construction/source/*.py` files preserve original template expressions. Their imports refer to modules outside this archive. They are provenance excerpts, not a standalone construction package.

## Release boundaries

This repository contains frozen scientific materials and offline analysis. Operational deployment scripts, experiment history and human-study databases are outside its scope. Recover additional scientific modules using an explicit file list.

Dataset publication is separate: the original benchmark records, complete image collection and full machine evidence are not contained here. The supplied automatic votes allow numerical replay without distributing those larger assets.

## Release metadata

The repository is [zucanlv/VisionValueBench](https://github.com/zucanlv/VisionValueBench). Licensing information, the paper citation and the dataset link will be supplied by the authors separately.
