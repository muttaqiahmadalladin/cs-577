# External DOME aggregate artifact

`manifest.json` is an aggregate record of the actual offline import, including pinned official-source hashes and deterministic local export hashes. It contains no person-level rank labels or transcript copies.

The local build produced 58 diagnostic windows, 34 unanimous most-dominant windows and 102 counterbalanced focal pairs. The four-person lexical-coverage secondary subset has 30 windows/90 pairs. All 20 participants are separated into five connected meeting groups; train/dev/test use three/one/one groups.

Rebuild with `python3 scripts/dome_dataset.py fetch` then `python3 scripts/dome_dataset.py build`. Raw and converted data stay in ignored `sources/external/` and `work/external_dome/`. See [validated dataset documentation](../../docs/research-followup/VALIDATED-DATASET.md) for interpretation, split policy, source discrepancy, multimodal limitations and unresolved standalone DOME redistribution terms.
