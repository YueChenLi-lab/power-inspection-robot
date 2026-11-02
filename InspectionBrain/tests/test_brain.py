from datetime import datetime
import ast
import contextlib
import io
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest

from inspection_brain.adapters import MockRegistry
from inspection_brain.evaluation import evaluate
from inspection_brain.hotwords import export_vosk_grammar
from inspection_brain.mission import OfflineDraftSink, build_draft
from inspection_brain.routing import LegacyDecision, MockLegacyDispatcher, OfflineRouter
from inspection_brain.service import DEFAULT_DATA, InspectionBrain
from inspection_brain.terminology import Lexicon

NOW = datetime.fromisoformat("2026-10-08T12:00:00+08:00")
ROOT = Path(__file__).resolve().parents[1]


class DomainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.brain = InspectionBrain()

    def ask(self, text, **kwargs):
        return self.brain.ask(text, now=NOW, **kwargs)

    def test_handwritten_golden_contracts(self):
        report = evaluate(ROOT/"tests/golden_cases.json", self.brain)
        for row in report["comparisons"]:
            with self.subTest(case=row["id"], text=row["raw_text"]):
                self.assertTrue(row["normalization_correct"], row)
                self.assertTrue(row["terms_correct"], row)
                self.assertTrue(row["entities_correct"], row)
                self.assertTrue(row["intent_correct"], row)
                self.assertTrue(row["status_correct"], row)
                self.assertTrue(row["route_correct"], row)
        self.assertEqual(report["failed_cases"], [])
        self.assertIsNone(report["asr_wer"])
        self.assertIsNone(report["asr_cer"])

    def test_distinct_equipment_types_never_alias(self):
        a = self.ask("电流互感器和电压互感器有什么区别？")["analysis"]
        self.assertEqual([e["equipment_category"] for e in a["device_entities"]],
                         ["current_transformer", "voltage_transformer"])
        a = self.ask("断路器和隔离开关有什么区别？")["analysis"]
        self.assertEqual(len({e["term_id"] for e in a["device_entities"]}), 2)

    def test_number_identity_never_repaired(self):
        for text in ("变压器温度70.3℃是否正常？", "01号变压器资料", "T-0001变压器资料"):
            with self.subTest(text=text):
                normalized = self.ask(text, apply_homophones=True)["analysis"]["normalization"]
                self.assertEqual(normalized["normalized_text"], text)
        a = self.ask("一号或二号主变型号")["analysis"]
        self.assertIsNone(a["device_entities"][0]["device_number"])
        self.assertTrue(a["uncertainties"])

    def test_homophone_entity_is_not_confirmed_identity(self):
        result = self.ask("一号变鸭器是什么？", apply_homophones=True)
        self.assertEqual(result["analysis"]["device_entities"], [])
        self.assertTrue(result["analysis"]["uncertainties"])
        self.assertFalse(result["analysis"]["normalization"]["authorization_granted"])

    def test_raw_operation_protected_even_with_correction_opt_in(self):
        for text in ("前进到一号主变", "不要合闸，解释局放", "去到变鸭器旁边", "关闭遇障停车", "move forward"):
            with self.subTest(text=text):
                result = self.ask(text, apply_homophones=True)
                self.assertEqual(result["analysis"]["normalization"]["normalized_text"], text)
                self.assertEqual(result["analysis"]["intent"], "operation_proposal")
                self.assertFalse(result["result"]["proposal"]["authorized"])
                self.assertEqual(result["executed_actions"], [])

    def test_time_recent_is_uncertain_and_explicit_is_exact(self):
        a = self.ask("一号主变最近有没有温度异常？")["analysis"]
        self.assertFalse(a["time_range"]["resolved"])
        a = self.ask("一号变压器近7天巡检记录")["analysis"]
        self.assertEqual(a["time_range"]["start"], "2026-10-01T12:00:00+08:00")
        a = self.ask("一号变压器昨天温度告警")["analysis"]
        self.assertEqual(a["time_range"]["end"], "2026-10-08T00:00:00+08:00")
        a = self.ask("一号变压器2026-10-09至2026-10-01温度告警")["analysis"]
        self.assertFalse(a["time_range"]["resolved"])

    def test_no_threshold_or_fake_normality(self):
        for text in ("一号变压器油温90℃是否异常？", "一号主变近7天有没有告警？", "查询99号变压器型号", "雷达状态正常吗？"):
            with self.subTest(text=text):
                r = self.ask(text)["result"]
                self.assertEqual(r["status"], "undetermined")
                self.assertIsNone(r["site_conclusion"])
                self.assertFalse(r["citations"])

    def test_sensor_temperature_is_not_an_electrical_asset_query(self):
        r = self.ask("相机温度多少？")
        self.assertEqual(r["analysis"]["intent"], "robot_sensor_status")
        self.assertEqual(r["analysis"]["required_data_sources"], ["robot_telemetry", "sensor_status"])
        self.assertEqual(r["result"]["status"], "undetermined")

    def test_mock_empty_records_cannot_confirm_normal(self):
        r = self.ask("一号主变近7天有没有温度异常？")["result"]
        self.assertEqual(r["data_preview"]["records"][0]["records"], [])
        self.assertIsNone(r["site_conclusion"])

    def test_conflicting_identity_does_not_select_device(self):
        r = self.ask("二号变压器编号T-001型号")["result"]
        self.assertEqual(r["data_preview"]["registry"][0]["status"], "not_found")

    def test_unsupported_identifier_is_not_truncated_to_known_asset(self):
        for text in ("T-001-A变压器型号", "EXAMPLE-T-001变压器型号", "一千一号变压器型号", "123456789号变压器型号"):
            with self.subTest(text=text):
                r = self.ask(text)
                entity = r["analysis"]["device_entities"][0]
                self.assertIsNone(entity["device_id"])
                self.assertIsNone(entity["device_number"])
                self.assertNotEqual(r["result"]["data_preview"]["registry"][0]["status"], "matched")

    def test_knowledge_missing_content_does_not_fabricate(self):
        r = self.ask("绝缘子是什么？")["result"]
        self.assertEqual(r["status"], "undetermined")

    def test_provider_cannot_forge_citation_or_threshold(self):
        class ForgingProvider:
            def compose(self, question, evidence):
                return {"passages": [{"chunk_id": evidence[0].id, "text": "80℃就是告警阈值"}]}
        brain = InspectionBrain(provider=ForgingProvider())
        self.assertEqual(brain.ask("什么是局部放电？", now=NOW)["result"]["status"], "undetermined")

    def test_draft_never_executes(self):
        a = self.ask("创建一号变压器巡检计划草案")["analysis"]
        draft = build_draft(a, self.brain.item_mapping)
        preview = OfflineDraftSink().submit_draft(draft)
        self.assertFalse(preview["stored"])
        self.assertFalse(preview["draft"]["authorized"])
        self.assertFalse(preview["draft"]["executable"])

    def test_hotword_export_disabled_and_never_imports_asr(self):
        r = export_vosk_grammar(DEFAULT_DATA/"hotwords.optional.json")
        self.assertIn("[unk]", json.loads(r["grammar_json"]))
        self.assertFalse(r["applied"])

    def test_aliases_and_phonetic_whitelist_do_not_touch_motion_variants(self):
        for text in ("向前两米", "去一号主变", "前往巡检点", "请前行", "返回充电处", "变压器资料查询后左转"):
            with self.subTest(text=text):
                r = self.ask(text, apply_homophones=True)
                self.assertEqual(r["analysis"]["intent"], "operation_proposal")
                self.assertEqual(r["analysis"]["normalization"]["normalized_text"], text)
                self.assertFalse(r["result"]["proposal"]["executable"])

    def test_package_has_no_hardware_network_or_legacy_imports(self):
        forbidden = {"socket", "urllib", "requests", "http", "aiohttp", "rclpy", "ctypes", "subprocess",
                     "RobotTerminal", "RobotNavigation", "RobotMotionGuard", "XavierScoutConsole", "vosk", "sherpa_onnx"}
        for path in (ROOT/"inspection_brain").rglob("*.py"):
            with self.subTest(module=str(path)):
                tree = ast.parse(path.read_text())
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        names = [a.name.split(".")[0] for a in node.names]
                    elif isinstance(node, ast.ImportFrom):
                        names = [(node.module or "").split(".")[0]]
                    else:
                        continue
                    self.assertFalse(forbidden.intersection(names))

    def test_missing_retrieval_returns_undetermined(self):
        class EmptyRetriever:
            def search(self, analysis, limit=3):
                return []
        result = InspectionBrain(retriever=EmptyRetriever()).ask("什么是局部放电？", now=NOW)
        self.assertEqual(result["result"]["status"], "undetermined")
        self.assertEqual(result["result"]["citations"], [])

    def test_document_loader_rejects_missing_source_and_rebuilds_index(self):
        from inspection_brain.electrical_knowledge import DocumentRepository
        source = json.loads((DEFAULT_DATA/"knowledge/example-partial-discharge.json").read_text())
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"imported.json"
            path.write_text(json.dumps(source))
            repository = DocumentRepository(folder, self.brain.lexicon)
            self.assertIn("partial_discharge", repository.term_index)
            self.assertEqual(repository.metadata()[0]["revision"], "example-v1")
            del source["source"]["uri"]
            path.write_text(json.dumps(source))
            with self.assertRaises(ValueError):
                DocumentRepository(folder, self.brain.lexicon)

    def test_lexicon_rejects_cross_type_alias_and_cycle(self):
        data = json.loads((DEFAULT_DATA/"electrical_terms.json").read_text())
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"terms.json"
            data["terms"][0]["aliases"].append("断路器")
            path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                Lexicon(path)
            data["terms"][0]["aliases"].remove("断路器")
            data["terms"][0]["parent_id"] = "main_transformer"
            path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                Lexicon(path)

    def test_invalid_input_and_naive_clock(self):
        for text in ("", "a"*2001, None):
            with self.assertRaises(ValueError):
                self.ask(text)
        with self.assertRaises(ValueError):
            self.brain.ask("什么是局部放电？", now=datetime(2026, 10, 8))


