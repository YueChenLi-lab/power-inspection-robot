from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
from voice_lab.server import VoiceLab
from voice_lab.metrics import aggregate,character_error,grouped_comparison
from inspection_brain.domain_v2.service import ElectricalBrainV2


class Round2ScoringTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.lab=VoiceLab(self.temp.name)
    def tearDown(self):self.lab.asr.close();self.temp.cleanup()
    def test_custom_reference_does_not_keep_wrong_question_id(self):
        row=self.lab.evaluate({"manual_transcript":"油温","reference_text":"油温","reference_confirmed":True,"question_id":"question-1"})
        self.assertEqual(row["question_id"],"")
        self.assertEqual(row["reference_binding"]["selected_question_id"],"question-1")
        self.assertEqual(row["reference_binding"]["status"],"custom_confirmed")
    def test_standard_binding_and_strict_cer(self):
        text="什么是局部放电？"
        row=self.lab.evaluate({"manual_transcript":text[:-1],"reference_text":text,"reference_confirmed":True,"question_id":"question-3"})
        self.assertEqual(row["question_id"],"question-3")
        self.assertEqual(row["metrics"]["before"]["characters"]["cer"],0)
        self.assertGreater(row["metrics"]["before"]["strict_characters"]["cer"],0)
        self.assertEqual(character_error("主变","主变压器",strict=True)["edits"],2)
    def test_sources_are_not_mixed_and_versions_grouped(self):
        for source in ("manual","windows_external"):
            row=self.lab.evaluate({"input_source":source,"manual_transcript":"什么是CT？","reference_text":"什么是电流互感器？","reference_confirmed":True})
            self.assertEqual(row["metrics"]["before"]["alias_equivalent_terms"]["recall"],1)
        result=aggregate(self.lab.records())
        self.assertEqual(result["asr"]["confirmed_runs"],0)
        self.assertEqual(result["windows_external"]["confirmed_runs"],1)
        self.assertEqual(len(grouped_comparison(self.lab.records())),2)
    def test_numeric_errors_not_hidden_by_term_score(self):
        row=self.lab.evaluate({"manual_transcript":"油温685℃，压力05赵帕，电压11000伏", "reference_text":"油温68.5℃，压力0.5MPa，电压110kV","reference_confirmed":True})
        metrics=row["metrics"]["before"]
        self.assertEqual(metrics["numeric_slots"]["accuracy"],0)
        self.assertEqual(metrics["numeric_slots"]["expected"],3)
        swapped=self.lab.evaluate({"manual_transcript":"油温82.3℃，绕组温度68.5℃","reference_text":"油温68.5℃，绕组温度82.3℃","reference_confirmed":True})
        self.assertEqual(swapped["metrics"]["before"]["numeric_slots"]["accuracy"],0)
    def test_import_preserves_history_and_excludes_unbound_old_metrics(self):
        source=Path(__file__).resolve().parents[2]/"voice-evaluation.json"
        self.assertEqual(self.lab.import_export(source),9)
        saved=self.lab.records()
        self.assertEqual(len(saved),9)
        self.assertEqual(aggregate(saved)["manual"]["confirmed_runs"],0)
        self.assertEqual(aggregate(saved)["legacy_records_excluded"],9)
        self.lab.import_export(source)
        self.assertEqual(self.lab.records(),saved)
        first=saved[0]
        fresh=self.lab.evaluate({"derived_from_record_id":first["record_id"],"manual_transcript":first["original_transcript"],"reference_text":first["reference_text"],"reference_confirmed":False})
        self.assertFalse(fresh["metrics"]["eligible"])
        self.assertEqual(len(self.lab.records()),10)
        original=json.loads(source.read_text())["records"]
        self.assertEqual({r['record_id']:r for r in saved},{r['record_id']:r for r in original})
    def test_complex_query_does_not_claim_complete_answer_from_one_keyword(self):
        source=Path(__file__).resolve().parents[2]/"voice-evaluation.json"
        raw=json.loads(source.read_text())["records"][5]["original_transcript"]
        answer=ElectricalBrainV2().ask(raw,apply_homophones=True)["result"]
        self.assertEqual(answer["status"],"undetermined")
        self.assertTrue(answer["missing_evidence"])
        self.assertIsNone(answer["site_conclusion"])
