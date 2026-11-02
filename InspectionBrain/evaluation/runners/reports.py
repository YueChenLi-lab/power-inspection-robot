"""Private immutable JSONL originals, atomic derived local views."""
import csv
import io
import json
import os
from pathlib import Path
import uuid
from ..metrics.evaluator import summarize


def encode(value):return json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)


def atomic(path,text):
    path=Path(path);temp=path.with_name('.'+path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with temp.open('x',encoding='utf-8') as f:f.write(text);f.flush();os.fsync(f.fileno())
        os.replace(temp,path)
    finally:
        if temp.exists():temp.unlink()


def append_record(path,record):
    with Path(path).open('a',encoding='utf-8') as f:
        f.write(json.dumps(record,ensure_ascii=False,allow_nan=False)+'\n');f.flush();os.fsync(f.fileno())


def load_records(path,identifier='case_id'):
    path=Path(path)
    if not path.exists():return []
    rows=[]
    with path.open(encoding='utf-8') as f:
        for line in f:
            try:rows.append(json.loads(line))
            except json.JSONDecodeError:raise ValueError(path.name+' has a truncated/corrupt line; original retained, repair from verified bytes before resume') from None
    if len({r[identifier] for r in rows})!=len(rows):raise ValueError('duplicate '+identifier+' in journal')
    return rows


def write_reports(folder,records,cases,status,*,warmup=None):
    folder=Path(folder);metrics=summarize(records,cases)
    metrics['completed_sample_call_attempts']=metrics['real_model_call_attempts']
    metrics['real_model_call_attempts_including_warmup']=metrics['real_model_call_attempts']+(warmup['real_model_call_attempts'] if warmup else 0)
    attempts=load_records(folder/'request_attempts.jsonl',identifier='attempt_id')
    finished_ids={r.get('http',{}).get('attempt_id') for r in records}
    if warmup:finished_ids.add(warmup.get('http',{}).get('attempt_id'))
    metrics['request_attempt_records']=len(attempts)
    metrics['incomplete_attempt_records']=sum(a['attempt_id'] not in finished_ids for a in attempts)
    if attempts:
        real=[a for a in attempts if a['source']=='REAL_OLLAMA']
        metrics['real_model_call_attempts']=sum(a['phase']=='sample' for a in real)
        metrics['real_model_call_attempts_including_warmup']=len(real)
        unknown=sum(a['phase']=='sample' and a['attempt_id'] not in finished_ids for a in real)
        metrics['incomplete_real_sample_attempts']=unknown
        if unknown:
            for key in ('api_success_rate','model_response_rate','timeout_rate'):
                rate=metrics[key];denominator=metrics['real_model_call_attempts']
                metrics[key]={**rate,'value':None,'denominator':denominator,'unknown_outcomes':unknown,
                              'lower_bound':rate['numerator']/denominator,'upper_bound':(rate['numerator']+unknown)/denominator,
                              'note':'中断尝试结果未知，给出范围而非把未知标为成功/失败'}
    metrics['call_accounting_note']='request_attempts.jsonl在HTTP打开前持久化，包含中断尝试；不保证请求已到达模型服务。目录GET不计推理。'
    atomic(folder/'raw_results.json',encode(records))
    atomic(folder/'metrics.json',encode(metrics))
    atomic(folder/'run_status.json',encode(status))
    failed=[{'case_id':r['case_id'],'failure_stage':r['failure_stage'],'error':r['error'],'schema_errors':r['schema_errors'],'validator_errors':r['validator'].get('errors',[]),'expected_decision':r['expected_decision'],'expected_rejection_or_review':r['reference_checks'].get('decision_note')=='expected_rejection_or_review','capability_boundary':next(c['capability_boundary'] for c in cases if c['case_id']==r['case_id'])} for r in records if r['failure_stage']]
    if status.get('blocker'):failed.insert(0,{'run_level_blocker':status['blocker'],'not_a_model_sample':True})
    atomic(folder/'failures.json',encode(failed))
    stream=io.StringIO();writer=csv.writer(stream)
    writer.writerow(['case_id','category','source','engine_status','failure_stage','http_status','json_parse','schema_pass','validator_accept','latency_seconds','human_gold_confirmed','manual_review','error'])
    def cell(value):
        value='' if value is None else str(value)
        return "'"+value if value.lstrip().startswith(('=','+','-','@')) else value
    for r in records:writer.writerow([cell(v) for v in [r['case_id'],r['category'],r['source'],r['engine_status'],r['failure_stage'],r['http'].get('status'),r['diagnostics'].get('json_parse_success'),None if r['schema_errors'] is None else not r['schema_errors'],r['validator'].get('valid'),r['latency_seconds'],r['reference_checks']['human_confirmed'],bool(r['reference_checks']['manual_review_reasons']),r['error']]])
    atomic(folder/'results.csv','\ufeff'+stream.getvalue())
    metadata=json.loads((folder/'metadata.json').read_text())
    lines=['# InspectionBrain v3 本地评测报告','',f"状态：{status['status']}",'',
           '本目录为私人本地记录，不提交GitHub。Mock/契约测试不能冒充真实模型；Schema/Validator通过不等于语义或现场事实正确。','',
           f"实际完整样本：{len(records)}；规划样本：{len(cases)}；真实推理API尝试：{metrics['real_model_call_attempts']}。",'',
           '## 创建时运行环境（后续观测见session文件与逐条observed_model）','', '```json',encode(metadata['observed_environment']),'```','',
           '## 分类','', '| 类别 | 规划 | 完成 | Validator接受 |','|---|---|---|---|']
    for key,row in metrics['by_category'].items():lines.append(f"| {key} | {row['planned']} | {row['completed']} | {row['validated']} |")
    lines+=['','拒绝案例保留为诊断，不全部代表测试失败；预期拒绝或澄清的样本不计正常接受失败。COMPLETED/exit0仅表示计划样本已记录，不代表模型通过。', '', '## 指标与分母','', '```json',encode(metrics),'```','',
            'API成功按实际HTTP状态/实际推理调用；完整响应、解析、Schema、Validator逐层使用对应分母。正常草案接受仅包含预期allow_draft样本。预期拒绝/澄清不当作正常接受失败；需要人工判断的决定不自动评分。','',
            '语义分数只统计明确人工确认、可按现Schema比较的维度；pending参考仅提供逐条临时匹配，不能算人工准确率。未知/不支持字段记人工复核，不为迁就用例改协议。','',
            'Warm-up不计入语义样本、延迟分布或调用成功率。Ollama load_duration为原生纳秒转毫秒，另记录第一次warm-up。','']
    if warmup:lines+=['## Warm-up（独立）','',f"状态：{warmup['engine_status']}；加载耗时：{warmup['ollama_metrics']['load_duration_ms']} ms；真实调用尝试：{warmup['real_model_call_attempts']}。",'']
    if status.get('blocker'):lines+=['## 阻塞','',str(status['blocker']),'']
    for title,items in [('典型工程接受（非执行）',[r for r in records if r['engine_status']=='validated_candidate'][:3]),('典型失败',[r for r in records if r['failure_stage']][:3])]:
        lines+=['## '+title,'']
        if not items:lines+=['无可报告的实际样本；不是预填成功或失败。','']
        for r in items:lines+=[f"- {r['case_id']} / {r['source']} / {r['engine_status']} / {r['failure_stage'] or '当前合同通过'}：{r['error'] or '草案不可执行，人工语义确认独立。'}"]
    lines+=['','## 边界与下一步','',
            '没有真实台账或硬件执行；不训练、不微调、不使用云端模型。当前合同可能无法表示某些口语、比较运算或关系；按能力边界复核，不降低Schema或绕过Guard。','',
            '若服务阻塞，先在同一WSL/Windows环境确认 /api/version 和 /api/tags，再运行10条试验。只有健康的真实pilot报告才能作为60条运行的前置条件。没有原始0/3错误元数据时，不猜根因。']
    atomic(folder/'evaluation_report.md','\n'.join(lines)+'\n')
    return metrics
