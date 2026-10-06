# Frozen automatic-vote numerical replay

Run `python analysis/reproduce_numeric.py` from the repository root after installing NumPy. Outputs are written to `analysis/recomputed/`.

The script and its seven required inputs/protocol files are copied unchanged from the saved numerical appendix. `profiles.csv` was also checked byte-for-byte against the current appendix's archived profile table. This subset excludes human-study response records and old manuscript drafts.

| File | Purpose |
| --- | --- |
| `votes.json.gz` | Binary automatic votes for 68,764 completed image records, retaining method/verifier order |
| `scenario_screening.json` | Source-scenario sampling metadata, including the final 960 IDs |
| `profiles.csv` | Frozen eight-configuration reference profiles; six main configurations and two controls |
| `paired_effects.csv` | Frozen paired language/cue comparisons and arm counts |
| `refinement.csv` | Frozen refinement comparisons and interactions |
| `analysis_protocol.json` | Original vote digest, sampling unit, bootstrap seed and family definitions |
| `reproduce_numeric.py` | Original independent numerical replay; requires NumPy |

The replay asserts point estimates against the frozen tables. Release validation also compares regenerated state counts and interval columns. It preserves the historical internal keys `scenario` (SAE) and `image` (IAE).
