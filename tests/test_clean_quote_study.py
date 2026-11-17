"""Behavioral gates for the exploratory clean-transcript quote study."""
import copy
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import clean_quote_study as study


def fixture():
    data = [{"id": "0", "meeting": "M0", "start_time": 1.0,
             "speakers": {"A": "p1", "B": "p2"}, "professor": "B",
             "turns_same_span": [{"speaker": "A", "text": "Let us test this."},
                                 {"speaker": "B", "text": "Yes, please test it."}]}]
    aspects = {a: {"reasons": {s: [f"{s} claim {i}" for i in range(3)] for s in "AB"},
                   "rebuttals": {s: [f"answer {s} claim {i}" for i in range(3)] for s in "AB"}}
               for a in study.ASPECTS}
    args = [{"id": "0", "aspects": aspects, "run_fingerprint": "pinned"}]
    scores = [{"id": "0", "answers": {k: .5 for k in study.expected_score_keys()},
               "run_fingerprint": "pinned"}]
    return data, args, scores, {"run_fingerprint": "pinned"}


class AlignmentTests(unittest.TestCase):
    def test_context_digest_pins_exact_fixed_records_not_file_formatting(self):
        rows = [{"id": "0", "cond": "fixed", "state": {"turns": []}}]
        self.assertEqual(study.context_digest(rows), study.context_digest(json.loads(json.dumps(rows, indent=2))))
        changed = copy.deepcopy(rows)
        changed[0]["state"]["turns"] = [{"speaker": "B", "text": "Changed"}]
        self.assertNotEqual(study.context_digest(rows), study.context_digest(changed))

    def test_normalizes_all_arguments_and_crosswalk(self):
        data, args, scores, manifest = fixture()
        rows, crosswalk = study.validate_banks(data, args, scores, manifest)
        self.assertEqual(len(rows), 48)
        self.assertEqual(crosswalk[0]["professor_participant"], "p2")
        r = next(r for r in rows if r["kind"] == "rebuttal" and r["target_side"] == "A")
        self.assertEqual(r["intended_side"], "B")
        self.assertIn("A claim", r["paired_reason"])

    def test_duplicate_ids_and_missing_score_ids_fail(self):
        d, a, s, m = fixture()
        with self.assertRaisesRegex(ValueError, "duplicate"):
            study.validate_banks(d + d, a, s, m)
        with self.assertRaisesRegex(ValueError, "IDs"):
            study.validate_banks(d, a, [], m)

    def test_mismatched_fingerprint_and_probabilities_fail(self):
        d, a, s, m = fixture()
        s[0]["run_fingerprint"] = "other"
        with self.assertRaisesRegex(ValueError, "fingerprint"):
            study.validate_banks(d, a, s, m)
        s[0]["run_fingerprint"] = "pinned"
        s[0]["answers"][next(iter(s[0]["answers"]))] = float("nan")
        with self.assertRaisesRegex(ValueError, "probability"):
            study.validate_banks(d, a, s, m)

    def test_nonbijective_participants_and_extra_score_key_fail(self):
        d, a, s, m = fixture()
        d[0]["speakers"]["B"] = "p1"
        with self.assertRaisesRegex(ValueError, "bijective"):
            study.validate_banks(d, a, s, m)
        d[0]["speakers"]["B"] = "p2"
        s[0]["answers"]["surprise"] = .5
        with self.assertRaisesRegex(ValueError, "168"):
            study.validate_banks(d, a, s, m)

    def test_blind_view_excludes_label_model_and_notes(self):
        d, a, s, m = fixture()
        d[0].update(gold="B", notes="professor is B", model_prediction="B")
        rows, _ = study.validate_banks(d, a, s, m)
        blind = study.blind_row(rows[0], d[0])
        self.assertEqual(blind["quote_present"], "")
        self.assertEqual(blind["should_keep"], "")
        for forbidden in ("gold", "professor", "model", "notes", "prediction", "participant"):
            self.assertFalse(any(forbidden in key for key in blind))
        self.assertNotIn("p1", json.dumps(blind))

    def test_stratified_sample_is_reproducible_and_balanced(self):
        d, a, s, m = fixture()
        rows, _ = study.validate_banks(d, a, s, m)
        more = [dict(r, argument_id=r["argument_id"].replace("0|", "1|", 1), snippet_id="1") for r in rows]
        sampled = study.stratified_sample(rows + more, 32)
        self.assertEqual(sampled, study.stratified_sample(list(reversed(rows + more)), 32))
        counts = {}
        for r in sampled:
            k = (r["aspect"], r["kind"], r["intended_side"])
            counts[k] = counts.get(k, 0) + 1
        self.assertEqual(set(counts.values()), {2})


