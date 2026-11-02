import argparse
from datetime import datetime
import json
import os

from .routing import MockLegacyDispatcher, OfflineRouter
from .service import InspectionBrain, SHANGHAI, DEFAULT_DATA

DEMO_QUESTIONS = ["电流互感器和电压互感器有什么区别？", "变压器巡检一般检查哪些项目？",
                  "什么是局部放电？", "检查一号变压器需要哪些信息？", "一号主变最近有没有温度异常？"]


def main(argv=None):
    parser = argparse.ArgumentParser(description="InspectionBrain离线电力领域演示（无硬件接口）")
    parser.add_argument("text", nargs="?")
    parser.add_argument("--demo", action="store_true", help="输出五个示例问题")
    parser.add_argument("--interactive", action="store_true", help="输入exit退出，Ctrl+C停止")
    parser.add_argument("--route", action="store_true", help="演示旧系统优先的离线路由")
    parser.add_argument("--enable-brain", action="store_true", help="仅在模拟路由启用Brain，默认关闭")
    parser.add_argument("--apply-homophones", action="store_true", help="只对允许的只读问题应用白名单同音词")
    parser.add_argument("--at", help="确定性参考时间，ISO8601必须带时区")
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA))
    parser.add_argument("--summary", action="store_true", help="简洁展示；默认输出完整结构化JSON")
    args = parser.parse_args(argv)
    try:
        now = datetime.fromisoformat(args.at) if args.at else datetime.now(SHANGHAI)
        if now.tzinfo is None:
            parser.error("--at必须包含时区，如2026-10-08T12:00:00+08:00")
        enabled = args.enable_brain or os.environ.get("INSPECTION_BRAIN_ENABLED", "0") == "1"
        brain = None
        if not args.route:
            brain = InspectionBrain(args.data_dir)
        elif enabled:
            try:
                brain = InspectionBrain(args.data_dir)
            except (ValueError, OSError, KeyError, TypeError):
                # Startup failure in the optional component must not prevent
                # the offline old-path demonstration from accepting raw text.
                brain = None
        router = OfflineRouter(MockLegacyDispatcher(), brain, enabled=enabled)
        def emit(text):
            result = router.route(text, now=now, apply_homophones=args.apply_homophones) if args.route else brain.ask(text, now=now, apply_homophones=args.apply_homophones)
            if args.summary and not args.route:
                answer = result["result"]
                print("问题：" + text)
                print("规范化：" + result["analysis"]["normalization"]["normalized_text"])
                print("意图：" + result["analysis"]["intent"] + "；结果：" + answer["status"])
                print(answer["answer"])
                for citation in answer["citations"]:
                    print("来源：["+citation["chunk_id"]+"] "+citation["source"]["uri"]+"（示例）")
                if answer.get("notice"):
                    print(answer["notice"])
                if result["analysis"]["uncertainties"]:
                    print("待确认：" + "；".join(result["analysis"]["uncertainties"]))
                print()
            else:
                print(json.dumps(result, ensure_ascii=False, indent=2))
        try:
            if args.demo:
                for question in DEMO_QUESTIONS:
                    emit(question)
            elif args.text:
                emit(args.text)
            elif args.interactive:
                while True:
                    try:
                        question = input("电力巡检（离线）> ")
                    except EOFError:
                        break
                    if question.strip().lower() in {"exit", "quit"}:
                        break
                    if question.strip():
                        try:
                            emit(question)
                        except ValueError as error:
                            print(json.dumps({"error": str(error)}, ensure_ascii=False))
            else:
                parser.print_help()
        finally:
            router.close()
    except (ValueError, OSError) as error:
        parser.error(str(error))
    except KeyboardInterrupt:
        return 130
    return 0
