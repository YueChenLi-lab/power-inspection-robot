// Independent panel: never replaces v2, reference text, raw ASR or scoring state.
export function setupV3({config, api, getCurrentInput, document}) {
  const el = id => document.getElementById(id);
  const show = (id, value) => { el(id).textContent = typeof value === 'string' ? value : JSON.stringify(value, null, 2); };
  const provider = config.semantic_v3;
  show('v3-provider-status', provider || '当前服务未提供v3配置；请只重启InspectionBrain测试台并强制刷新浏览器。原v2仍可使用。');
  el('v3-mode').value = 'v2_rules';
  el('v3-analyze').disabled = !provider;
  let running = false;
  let inputRevision = 0;
  el('v3-analyze').addEventListener('click', async () => {
    if (running || !provider) return;
    running = true; el('v3-analyze').disabled = true;
    show('v3-status', '独立语义分析处理中；不重跑ASR、不提交人工参考。');
    try {
      const input = getCurrentInput();
      const revision = inputRevision;
      if (!input) throw new Error('请先取得本次有效ASR，或在手动输入区填写转写文本。');
      const record = await api('/api/semantic', {...input, mode:el('v3-mode').value});
      if (revision !== inputRevision || JSON.stringify(getCurrentInput()) !== JSON.stringify(input)) throw new Error('当前音频或输入已变化；旧输入的语义记录已独立保存，请分析当前输入。');
      const result = record.result;
      const kind = result.provider.is_real_llm ? '兼容文本模型' : result.provider.provider === 'mock' ? 'Mock脚本（非真实LLM）' : 'v2规则（未连接LLM）';
      show('v3-original', `${record.input_source} / audio_id=${record.provenance.audio_id || '无'} / SHA256=${record.provenance.audio_sha256 || '无'}\n${record.original_transcript}`);
      show('v3-v2', result.v2.analysis);
      const selected = result.fallback_used ? result.fallback : result.v3;
      show('v3-semantic', selected || '仅v2 / 模型不可用；没有伪造LLM结果。');
      show('v3-draft', result.structured_task_draft || '没有通过校验的模型草案；请确认或选择自动回退。');
      show('v3-validation', {validation:result.validation, error:result.error, fallback_used:result.fallback_used, fallback_success:result.fallback_success});
      show('v3-candidate', result.model_candidate || '无模型候选。');
      show('v3-status', `${kind}；模型=${result.provider.model || '未配置'} / ${result.provider.model_version || '未提供'}；耗时=${result.llm_inference_seconds == null ? '未运行模型' : result.llm_inference_seconds.toFixed(3)+'秒'}；状态=${result.status}；${result.error || '无运行错误'}；回退=${result.fallback_used ? '已明确使用v2' : '无'}；词库=${result.lexicon_version} / ${result.lexicon_sha256}；不可执行。`);
      try { show('v3-summary', (await api('/api/semantic/records')).summary); }
      catch (error) { show('v3-summary', '分析已显示；独立统计刷新失败：'+error.message); }
    } catch (error) {
      // Do not leave a previous audio's valid-looking draft after a failed request.
      for (const id of ['v3-original','v3-v2','v3-semantic','v3-draft','v3-validation','v3-candidate']) show(id,'本次对照未完成；'+error.message);
      show('v3-status', '对照失败：'+error.message+'；原始ASR、v2结果与人工参考均保留。');
    } finally { running=false; el('v3-analyze').disabled = false; }
  });
  return {invalidate(){
    inputRevision++;
    for (const id of ['v3-original','v3-v2','v3-semantic','v3-draft','v3-validation','v3-candidate']) show(id,'当前输入已更新，等待重新对照；历史语义记录保留。');
    show('v3-status','当前输入已更新，请点击对照分析；原ASR和人工参考保持独立。');
  }};
}
