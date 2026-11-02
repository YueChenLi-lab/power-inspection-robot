export const dimensionLabels = {intents:'意图', equipment_relations:'设备关系', numeric_relations:'数值与单位', negations:'否定', self_corrections:'自我修正', temporal_constraints:'时间', task_dependencies:'依赖'};
export function formatRate(metric) { return metric?.value == null ? '未评 / 无样本' : `${(metric.value * 100).toFixed(1)}% (${metric.numerator}/${metric.denominator})`; }
export function annotationValue(text) { return text === 'true' ? true : text === 'false' ? false : null; }
export function makeClient(fetcher, token = () => '') {
  return async (path, body) => {
    const response = await fetcher(path, body === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json','X-Evaluation-Token':token()}, body:JSON.stringify(body)});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
    return result;
  };
}
export function requestFromState(state) {
  const result = {provider:state.provider, model:state.model};
  if (state.reference) result.reference_time = state.reference;
  if (state.selectedCase && state.text === state.selectedCase.original_request) result.case_id = state.selectedCase.case_id;
  else result.original_request = state.text;
  return result;
}
export function createUI(doc, fetcher = globalThis.fetch.bind(globalThis), pause = ms => new Promise(resolve => setTimeout(resolve,ms))) {
  const $ = id => doc.getElementById(id);
  const node = (tag,text) => { const n = doc.createElement(tag); if (text !== undefined) n.textContent = String(text); return n; };
  let csrf = '', cases = [], knownModels = [], selectedRecord = null, currentBatch = null;
  const api = makeClient(fetcher,() => csrf);
  const notify = (text,error = false) => { $('notice').textContent = text; $('notice').dataset.error = String(error); };
  const guarded = action => async () => { try { await action(); } catch (error) { notify(error.message,true); } };
  function busy(value) { $('run').disabled=value; $('run-batch').disabled=value; }
  function option(select,value,label) { const o=node('option',label);o.value=value;select.append(o); }
  function renderConfig(config) {
    const status=config.status; $('connection').textContent=status.connected === true ? `已连接 · Ollama ${status.version}` : status.connected === false ? '不可用' : '未检查';
    $('connection').dataset.state=status.connected === true ? 'connected' : status.connected === false ? 'error' : '';
    const rows = [['Provider',config.provider],['Schema',config.schema_version],['Prompt',config.prompt_version],['配置',JSON.stringify(config.configuration)],['最近请求',config.last_request_time || '尚未请求'],['状态',status.error || '本地服务可访问']];
    $('model-status').replaceChildren();
    for (const [key,value] of rows) $('model-status').append(node('dt',key),node('dd',value));
  }
  function currentModel() {
    const m=knownModels.find(m => m.name === $('model').value);
    $('selected-model-info').textContent=m ? `当前选择：${m.name} / 摘要 ${m.digest || '不可用'} / ${JSON.stringify(m.details || {})}` : '尚未选择已安装模型';
  }
  async function checkModels() {
    const previous=$('model').value;const config=await api('/api/models/check',{});renderConfig(config);
    $('model').replaceChildren();option($('model'),'','请选择已安装模型');
    for (const m of config.status.models) option($('model'),m.name,`${m.name} · ${m.digest?.slice(0,14) || '摘要不可用'}`);
    knownModels=config.status.models;const available = knownModels.map(m => m.name);
    $('model').value=available.includes(previous) ? previous : available.includes(config.default_model) ? config.default_model : '';
    currentModel();notify(config.status.connected ? `发现 ${available.length} 个本地模型；未自动下载模型` : config.status.error,!config.status.connected);
  }
  function state() {return {provider:$('provider').value,model:$('model').value,text:$('input').value,reference:$('reference-time').value,selectedCase:cases.find(c => c.case_id === $('case').value)};}
  function detail(title,value,open=false) {const d=node('details');d.open=open;d.append(node('summary',title),node('pre',typeof value === 'string' ? value : JSON.stringify(value,null,2)));return d;}
  function renderRecord(record,target=$('layers')) {
    target.replaceChildren();
    for (const [title,value] of [['A · 原始输入',{text:record.original_request,reference_time:record.reference_time}],['B · 模型响应（thinking 已剔除）',{source:record.source,model:record.model_name,model_version:record.model_version,latency:record.latency,token_metrics:record.token_metrics,raw_response:record.raw_response,reasoning_redacted:record.reasoning_redacted}],['解析后的 JSON',record.parsed_json],['C · 请求 / JSON 解析 / Schema',{request:record.request_result,parse:record.parse_result,schema:record.schema_result}],['D · 独立工程证据检查',record.evidence_result],['完整 Evidence / Semantic Validator',record.validator_result],['E · SafetyGuard',record.safety_result],['F · 不可执行任务草案',record.task_draft]]) target.append(detail(title,value,title.startsWith('C') || title.startsWith('F')));
  }
  function showRecord(record) {
    $('outcome').textContent=record.outcome;$('outcome').dataset.state=record.outcome;
    $('result-source').textContent=`${record.source} · ${record.model_name || '未选择模型'} · ${record.evaluation_id} · ACCEPTED 仅为工程校验`;
    renderRecord(record);
  }
  async function run() {
    busy(true);$('outcome').textContent='运行中';$('outcome').dataset.state='';$('result-source').textContent='当前请求尚无结果';$('layers').replaceChildren();notify('正在执行，所有结果将作为独立记录保存…');
    try { const record=await api('/api/evaluate',requestFromState(state()));showRecord(record);renderConfig(await api('/api/config'));notify(`记录已保存：${record.outcome}`,record.outcome === 'PROVIDER_ERROR'); }
    catch (error) { $('outcome').textContent='请求未完成';$('outcome').dataset.state='error';throw error; }
    finally { busy(false); }
  }
  async function runBatch() {
    const ids=[...$('batch-cases').querySelectorAll('input')].filter(n => n.checked).map(n => n.value);
    const data={case_ids:ids,provider:$('provider').value,model:$('model').value};
    if ($('reference-time').value) data.reference_time=$('reference-time').value;
    busy(true);
    try {
      let batch=await api('/api/batches',data);currentBatch=batch.batch_id;$('batch-results').replaceChildren();let rendered=0;
      while (true) {
        $('batch-progress').max=batch.total;$('batch-progress').value=batch.completed;
        $('batch-state').textContent=`${batch.status} · ${batch.completed}/${batch.total}`;
        for (const id of batch.evaluation_ids.slice(rendered)) {const r=await api(`/api/records/${encodeURIComponent(id)}`);$('batch-results').append(node('p',`${r.case_id} · ${r.source} · ${r.outcome}`));rendered++;}
        if (batch.status !== 'RUNNING') {if (batch.error) notify(batch.error,true);else notify('批量完成；每条结果已独立保存');break;}
        await pause(350);batch=await api(`/api/batches/${encodeURIComponent(currentBatch)}`);
      }
    } finally {busy(false);}
  }
  function table(headers,rows) {const wrap=node('div');wrap.className='table-wrap';const t=node('table'),head=node('tr');for (const h of headers) head.append(node('th',h));t.append(head);for (const row of rows) {const tr=node('tr');for (const value of row) {const td=node('td');typeof value === 'object' && value?.nodeType ? td.append(value) : td.textContent=String(value ?? '—');tr.append(td);}t.append(tr);}wrap.append(t);return wrap;}
  async function statistics() {
    const data=await api('/api/statistics');$('statistics').replaceChildren();
    if (!data.groups.length) {$('statistics').append(node('p','暂无记录。没有用预填数据生成指标。'));return;}
    for (const g of data.groups) {
      const box=node('article');box.append(node('h3',`${g.source} · ${g.model_name || '未选择模型'} · ${g.model_version}`));const m=g.metrics;
      box.append(node('p',`配置 ${g.configuration_sha256.slice(0,12)} / ${g.schema_version} / ${g.prompt_version}`));const grid=node('div');grid.className='metric-grid';
      for (const [label,metric] of [['请求成功',m.request_success_rate],['JSON 解析',m.json_parse_rate],['Schema',m.schema_pass_rate],['完整 Validator',m.validator_acceptance_rate],['人工证据一致性',m.human_evidence_consistency],['人工语义准确率',m.semantic_accuracy]]) {const c=node('div');c.className='metric';c.append(node('small',label),node('strong',formatRate(metric)));grid.append(c);}box.append(grid);
      box.append(node('p',`端到端耗时：平均 ${m.latency.average_ms?.toFixed(2) ?? '—'} ms / P50 ${m.latency.p50_ms?.toFixed(2) ?? '—'} ms / P95 ${m.latency.p95_ms?.toFixed(2) ?? '—'} ms；N=${m.latency.sample_count}。${m.latency.p95_note}`));
      box.append(table(['端到端耗时区间 ms','样本数'],m.latency.histogram.map(b => [`${b.low_ms.toFixed(2)}–${b.high_ms.toFixed(2)}`,b.count])));
      box.append(node('p',`真实回退次数 ${m.fallback_count}；候选安全违规 ${m.safety_violation_count}。RULES 为显式对照时不计作自动回退。`));
      box.append(table(['类别','N','请求成功','Schema','Validator','人工语义'],Object.entries(g.categories).map(([name,v]) => [name,v.samples,formatRate(v.request_success_rate),formatRate(v.schema_pass_rate),formatRate(v.validator_acceptance_rate),formatRate(v.semantic_accuracy)])));
      box.append(detail('工程证据指标 / 失败计数', {engineering_evidence:m.engineering_evidence_constraint_rate,failures:m.failure_counts,outcomes:m.outcomes}));
      $('statistics').append(box);
    }
  }
  function filters() {const q=new URLSearchParams();if ($('history-source').value) q.set('source',$('history-source').value);if ($('history-category').value) q.set('category',$('history-category').value);return q;}
  async function history() {
    const q=filters();const data=await api('/api/records?'+q);$('history').replaceChildren();
    $('history').append(table(['时间','来源 / 模型','类别','结果','操作'],data.records.map(r => {const b=node('button','详情 / 标注');b.addEventListener('click',guarded(() => openAnnotation(r.evaluation_id)));return [r.timestamp,`${r.source} / ${r.model_name}`,r.category,r.outcome,b];})));
    for (const kind of ['json','csv','markdown']) {const params=new URLSearchParams(q);params.set('format',kind);$('export-'+kind).href='/api/export?'+params;}
  }
  async function openAnnotation(id) {
    const r=await api(`/api/records/${encodeURIComponent(id)}`);selectedRecord=id;$('annotation-panel').hidden=false;$('annotation-record').textContent=`${r.source} · ${r.model_name} · ${r.original_request}`;renderRecord(r,$('annotation-detail'));
    const reference=cases.find(c => c.case_id === r.case_id);if(reference) $('annotation-detail').append(detail('独立用例期望（pending，不是已确认Gold，未发送给模型）',{expected:reference.expected,must_preserve:reference.must_preserve,must_not:reference.must_not,annotation_status:reference.annotation_status}));
    $('annotation-confirmed').checked=false;$('annotation-evidence').value=r.annotation?.evidence_consistent == null ? '' : String(r.annotation.evidence_consistent);$('annotator').value=r.annotation?.annotator || '';$('annotation-notes').value=r.annotation?.notes || '';
    for (const key of Object.keys(dimensionLabels)) $('dimension-'+key).value=r.annotation?.semantic_dimensions?.[key] == null ? '' : String(r.annotation.semantic_dimensions[key]);
    $('save-annotation').disabled=r.parse_result.passed !== true;
  }
  async function saveAnnotation() {
    if (!selectedRecord) throw new Error('先选择记录');
    const dimensions={};for (const key of Object.keys(dimensionLabels)) dimensions[key]=annotationValue($('dimension-'+key).value);
    await api(`/api/annotations/${selectedRecord}`,{annotator:$('annotator').value,confirmed:$('annotation-confirmed').checked,evidence_consistent:annotationValue($('annotation-evidence').value),semantic_dimensions:dimensions,notes:$('annotation-notes').value});notify('人工标注已追加保存，未修改模型结果或数据集参考答案');
  }
  async function init() {
    const [config,dataset]=await Promise.all([api('/api/config'),api('/api/dataset')]);csrf=config.csrf_token;cases=dataset.cases;renderConfig(config);
    for (const c of cases) {option($('case'),c.case_id,`${c.case_id} · ${c.category}`);const label=node('label');label.className='check';const input=node('input');input.type='checkbox';input.checked=true;input.value=c.case_id;label.append(input,node('span',`${c.case_id} · ${c.category} · 标注 ${c.annotation_status}`));$('batch-cases').append(label);}
    for (const category of [...new Set(cases.map(c => c.category)),'手动输入']) option($('history-category'),category,category);
    for (const [key,label] of Object.entries(dimensionLabels)) {const l=node('label',label),select=node('select');select.id='dimension-'+key;for (const [v,t] of [['','未评'],['true','正确'],['false','错误']]) option(select,v,t);l.append(select);$('annotation-dimensions').append(l);}
    $('case').addEventListener('change',() => {const c=cases.find(c => c.case_id === $('case').value);if (c) $('input').value=c.original_request;});
    $('model').addEventListener('change',currentModel);
    $('check-models').addEventListener('click',guarded(checkModels));$('run').addEventListener('click',guarded(run));$('run-batch').addEventListener('click',guarded(runBatch));$('refresh-statistics').addEventListener('click',guarded(statistics));$('refresh-history').addEventListener('click',guarded(history));$('history-source').addEventListener('change',guarded(history));$('history-category').addEventListener('change',guarded(history));$('save-annotation').addEventListener('click',guarded(saveAnnotation));
    for (const button of doc.querySelectorAll('[data-tab]')) button.addEventListener('click',guarded(async () => {for (const page of doc.querySelectorAll('.page')) page.hidden=page.id !== 'page-'+button.dataset.tab;for (const tab of doc.querySelectorAll('[data-tab]')) tab.setAttribute('aria-selected',String(tab === button));if (button.dataset.tab === 'statistics') await statistics();if (button.dataset.tab === 'history') await history();}));
    return config;
  }
  return {init,run,runBatch,statistics,history,checkModels,openAnnotation,saveAnnotation,renderRecord};
}
if (typeof document !== 'undefined') createUI(document).init().catch(error => {const n=document.getElementById('notice');n.textContent=error.message;n.dataset.error='true';});
