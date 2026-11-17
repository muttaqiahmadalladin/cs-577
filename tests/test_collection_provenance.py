import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import score_run
import wu_codex_pipeline


class CollectionProvenanceTests(unittest.TestCase):
    def test_template_loader_works_without_historical_checkout_and_caches(self):
        def response(request, **kwargs):
            url = request.full_url
            self.assertIn("fed11b69765b4a398ce4a985adedfb65ec3098ab/", url)
            text = "definition = {'style': 'test definition'}\n\n" if url.endswith("prompts.py") else "pinned template"
            return io.BytesIO(text.encode())
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "run"
            with patch.object(wu_codex_pipeline, "OUT", out), patch.object(wu_codex_pipeline.urllib.request, "urlopen", side_effect=response) as request:
                templates = wu_codex_pipeline.load_templates()
                self.assertEqual(templates["definition"], {"style": "test definition"})
                self.assertEqual(set(templates), set(wu_codex_pipeline.TEMPLATES) | {"definition"})
                self.assertTrue((out / "templates.json").is_file())
                self.assertEqual(request.call_count, len(wu_codex_pipeline.TEMPLATES) + 1)
                request.reset_mock()
                self.assertEqual(wu_codex_pipeline.load_templates(), templates)
                request.assert_not_called()

    def test_export_preserves_recorded_model_and_usage(self):
        record = {"id": "7", "answers": {"a": 0.5}, "model": "jev-1.14.0", "usage": {"tokens": 9}, "run_fingerprint": "abc"}
        exported = score_run.export_jev_record("7", record)
        self.assertEqual(exported, record)
        self.assertEqual(record["model"], "jev-1.14.0")

    def test_export_does_not_invent_missing_model(self):
        exported = score_run.export_jev_record("7", {"id": "7", "answers": {"a": 0.5}})
        self.assertNotIn("model", exported)

    def test_export_rejects_misaligned_metadata(self):
        with self.assertRaises(ValueError):
            score_run.export_jev_record("7", {"id": "8", "answers": {"a": 0.5}, "model": "wrong"})


if __name__ == "__main__":
    unittest.main()