class AnnotationTests(unittest.TestCase):
    def setUp(self):
        d, a, s, m = fixture()
        self.data = d[0]
        self.rows = study.validate_banks(d, a, s, m)[0]
        self.row = study.blind_row(self.rows[0], self.data)

    def completed(self, **updates):
        r = dict(self.row, quote="Let us test this.", quote_speaker="A", quote_present="yes",
                 attribution_correct="yes", claim_supported="yes", should_keep="yes",
                 rebuttal_answers_reason="uncertain", annotator_id="human-1", annotator_type="human")
        r.update(updates)
        return r

    def test_empty_worksheets_are_incomplete_and_proxy_is_rejected(self):
        report = study.annotation_report([self.row], [self.row])
        self.assertFalse(report["ready_for_human_conclusion"])
        self.assertEqual(report["first_complete"], 0)
        with self.assertRaisesRegex(ValueError, "human"):
            study.annotation_report([self.completed(annotator_type="assistant_proxy")], [self.completed(annotator_id="human-2")])

    def test_same_annotator_is_not_independent_and_uncertain_is_separate(self):
        first = self.completed(claim_supported="uncertain", should_keep="uncertain")
        with self.assertRaisesRegex(ValueError, "independent"):
            study.annotation_report([first], [first])
        second = self.completed(annotator_id="human-2", claim_supported="uncertain", should_keep="uncertain")
        report = study.annotation_report([first], [second])
        self.assertEqual(report["fields"]["should_keep"]["uncertain_pairs"], 1)
        self.assertEqual(report["fields"]["should_keep"]["binary_pairs"], 0)

    def test_wrong_speaker_and_empty_quote_cannot_be_accepted(self):
        row = self.completed(quote_speaker="B")
        self.assertFalse(study.strict_keep(row, self.data["turns_same_span"]))
        self.assertFalse(study.strict_keep(self.completed(quote=""), self.data["turns_same_span"]))
        self.assertTrue(study.strict_keep(self.completed(), self.data["turns_same_span"]))
        self.assertFalse(study.strict_keep(self.completed(claim_supported="uncertain"), self.data["turns_same_span"]))

    def test_machine_answer_must_cover_exact_ids_and_ground_accepted_quotes(self):
        answer = self.completed()
        study.validate_quote_answers([answer], [self.row], self.data["turns_same_span"])
        with self.assertRaisesRegex(ValueError, "duplicate|IDs"):
            study.validate_quote_answers([answer, answer], [self.row], self.data["turns_same_span"])
        with self.assertRaisesRegex(ValueError, "quote"):
            study.validate_quote_answers([dict(answer, quote="invented")], [self.row], self.data["turns_same_span"])

    def test_changed_claim_cannot_reuse_an_argument_id(self):
        with self.assertRaisesRegex(ValueError, "immutable"):
            study.validate_quote_answers([self.completed(claim="a different argument")], [self.row], self.data["turns_same_span"])

    def test_prepare_cannot_overwrite_entered_human_judgments(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "annotator.csv"
            study.write_csv(path, [self.completed()])
            original = path.read_bytes()
            with self.assertRaisesRegex(ValueError, "refusing"):
                study.write_csv(path, [self.row])
            self.assertEqual(path.read_bytes(), original)

    def test_reading_editor_padded_csv_preserves_source_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "formatted.csv"
            path.write_text('argument_id    , claim        , quote_present\ncase-1         , a claim      , uncertain\n')
            before = path.read_bytes()
            row = study.read_annotations(path)[0]
            self.assertEqual(row["argument_id"], "case-1")
            self.assertEqual(row["claim"], "a claim")
            self.assertEqual(row["quote_present"], "uncertain")
            self.assertEqual(path.read_bytes(), before)

    def test_agreement_refuses_changed_claim_or_transcript(self):
        first = self.completed()
        for changed in ({"claim": "different claim"}, {"kind": "rebuttal"},
                        {"transcript_json": '[{"speaker":"B","text":"different"}]'}):
            with self.assertRaisesRegex(ValueError, "immutable"):
                study.annotation_report([first], [self.completed(annotator_id="human-2", **changed)])

    def test_agreement_checks_canonical_case_and_checker_identity(self):
        first, second = self.completed(), self.completed(annotator_id="human-2")
        with self.assertRaisesRegex(ValueError, "immutable"):
            study.annotation_report([first], [second], [dict(first, claim="different claim", annotator_type="model")])
        with self.assertRaisesRegex(ValueError, "immutable"):
            study.annotation_report([first], [second], canonical=[dict(self.row, claim="canonical different")])

    def test_agreement_refuses_human_quote_on_wrong_speaker(self):
        with self.assertRaisesRegex(ValueError, "quote"):
            study.annotation_report([self.completed(quote_speaker="B")], [self.completed(annotator_id="human-2")])

    def test_completed_human_reason_allows_blank_rebuttal_answer(self):
        row = self.completed(rebuttal_answers_reason="")
        self.assertTrue(study.annotation_complete(row))
        study.validate_quote_answers([row], [self.row], self.data["turns_same_span"], allow_reason_blank=True)

    def test_checker_can_pin_transcript_by_hash_without_leaking_it_again(self):
        checker = self.completed(annotator_type="model")
        checker.pop("transcript_json")
        checker["transcript_sha256"] = study.object_hash(self.data["turns_same_span"])
        report = study.annotation_report([self.completed()], [self.completed(annotator_id="human-2")], [checker], canonical=[self.row])
        self.assertEqual(report["first_checker_errors"]["compared"], 1)

    def test_truncating_both_worksheets_does_not_complete_frozen_packet(self):
        with self.assertRaisesRegex(ValueError, "packet"):
            study.annotation_report([self.completed()], [self.completed(annotator_id="human-2")],
                                    expected_ids={self.row["argument_id"], "another-frozen-case"})

    def test_human_holistic_disagreement_does_not_make_annotation_invalid(self):
        row = self.completed(claim_supported="uncertain", should_keep="yes")
        study.validate_quote_answers([row], [self.row], self.data["turns_same_span"], enforce_strict_keep=False)
        self.assertFalse(study.strict_keep(row, self.data["turns_same_span"]))


class CollectionTests(unittest.TestCase):
    def test_inference_rejects_changed_human_transcript_before_solving(self):
        d, a, s, m = fixture()
        rows, crosswalk = study.validate_banks(d, a, s, m)
        annotations = [dict(study.blind_row(r, d[0]), annotator_id="human-test", annotator_type="human",
                            quote="Let us test this.", quote_speaker="A", quote_present="yes", attribution_correct="yes",
                            claim_supported="yes", rebuttal_answers_reason="yes", should_keep="yes") for r in rows]
        annotations[0]["transcript_json"] = '[{"speaker":"B","text":"edited transcript"}]'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "annotations.jsonl"
            study.write_jsonl(path, annotations)
            args = SimpleNamespace(annotations=str(path), source="human", out=str(Path(tmp) / "output"))
            with patch.object(study, "load_inputs", return_value=(d, rows, crosswalk, s, m, {})):
                with self.assertRaisesRegex(ValueError, "immutable"):
                    study.evaluate(args)

    def test_failed_billed_answer_is_accounted_and_quarantined_not_cached(self):
        d, a, s, m = fixture()
        rows, crosswalk = study.validate_banks(d, a, s, m)
        invalid_response = {"id": "billed-failure", "model": "exact-model", "usage": {"cost": .05, "total_tokens": 100},
                            "choices": [{"finish_reason": "stop", "message": {"content": '{"annotations": []}'}}]}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "pilot"
            args = SimpleNamespace(ids="0", max_requests=1, model="exact-model", base_url="https://provider.invalid/v1",
                                   api_key_env="TEST_QUOTE_KEY", execute=True, max_cost_usd=.1, max_tokens=1000,
                                   timeout=1, out=str(out))
            with patch.object(study, "ROOT", Path(tmp)), patch.object(study, "load_inputs", return_value=(d, rows, crosswalk, s, m, {})), \
                 patch.object(study, "stratified_sample", return_value=rows), patch.dict(study.os.environ, {"TEST_QUOTE_KEY": "never-print-me"}), \
                 patch.object(study.urllib.request, "urlopen", return_value=io.BytesIO(json.dumps(invalid_response).encode())):
                with self.assertRaisesRegex(ValueError, "not accepted or cached"):
                    study.collect(args)
            report = json.loads((out / "collection_manifest.json").read_text())
            self.assertEqual(report["actual_usd_reported"], .05)
            self.assertEqual(report["failed_requests"][0]["response_id"], "billed-failure")
            self.assertTrue(list((Path(tmp) / "work/clean_quote_study/quarantine").glob("*.json")))
            self.assertFalse(list((Path(tmp) / "work/clean_quote_study/quote_cache").glob("*.json")))
            self.assertNotIn("never-print-me", (out / "collection_manifest.json").read_text())

    def test_overlapping_and_seen_speaker_candidates_rejected(self):
        candidate = {"meeting": "new", "start_segment": 10, "end_segment": 30,
                     "participants": ["newprof", "newperson"]}
        self.assertTrue(study.check_candidate(candidate, {"old"}, {"oldperson"}, []))
        self.assertFalse(study.check_candidate(candidate, {"old"}, {"newprof"}, []))
        self.assertFalse(study.check_candidate(candidate, {"old"}, set(),
                                              [dict(candidate, start_segment=29, end_segment=40)]))


if __name__ == "__main__":
    unittest.main()
