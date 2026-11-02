#!/usr/bin/env python3
"""Generate pending development manifest OR evaluate independently annotated texts."""
import argparse
from datetime import datetime
import json
from pathlib import Path
from brain_v3.config import ProviderConfig
from brain_v3.engine import SemanticEngine
from brain_v3.evaluation import development_manifest, evaluate_result, comparison_summary
from inspection_brain.service import SHANGHAI


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--storage", type=Path, default=Path(__file__).parent/"runtime/voice_lab")
    parser.add_argument("--annotations", type=Path)
    parser.add_argument("--manifest", type=Path, help="去重真实音频清单；仅重新分析已存转写，不重新识别")
    parser.add_argument("--reference-time", default=None, help="有时区的ISO时间；清单分析的时间解析锚点")
    parser.add_argument("--provider", choices=("mock", "rules", "configured"), default="mock")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("输出文件已存在；请使用新文件名保留历史报告")
    if args.annotations and args.manifest:
        parser.error("annotations和manifest只能选择一种")
    if args.annotations or args.manifest:
        config = ProviderConfig.from_environment() if args.provider == "configured" else ProviderConfig(provider=args.provider)
        engine = SemanticEngine(config=config)
        data = json.loads((args.annotations or args.manifest).read_text())
        rows = []
        for sample in data["samples"]:
            if args.manifest:
                variants = [v for v in sample["transcript_variants"] if v.get("engine") == "sensevoice"]
                if not variants:
                    rows.append({"sample_id":sample["sample_id"],"skipped":True,"reason":"没有已保存真实SenseVoice转写"})
                    continue
                text = variants[0]["original_request"]
                now = datetime.fromisoformat(args.reference_time) if args.reference_time else datetime.now(SHANGHAI)
            else:
                text = sample["original_request"]
                now = datetime.fromisoformat(sample["reference_time"])
            result = engine.analyze(text, mode="auto_fallback", now=now)
            rows.append({"sample_id": sample["sample_id"], "dataset_role": sample["dataset_role"],
                         "audio_sha256":sample.get("audio_sha256"),
                         "result": result, "metrics": evaluate_result(result, sample.get("semantic_annotation"))})
        report = {"evaluation_kind": "development_semantic_NOT_ASR_CER", "results": rows,
                  "comparison_summary":comparison_summary(rows),
                  "input_kind":"stored_real_asr_transcripts_NO_AUDIO_RERUN" if args.manifest else "independent_handwritten_annotations",
                  "real_llm_connected": any(r.get("result",{}).get("provider",{}).get("is_real_llm") and r["result"]["status"] == "validated_candidate" for r in rows)}
    else:
        report = development_manifest(args.storage)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(args.output)


if __name__ == "__main__":
    main()
