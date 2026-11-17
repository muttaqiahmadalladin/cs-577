# External BEGIN aggregate artifact

`manifest.json` is an aggregate record of the offline import of Google's BEGIN dialogue-grounding benchmark (`google/BEGIN-dataset`, commit `6e65f0d5a1ed1b9574643a7640ff1678d4e979b5`), including pinned source SHA-256 hashes, exact dev/test overlap diagnostics, label distributions, and deterministic local export hashes. Raw TSVs and converted dialogue examples remain in ignored `sources/external/begin/` and `work/external_begin/`.

The local build validated **1,229 official development rows** and **11,059 official test rows** across `cmu-dog`, `topicalchat`, and `wow`, plus a frozen 12-item class-balanced development pilot (`4` each of `fully_attributable`, `not_fully_attributable`, and `generic`).

Rebuild with:

```sh
python3 scripts/begin_dataset.py fetch-build
python3 -m unittest discover -s tests -p 'test_begin_dataset.py' -v
```

See [validated dataset documentation](../../docs/research-followup/VALIDATED-DATASET.md) for how BEGIN (human-validated evidence attribution) and DOME (human-validated conversational dominance) complement each other.
