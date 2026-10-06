# Validation

Checked on 2026-10-06 using Python 3 and NumPy 2.3.5. No image-generation or model-annotation calls were made.

- All 33 original material SHA-256 entries match the archived manifest.
- The four annotation prompts and their four schemas match the execution hashes in the saved v2.1 run metadata.
- The standalone numerical replay completes its 5,000-replicate bootstrap.
- Regenerated `profiles.csv` (96 rows), `paired_effects.csv` (1,512 rows), and `refinement.csv` (240 rows) match every reference CSV column exactly, including state counts, estimates, pointwise intervals and simultaneous bands.
- The new standard-library score helper checks all 96 profile rows. Independent rational-arithmetic checks and boundary checks cover A-only, B-only, Both, Neither, empty samples, invalid counts and undefined results.
- Prompt/workflow and selected release-file audits were independently reviewed.

`scripts/verify_manifest.py` verifies source-file integrity after copying or extraction. The replay checks frozen point estimates at runtime; interval-column comparison was also performed for this release. These checks validate the archived materials and numerical replay, not the missing generation/annotation API runner.
