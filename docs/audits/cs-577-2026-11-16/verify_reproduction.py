"""Record offline reproduction evidence without changing the audited checkout."""
import hashlib
import json
import subprocess
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[3]
AUDIT = Path(__file__).resolve().parent
SOURCE = PROJECT / "data/audit-sources/cs-577-2026-11-16"
REPRO = PROJECT / "data/audit-sources/cs-577-2026-11-16-reproduction"


def git(*args):
    return subprocess.check_output(["git", *args], cwd=SOURCE, text=True).strip()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    log = (AUDIT / "reproduction.log").read_text()
    files = git("ls-files").splitlines()
    changed = []
    for name in files:
        original, rerun = SOURCE / name, REPRO / name
        if not rerun.exists() or original.read_bytes() != rerun.read_bytes():
            semantic_equal = False
            if rerun.exists() and original.suffix == ".json":
                semantic_equal = json.loads(original.read_text()) == json.loads(rerun.read_text())
            changed.append({"path": name, "json_semantically_equal": semantic_equal})
    evidence = {
        "repository": "https://github.com/muttaqiahmadalladin/cs-577",
        "commit": git("rev-parse", "HEAD"),
        "date": "2026-11-16",
        "source_checkout_clean": not git("status", "--porcelain"),
        "reproduction_command": "<nlp_research>/.venv/bin/python scripts/reproduce.py",
        "reproduction_directory": str(REPRO),
        "reproduction_log_sha256": digest(AUDIT / "reproduction.log"),
        "completed_steps": log.count("=== step "),
        "all_steps_passed": log.rstrip().endswith("All steps passed."),
        "report_check_passed": "check: 60 of 60 report values reproduced" in log,
        "rebuilt_dataset_exact": "committed dataset reproduced exactly" in log,
        "tracked_file_count": len(files),
        "tracked_files_changed_by_reproduction": changed,
        "input_sha256": {p.name: digest(p) for p in sorted((REPRO / "sources").iterdir()) if p.is_file()},
        "qualification": "Replays stored outputs; does not establish hosted-model regenerability or that every written claim is covered by assertions.",
    }
    assert evidence["source_checkout_clean"]
    assert evidence["all_steps_passed"] and evidence["completed_steps"] == 12
    assert evidence["report_check_passed"] and evidence["rebuilt_dataset_exact"]
    (AUDIT / "reproduction-verification.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
