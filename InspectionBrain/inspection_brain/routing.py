"""Parallel routing simulation. Legacy decisions always precede normalization."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass
from typing import Protocol

from .safety import action_markers


@dataclass(frozen=True)
class LegacyDecision:
    kind: str  # control / fixed_reply / passthrough
    payload: object


class LegacyDispatcher(Protocol):
    def classify(self, raw_text: str) -> LegacyDecision: ...


class MockLegacyDispatcher:
    """Illustrative fixture, not a reimplementation of the production parser."""
    def __init__(self, fixed_replies=None):
        self.fixed_replies = fixed_replies or {"你好": "示例旧固定回复：你好", "你是谁": "示例旧固定回复：巡检机器人"}

    def classify(self, raw_text):
        if raw_text in self.fixed_replies:
            return LegacyDecision("fixed_reply", self.fixed_replies[raw_text])
        if action_markers(raw_text):
            return LegacyDecision("control", {"raw_text": raw_text, "executed": False,
                                               "requires_original_authorization": True})
        return LegacyDecision("passthrough", {"raw_text": raw_text, "executed": False})


class OfflineRouter:
    def __init__(self, legacy: LegacyDispatcher, brain=None, *, enabled=False, timeout_s=0.25):
        if timeout_s <= 0:
            raise ValueError("Brain超时必须大于0")
        self.legacy, self.brain, self.enabled, self.timeout_s = legacy, brain, enabled, timeout_s
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="brain-offline")
        self.pending = None

    def route(self, raw_text, **brain_kwargs):
        old = self.legacy.classify(raw_text)
        base = {"raw_text": raw_text, "legacy_decision": {"kind": old.kind, "payload": old.payload},
                "mode": "offline_simulation", "executed_actions": []}
        if not self.enabled or old.kind in {"control", "fixed_reply"} or action_markers(raw_text):
            return dict(base, route="legacy", reason="flag_off" if not self.enabled else "legacy_priority")
        if self.brain is None:
            return dict(base, route="legacy", reason="brain_unavailable")
        if self.pending is not None and not self.pending.done():
            return dict(base, route="legacy", reason="brain_busy")
        self.pending = self.pool.submit(self.brain.ask, raw_text, **brain_kwargs)
        try:
            response = self.pending.result(timeout=self.timeout_s)
        except TimeoutError:
            self.pending.cancel()
            return dict(base, route="legacy", reason="brain_timeout")
        except Exception:
            return dict(base, route="legacy", reason="brain_failed")
        if not isinstance(response, dict) or not isinstance(response.get("analysis"), dict):
            return dict(base, route="legacy", reason="brain_invalid_response")
        # Never fall forward to an operation synthesized by a future provider.
        def carries_authority(value):
            if isinstance(value, dict):
                return any((key in {"authorized", "executable", "authorization_granted",
                                    "hardware_commands_enabled", "chassis_commands_enabled"} and item is not False)
                           or carries_authority(item) for key, item in value.items())
            return isinstance(value, list) and any(carries_authority(item) for item in value)
        if (response["analysis"].get("intent") not in {"equipment_knowledge", "equipment_information",
                "inspection_history", "temperature_alarm_query", "inspection_plan_draft", "anomaly_procedure_explanation"}
                or response.get("executed_actions") != [] or carries_authority(response)
                or response.get("hardware_commands_enabled") is not False
                or response.get("chassis_commands_enabled") is not False):
            return dict(base, route="legacy", reason="unsupported_or_unsafe_brain_response")
        return dict(base, route="brain", brain_response=response)

    def close(self):
        # No waiting on a stalled provider in the caller's dispatch path.
        self.pool.shutdown(wait=False, cancel_futures=True)
