"""Real WAV inference diagnostics. Never substitutes any manual text."""
import argparse
import json
from pathlib import Path
import sys
from voice_lab.asr import LocalASR
from voice_lab.audio import decode_wav

ROOT=Path(__file__).resolve().parent
MODEL=ROOT/"models"/"sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17"


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("wav",type=Path)
    parser.add_argument("--model",type=Path,default=MODEL/"model.int8.onnx")
    parser.add_argument("--tokens",type=Path,default=MODEL/"tokens.txt")
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    asr=LocalASR("sensevoice",sensevoice_model=args.model,sensevoice_tokens=args.tokens)
    try:
        audio=decode_wav(args.wav.read_bytes())
        result={"input":str(args.wav.resolve()),"input_duration":audio.duration,"original_sample_rate":audio.sample_rate,
                "asr_sample_rate":16000,"status":asr.status,"result":asr.transcribe(audio.pcm16)}
        encoded=json.dumps(result,ensure_ascii=False,indent=2)
        print(encoded)
        if args.output:args.output.write_text(encoded+"\n")
        return 0 if result["result"]["status"]=="ok" else 1
    except Exception as exc:
        print(json.dumps({"error":str(exc),"status":asr.status},ensure_ascii=False));return 1
    finally:asr.close()


if __name__=="__main__":sys.exit(main())
