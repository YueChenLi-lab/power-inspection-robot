"""Future Mission Manager input contract; drafts have no execution capability."""
from dataclasses import asdict, dataclass
from typing import Protocol


@dataclass(frozen=True)
class MissionDraft:
    schema_version: int
    requested_text: str
    devices: list
    steps: list
    unresolved: list
    status: str = "draft_requires_review"
    requires_human_authorization: bool = True
    authorized: bool = False
    executable: bool = False

    def to_dict(self):
        return asdict(self)


class MissionDraftSink(Protocol):
    """Future integration may store a draft, never infer permission to run."""
    def submit_draft(self, draft: MissionDraft) -> dict: ...


class OfflineDraftSink:
    def submit_draft(self, draft):
        if draft.executable or draft.authorized:
            raise ValueError("第一阶段不接受执行授权")
        return {"stored": False, "mode": "offline_preview", "draft": draft.to_dict()}


def build_draft(analysis, item_mapping):
    steps = []
    for entity in analysis["device_entities"]:
        items = item_mapping.get(entity["term_id"], [])
        if entity["term_id"] == "main_transformer":
            items = item_mapping.get("transformer", [])
        steps.append({"skill": "review_inspection_requirements", "device": entity,
                      "example_items": items, "status": "proposed", "executable": False})
    return MissionDraft(1, analysis["normalization"]["raw_text"], analysis["device_entities"],
                        steps, list(dict.fromkeys(analysis["uncertainties"] +
                        ["需真实台账、适用规程、现场授权与安全条件复核"])))
