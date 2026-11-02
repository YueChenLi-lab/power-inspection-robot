"""Explicit real-model smoke / offline contract evaluation. No hardware imports."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"InspectionBrain"))
from brain_v3.config import ProviderConfig
from brain_v3.engine import SemanticEngine
from brain_v3.schema import schema_errors
from brain_v3.validator import SemanticValidator

CASES = ["查询3号断路器的上周告警。", "不是2号断路器，是3号断路器。查询上周告警，但不要启动机器人。",
         "查询3号断路器上周的红外测温记录，比较最近两次测温结果。"]


class TimedValidator(SemanticValidator):
    def validate(self, candidate, evidence):
        start = time.perf_counter()
        errors = schema_errors(candidate)
        schema_time = time.perf_counter()-start
        start = time.perf_counter()
        result = super().validate(candidate, evidence)
        self.timings = {"schema_seconds": schema_time, "evidence_semantic_seconds": time.perf_counter()-start,
                        "schema_valid": not errors}
        return result


def evaluate(config):
    engine = SemanticEngine(config=config)
    engine.validator = TimedValidator()
    rows = []
    for text in CASES:
        result = engine.analyze(text, mode="v3_llm", now=datetime.fromisoformat("2026-11-02T12:00:00+08:00"))
        rows.append({"input": text, "result": result, "timings": getattr(engine.validator, "timings", {}),
                     "provider_timings": getattr(engine.provider, "timings", {}),
                     "raw_response": getattr(engine.provider, "last_response", None)})
    return rows


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mock", action="store_true")
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    config = ProviderConfig(provider="mock") if a.mock else ProviderConfig.from_environment()
    if not a.mock and (config.provider != "ollama" or not config.enabled):
        p.error("真实smoke要求BRAIN_V3_PROVIDER=ollama且BRAIN_V3_ENABLE_LLM=true")
    rows = evaluate(config)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    # Explicit private diagnostics export; caller must choose a non-public path.
    a.output.write_text(json.dumps({"mock_http": False, "rows": rows}, ensure_ascii=False, indent=2))
    print(json.dumps({"samples": len(rows), "accepted": sum(r["result"]["status"] == "validated_candidate" for r in rows),
                      "real_model_requested": not a.mock}))
    return 0 if all(r["result"]["status"] == "validated_candidate" for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
