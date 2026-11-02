"""Independent synthetic semantic/safety contracts; no audio gold inference."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import unittest
from unittest.mock import patch

from brain_v3.config import ProviderConfig, voice_lab_configuration
from brain_v3.engine import SemanticEngine
from brain_v3.providers import MockProvider, OpenAICompatibleProvider, ProviderError
from brain_v3.schema import SCHEMA, schema_errors
from brain_v3.safety import SafetyGuard
from brain_v3.validator import SemanticValidator

NOW = datetime(2026, 10, 9, 4, tzinfo=timezone.utc)


class EngineTests(unittest.TestCase):
    def result(self, text):
        return SemanticEngine(provider=MockProvider()).analyze(text, mode="v3_llm", now=NOW)

    def test_device_self_correction_keeps_both_quotes_and_rejects_two(self):
        r = self.result("不是2号断路器，是3号断路器")
        self.assertTrue(r["validation"]["valid"])
        s = r["v3"]["semantic"]
        self.assertEqual([(e["device_number"], e["status"]) for e in s["equipment_entities"]], [("2", "negated"), ("3", "active")])
        self.assertEqual(s["self_corrections"][0]["accepted_ids"], ["e2"])
        self.assertEqual(s["structured_task_draft"]["target_equipment"][0]["entity_id"], "e2")
        self.assertEqual(s["equipment_entities"][1]["identity_status"], "unverified")

    def test_numeric_self_correction_preserves_decimal_and_exclusion(self):
        s = self.result("67.8摄氏度，不是678摄氏度")["v3"]["semantic"]
        self.assertEqual([(m["normalized_value"], m["status"]) for m in s["metric_entities"]], [("67.8", "active"), ("678", "negated")])
        self.assertEqual(s["self_corrections"][0]["accepted_ids"], ["m1"])
        self.assertEqual(s["self_corrections"][0]["rejected_ids"], ["m2"])

    def test_measurement_device_and_phase_association_are_not_interchangeable(self):
        r = self.result("1号主变A相电流12.5A，2号主变B相电流15.2A")
        s = r["v3"]["semantic"]
        values = [m for m in s["metric_entities"] if m["kind"] == "measurement"]
        self.assertEqual([v["owner_id"] for v in values], ["e1", "e2"])
        phases = {m["entity_id"]:m for m in s["metric_entities"] if m["kind"] == "phase"}
        self.assertEqual([phases[v["phase_entity_id"]]["normalized_value"] for v in values], ["A", "B"])
        wrong = deepcopy(s);next(m for m in wrong["metric_entities"] if m["kind"] == "measurement")["owner_id"] = "e2"
        self.assertFalse(SemanticValidator().validate(wrong, s)["valid"])

    def test_intent_cannot_target_another_devices_clause(self):
        r=self.result("查询1号主变巡检记录，并生成2号断路器的复检建议")
        self.assertTrue(r["validation"]["valid"],r["validation"])
        s=r["v3"]["semantic"]
        history=next(i for i in s["intents"] if i["type"] == "inspection_history")
        self.assertEqual(history["entity_ids"],["e1"])
        forged=deepcopy(s);next(i for i in forged["intents"] if i["type"] == "inspection_history")["entity_ids"]=["e2"]
        self.assertFalse(SemanticValidator().validate(forged,s)["valid"])

    def test_plan_with_negative_navigation_is_not_an_operation(self):
        r = self.result("制定巡检计划，但不要启动导航")
        s = r["v3"]["semantic"]
        self.assertEqual([i["type"] for i in s["intents"]], ["inspection_plan_draft"])
        self.assertTrue(s["negations"])
        self.assertTrue(any("不要启动导航" in p for p in r["structured_task_draft"]["prohibitions"]))
        self.assertFalse(r["executable"])

    def test_multi_intent_data_dependencies_and_time(self):
        s = self.result("查询今天一号主变巡检记录，同时对比最近三次测温结果并生成复检建议。")["v3"]["semantic"]
        kinds = {i["type"] for i in s["intents"]}
        self.assertTrue({"inspection_history", "temperature_comparison", "reinspection_recommendation"} <= kinds)
        self.assertEqual(s["temporal_constraints"][0]["start"], "2026-10-09T00:00:00+08:00")
        self.assertEqual(len(s["task_dependencies"]), 2)

    def test_real_transcript_text_is_development_fixture_not_semantic_gold(self):
        text = "请查询2号主变电压高套管的红外测温记录，并与上周的结果比较。"
        r = self.result(text)
        s = r["v3"]["semantic"]
        self.assertEqual(r["original_request"], text)
        self.assertEqual({i["type"] for i in s["intents"]}, {"thermometry_history", "temperature_comparison"})
        self.assertEqual(s["equipment_entities"][1]["part_of"], "e1")
        self.assertIsNone(r["structured_task_draft"]["site_conclusion"])
        self.assertEqual(s["temporal_constraints"][1]["start"], "2026-09-28T00:00:00+08:00")
        self.assertFalse(s["temporal_constraints"][0]["resolved"])

    def test_conditions_preserved_and_drafts_never_execute(self):
        r = self.result("如果人工授权后，启动导航")
        # This split condition is conservatively represented, with review required.
        self.assertTrue(r["v3"]["semantic"]["conditions"])
        self.assertEqual(r["v3"]["semantic"]["intents"][0]["request_kind"], "conditional_task")
        self.assertIn("i1", r["v3"]["semantic"]["conditions"][0]["scope_ids"])
        for text in ("如果温度超过67.8摄氏度就生成复检建议", "前进一米", "不能自动执行倒闸操作", "我批准立即导航"):
            with self.subTest(text=text):
                result = self.result(text)
                self.assertFalse(result["authorized"])
                self.assertFalse(result["executable"])
                self.assertFalse(result["structured_task_draft"]["hardware_commands_enabled"])

    def test_default_v2_no_model_calls(self):
        class Forbidden(MockProvider):
            def generate(self, request):
                raise AssertionError("default must not call model")
        r = SemanticEngine(provider=Forbidden()).analyze("什么是局部放电？", now=NOW)
        self.assertEqual(r["status"], "v2_only")
        self.assertIsNone(r["v3"])

    def test_unavailable_llm_is_clear_and_auto_fallback_is_labelled(self):
        engine = SemanticEngine()
        r = engine.analyze("制定巡检计划", mode="v3_llm", now=NOW)
        self.assertEqual(r["status"], "provider_unavailable")
        self.assertIsNone(r["structured_task_draft"])
        r = engine.analyze("制定巡检计划", mode="auto_fallback", now=NOW)
        self.assertTrue(r["fallback_used"]); self.assertTrue(r["fallback_success"])
        self.assertEqual(r["structured_task_draft"]["reasoning_source"], "rules_v2")
        self.assertFalse(r["provider"]["is_real_llm"])

    def test_mock_is_explicit_and_no_reference_or_audio_in_prompt(self):
        class Capture(MockProvider):
            def generate(inner, request):
                self.assertNotIn("reference_text", request)
                self.assertNotIn("audio", request)
                self.assertNotIn("data_preview", request)
                self.assertIn("original_request", request)
                self.assertIn("correction_candidates", request)
                return super(Capture, inner).generate(request)
        r = SemanticEngine(provider=Capture()).analyze("查询2号主片高压套管记录", mode="v3_llm", now=NOW, apply_homophones=True)
        self.assertFalse(r["provider"]["is_real_llm"])
        self.assertEqual(r["provider"]["model"], "mock-script")

    def test_context_does_not_add_device_or_number(self):
        r = SemanticEngine(provider=MockProvider()).analyze("查询巡检记录", mode="v3_llm", now=NOW, dialogue_context=["上次提到3号断路器678摄氏度"])
        self.assertEqual(r["v3"]["semantic"]["equipment_entities"], [])
        with self.assertRaises(ValueError):
            SemanticEngine().analyze("查询记录", dialogue_context=["x"*501])


class CandidateRejectionTests(unittest.TestCase):
    def setUp(self):
        self.text = "不是2号断路器，是3号断路器，油温67.8摄氏度，不是678摄氏度。制定巡检计划，但不要启动导航"
        self.base = SemanticEngine(provider=MockProvider()).analyze(self.text, mode="v3_llm", now=NOW)["model_candidate"]

    def reject(self, change, contains):
        candidate = deepcopy(self.base); change(candidate)
        outcome = SemanticValidator().validate(candidate, self.base)
        self.assertFalse(outcome["valid"], candidate)
        self.assertTrue(any(contains in e for e in outcome["errors"]), outcome)
        engine = SemanticEngine(provider=MockProvider(candidate))
        r = engine.analyze(self.text, mode="auto_fallback", now=NOW)
        self.assertTrue(r["fallback_success"])
        self.assertIsNone(r["v3"]["structured_task_draft"])
        self.assertFalse(r["structured_task_draft"]["authorized"])

    def test_schema_forbids_authorization_execution_tools_and_fake_site_conclusion(self):
        for field, value in (("authorized", True), ("executable", True), ("site_conclusion", "设备过热故障已确认")):
            with self.subTest(field=field):
                self.reject(lambda c: c["structured_task_draft"].update({field:value}), "structured_task_draft")
        self.reject(lambda c:c.update(tools=[{"name":"navigate"}]), "unexpected_field")

    def test_span_and_reference_forgery(self):
        self.reject(lambda c:c["source_spans"][0].update(quote="伪造原文"), "source_span")
        self.reject(lambda c:c["equipment_entities"][0].update(source_span_ids=["fake"]), "unknown_span_reference")

    def test_decimal_voltage_unit_phase_or_device_cannot_change(self):
        self.reject(lambda c:c["equipment_entities"][1].update(device_number="2"), "equipment_entities")
        self.reject(lambda c:next(m for m in c["metric_entities"] if m["raw_value"] == "67.8").update(normalized_value="678"), "metric_entities")
        for text in ("11000伏", "A相电流12.5A", "0.5 MPa", "01号断路器"):
            baseline = SemanticEngine(provider=MockProvider()).analyze(text, mode="v3_llm", now=NOW)["model_candidate"]
            forged = deepcopy(baseline); forged["metric_entities"][0]["normalized_unit"] = "kV"
            self.assertFalse(SemanticValidator().validate(forged, baseline)["valid"])

    def test_negation_correction_and_condition_cannot_disappear(self):
        for key in ("negations", "self_corrections"):
            self.reject(lambda c:c.update({key:[]}), key)
        self.reject(lambda c:c["equipment_entities"][0].update(status="active"), "equipment_entities")

    def test_safety_seals_even_when_caller_supplies_trusted_validation(self):
        forged = deepcopy(self.base);forged["structured_task_draft"]["authorized"] = True
        safe = SafetyGuard().seal(forged, {"valid":True}, "mock_script")
        self.assertFalse(safe["authorized"])
        self.assertFalse(safe["structured_task_draft"]["authorized"])
        self.assertFalse(safe["semantic"]["structured_task_draft"]["authorized"])

    def test_unknown_field_enum_boolean_zero_and_missing_schema_rejected(self):
        self.reject(lambda c:c["structured_task_draft"].update(executable=0), "type")
        self.reject(lambda c:c["intents"][0].update(request_kind="execute"), "enum")
        self.reject(lambda c:c.pop("negations"), "required")


class ProviderConfigTests(unittest.TestCase):
    def test_bad_optional_environment_does_not_block_v2_or_echo_secret(self):
        with patch.dict("os.environ", {"BRAIN_V3_TIMEOUT":"MISASSIGNED_SECRET_VALUE"}, clear=True):
            config, error = voice_lab_configuration()
            self.assertEqual(config.provider,"rules");self.assertFalse(config.enabled)
            self.assertIn("配置无效",error);self.assertNotIn("MISASSIGNED_SECRET_VALUE",error)
        for bad in (float('nan'),float('inf'),True):
            with self.assertRaises(ValueError):ProviderConfig(temperature=bad)

    def test_no_external_call_by_default_and_secrets_redacted(self):
        c = ProviderConfig(provider="openai_compatible", model="configured", api_key="TEST_SECRET")
        p = OpenAICompatibleProvider(c)
        with patch.object(p.opener, "open", side_effect=AssertionError("network must stay off")):
            with self.assertRaises(ProviderError):p.generate({})
        self.assertNotIn("TEST_SECRET", repr(c)+json.dumps(c.public())+json.dumps(p.status()))
        with self.assertRaises(ValueError):ProviderConfig(base_url="https://example.com/v1")
        with self.assertRaises(ValueError):ProviderConfig(base_url="http://example.com/v1", allow_external_text=True)
        with self.assertRaises(ValueError):ProviderConfig(base_url="http://secret@localhost:1234/v1")
        allowed = ProviderConfig(base_url="https://example.com/v1", allow_external_text=True)
        self.assertEqual(allowed.endpoint(), "https://example.com/v1/chat/completions")

    def test_schema_matches_official_jsonschema_implementation_when_available(self):
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest("optional jsonschema package unavailable; production uses bundled exact validator")
        Draft202012Validator.check_schema(SCHEMA)
        valid = SemanticEngine(provider=MockProvider()).analyze("不是2号断路器，是3号断路器", mode="v3_llm", now=NOW)["model_candidate"]
        for value in (valid, {**valid, "schema_version":"bad"}, {**valid, "extra":True}, {**valid, "negations":None}):
            self.assertEqual(bool(schema_errors(value)), not Draft202012Validator(SCHEMA).is_valid(value))


if __name__ == "__main__":
    unittest.main()
