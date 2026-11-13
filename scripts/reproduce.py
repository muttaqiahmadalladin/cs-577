#!/usr/bin/env python3
"""One command for the whole offline reproduction: sources -> dataset -> every number in the report.

  pip install -r requirements.txt
  python3 scripts/reproduce.py

Steps
  1. get_sources.py            download the five external inputs and verify their SHA-256
  2. build_dataset.py --check  rebuild the snippet set from the sources and compare it with data/ byte for byte
  3. build_dataset.py          write the work files used by the collection and analysis scripts
  4. convert_released_cache.py convert the released argument cache to JSON
  5. analyze.py --check        recompute every table and paired test and compare with the values in the report
  6. grounded_extension.py     Dung's grounded extension on the rebuilt snippets
  7. grounded_policy_search.py the 288-policy search with selection on held-out meetings
  8. data_differences.py       the per-snippet list of differences between the released file and the rebuilt set
  9. score_run.py --run glm_run   rescore the stored GLM-5.3 run and compare with results/glm_run/results.json
 10. grounded_policy_search.py --run glm_run   the 288-policy search over the GLM arguments
 11. qbaf.py                   gradual argumentation (QBAF) over the stored arguments, and the vote of direct answers

No step calls a model. Model outputs are read from results/. Exit status is non-zero if any step fails.
"""
import subprocess, sys
from pathlib import Path

S = Path(__file__).resolve().parent
STEPS = [["get_sources.py"], ["build_dataset.py", "--check"], ["build_dataset.py"], ["convert_released_cache.py"],
         ["analyze.py", "--check"], ["grounded_extension.py"], ["grounded_policy_search.py"], ["data_differences.py"],
         ["score_run.py", "--run", "glm_run", "--name", "glm-5.3"], ["grounded_policy_search.py", "--run", "glm_run"], ["qbaf.py"]]
for i, step in enumerate(STEPS, 1):
    print(f"\n=== step {i} of {len(STEPS)}: {' '.join(step)} ===", flush=True)
    if subprocess.run([sys.executable, str(S / step[0]), *step[1:]], cwd=S).returncode: sys.exit(f"step {i} failed")
print("\nAll steps passed.")
