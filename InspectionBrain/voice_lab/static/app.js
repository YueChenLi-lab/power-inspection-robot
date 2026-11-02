import {resample, pcmWav, mergeChunks, base64} from './audio.js';

const $ = id => document.getElementById(id);
let config, audio = null, busy = false, recorder = null, audioURL = null;
let derivedFrom = null;
let currentRecord = null, analysisSignature = null;
let semanticPanel = null;
const accepted = new Set(), rejected = new Set();
const show = (id, value) => { $(id).textContent = typeof value === 'string' ? value : JSON.stringify(value, null, 2); };
const message = value => show('message', value);
const score = value => value === null || value === undefined ? '无分母' : (value * 100).toFixed(2) + '%';
const hasASRText = () => audio?.asr?.status === 'ok' && typeof audio.asr.text === 'string' && !!audio.asr.text.trim();
const seconds = (value, digits) => value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value)) ? Number(value).toFixed(digits) + ' 秒' : '未提供';
function controls() {
  $('record-start').disabled = busy || !!recorder || !config;
  $('record-stop').disabled = !recorder || busy;
  for (const id of ['wav-file', 'evaluate', 'input-source', 'manual', 'homophones', 'question', 'reference', 'reference-confirmed', 'copy-reference']) $(id).disabled = busy || !!recorder || !config;
  $('input-source').querySelector('option[value="asr"]').disabled = !hasASRText();
  $('analyze-asr').disabled = busy || !!recorder || !config || !hasASRText() || !audio.audio_id;
  $('analyze-text').disabled = busy || !!recorder || !config || !$('manual').value.trim();
  $('retranscribe').disabled=busy || !!recorder || !audio || !config;
}
function signature(source) {
  return JSON.stringify([source,audio?.audio_id || '',source==='asr'?audio?.asr.text:$('manual').value,
    config?.lexicon?.loaded_sha256,config?.domain_version,$('homophones').checked,[...accepted].sort(),[...rejected].sort()]);
}
function versionStatus(status = config?.lexicon) {
  if (!status) {show('version-status','服务未提供词库自检信息，请 Ctrl+C 重启 InspectionBrain 测试台并刷新页面；不能据磁盘文件推断实际运行版本。');return;}
  show('version-status',`实际运行词库：${status.loaded_version}\nSHA256：${status.loaded_sha256 || '未提供'}\n文件：${status.path || '未提供'}\n${status.restart_required ? '磁盘词库与运行版本不同 / 文件不可读，需要重启 InspectionBrain 测试台。磁盘版本：'+(status.disk_version || '未知') : '运行版本与磁盘一致。'}`);
}
function scoringState() {
  const text=$('reference').value.trim(), confirmed=$('reference-confirmed').checked;
  show('reference-stage',!text?'尚未输入人工标准文本':confirmed?'人工标准文本已确认':'人工标准文本待核实确认');
  const valid=currentRecord?.metrics.eligible && confirmed && currentRecord.input_source===$('input-source').value && currentRecord.reference_text===$('reference').value && analysisSignature===signature(currentRecord.input_source);
  const reason=!text?'尚未输入人工标准文本':!confirmed?'人工标准文本尚未勾选确认':'当前配置 / 参考尚未评分';
  show('score-stage',valid?'评分完成':!text || !confirmed?`未计分：尚未确认人工标准文本（${reason}）`:'参考已确认，可直接评分保存，无需重新录音');
  if (currentRecord) {
    show('metrics',`${valid?'本次评分完成':'当前未计分：'+reason+'；以下为已保存记录的结果，不代表修改后的配置'}\n${currentRecord.input_source==='asr'?'实际本地 ASR':'人工 / 外部转写，独立统计'}\n${metricSummary(currentRecord.metrics)}`+
      (currentRecord.cleaned_display_metrics?'\n\n仅可读文本对照（不是模型输出改善）：\n'+metricSummary(currentRecord.cleaned_display_metrics):''));
  }
}
async function api(path, payload) {
  const options = payload === undefined ? {} : {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Voice-Lab-Token': config.csrf_token}, body: JSON.stringify(payload)};
  const response = await fetch(path, options);
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || '请求失败');
  return body;
}
function resetResults() {
  semanticPanel?.invalidate();
  audio = null;
  currentRecord=null;analysisSignature=null;
  derivedFrom=null;accepted.clear();rejected.clear();$('candidates').replaceChildren();
  $('reference-confirmed').checked=false;
  $('input-source').value = 'manual';
  show('raw-asr', config?.asr.configured ? '等待本次音频转写。' : 'ASR 未配置：没有实际识别结果。');
  for (const id of ['original-input', 'enhanced', 'cleaned', 'trace', 'numbers', 'normalization', 'entities', 'intent', 'metrics']) show(id, '尚未分析。');
  show('audio-status', '本次音频尚未上传。');
  show('upload-stage', '尚未上传'); show('recognition-stage', '尚未识别'); show('analysis-stage', '尚未分析');
  show('current-result-status','尚未保存本次结果。');scoringState();
  if (audioURL) URL.revokeObjectURL(audioURL);
  audioURL = null; $('playback').removeAttribute('src'); $('download-audio').hidden = true;
}
function playback(buffer, filename) {
  if (audioURL) URL.revokeObjectURL(audioURL);
  audioURL = URL.createObjectURL(new Blob([buffer], {type: 'audio/wav'}));
  $('playback').src = audioURL;
  $('download-audio').href = audioURL; $('download-audio').download = filename;
  $('download-audio').hidden = false;
}
function displayAudio(result) {
  semanticPanel?.invalidate();
  audio = result;
  currentRecord=null;analysisSignature=null;derivedFrom=null;
  const asr = result.asr || {};
  // Commit the authoritative transcription before formatting optional metadata.
  show('raw-asr', hasASRText() ? asr.text : asr.message || 'ASR 无有效转写（空结果）；没有替代文本。');
  $('input-source').value = hasASRText() ? 'asr' : 'manual';
  show('upload-stage', '上传成功：原 WAV 已保存');
  show('recognition-stage', hasASRText() ? '识别成功' : asr.status === 'unconfigured' ? 'ASR 未配置' : '识别失败 / 无有效转写');
  show('analysis-stage', '尚未分析');
  show('current-result-status','本次转写尚未分析 / 评分。');scoringState();
  show('audio-status', `audio_id: ${result.audio_id || '未提供'}\n原 WAV：${seconds(result.duration_seconds, 2)}，${result.sample_rate ?? '未提供'} Hz，${result.channels ?? '未提供'}声道\nSHA256: ${result.sha256 || '未提供'}`);
  const engine = asr.engine || config?.asr.engine || '未提供';
  const model = asr.model_id || config?.asr.model_id || '未提供';
  const version = asr.model_version || config?.asr.model_version || '未提供';
  show('asr-status', `${hasASRText() ? '识别成功' : asr.message || '没有有效识别结果'}\n引擎：${engine}；模型：${model} / ${version}；本次推理：${seconds(asr.inference_seconds, 3)}`);
}
async function upload(buffer, filename, captureSource) {
  playback(buffer, filename);
  show('upload-stage', '上传 / 识别处理中'); show('recognition-stage', '等待本地 ASR 返回');
  message('正在保存原 WAV 并检查本地 ASR…');
  try {
    const result = await api('/api/audio', {wav_base64: base64(buffer), filename, capture_source: captureSource});
    displayAudio(result);
    message(hasASRText() ? '识别成功：原始转写已显示。可直接点击“分析本次识别结果”；计分需另行确认参考文本。' : '上传成功；没有有效 ASR 转写，请粘贴已有识别文本。');
  } catch (error) {
    show('upload-stage', '上传请求失败'); show('recognition-stage', '未取得识别结果');
    throw error;
  }
}

