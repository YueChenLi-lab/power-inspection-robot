"""Deterministic electrical intent and entity analysis; no actuator path."""
from datetime import datetime, timedelta
import re

from .safety import action_markers, operation_proposal

INTENTS = {"equipment_knowledge", "robot_sensor_status", "equipment_information",
           "inspection_history", "temperature_alarm_query", "inspection_plan_draft",
           "anomaly_procedure_explanation", "operation_proposal", "unknown"}
ID_PATTERN = re.compile(r"(?<![A-Za-z0-9_-])([A-Za-z]{1,8}[-_]\d{1,12})(?![A-Za-z0-9_-])")
NUMBER_PATTERN = re.compile(r"(?<![0-9零〇一二三四五六七八九十百千万亿两])([0-9]{1,8}|[零〇一二三四五六七八九十百千万亿两]{1,16})号\s*$")


def chinese_integer(value):
    if value.isdecimal():
        return value  # Keep leading zeroes: 01 is not silently changed to 1.
    digits = {c: n for n, c in enumerate("零一二三四五六七八九")}
    digits.update({"〇": 0, "两": 2})
    if all(c in digits for c in value):
        return "".join(str(digits[c]) for c in value)
    if re.fullmatch(r"[一二三四五六七八九]?十[一二三四五六七八九]?", value):
        before, after = value.split("十")
        return str(digits.get(before, 1) * 10 + digits.get(after, 0))
    return None  # Unsupported numbering gets uncertainty, not a guessed ID.


def extract_entities(raw_text, normalization, lexicon):
    # Entity identity is taken ONLY from raw exact terms and local adjacency.
    # Applied phonetic repairs remain candidates requiring confirmation.
    entities, uncertainty = [], []
    ids = list(ID_PATTERN.finditer(raw_text))
    for start, end, term, surface in lexicon.matches(raw_text):
        if term.category != "equipment":
            continue
        prefix = raw_text[:start]
        number = NUMBER_PATTERN.search(prefix)
        hash_number = re.search(r"#([0-9]{1,8})\s*$", prefix) if not number else None
        designator = number.group(1) if number else hash_number.group(1) if hash_number else None
        device_number = chinese_integer(designator) if designator else None
        if designator and device_number is None:
            uncertainty.append("设备序号格式不支持，请确认: " + designator)
        explicit = [m for m in ids if (m.end() <= start and not raw_text[m.end():start].strip()) or
                    (m.start() >= end and re.fullmatch(r"[\s（(]*(?:编号[:：]?\s*)?", raw_text[end:m.start()]))]
        explicit_id = explicit[0].group(1) if len(explicit) == 1 else None
        if len(explicit) > 1:
            uncertainty.append("同一设备关联多个编号，请确认")
        if re.search(r"号\s*(?:和|或|、)\s*(?:[0-9零一二三四五六七八九十]+号)?\s*$", prefix):
            uncertainty.append("并列或可选设备序号，需拆分并确认")
            device_number = None
        entities.append({"term_id": term.id, "standard_name": term.standard_name,
                         "equipment_category": term.equipment_category, "surface": surface,
                         "span": [start, end], "device_number": device_number,
                         "number_surface": designator, "device_id": explicit_id,
                         "identity_status": "unresolved_registry" if device_number or explicit_id else "type_only"})
    if ids and not any(e["device_id"] for e in entities):
        uncertainty.append("编号未可靠关联设备类型，请确认")
    for candidate in normalization["homophone_candidates"]:
        if any(lexicon.by_id[t].category == "equipment" for t in candidate["term_ids"]):
            uncertainty.append("同音设备类型需确认: " + candidate["surface"])
    return entities, uncertainty


def extract_time(text, now):
    end = now.isoformat()
    for label, offset in (("今天", 0), ("昨天", 1), ("昨日", 1)):
        if label in text:
            start = (now - timedelta(days=offset)).replace(hour=0, minute=0, second=0, microsecond=0)
            return {"expression": label, "start": start.isoformat(),
                    "end": (start + timedelta(days=1)).isoformat(), "resolved": True}, []
    match = re.search(r"(?:最近|近|过去)(\d{1,3})天", text)
    if match:
        days = int(match.group(1))
        if days > 0:
            return {"expression": match.group(0), "start": (now-timedelta(days=days)).isoformat(),
                    "end": end, "resolved": True}, []
    dates = re.findall(r"\d{4}-\d{2}-\d{2}", text)
    if dates:
        try:
            parsed = [datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=now.tzinfo) for d in dates]
            if len(parsed) > 2 or (len(parsed) == 2 and parsed[0] > parsed[1]):
                raise ValueError("invalid interval")
            return {"expression": "至".join(dates), "start": parsed[0].isoformat(),
                    "end": (parsed[-1]+timedelta(days=1)).isoformat(), "resolved": True}, []
        except ValueError:
            return {"expression": "至".join(dates), "start": None, "end": None, "resolved": False}, ["日期范围无效"]
    recent = next((word for word in ("最近", "近期", "历史", "上次") if word in text), None)
    return {"expression": recent, "start": None, "end": None, "resolved": False}, \
           (["时间范围未明确，请指定起止日期或最近几天"] if recent else [])


