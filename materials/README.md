# Full prompt and annotation materials

The paper presents **editorial summaries**, not replacement execution prompts. This archive preserves full templates, schemas, decision cards, filtering instructions, and human-review examples. No model calls were made when preparing it.

- `annotation/`: the four executed `pooled-two-layer-v2.1` prompt templates and JSON schemas. Original keys and terminology (including `endpoint`) remain unchanged. The four Markdown files were checked against the production-freeze digests recorded in the original appendix builder. All six decision cards are identical across the prompts and are also extracted under `annotation/cards/`. Proposal-stage shared-rule variants remain in their complete prompts.
- `construction/`: concept, scenario and translation templates including every few-shot example. Named placeholders replace Python interpolation expressions; source modules are included for the exact original template expressions. `rendering.json` contains the saved language wrappers and country labels.
- `filtering/`: the recorded fixed-orientation filtering template and all-six-dimension rubric. These document the automated filtering stage, not an independently executed review.
- `human/`: all six human-readable cards, worked examples and images, copied from the saved review interface materials. These files establish what the materials contained, not participant identities, study timing or completion.

`manifest.json` records per-file SHA-256 digests, source paths and extraction steps. Annotation prompts and schemas are byte-identical to their saved sources; card extraction normalizes only surrounding blank lines. Construction templates preserve the source text with the placeholder substitutions described above. The PDF uses the manuscript terms SAE/IAE and orientation; archived execution vocabulary is deliberately unchanged.

In the unmodified `human/examples.json`, `/local-dimension-examples/<DIM>.jpg` maps to `human/images/<DIM>.jpg` in this archive.

The archive does not contain API keys, participant responses, or private run configuration.
