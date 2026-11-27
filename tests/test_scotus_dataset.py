"""Unit and data-integrity tests for the SCOTUS OT2026 post-cutoff dataset and perturbation/metrics tools."""
import json, re, unittest
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build_scotus_dataset as b
import perturb_and_metrics as pm


class TestScotusDataset(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        out = ROOT / "data" / "scotus_ot2026"
        cls.man = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        cls.raw = [json.loads(l) for l in (out / "snippets_raw.jsonl").read_text(encoding="utf-8").splitlines()]
        cls.masked = [json.loads(l) for l in (out / "snippets_masked.jsonl").read_text(encoding="utf-8").splitlines()]

    def test_post_cutoff_dates(self):
        for r in self.raw:
            self.assertGreaterEqual(r["argument_date"], "2026-10-01")

    def test_counts_and_balance(self):
        self.assertEqual(len(self.raw), 333)
        self.assertEqual(len(self.masked), 333)
        a_count = sum(r["professor"] == "A" for r in self.masked)
        self.assertEqual(a_count, 166)

    def test_non_overlapping_same_span_within_case(self):
        by_case = {}
        for r in self.raw:
            by_case.setdefault(r["meeting"], []).append(tuple(r["turn_index"]))
        for docket, spans in by_case.items():
            spans.sort()
            for (a, b_), (c, d) in zip(spans, spans[1:]):
                self.assertLessEqual(b_, c, f"overlapping spans in {docket}: {(a, b_)} vs {(c, d)}")

    def test_case_and_advocate_disjoint_splits(self):
        dev_cases = {r["meeting"] for r in self.raw if r["split"] == "dev"}
        test_cases = {r["meeting"] for r in self.raw if r["split"] == "test"}
        self.assertFalse(dev_cases & test_cases)
        dev_adv = {b.surname_of(n) for d in dev_cases for n in self.man["cases"][d]["advocates_from_appearances"]}
        test_adv = {b.surname_of(n) for d in test_cases for n in self.man["cases"][d]["advocates_from_appearances"]}
        self.assertFalse(dev_adv & test_adv, f"shared advocates across split: {dev_adv & test_adv}")

    def test_focal_only_turns_and_label_consistency(self):
        for r, m in zip(self.raw, self.masked):
            self.assertEqual(r["id"], m["id"])
            self.assertEqual(r["professor"], m["professor"])
            self.assertEqual(r["roles"][r["professor"]], "justice")
            self.assertEqual(r["roles"][pm.swap_ab(r["professor"])], "advocate")
            for w in ("turns_same_span", "turns_pm15", "turns_pm60"):
                self.assertTrue(all(t["speaker"] in ("A", "B") for t in m[w]))
                self.assertGreaterEqual(len(m[w]), 4)

    def test_zero_role_and_surname_leaks_in_masked(self):
        for scope in ("same_span", "all_windows"):
            for k, v in self.man["leak_check_masked"][scope].items():
                self.assertEqual(v, 0, f"leak in {scope}.{k}: {v}")

    def test_perturbations_preserve_turns_and_swap_flips_gold(self):
        s = self.masked[0]
        for kind in pm.PERTURBATIONS:
            p = pm.perturb_snippet(s, kind)
            self.assertEqual(len(p["turns_same_span"]), len(s["turns_same_span"]))
            if kind == "no_commas":
                self.assertTrue(all("," not in t["text"] for t in p["turns_same_span"]))
            if kind == "letter_swap":
                self.assertNotEqual(p["professor"], s["professor"])

    def test_two_class_metrics(self):
        m = pm.classification_metrics([("A", "A"), ("A", "A"), ("A", "B"), ("B", "A")])
        self.assertAlmostEqual(m["accuracy"], 0.5)
        self.assertAlmostEqual(m["class_A"]["precision"], 2 / 3)
        self.assertAlmostEqual(m["class_A"]["recall"], 2 / 3)
        self.assertAlmostEqual(m["class_B"]["recall"], 0.0)

    def test_nous_eval_30_arms_and_report_numbers(self):
        summary_path = ROOT / "results" / "nous_eval" / "summary.json"
        self.assertTrue(summary_path.exists())
        s = json.loads(summary_path.read_text(encoding="utf-8"))
        self.assertEqual(set(s["models"].keys()), {"gemma-4-26b", "llama-3.3-70b", "gpt-4o-mini"})
        for m in s["models"]:
            self.assertEqual(len(s["models"][m]["arms"]), 10)
        g_scotus = s["models"]["gemma-4-26b"]["arms"]["scotus_masked"]
        self.assertEqual(g_scotus["n"], 333)
        self.assertAlmostEqual(round(g_scotus["accuracy"] * 100, 1), 66.7)
        self.assertAlmostEqual(round(g_scotus["mcc"], 3), 0.336)
        self.assertAlmostEqual(round(g_scotus["dev"]["accuracy"] * 100, 1), 71.4)
        self.assertAlmostEqual(round(g_scotus["test"]["accuracy"] * 100, 1), 65.4)


if __name__ == "__main__":
    unittest.main()




