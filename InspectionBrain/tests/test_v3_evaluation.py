from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from brain_v3.config import ProviderConfig
from brain_v3.engine import SemanticEngine
from brain_v3.evaluation import development_manifest, evaluate_result, runtime_summary, comparison_summary
from brain_v3.store import SemanticStore

NOW = datetime(2026, 10, 9, 4, tzinfo=timezone.utc)


class SemanticEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.engine = SemanticEngine(config=ProviderConfig(provider="mock"))
        self.text = "不是2号断路器，是3号断路器"
        self.result = self.engine.analyze(self.text, mode="v3_llm", now=NOW)
        # Handwritten independent synthetic relation annotation, not copied model output.
        self.gold = {"annotation_version":"semantic-gold-v1", "annotation_source":"handwritten_synthetic",
                     "confirmed":True, "annotator":"independent_safety_contract_fixture",
                     "original_sha256":hashlib.sha256(self.text.encode()).hexdigest(),
                     "expected":{"equipment_relations":[["circuit_breaker","2","negated",None],["circuit_breaker","3","active",None]],
                                 "self_corrections":[["equipment",[["circuit_breaker","2","negated"]],[["circuit_breaker","3","active"]]]]}}

    def test_independent_relation_annotation_v2_v3_comparison(self):
        metric = evaluate_result(self.result, self.gold)
        self.assertTrue(metric["eligible"])
        self.assertTrue(metric["v3"]["all_annotated_dimensions_exact"])
        self.assertFalse(metric["v2"]["all_annotated_dimensions_exact"])
        self.assertFalse(metric["asr_cer_improvement_claimed"])

    def test_no_gold_or_unconfirmed_or_asr_gold_cannot_score(self):
        for annotation in (None, {**self.gold,"confirmed":False}, {**self.gold,"annotation_source":"asr_output"}):
            with self.subTest(annotation=annotation):
                self.assertFalse(evaluate_result(self.result, annotation)["eligible"])
        self.assertFalse(evaluate_result(self.result, {**self.gold,"original_sha256":"wrong"})["eligible"])

    def test_idempotent_runs_and_audio_sha_dedup(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SemanticStore(directory, self.engine)
            audio = {"audio_id":"a1","sha256":"1"*64,"asr":{"model_id":"INT8","model_version":"2024-07-17"}}
            first = store.analyze(self.text, source="asr", audio=audio, mode="v3_llm", now=NOW)
            second = store.analyze(self.text, source="asr", audio=audio, mode="v3_llm", now=NOW)
            self.assertEqual(first["record_id"], second["record_id"])
            variant = store.analyze(self.text, source="asr", audio=audio, mode="v3_llm", now=NOW, apply_homophones=True)
            self.assertNotEqual(first["analysis_key"], variant["analysis_key"])
            store.analyze(self.text, source="asr", audio={**audio,"audio_id":"a2"}, mode="v3_llm", now=NOW)
            store.analyze(self.text, source="manual", mode="v3_llm", now=NOW)
            summary = store.export()["summary"]
            self.assertEqual(summary["analysis_run_count"],4)
            self.assertEqual(summary["unique_asr_audio_sha256_count"],1)
            self.assertEqual(summary["manual_run_count"],1)
            self.assertEqual(summary["mock_candidate_count"],4)
            self.assertIsNone(summary["semantic_accuracy"])
            self.assertIsNone(summary["real_llm_mean_inference_seconds"])
            self.assertFalse((Path(directory)/"records").exists())

    def test_history_manifest_is_pending_deduplicated_and_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory);(path/"audio").mkdir();(path/"records").mkdir()
            wav = b"distinct original audio bytes"; sha=hashlib.sha256(wav).hexdigest()
            for aid in ("a1","a2"):
                (path/"audio"/(aid+".wav")).write_bytes(wav)
                (path/"audio"/(aid+".json")).write_text(json.dumps({"audio_id":aid,"sha256":sha,"asr":{"status":"ok","engine":"sensevoice","text":self.text}}))
            old = {"record_id":"historic","audio":{"sha256":sha},"brain":{"analysis":{"lexicon_version":"electrical-v2.1"}}}
            p=path/"records/historic.json";p.write_text(json.dumps(old));before=p.read_bytes()
            manifest=development_manifest(path)
            self.assertEqual(manifest["unique_audio_sha256_count"],1)
            self.assertEqual(manifest["confirmed_semantic_gold_count"],0)
            sample=manifest["samples"][0]
            self.assertIsNone(sample["semantic_annotation"]["expected"])
            self.assertFalse(sample["semantic_annotation"]["confirmed"])
            self.assertEqual(sample["historical_lexicon_versions"],["electrical-v2.1"])
            self.assertEqual(p.read_bytes(),before)
            (path/"audio/a1.wav").write_bytes(b"corrupt")
            with self.assertRaises(ValueError):development_manifest(path)

    def test_schema_rate_and_fallback_rate_are_not_semantic_accuracy(self):
        r=SemanticEngine().analyze(self.text,mode="auto_fallback",now=NOW)
        summary=runtime_summary([{"result":r,"provenance":{"audio_sha256":"1"*64},"input_source":"asr"}])
        self.assertEqual(summary["fallback_success_count"],1)
        self.assertEqual(summary["candidate_count"],0)
        self.assertIsNone(summary["semantic_accuracy"])

    def test_handwritten_semantic_contracts_not_only_text_accuracy(self):
        data=json.loads((Path(__file__).with_name("v3_semantic_annotations.json")).read_text())
        for sample in data["samples"]:
            with self.subTest(sample=sample["sample_id"]):
                r=self.engine.analyze(sample["original_request"],mode="v3_llm",now=datetime.fromisoformat(sample["reference_time"]))
                self.assertTrue(r["validation"]["valid"],r["validation"])
                m=evaluate_result(r,sample["semantic_annotation"])
                self.assertTrue(m["eligible"])
                self.assertTrue(m["v3"]["all_annotated_dimensions_exact"],m)

    def test_comparison_deduplicates_audio_and_requires_gold_per_dimension(self):
        metrics=evaluate_result(self.result,self.gold)
        row={"sample_id":"first","dataset_role":"development","audio_sha256":"1"*64,"result":self.result,"metrics":metrics}
        groups=comparison_summary([row,{**row,"sample_id":"repeat"}])
        self.assertEqual(groups[0]["unique_development_samples"],1)
        self.assertEqual(groups[0]["confirmed_semantic_samples"],1)
        self.assertEqual(groups[0]["dimensions"]["v3"]["equipment_relations"]["exact_accuracy"],1)
        self.assertIsNone(groups[0]["dimensions"]["v3"]["intents"])
        self.assertEqual(groups[0]["real_llm_candidate_count"],0)
        row["metrics"]=evaluate_result(self.result,None)
        unscored=comparison_summary([row])[0]
        self.assertEqual(unscored["confirmed_semantic_samples"],0)
        self.assertTrue(all(v is None for v in unscored["dimensions"]["v3"].values()))

    def test_v2_existing_negation_condition_and_time_are_not_scored_as_absent(self):
        data=json.loads(Path(__file__).with_name("v3_semantic_annotations.json").read_text())
        for sample in data["samples"]:
            if sample["sample_id"] not in ("plan-no-navigation","conditional-advice","week-comparison","legitimate-two-assets"):
                continue
            with self.subTest(sample=sample["sample_id"]):
                r=self.engine.analyze(sample["original_request"],mode="v3_llm",now=datetime.fromisoformat(sample["reference_time"]))
                metrics=evaluate_result(r,sample["semantic_annotation"])
                self.assertTrue(metrics["v2"]["all_annotated_dimensions_exact"],metrics)


if __name__ == "__main__":unittest.main()
