"""Append-only, idempotent semantic runs separate from historical voice scoring."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import threading
import uuid
from inspection_brain.service import SHANGHAI
from . import ENGINE_VERSION
from .evaluation import runtime_summary


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()).hexdigest()


class SemanticStore:
    def __init__(self, storage, engine):
        self.directory = Path(storage)/"semantic_v3"
        # Create lazily, so installing v3 doesn't touch existing runtime data.
        self.engine = engine
        self.lock = threading.RLock()

    def records(self):
        with self.lock:
            return [json.loads(p.read_text()) for p in sorted(self.directory.glob("*.json"))]

    def analyze(self, original, *, source, audio=None, mode="v2_rules", apply_homophones=False,
                dialogue_context=None, now=None):
        context = dialogue_context or []
        now = now or datetime.now(SHANGHAI)
        if now.tzinfo is None:
            raise ValueError("参考时间须包含时区")
        provenance = {"audio_id": (audio or {}).get("audio_id"), "audio_sha256": (audio or {}).get("sha256"),
            "asr_model_id": ((audio or {}).get("asr") or {}).get("model_id") if source == "asr" else None,
            "asr_model_version": ((audio or {}).get("asr") or {}).get("model_version") if source == "asr" else None,
            "original_sha256": hashlib.sha256(original.encode()).hexdigest(), "input_source": source,
            "mode": mode, "apply_homophones": apply_homophones, "dialogue_context_sha256": digest(context),
            "lexicon_version": self.engine.brain.normalizer.version, "lexicon_sha256": self.engine.brain.normalizer.sha256,
            "engine_version": ENGINE_VERSION, "provider": self.engine.provider.status(),
            "provider_configuration_sha256": self.engine.config.sha256,
            # Relative calendar constraints are re-evaluated on each new local day.
            "reference_date": now.astimezone(SHANGHAI).date().isoformat()}
        key = digest(provenance)
        with self.lock:
            existing = next((r for r in self.records() if r["analysis_key"] == key), None)
            # Don't cache an outage/rejection permanently: same request may retry.
            if existing and existing["result"]["status"] in ("validated_candidate", "v2_only"):
                return existing
            result = self.engine.analyze(original, mode=mode, now=now, apply_homophones=apply_homophones, dialogue_context=context)
            record = {"record_id": uuid.uuid4().hex, "created_at": datetime.now(SHANGHAI).isoformat(),
                      "schema_version": "semantic-run-v1", "analysis_key": key,
                      "input_source": source, "original_transcript": original,
                      "provenance": provenance, "result": result, "executed_actions": [],
                      "hardware_commands_enabled": False}
            self.directory.mkdir(parents=True, exist_ok=True)
            with (self.directory/(record["record_id"]+".json")).open("x", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2, allow_nan=False)
            return record

    def export(self):
        records = self.records()
        return {"schema_version": "semantic-export-v1", "records": records, "summary": runtime_summary(records),
                "historical_voice_records_untouched": True}
