import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from voice_lab.audit_export import audit

SOURCE = Path(__file__).resolve().parents[2]/"voice-evaluation.json"


class ActualExportTests(unittest.TestCase):
    def test_actual_export_is_read_and_preserved(self):
        original = SOURCE.read_bytes()
        self.assertEqual(hashlib.sha256(original).hexdigest(), "003cadbb21918b998d0504807bc7ad24e40d6ac36dc0074160782572b0213ee5")
        with tempfile.TemporaryDirectory() as folder:
            report = audit(SOURCE, folder)
        self.assertEqual(report["record_count"], 9)
        self.assertEqual(report["sources"], {"manual": 9})
        self.assertEqual(report["real_asr_samples"], 0)
        self.assertEqual(report["confirmed_references"], 1)
        self.assertEqual(report["homophones_enabled"], 0)
        data = json.loads(original)
        self.assertEqual([r["original_record"] for r in report["records"]], data["records"])
        self.assertEqual(SOURCE.read_bytes(), original)
