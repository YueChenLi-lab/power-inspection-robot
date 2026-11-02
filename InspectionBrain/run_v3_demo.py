#!/usr/bin/env python3
"""Independent text semantic demonstration; default offline Mock, no audio/model install."""
import argparse
import json
from brain_v3.config import ProviderConfig
from brain_v3.engine import SemanticEngine


def main():
    parser = argparse.ArgumentParser(description="v3只读语义草案演示（Mock非真实LLM）")
    parser.add_argument("text", nargs="?", default="制定巡检计划，但不要启动导航")
    parser.add_argument("--provider", choices=("mock", "rules", "configured"), default="mock")
    parser.add_argument("--mode", choices=("v2_rules", "v3_llm", "auto_fallback"), default="v3_llm")
    parser.add_argument("--homophones", action="store_true")
    args = parser.parse_args()
    config = ProviderConfig.from_environment() if args.provider == "configured" else ProviderConfig(provider=args.provider)
    print(json.dumps(SemanticEngine(config=config).analyze(args.text, mode=args.mode, apply_homophones=args.homophones), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
