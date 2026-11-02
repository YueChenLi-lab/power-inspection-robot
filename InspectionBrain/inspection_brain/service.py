"""Offline application service: term -> intent -> evidence or abstention."""
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path

from .adapters import MockRegistry, MockRecords, MockRobotStatus
from .electrical_knowledge import DocumentRepository, KnowledgeQA
from .electrical_knowledge.repository import undetermined
from .intent import ElectricalIntentAnalyzer
from .mission import build_draft
from .terminology import Lexicon, TextNormalizer

SHANGHAI = timezone(timedelta(hours=8), "Asia/Shanghai")
DEFAULT_DATA = Path(__file__).resolve().parent / "data"


class InspectionBrain:
    def __init__(self, data_dir=DEFAULT_DATA, *, registry=None, records=None,
                 robot_status=None, retriever=None, provider=None):
        data_dir = Path(data_dir)
        self.lexicon = Lexicon(data_dir/"electrical_terms.json")
        self.analyzer = ElectricalIntentAnalyzer(TextNormalizer(self.lexicon))
        self.repository = DocumentRepository(data_dir/"knowledge", self.lexicon)
        self.qa = KnowledgeQA(retriever or self.repository, provider)
        self.registry = registry or MockRegistry(data_dir/"mock_devices.json")
        self.records = records or MockRecords(data_dir/"mock_records.json")
        self.robot_status = robot_status or MockRobotStatus()
        mapping = json.loads((data_dir/"inspection_items.json").read_text(encoding="utf-8"))
        self.item_mapping = mapping["mappings"]

    def ask(self, text, *, now=None, apply_homophones=False):
        analysis = self.analyzer.analyze(text, now=now or datetime.now(SHANGHAI),
                                         apply_homophones=apply_homophones)
        intent = analysis["intent"]
        if intent == "operation_proposal":
            result = {"status": "requires_human_confirmation", "answer": "已识别为操作提案；本模块不授权、不执行任何硬件动作。原控制请求只能由原系统按原文处理。",
                      "citations": [], "is_example": False, "site_conclusion": None,
                      "proposal": analysis["operation_proposal"]}
        elif intent == "inspection_plan_draft":
            draft = build_draft(analysis, self.item_mapping)
            result = {"status": "draft_requires_review", "answer": "已生成离线巡检计划草案，需确认真实设备、规程与现场授权；草案不可执行。",
                      "citations": [], "is_example": True, "site_conclusion": None,
                      "mission_draft": draft.to_dict()}
        elif intent in {"equipment_knowledge", "anomaly_procedure_explanation"}:
            result = self.qa.answer(analysis)
        elif intent == "robot_sensor_status":
            result = undetermined("未连接实时机器人/传感器数据，无法判断当前状态。", analysis["required_data_sources"])
            result["data_preview"] = self.robot_status.read()
        elif intent in {"equipment_information", "inspection_history", "temperature_alarm_query"}:
            matches = [self.registry.lookup(entity) for entity in analysis["device_entities"]]
            preview = []
            if intent != "equipment_information":
                for match in matches:
                    if match["status"] == "matched":
                        preview.append(self.records.query(match["devices"][0]["asset_id"],
                                                          analysis["time_range"],
                                                          "inspection" if intent == "inspection_history" else "thermometry"))
            result = undetermined("需要真实设备台账及相应记录。当前只有Mock示例，不能判断该设备的资料、历史结果或温度异常；没有记录不等于正常。",
                                  analysis["required_data_sources"])
            result.update(data_preview={"registry": matches, "records": preview, "is_example": True})
        else:
            result = undetermined("尚未识别明确的电力业务问题，或缺少适用证据；请补充设备与问题范围。", analysis["required_data_sources"])
        return {"mode": "offline", "analysis": analysis, "result": result,
                "chassis_commands_enabled": False, "hardware_commands_enabled": False,
                "executed_actions": []}
