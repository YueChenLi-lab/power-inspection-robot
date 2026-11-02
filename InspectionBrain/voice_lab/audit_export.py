"""Read real exports without modifying their records or pretending manual text is ASR."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

NOTES = {
    1: [("评分配置", "所选CT/PT问题与温度异常输入/参考不对应；参考未确认。")],
    2: [("意图", "隔离开关异常查询误为unknown，应请求实时状态/缺陷数据。"), ("评分配置", "参考仅设备名，不是完整朗读问题；未确认。")],
    3: [("评分配置", "参考对应问题但未确认，当前不应计分；知识回答为示例。")],
    4: [("评分配置", "question-4参考却是question-2，且不对应本次输入；未确认。")],
    5: [("术语", "绕阻温度及冷却风机、套管、高压侧接头索引覆盖不足。"), ("意图", "记录查询、测温对比、条件缺陷记录及复检建议被合并为巡检计划草案。"), ("评分配置", "长句使用question-4且参考未确认；同音纠错关闭与规则缺失并存。")],
    6: [("术语", "分和闸、祭奠保护、电流护管护感器；二次回路/零序电流/温升词组不足。供电可****性是遮蔽文本，不能擅自还原。"), ("知识相关性", "只返回局部放电定义，未覆盖开关柜状态、二次回路、保护及可靠性需求。"), ("评分配置", "长句与question-4不一致；未确认，纠错关闭。")],
    7: [("数值单位", "11000伏≠110kV；685/823/125℃与参考小数不等价；05赵帕不能猜测为0.5MPa。"), ("口语重复", "三号柜开关3号开关柜疑似重启；1号的主变为可读候选，缺音频须人工核实。"), ("编号相别", "a箱/b箱需上下文候选与确认，不能全局替换；主变序号邻接断开。"), ("评分配置", "唯一确认样本，题目ID与长参考不符。旧CER40/116→42/116，变差2字符；主变别名扩写不应改变专业实体评分。")],
    8: [("术语", "人工复合可能为人工复核，需领域上下文候选。"), ("否定意图", "不要未经授权启动机器人自主导航是禁止条件，应保留计划草案与禁止导航约束。"), ("评分配置", "参考未确认且question-4不是本长句；纠错关闭。")],
    9: [("术语", "绕阻/由窄/钨闪/抬杠/6氟化硫/道闸等候选；时千伏涉及电压等级不能自动猜成十千伏。"), ("口语重复", "变压器管套管变压器套管疑似重启，缺音频需确认。"), ("否定意图", "不能自动执行道闸操作应保留禁止语义，不能作为肯定执行请求。"), ("评分配置", "参考未确认、题目错配、纠错关闭；不能据此宣称真实ASR提升。")],
}


def audit(path, output):
    path, output = Path(path), Path(output)
    raw = path.read_bytes()
    data = json.loads(raw.decode("utf-8-sig"))
    records = data["records"] if isinstance(data, dict) else data
    if not isinstance(records, list) or not records:
        raise ValueError("真实导出中没有记录")
    expected_fields = ["original_transcript", "enhanced_text", "reference_text", "reference_confirmed",
                       "input_source", "raw_asr_text", "apply_homophones", "brain", "metrics"]
    digest = hashlib.sha256(raw).hexdigest()
    if digest!="003cadbb21918b998d0504807bc7ad24e40d6ac36dc0074160782572b0213ee5":
        raise ValueError("该逐条诊断仅针对本轮已核实的实际导出哈希；不同文件需重新人工分析，不能套用样本结论")
    rows = []
    for index, record in enumerate(records, 1):
        if any(key not in record for key in expected_fields):
            raise ValueError("实际记录字段不完整: " + str(index))
        rows.append({"index": index, "record_id": record.get("record_id"),
                     "source_sha256": digest, "observations": NOTES.get(index, []),
                     "original_record": record,
                     "classification_basis": "manual text and supplied reference; unconfirmed references are diagnostic only"})
    report = {"source": str(path.resolve()), "source_sha256": digest, "record_count": len(records),
              "sources": dict(Counter(r["input_source"] for r in records)),
              "confirmed_references": sum(r["reference_confirmed"] is True for r in records),
              "homophones_enabled": sum(r["apply_homophones"] is True for r in records),
              "real_asr_samples": sum(r.get("audio") is not None and r.get("raw_asr_text") is not None and r["input_source"] == "asr" for r in records),
              "asr_improvement": None, "records": rows}
    output.mkdir(parents=True, exist_ok=True)
    (output/"round2_error_analysis.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n")
    lines = ["# 第二轮实际测试数据错误分析", "", f"来源：`{path.resolve()}`；SHA256：`{digest}`。",
             "", f"读取{len(records)}条原始记录，所有必需字段与原brain.analysis/result、metrics保存在JSON报告。未覆盖源文件或历史记录。",
             "", "9条manual、0条音频/真实ASR，1条确认参考，9条同音纠错关闭。术语错误归因为人工导入转写候选，不归因SenseVoice。",
             "", "|条目|原始文本|错误分类与诊断|", "|---|---|---|"]
    for row in rows:
        original = row["original_record"]["original_transcript"].replace("|", "\\|")
        notes = "；".join(f"{kind}：{note}" for kind, note in row["observations"])
        lines.append(f"|{row['index']} / {row['record_id'][:8]}|{original}|{notes}|")
    lines += ["", "唯一已确认样本的旧评分为CER40/116=34.48%→42/116=36.21%，增加2个编辑字符（1.72个百分点），没有改善。其他8条不计算正式CER。",
              "", "原有词库没有上述新增混淆项，是规则缺失；apply_homophones=false又禁止应用已存在候选，是配置状态。需分开验证词库覆盖和纠错开关。",
              "", "本批记录是规则开发数据，不能用同一批调规则后报告泛化识别率。另设独立合成挑战集，实际未见语音留待用户另采；无音频不判断嘴瓢发生原因。"]
    (output/"ROUND2_ERROR_ANALYSIS.md").write_text("\n".join(lines)+"\n")
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1]/"reports")
    args = parser.parse_args()
    result = audit(args.source, args.output)
    print(json.dumps({key: result[key] for key in ("source_sha256", "record_count", "sources", "confirmed_references", "real_asr_samples")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