class RoutingTests(unittest.TestCase):
    def test_cli_route_flag_off_or_broken_data_does_not_load_block_old_path(self):
        from inspection_brain.cli import main
        with tempfile.TemporaryDirectory() as folder:
            for extra in ([], ["--enable-brain"]):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    code = main(["--route", "--data-dir", folder, *extra, "什么是局部放电？"])
                self.assertEqual(code, 0)
                self.assertEqual(json.loads(output.getvalue())["route"], "legacy")

    def test_flag_off_preserves_exact_legacy_payload_and_raw_text(self):
        sentinel = object()
        class Legacy:
            def classify(self, raw):
                self.seen = raw
                return LegacyDecision("fixed_reply", sentinel)
        class Brain:
            def ask(self, raw):
                raise AssertionError("must not call")
        legacy = Legacy()
        router = OfflineRouter(legacy, Brain(), enabled=False)
        try:
            text = "什么是局部放店？"
            result = router.route(text)
            self.assertEqual(legacy.seen, text)
            self.assertIs(result["legacy_decision"]["payload"], sentinel)
            self.assertEqual(result["route"], "legacy")
        finally:
            router.close()

    def test_old_fixed_and_control_have_priority_even_when_brain_enabled(self):
        class Brain:
            def ask(self, raw):
                raise AssertionError("must not call")
        router = OfflineRouter(MockLegacyDispatcher(), Brain(), enabled=True)
        try:
            for text in ("你好", "你是谁", "前进", "前进并解释局放"):
                self.assertEqual(router.route(text)["route"], "legacy")
        finally:
            router.close()

    def test_missing_failed_and_malformed_brain_fall_back(self):
        class Broken:
            def ask(self, raw):
                raise RuntimeError("unavailable")
        class Malformed:
            def ask(self, raw):
                return None
        for brain in (None, Broken(), Malformed()):
            router = OfflineRouter(MockLegacyDispatcher(), brain, enabled=True)
            try:
                r = router.route("什么是局部放电？")
                self.assertEqual(r["route"], "legacy")
                self.assertEqual(r["raw_text"], "什么是局部放电？")
            finally:
                router.close()

    def test_bounded_fallback_during_slow_provider_and_no_unbounded_queue(self):
        entered, release = threading.Event(), threading.Event()
        class Slow:
            def ask(self, raw):
                entered.set()
                release.wait(timeout=2)
                return {"analysis": {"intent": "equipment_knowledge"}}
        router = OfflineRouter(MockLegacyDispatcher(), Slow(), enabled=True, timeout_s=.02)
        try:
            start = time.monotonic()
            self.assertEqual(router.route("什么是变压器？")["reason"], "brain_timeout")
            self.assertLess(time.monotonic()-start, .5)
            self.assertTrue(entered.is_set())
            self.assertEqual(router.route("什么是变压器？")["reason"], "brain_busy")
            self.assertEqual(router.route("前进")["route"], "legacy")
        finally:
            release.set()
            router.close()

    def test_brain_cannot_return_an_authorized_operation(self):
        class Unsafe:
            def ask(self, raw):
                return {"analysis": {"intent": "operation_proposal"}, "hardware_commands_enabled": True}
        router = OfflineRouter(MockLegacyDispatcher(), Unsafe(), enabled=True)
        try:
            self.assertEqual(router.route("什么是局部放电？")["route"], "legacy")
        finally:
            router.close()

    def test_nested_proposal_authority_is_rejected_despite_safe_outer_flags(self):
        class Unsafe:
            def ask(self, raw):
                return {"analysis": {"intent": "equipment_knowledge"}, "executed_actions": [],
                        "chassis_commands_enabled": False, "hardware_commands_enabled": False,
                        "result": {"proposal": {"authorized": True}}}
        router = OfflineRouter(MockLegacyDispatcher(), Unsafe(), enabled=True)
        try:
            self.assertEqual(router.route("什么是局部放电？")["route"], "legacy")
        finally:
            router.close()

    def test_legacy_receives_original_only_on_normalized_knowledge_input(self):
        class Legacy:
            def classify(self, raw):
                self.seen = raw
                return LegacyDecision("passthrough", {"raw": raw})
        legacy = Legacy()
        router = OfflineRouter(legacy, InspectionBrain(), enabled=True)
        try:
            r = router.route("CT和PT有什么区别？")
            self.assertEqual(legacy.seen, "CT和PT有什么区别？")
            self.assertEqual(r["route"], "brain")
            self.assertEqual(r["brain_response"]["analysis"]["normalization"]["normalized_text"], "电流互感器和电压互感器有什么区别？")
            self.assertEqual(r["executed_actions"], [])
        finally:
            router.close()


if __name__ == "__main__":
    unittest.main()
