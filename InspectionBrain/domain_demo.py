import argparse
import json
from inspection_brain.domain_v2.service import ElectricalBrainV2

if __name__=="__main__":
    parser=argparse.ArgumentParser(description="第二轮电力领域离线语义演示")
    parser.add_argument("text")
    parser.add_argument("--apply-homophones",action="store_true")
    args=parser.parse_args()
    print(json.dumps(ElectricalBrainV2().ask(args.text,apply_homophones=args.apply_homophones),ensure_ascii=False,indent=2))