async function startRecording() {
  busy = true; controls(); message('正在申请 Windows 浏览器麦克风权限…');
  let stream, context;
  try {
    if (!navigator.mediaDevices?.getUserMedia || !window.AudioWorkletNode) throw new Error('浏览器不支持录音；请使用新版 Edge/Chrome 打开 http://localhost:8890/，或上传 WAV。');
    stream = await navigator.mediaDevices.getUserMedia({audio: {channelCount: 1, echoCancellation: false, noiseSuppression: false, autoGainControl: false}, video: false});
    context = new AudioContext();
    await context.resume();
    await context.audioWorklet.addModule('/pcm-worklet.js');
    const source = context.createMediaStreamSource(stream);
    const node = new AudioWorkletNode(context, 'pcm-collector');
    const mute = context.createGain(); mute.gain.value = 0;
    const session = {stream, context, source, node, mute, chunks: [], flushResolve: null, timer: null};
    node.port.onmessage = event => {
      if (event.data.pcm) session.chunks.push(event.data.pcm);
      if (event.data.flushed && session.flushResolve) session.flushResolve();
    };
    resetResults(); recorder = session;
    source.connect(node); node.connect(mute); mute.connect(context.destination);
    session.timer = setTimeout(() => stopRecording(), 30000);
    for (const track of stream.getAudioTracks()) track.onended = () => { if (recorder === session) stopRecording(); };
    show('record-status', '正在录音，点击结束；30秒自动结束。'); message('请朗读所选题目。');
  } catch (error) {
    if (stream) stream.getTracks().forEach(track => track.stop());
    if (context) await context.close();
    message('无法录音：' + error.message + ' 可改用上传 WAV 或手动粘贴。');
  } finally { busy = false; controls(); }
}
async function stopRecording() {
  if (!recorder || busy) return;
  busy = true; const session = recorder; clearTimeout(session.timer); controls();
  try {
    await new Promise(resolve => {
      const timeout = setTimeout(resolve, 1000);
      session.flushResolve = () => { clearTimeout(timeout); resolve(); };
      session.node.port.postMessage('flush');
    });
    session.source.disconnect(); session.node.disconnect(); session.mute.disconnect();
    session.stream.getTracks().forEach(track => { track.onended = null; track.stop(); });
    await session.context.close();
    const samples = mergeChunks(session.chunks);
    const wav = pcmWav(resample(samples, session.context.sampleRate));
    show('record-status', `录音已结束：${(samples.length/session.context.sampleRate).toFixed(2)}秒。`);
    await upload(wav, 'microphone.wav', 'browser_microphone');
  } catch (error) { message(error.message); }
  finally {
    session.stream.getTracks().forEach(track => track.stop());
    if (session.context.state !== 'closed') await session.context.close();
    recorder = null; busy = false; controls();
  }
}
function metricSummary(metrics) {
  if (!metrics.eligible) return '未计分：尚未确认人工标准文本。'+(metrics.reason || '');
  return ['before', 'after'].map((stage, i) => {
    const m = metrics[stage];
    return `${i ? '增强后' : '原始输入'}：严格CER ${score(m.strict_characters?.cer)}；旧兼容CER ${score(m.characters.cer)}\n术语召回率 ${score(m.terms.accuracy)} (${m.terms.correct}/${m.terms.expected})；精确率 ${score(m.terms.precision)}；多识别 ${m.terms.extra}\n术语别名等价召回率 ${score(m.alias_equivalent_terms?.accuracy)}\n设备编号准确率 ${score(m.device_numbers.accuracy)} (${m.device_numbers.correct}/${m.device_numbers.expected})；多识别 ${m.device_numbers.extra}\n数值槽位准确率 ${score(m.numeric_slots?.accuracy)}`;
  }).join('\n\n');
}
function render(record) {
  const analysis = record.brain.analysis;
  show('raw-asr', hasASRText() ? audio.asr.text : record.raw_asr_text ?? '无实际 ASR 原始转写（本条为手动文本评测）。');
  show('original-input', `来源：${record.input_source === 'asr' ? '实际本地 ASR' : '手动粘贴，不是 ASR 测量'}\n${record.original_transcript}`);
  show('enhanced', record.enhanced_text); show('normalization', analysis.normalization);
  show('cleaned',record.cleaned_display_text || record.enhanced_text);
  show('trace',analysis.correction_trace || []);show('numbers',analysis.numeric_entities || []);
  $('candidates').replaceChildren();
  for (const candidate of analysis.correction_candidates || []) {
    const label=document.createElement('label');
    label.textContent=`${candidate.surface} → ${candidate.replacement}；${candidate.reason}；${candidate.confidence_level}；位置${JSON.stringify(candidate.source_span)} `;
    const decision=document.createElement('select');
    for (const [value,text] of [['pending','待确认'],['accept','确认：仅可读文本'],['reject','拒绝']]) {const option=document.createElement('option');option.value=value;option.textContent=text;decision.append(option);}
    decision.value=accepted.has(candidate.id)?'accept':rejected.has(candidate.id)?'reject':'pending';
    decision.disabled=!candidate.display_confirmation_allowed;
    decision.addEventListener('change',()=>{accepted.delete(candidate.id);rejected.delete(candidate.id);if(decision.value==='accept')accepted.add(candidate.id);if(decision.value==='reject')rejected.add(candidate.id);scoringState();});
    label.append(decision);$('candidates').append(label);
  }
  show('entities', {原始文本设备实体: analysis.device_entities, 增强后对照候选_不确认真实设备身份: record.enhanced_entities_diagnostic.entities,
                   检查部位:analysis.inspection_parts,测量方式:analysis.measurement_methods,术语及巡检业务实体: analysis.normalization.recognized_terms});
  show('intent', {主意图: analysis.intent,多意图:analysis.intents,禁止及条件约束:analysis.constraints,条件语义:analysis.conditional_clauses, 所需数据来源: analysis.required_data_sources, 时间范围: analysis.time_range,
                 不确定信息: analysis.uncertainties, 操作提案: analysis.operation_proposal,
                 回答状态: record.brain.result.status, 解释: record.brain.result.answer,
                 比较约束:analysis.comparison_constraints,本条词库版本:analysis.lexicon_version,本条词库SHA256:analysis.lexicon_sha256,
                 来源: record.brain.result.citations, 已执行动作: record.executed_actions});
  show('metrics', (record.input_source === 'asr' ? '实际本地 ASR 样本对照\n' : record.input_source==='windows_external'?'Windows外部转写，独立统计\n':'手动文本实验，不计入 ASR 样本\n') + metricSummary(record.metrics)+ (record.cleaned_display_metrics?'\n\n仅可读文本对照（包含人工确认候选，不是模型输出改善）：\n'+metricSummary(record.cleaned_display_metrics):''));
  show('current-result-status',`当前记录：${record.record_id || '未提供'}；关联原分析：${record.derived_from_record_id || '无'}；本条词库：${analysis.lexicon_version || '历史版本未标注'}`);
  scoringState();
}
async function refresh() {
  const result = await api('/api/records');
  $('records').replaceChildren();
  for (const row of result.records) {
    const tr = document.createElement('tr');
    const values = [`${row.created_at}\n${row.input_source}\n${row.question_id || '自定义'}`, row.reference_text + (row.reference_confirmed ? '\n已核实' : '\n未核实'),
                    `${row.original_transcript}\n→ ${row.enhanced_text}`, row.metrics.eligible ? `${score(row.metrics.before.characters.cer)} / ${score(row.metrics.after.characters.cer)}` : '未评测'];
    for (const value of values) { const td = document.createElement('td'); td.textContent = value; tr.append(td); }
    const cell=document.createElement('td'),button=document.createElement('button');button.textContent='载入原样本';
    button.addEventListener('click',()=>{
      if (busy || recorder) return;
      resetResults();derivedFrom=row.record_id || null;
      audio=row.audio || null;
      if (audio) displayAudio(audio);
      currentRecord=row;derivedFrom=row.record_id || null;
      $('manual').value=row.original_transcript;
      $('input-source').value=audio?.asr?.status==='ok'?'asr':row.input_source==='windows_external'?'windows_external':'manual';
      $('question').value=row.question_id || '';$('reference').value=row.reference_text;
      $('reference-confirmed').checked=false;referenceKind();
      show('raw-asr',row.raw_asr_text===null?'该历史样本没有实际ASR':row.raw_asr_text || '该历史样本没有实际ASR');
      $('homophones').checked=!!row.apply_homophones;render(row);show('analysis-stage','历史分析已载入；评分将关联此记录');
      controls();message('原始样本已载入；重新核实参考文本后分析会保存新记录，不覆盖历史。');
    });cell.append(button);tr.append(cell);
    $('records').append(tr);
  }
  show('aggregate', {说明: 'asr为实际识别样本，manual为人工粘贴文本实验；零样本或零分母均不宣称改善。', ...result.aggregate});
  show('comparison-groups',result.comparison_groups || []);
  show('sample-statistics',result.statistics || '服务未提供独立样本统计，请重启 InspectionBrain 测试台加载新后端。');
  if (result.lexicon) config.lexicon=result.lexicon;
  versionStatus();
}
async function initializeV3() {
  try {
    const {setupV3}=await import('./v3.js');
    semanticPanel=setupV3({config, api, document, getCurrentInput:()=>{
    if (busy || recorder) return null;
    const source=$('input-source').value;
    if (source==='asr' && (!hasASRText() || !audio?.audio_id)) return null;
    if (source!=='asr' && !$('manual').value.trim()) return null;
    return {input_source:source,audio_id:audio?.audio_id || '',manual_transcript:source==='asr'?'':$('manual').value,apply_homophones:$('homophones').checked};
    }});
  } catch (error) {show('v3-provider-status','v3面板未加载：'+error.message+'；原v2流程仍可使用。');$('v3-analyze').disabled=true;}
}
function referenceKind() {
  const question=config?.questions.find(q=>q.id===$('question').value);
  show('question-standard',question?.text || '自定义题目');
  show('reference-kind',question && $('reference').value===question.text?'对应标准题目；仍需确认确实为本次朗读':'自定义参考：保存时不沿用错配题目ID');
  scoringState();
}
$('question').addEventListener('change',()=>{
  const question=config.questions.find(q=>q.id===$('question').value);
  $('reference').value=question?.text || '';$('reference-confirmed').checked=false;referenceKind();
});
$('record-start').addEventListener('click', startRecording);
$('record-stop').addEventListener('click', stopRecording);
$('reference').addEventListener('input', () => { $('reference-confirmed').checked = false;referenceKind(); });
$('reference-confirmed').addEventListener('change',scoringState);
$('manual').addEventListener('input',()=>{semanticPanel?.invalidate();accepted.clear();rejected.clear();$('candidates').replaceChildren();$('reference-confirmed').checked=false;scoringState();controls();});
$('homophones').addEventListener('change',()=>{semanticPanel?.invalidate();accepted.clear();rejected.clear();$('candidates').replaceChildren();scoringState();});
$('input-source').addEventListener('change',()=>{semanticPanel?.invalidate();scoringState();});
$('copy-reference').addEventListener('click', () => {
  const question = config.questions.find(q => q.id === $('question').value);
  if (question) { $('reference').value = question.text; $('reference-confirmed').checked = false;referenceKind(); }
});
$('wav-file').addEventListener('change', async () => {
  const file = $('wav-file').files[0]; if (!file) return;
  busy = true; resetResults(); controls();
  try {
    if (file.size > config.max_audio_bytes) throw new Error('WAV超过12 MiB限制');
    await upload(await file.arrayBuffer(), file.name, 'wav_upload');
  } catch (error) { message(error.message); }
  finally { busy = false; $('wav-file').value = ''; controls(); }
});
async function evaluate(stage = 'score', asrOnly = false) {
  if (busy || recorder) return;
  if (asrOnly && (!hasASRText() || !audio.audio_id)) {message('本次音频没有可分析的实际 ASR 转写。');return;}
  if (stage==='score' && (!$('reference').value.trim() || !$('reference-confirmed').checked)) {scoringState();message('未计分：尚未确认人工标准文本。请校对并勾选确认后评分，无需重新录音；没有参考时可先做领域分析。');return;}
  if (asrOnly) $('input-source').value = 'asr';
  const source=$('input-source').value, sig=signature(source);
  if (stage==='analysis' && currentRecord && analysisSignature===sig) {scoringState();message('已显示本次音频和配置的分析；没有新增重复记录。评分请校对参考后点击“评分并保存”。');return;}
  const parent=currentRecord && currentRecord.input_source===source && currentRecord.original_transcript===(source==='asr'?audio?.asr.text:$('manual').value)?currentRecord.record_id:null;
  busy = true; controls();
  if (stage==='score') show('score-stage','评分保存处理中（不重跑 ASR）');
  else show('analysis-stage', '领域分析处理中');
  try {
    const record = await api('/api/evaluate', {mode:stage,audio_id: audio?.audio_id || '', input_source: source,
      manual_transcript: source==='asr' ? '' : $('manual').value, reference_text: stage==='analysis' ? '' : $('reference').value,
      reference_confirmed: stage==='analysis' ? false : $('reference-confirmed').checked, question_id: stage==='analysis' ? '' : $('question').value, apply_homophones: $('homophones').checked,
      external_asr_engine:$('external-engine').value,external_asr_version:$('external-version').value,
      accepted_candidate_ids:[...accepted],rejected_candidate_ids:[...rejected],derived_from_record_id:parent || ''});
    currentRecord=record;derivedFrom=record.record_id || null;analysisSignature=sig;
    render(record); show('analysis-stage', '领域分析成功（不表示现场结论或动作执行）');
    message(stage==='analysis' ? ($('reference').value.trim() && $('reference-confirmed').checked ? '领域分析成功，本次仅分析未计分。人工参考已确认，可直接评分保存，无需重录。' : '领域分析成功。未计分：尚未确认人工标准文本；校对参考并确认后直接评分，无需重录。') : record.metrics.eligible?'评分完成，当前结果与汇总已更新；重复保存同一配置和参考不会新增记录。':'未计分：服务没有接受有效人工参考，请检查确认状态。');
    await refresh().catch(error => message('领域分析成功；刷新历史记录失败：' + error.message));
  } catch (error) { show(stage==='score'?'score-stage':'analysis-stage', (stage==='score'?'评分保存失败：':'领域分析失败：') + error.message); message(error.message); }
  finally { busy = false; controls(); }
}
$('evaluate').addEventListener('click', () => evaluate());
$('analyze-asr').addEventListener('click', () => evaluate('analysis',true));
$('analyze-text').addEventListener('click', () => {if($('input-source').value==='asr')$('input-source').value='manual';return evaluate('analysis');});
$('retranscribe').addEventListener('click',async()=>{
  if(!audio || busy)return;
  busy=true;controls();
  try {const result=await api('/api/retranscribe',{audio_id:audio.audio_id});displayAudio(result);accepted.clear();rejected.clear();$('candidates').replaceChildren();for(const id of ['original-input','enhanced','cleaned','metrics','trace','intent','entities','numbers','normalization'])show(id,'等待分析本次新转写。');scoringState();message(hasASRText()?'原音频已再次识别，新转写独立保存；人工参考仍保留；可重新分析或评分，不增加独立音频样本。':'原音频已保存，本次未取得有效转写；可重试或手动粘贴。');}
  catch(error){message(error.message);}
  finally{busy=false;controls();}
});
$('refresh').addEventListener('click', () => refresh().catch(error => message(error.message)));
window.addEventListener('pagehide', () => {
  if (recorder) { clearTimeout(recorder.timer); recorder.stream.getTracks().forEach(track => track.stop()); recorder.context.close(); }
  if (audioURL) URL.revokeObjectURL(audioURL);
});
controls();
try {
  config = await api('/api/config');
  versionStatus();
  show('asr-status', config.asr.label + '：' + config.asr.reason+'\n模型：'+(config.asr.model_id || '未配置')+' / '+(config.asr.model_version || '')+'；领域版本：'+(config.domain_version || 'v1'));
  for (const q of config.questions) { const option = document.createElement('option'); option.value = q.id; option.textContent = `[${q.kind}] ${q.text}`; $('question').append(option); }
  resetResults(); await initializeV3(); await refresh();
} catch (error) { message('无法加载测试台：' + error.message); }
controls();
