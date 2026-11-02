from datetime import datetime
import json
from pathlib import Path
import unittest
from inspection_brain.domain_v2.service import ElectricalBrainV2
from inspection_brain.domain_v2.numbers import extract_numeric_slots, equivalent_value

NOW=datetime.fromisoformat("2026-10-09T12:00:00+08:00")
SOURCE=Path(__file__).resolve().parents[2]/"voice-evaluation.json"


class DomainV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.brain=ElectricalBrainV2()
    def ask(self,text,**kwargs):return self.brain.ask(text,now=NOW,**kwargs)
    def test_real_data_rules_and_switch_are_separate(self):
        rows=json.loads(SOURCE.read_text())["records"]
        for index in (4,5,8):
            text=rows[index]["original_transcript"]
            off=self.ask(text)
            on=self.ask(text,apply_homophones=True)
            self.assertEqual(off["analysis"]["raw_transcript"],text)
            self.assertTrue(off["analysis"]["normalization"]["homophone_candidates"])
            self.assertNotEqual(on["analysis"]["term_normalized_text"],text)
        self.assertIn("绕组温度",self.ask(rows[4]["original_transcript"],apply_homophones=True)["analysis"]["term_normalized_text"])
        self.assertIn("继电保护",self.ask(rows[5]["original_transcript"],apply_homophones=True)["analysis"]["term_normalized_text"])
    def test_non_electrical_context_not_corrected(self):
        for text in ("祭奠保护传统仪式","这叫设备抬杠大赛","人工复合材料很便宜","由窄分接开关这个网名很有趣","我写的功绿小说是什么"):
            r=self.ask(text,apply_homophones=True)
            self.assertEqual(r["analysis"]["term_normalized_text"],text)
    def test_main_transformer_confusion_requires_equipment_context(self):
        # Text reported by the user; this regression does not simulate model inference.
        raw="请查询2号主片高压套管的红外记录、红外测温记录，并与上周的结果比较。"
        off=self.ask(raw)["analysis"]
        candidate=next(c for c in off["normalization"]["homophone_candidates"] if c["surface"]=="主片")
        self.assertEqual(off["term_normalized_text"],raw)
        self.assertEqual(candidate["replacement"],"主变")
        self.assertEqual(candidate["term_ids"],["main_transformer"])
        self.assertEqual(candidate["standard_names"],["主变压器"])
        self.assertEqual(candidate["reason"],"switch_disabled")
        self.assertIn("高压套管",candidate["context_hits"])
        self.assertFalse(candidate["authorization_granted"])
        on=self.ask(raw,apply_homophones=True)
        self.assertEqual(on["analysis"]["raw_transcript"],raw)
        self.assertEqual(on["analysis"]["term_normalized_text"],raw.replace("主片","主变"))
        self.assertEqual(on["executed_actions"],[])
        self.assertFalse(on["hardware_commands_enabled"])
        for unrelated in ("请查询这部电影主片的记录","主片的红外记录","主片的温度是多少","查询变压器纪录片主片的播放记录"):
            with self.subTest(text=unrelated):
                a=self.ask(unrelated,apply_homophones=True)["analysis"]
                self.assertEqual(a["term_normalized_text"],unrelated)
                candidates=a["normalization"]["homophone_candidates"]
                self.assertTrue(candidates)
                self.assertFalse(candidates[0]["display_confirmation_allowed"])
                confirmed=self.ask(unrelated,accepted_candidate_ids=[c["id"] for c in candidates])["analysis"]
                self.assertEqual(confirmed["cleaned_display_text"],unrelated)
    def test_main_transformer_confusion_cannot_authorize_operations(self):
        raw="导航到2号主片高压套管"
        first=self.ask(raw,apply_homophones=True)["analysis"]
        candidates=first["normalization"]["homophone_candidates"]
        self.assertTrue(candidates)
        self.assertTrue(first["normalization"]["operation_text_protected"])
        self.assertEqual(first["term_normalized_text"],raw)
        self.assertFalse(candidates[0]["display_confirmation_allowed"])
        confirmed=self.ask(raw,apply_homophones=True,accepted_candidate_ids=[c["id"] for c in candidates])
        self.assertEqual(confirmed["analysis"]["cleaned_display_text"],raw)
        self.assertEqual(confirmed["executed_actions"],[])
        self.assertFalse(confirmed["hardware_commands_enabled"])
    def test_high_risk_only_candidates(self):
        for text in ("解释断路器分和闸状态","六氟化硫设备的a箱接头温度是多少","变压器由窄分接开关运行情况"):
            a=self.ask(text,apply_homophones=True)["analysis"]
            self.assertEqual(a["term_normalized_text"],text)
            self.assertTrue(a["normalization"]["homophone_candidates"])
    def test_cleanup_requires_confirmation_for_restart(self):
        for original,expected in [("三号柜开关3号开关柜的a箱接头温度","三号开关柜的A相接头温度"),("变压器管套管变压器套管渗漏油","变压器套管渗漏油")]:
            first=self.ask(original)["analysis"]
            self.assertEqual(first["cleaned_display_text"],original)
            ids=[c["id"] for c in first["correction_candidates"]]
            confirmed=self.ask(original,accepted_candidate_ids=ids)["analysis"]
            self.assertEqual(confirmed["cleaned_display_text"],expected)
            self.assertEqual(confirmed["raw_transcript"],original)
            self.assertTrue(confirmed["correction_trace"])
        self.assertEqual(self.ask("1号的主变的油温")["analysis"]["cleaned_display_text"],"1号主变的油温")
    def test_legal_repeat_and_operations_preserved(self):
        for text in ("分别检查一号变压器和二号变压器","前进到一号变压器并前进到二号变压器"):
            a=self.ask(text)["analysis"]
            confirmed=self.ask(text,accepted_candidate_ids=[c["id"] for c in a["correction_candidates"]])["analysis"]
            self.assertEqual(confirmed["cleaned_display_text"],text)
        text="油温油温是什么"
        a=self.ask(text)["analysis"]
        self.assertEqual(a["cleaned_display_text"],text)
        rejected=self.ask(text,rejected_candidate_ids=[c["id"] for c in a["correction_candidates"]])["analysis"]
        self.assertEqual(rejected["cleaned_display_text"],text)
    def test_numeric_values_never_guessed(self):
        raw="11000伏油温685摄氏度绕组823℃温差125℃压力05赵帕"
        result=self.ask(raw,apply_homophones=True)
        self.assertEqual(result["analysis"]["term_normalized_text"],raw)
        slots=result["analysis"]["numeric_entities"]
        self.assertEqual([s["raw_value"] for s in slots],["11000","685","823","125","05"])
        self.assertIsNone(slots[-1]["normalized_value"])
        self.assertIsNone(slots[-1]["normalized_unit"])
        self.assertIsNone(result["result"]["site_conclusion"])
        self.assertNotEqual(equivalent_value(slots[0]),equivalent_value(extract_numeric_slots("110kV")[0]))
    def test_exact_number_format_conversion(self):
        slots=extract_numeric_slots("一百一十千伏，六十八点五摄氏度，百分之七十五，零点五兆帕，01号，A相")
        self.assertEqual([s["normalized_value"] for s in slots],["110","68.5","75","0.5","01","A"])
        self.assertEqual(equivalent_value(slots[0]),equivalent_value(extract_numeric_slots("110000V")[0]))
        self.assertIsNone(extract_numeric_slots("0.5mPa")[0]["normalized_unit"])
    def test_multi_intent_and_real_cases(self):
        a=self.ask("查询今天一号主变巡检记录，同时对比最近三次测温结果并生成复检建议。")["analysis"]
        kinds={r["type"] for r in a["intents"]}
        self.assertTrue({"inspection_history","temperature_comparison","reinspection_recommendation"}<=kinds)
        self.assertNotIn("inspection_plan_draft",kinds)
        rows=json.loads(SOURCE.read_text())["records"]
        for row in rows:
            r=self.ask(row["original_transcript"],apply_homophones=True)
            self.assertEqual(r["executed_actions"],[])
            self.assertFalse(r["hardware_commands_enabled"])
    def test_negation_scope_and_conditions(self):
        for text in ("不执行倒闸操作","不移动","不能操作","不要启动"):
            self.assertIsNone(self.ask(text)["analysis"]["operation_proposal"],text)
        a=self.ask("制定巡检计划，但不要未经授权启动机器人自主导航。")["analysis"]
        self.assertEqual(a["intent"],"inspection_plan_draft")
        self.assertIsNone(a["operation_proposal"])
        self.assertTrue(a["constraints"])
        a=self.ask("不能自动执行倒闸操作。")["analysis"]
        self.assertEqual(a["intent"],"prohibited_operation")
        self.assertIsNone(a["operation_proposal"])
        a=self.ask("前进，但不要后退")["analysis"]
        self.assertEqual(a["intent"],"operation_proposal")
        self.assertIn("后退",[s["action"] for s in a["constraints"]])
        a=self.ask("如果得到授权再启动机器人")["analysis"]
        self.assertTrue(any(s["polarity"]=="conditional" for s in a["action_scopes"]))
        self.assertFalse(a["operation_proposal"]["authorized"])
    def test_status_query_is_not_unknown(self):
        r=self.ask("隔离开关有没有异常？")
        self.assertEqual(r["analysis"]["intent"],"equipment_status_query")
        self.assertEqual(r["result"]["status"],"undetermined")
        self.assertIn("live_equipment_status",r["analysis"]["required_data_sources"])
    def test_separate_synthetic_challenges(self):
        data=json.loads((Path(__file__).parent/"heldout_challenges.json").read_text())
        for row in data["cases"]:
            with self.subTest(text=row["text"]):
                result=self.ask(row["text"],apply_homophones=True)
                a=result["analysis"]
                if "required_intent" in row:self.assertIn(row["required_intent"],[i["type"] for i in a["intents"]])
                if "positive_operation" in row:self.assertEqual(a["operation_proposal"] is not None,row["positive_operation"])
                if row.get("unchanged"):self.assertEqual(a["term_normalized_text"],row["text"])
                self.assertFalse(result["hardware_commands_enabled"])
