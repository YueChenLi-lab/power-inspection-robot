"""Read-only contracts. Mock adapters never contact a network or hardware."""
from datetime import datetime
import json
from pathlib import Path
from typing import Protocol


class EquipmentRegistry(Protocol):
    def lookup(self, entity: dict) -> dict: ...


class InspectionRecords(Protocol):
    def query(self, asset_id: str, time_range: dict, kind: str) -> dict: ...


class RobotStatus(Protocol):
    def read(self) -> dict: ...


class MockRegistry:
    def __init__(self, path):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if data.get("is_example") is not True or any(d.get("is_example") is not True for d in data["devices"]):
            raise ValueError("Mock台账必须明确标记示例")
        self.devices = data["devices"]

    def lookup(self, entity):
        if not entity["device_id"] and entity["device_number"] is None:
            return {"status": "unresolved", "devices": [], "is_example": True,
                    "reason": "只有设备类型，未指定编号"}
        candidates = [dict(d) for d in self.devices if entity["term_id"] in d["term_ids"]
                      and (entity["device_id"] is None or d["device_id"] == entity["device_id"])
                      and (entity["device_number"] is None or d["local_number"] == entity["device_number"])]
        return {"status": "matched" if len(candidates) == 1 else "ambiguous" if candidates else "not_found",
                "devices": candidates, "is_example": True,
                "reason": "示例映射；不是实际设备身份验证"}


class MockRecords:
    def __init__(self, path):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if data.get("is_example") is not True or any(r.get("is_example") is not True for r in data["records"]):
            raise ValueError("Mock记录必须明确标记示例")
        self.records = data["records"]

    def query(self, asset_id, time_range, kind):
        if not time_range["resolved"]:
            return {"status": "needs_time_range", "records": [], "is_example": True}
        start, end = (datetime.fromisoformat(time_range[k]) for k in ("start", "end"))
        rows = [dict(r) for r in self.records if r["asset_id"] == asset_id and r["kind"] == kind
                and start <= datetime.fromisoformat(r["sampled_at"]) < end]
        return {"status": "mock_only", "records": rows, "is_example": True,
                "absence_is_not_normal": True}


class MockRobotStatus:
    def read(self):
        return {"status": "not_connected", "is_example": True,
                "measurements": {}, "reason": "未连接真实机器人或传感器"}
