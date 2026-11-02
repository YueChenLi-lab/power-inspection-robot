"""Final authority is deterministic code. This module exposes no tool/actuator."""
from copy import deepcopy
from .evidence import build_draft


class SafetyGuard:
    def seal(self, candidate, validation, origin):
        # Even a caller bypassing Validator cannot obtain an accepted unsafe draft.
        if not validation.get("valid"):
            return {"status": "clarification_required", "authorized": False, "executable": False,
                    "hardware_commands_enabled": False, "human_confirmation_required": True,
                    "site_conclusion": None, "clarification_requests": ["模型候选未通过独立校验，请人工确认或使用明确标记的v2回退。"],
                    "structured_task_draft": None}
        final = deepcopy(candidate)
        # Rebuild instead of passing the model's draft/authorization through.
        draft = build_draft(final, origin)
        draft.update(authorized=False, executable=False, hardware_commands_enabled=False,
                     human_confirmation_required=True, site_conclusion=None)
        final["structured_task_draft"] = draft
        return {"status": "draft_requires_review", "authorized": False, "executable": False,
                "hardware_commands_enabled": False, "human_confirmation_required": True,
                "site_conclusion": None, "clarification_requests": final["clarification_requests"],
                "semantic": final, "structured_task_draft": draft}
