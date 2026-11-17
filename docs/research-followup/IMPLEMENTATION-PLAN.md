# Audit follow-up implementation plan

> For agentic workers: use the subagent-driven implementation and verification workflow. The user authorized executing the existing next-step plan and pushing this branch without merging.

**Goal:** Complete the report/evaluation repairs, prepare and execute feasible clean-data follow-up work, and make remaining human dependencies concrete.

**Architecture:** Preserve the original stored-answer reproduction and its historical results. Add a separately labeled post-audit evaluation with deterministic decisions, prediction-level provenance, clustered uncertainty and structural baselines. Build a source-aligned clean-data study with blinded annotation inputs and explicit gates for independent humans and fresh-speaker confirmation.

**Tech stack:** Existing Python/numpy/PuLP/CBC, standard-library unittest, LaTeX/Tectonic and existing stored JSON outputs.

**Spec:** `docs/audits/cs-577-2026-11-16/NEXT-STEPS.md`.

## Constraints

- Work only on `audit/independent-research-review-2026-11-16`; push to the existing draft PR; never merge.
- Preserve historical collection outputs, original audit records and the original sixty asserted values.
- New analyses explicitly identify their own formulas, deterministic tie policy and exploratory status.
- No fabricated human annotations, unknown model versions, prospective holdout claims, or new empirical results without actual execution.
- Never expose API keys; API qualification is separate from spending on a full collection.
- Existing source-level reproduction remains runnable. New behavior receives focused regression tests, followed by full integration verification.

## Review focus

1. Equal objectives and floating-point quantization must yield an explicit deterministic result without silently rewriting historical tables.
2. Missing/duplicate/mismatched IDs and score/argument banks must fail validation rather than contaminate comparisons.
3. Meeting resampling, speaker membership and overlapping windows must preserve paired observations and honest generalization claims.
4. Annotation exports must hide role/model predictions and keep labels independently attributable to two human annotators.
5. Missing credentials, unsupported models, failed requests and incomplete annotations must remain explicit blockers with no invented outputs.

## Owned tasks and acceptance

### Task 1: report repair

Owner: report worker. Files: `README.md`, `docs/DATA.md`, `docs/EXPERIMENTS.md`, `docs/REPRODUCE.md`, `report/report.tex`, plus worker notes under `docs/research-followup/`.

- [x] Correct majority-speaker explanation while preserving valid conditional counts.
- [x] Add the invariant128 attribution sensitivity, scoped graph null language, role/proxy and judge-instability wording.
- [x] Document inherited similarity redundancy and strongest-survivor reduction precisely.
- [x] Reconcile current twelve-step runner and historical versus new evaluation; do not overwrite original table values from an unrun method.
- [x] Check all numeric changes against committed evidence; parent compiles PDF after integration.

### Task 2: evaluation implementation

Owner: evaluation worker. Files: new `scripts/post_audit_evaluation.py`, optional focused helper modules, `tests/test_post_audit_evaluation.py`, and new `results/post_audit/` outputs. No edits to historical result files or collection scripts.

- [x] Write failing behavioral tests for deterministic ties, conditional objectives, input alignment and paired cluster intervals.
- [x] Implement separate deterministic evaluation; match historical primary full-graph predictions, report the tie-sensitive ablation explicitly.
- [x] Export per-example decisions/objectives, plain sum/strongest-survivor baselines, separate similarity/contradiction diagnostics and clustered graph/judge comparisons.
- [x] Produce evaluation/input hashes, model/formula metadata with missing versions left unknown, and a report-value provenance map.
- [x] Run generated outputs and focused tests, then make rerun commands explicit.

### Task 3: clean-data study preparation and external validated datasets

Owner: study and external-data workers. Files: `scripts/clean_quote_study.py`, `scripts/dome_dataset.py`, `scripts/begin_dataset.py`, `tests/test_clean_quote_study.py`, `tests/test_dome_dataset.py`, `tests/test_begin_dataset.py`, `data/clean_quote_study/`, `results/external_dome/`, `results/external_begin/`, `results/external_evidence/`, `docs/research-followup/`.

- [x] Test and validate same-span transcript/argument/score alignment and provenance; use a fixed clean bank, with no old malformed-text annotations.
- [x] Generate deterministic stratified blinded annotation worksheets for two independent humans and a separate private answer key under ignored `work/`.
- [x] Implement validation/reporting for uncertainty, agreement, false rejection/acceptance and completion state without treating proxy labels as human.
- [x] Freeze exploratory primary filter/uncertainty policy and generate paired filter-off/on inputs/evaluation that holds every other factor fixed.
- [x] Assess actual fresh-meeting/speaker availability from corpus metadata. Reject unsupported speaker-disjoint confirmation; do not force a misleading split.
- [x] Prepare matched role/power, letter-swap, repeated judge-order and context-control request designs with no model calls by the worker.
- [x] Import and validate external human-labeled benchmarks (`scripts/dome_dataset.py` for DOME + AMI conversational dominance; `scripts/begin_dataset.py` for Google BEGIN dialogue evidence attribution) with pinned source SHA-256 checks and unit/integration tests.

### Task 4: coordinator integration, review and publication

- [x] Qualify existing model access without logging credentials; run feasible new calls only with a clear request bound and valid access.
- [x] Make any required human action concrete: exact file or portal, what to enter, and which result depends on it.
- [x] Run unittest suite, original full reproduction in a separate copy, new evaluation/study checks and Tectonic PDF build.
- [x] Independent final review; fix real blocking issues and verify fixes.
- [x] Record completed versus blocked gates and actual empirical results; update concise draft PR description; commit/push this branch.

## Coordinator decisions

- Preserve the current historical CBC evaluation; the post-audit deterministic policy is a separately named evaluation. Cost if wrong: readers may need an additional table, but historical results remain reproducible.
- Never treat a retrospective split of the already inspected151 examples as fresh confirmation. Fresh speaker availability is measured before selecting a new test set.
- Missing independent human judgments or funded model access blocks the affected empirical conclusion, not report repairs, offline evaluation or preparation.
