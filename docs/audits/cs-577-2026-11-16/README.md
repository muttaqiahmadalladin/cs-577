# Independent research audit — 2026-11-16

Start with [AUDIT.md](AUDIT.md) for the consolidated findings and [NEXT-STEPS.md](NEXT-STEPS.md) for the staged research plan.

This package contains three independent AI reviews, their subsequent peer discussion, the offline reproduction record, and supporting verification artifacts. It audits commit [`2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa`](https://github.com/muttaqiahmadalladin/cs-577/tree/2e0af7fe7a1dd2be01503c9fa62e7ebdf9a7deaa). It adds documentation and audit helpers under `docs/`; the experiment implementation and published results remain unchanged.

## Review records

| Perspective | Independent review | Peer discussion |
| --- | --- | --- |
| Methodology and data | [Review](independent-methodology.md) | [Discussion](discussion-methodology.md) |
| Implementation | [Review](independent-implementation.md) | [Discussion](discussion-implementation.md) |
| Statistics | [Review](independent-statistics.md) | [Discussion](discussion-statistics.md) |

First-pass reports retain their initial severity ratings. The consolidated audit and discussion records contain the final calibrated ratings.

## Verification from this repository

Using Python with the repository's existing requirements installed, run from its root:

```sh
python3 docs/audits/cs-577-2026-11-16/implementation/checks.py .
python3 docs/audits/cs-577-2026-11-16/statistics/verify_statistics.py .
```

These read stored outputs and print JSON; they make no model calls. Compare their output with [implementation/verification.json](implementation/verification.json) and [statistics/verification.json](statistics/verification.json). The implementation helper accepts a repository path so the package works outside the original author's workspace.

For the full repository reproduction, use its documented `python3 scripts/reproduce.py` in a separate disposable copy: that command writes regenerated files. The audit's original execution passed all twelve steps and retained byte-identical copies of all 369 original tracked files.

## Historical evidence and provenance

- [reproduction.log](reproduction.log) and [reproduction-verification.json](reproduction-verification.json) record the original audited snapshot. The file count refers to that snapshot before this documentation package was added.
- [verify_reproduction.py](verify_reproduction.py) is the original coordinator's archival verifier. Its default paths intentionally refer to the two original local research checkouts; it is not the portable reproduction entry point above.
- [methodology-spot-check.json](methodology-spot-check.json) records the majority-mapping cross-check; the methodology review includes its executable recipe.
- [audit-evidence.html](audit-evidence.html) is the uncertainty chart source used in the audit conversation. Its colors inherit the host's theme variables.
- Original source package: [KrishMay05/nlp_research, commit 5f3f872](https://github.com/KrishMay05/nlp_research/tree/5f3f87242c5b6628222744041513132fe15b6abd/docs/audits/cs-577-2026-11-16). Historical paths in the reviews refer to that workspace. Scientific findings and original evidence have been preserved; this copy adds this index and adapts the consolidated replay instructions and implementation helper's source-root resolution.

No proposed methodological change has been implemented by importing this audit package.