class ElectricalIntentAnalyzer:
    def __init__(self, normalizer):
        self.normalizer = normalizer

    def analyze(self, text, *, now, apply_homophones=False):
        if now.tzinfo is None:
            raise ValueError("参考时间必须包含时区")
        normal = self.normalizer.normalize(text, apply_homophones=apply_homophones)
        entities, uncertainty = extract_entities(text, normal, self.normalizer.lexicon)
        time_range, time_uncertainty = extract_time(text, now)
        query = normal["normalized_text"]
        markers = action_markers(text)
        recognized = {t["category"] for t in normal["recognized_terms"]}
        if markers:
            intent = "operation_proposal"
            sources = ["legacy_dispatcher", "human_authorization"]
        elif re.search(r"(?:创建|制定|生成|安排|拟定).*(?:巡检|复检|计划)|巡检计划.*草案", query):
            intent = "inspection_plan_draft"
            sources = ["equipment_registry", "inspection_procedure", "mission_manager_future"]
        elif re.search(r"机器人|底盘|雷达|相机|传感器|电池|云台", query) and re.search(r"状态|电量|电压|速度|在线|正常|温度|多少", query):
            intent = "robot_sensor_status"
            sources = ["robot_telemetry", "sensor_status"]
        elif re.search(r"温度|油温|测温|告警|报警|过热", query) and re.search(r"有没有|是否|查询|最近|近期|今天|昨天|记录|多少|当前|现在|异常", query) and not re.search(r"什么|解释|一般|规程|如何", query):
            intent = "temperature_alarm_query"
            sources = ["equipment_registry", "thermometry_records", "alarm_records", "applicable_rules"]
        elif re.search(r"巡检记录|缺陷记录|历史.*巡检|上次.*(?:巡检|复检)|最近.*(?:巡检|复检)", query):
            intent = "inspection_history"
            sources = ["equipment_registry", "inspection_records"]
        elif re.search(r"台账|设备资料|说明书|型号|厂家|额定|出厂|档案", query):
            intent = "equipment_information"
            sources = ["equipment_registry", "equipment_manuals"]
        elif "defect" in recognized or re.search(r"规程|流程|注意事项|检查.*需要.*信息|巡检.*项目", query):
            intent = "anomaly_procedure_explanation"
            sources = ["knowledge_documents", "inspection_procedure"]
        elif "equipment" in recognized and re.search(r"什么|区别|介绍|原理|作用|一般|检查|哪些", query):
            intent = "equipment_knowledge"
            sources = ["knowledge_documents"]
        else:
            intent, sources = "unknown", []
        if intent in {"temperature_alarm_query", "inspection_history"}:
            uncertainty.extend(time_uncertainty)
            if not time_range["expression"]:
                uncertainty.append("未提供查询时间范围")
        if intent in {"equipment_information", "inspection_history", "temperature_alarm_query", "inspection_plan_draft"}:
            if not entities or any(not e["device_id"] and not e["device_number"] for e in entities):
                uncertainty.append("未明确设备编号；不能自动选择现场设备")
        if any(e["device_id"] or e["device_number"] is not None for e in entities):
            uncertainty.append("设备编号尚未与真实台账核对")
        if re.search(r"(?:多少|有没有|是否|当前|现在|最近).*(?:电压|电流|功率|油温|负载率)|(?:电压|电流|功率|油温|负载率).*(?:多少|当前|现在|最近)", query) and intent == "unknown":
            sources = ["equipment_measurements"]
            uncertainty.append("实时指标请求尚未覆盖，不能用通用知识猜测读数")
        if intent == "unknown":
            uncertainty.append("未匹配已支持的电力业务意图，请明确问题")
        return {"schema_version": 1, "intent": intent, "normalization": normal,
                "device_entities": entities, "device_ids": [e["device_id"] for e in entities if e["device_id"]],
                "time_range": time_range, "reference_time": now.isoformat(),
                "required_data_sources": sources, "uncertainties": list(dict.fromkeys(uncertainty)),
                "operation_proposal": operation_proposal(text, markers) if markers else None,
                "chassis_commands_enabled": False, "hardware_commands_enabled": False}
