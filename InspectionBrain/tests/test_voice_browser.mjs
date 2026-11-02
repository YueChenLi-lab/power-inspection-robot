// Browser-flow simulation only. This does not assert Windows microphone/device acceptance.
import test from 'node:test';
import assert from 'node:assert/strict';
import {pcmWav} from '../voice_lab/static/audio.js';

test('page records microphone WAV, keeps unconfigured ASR null, saves manual evaluation and releases tracks', async () => {
  class Element {
    constructor(id) { this.id = id; this.value = ''; this.checked = false; this.disabled = false; this.textContent = ''; this.children = []; this.events = {}; this.files = []; this.option = {}; }
    addEventListener(name, fn) { this.events[name] = fn; }
    querySelector() { return this.option; }
    append(value) { this.children.push(value); }
    replaceChildren() { this.children = []; }
    removeAttribute(key) { delete this[key]; }
  }
  const elements = new Map();
  const get = id => { if (!elements.has(id)) elements.set(id, new Element(id)); return elements.get(id); };
  const requests = [];
  const records = [];
  const status = {configured: false, label: 'ASR 未配置', reason: '无模型'};
  let stops = 0;
  const track = {stop() { stops++; }, onended: null};
  const stream = {getTracks: () => [track], getAudioTracks: () => [track]};
  const graph = () => ({connect() {}, disconnect() {}});
  class Context {
    constructor() { this.sampleRate = 48000; this.state = 'running'; this.audioWorklet = {addModule: async path => assert.equal(path, '/pcm-worklet.js')}; this.destination = {}; }
    async resume() {}
    createMediaStreamSource() { return graph(); }
    createGain() { return {...graph(), gain: {value: 1}}; }
    async close() { this.state = 'closed'; }
  }
  class Worklet {
    constructor(context, name) {
      assert.equal(name, 'pcm-collector');
      this.port = {onmessage: null, postMessage: () => {
        this.port.onmessage({data: {pcm: new Float32Array(4800).fill(.1)}});
        this.port.onmessage({data: {flushed: true}});
      }};
    }
    connect() {} disconnect() {}
  }
  globalThis.document = {getElementById: get, createElement: id => new Element(id)};
  globalThis.window = {AudioWorkletNode: Worklet, addEventListener() {}};
  globalThis.AudioWorkletNode = Worklet; globalThis.AudioContext = Context;
  Object.defineProperty(globalThis, 'navigator', {configurable: true, value: {mediaDevices: {getUserMedia: async options => {
    assert.equal(options.video, false); return stream;
  }}}});
  globalThis.fetch = async (path, options = {}) => {
    const data = options.body ? JSON.parse(options.body) : undefined;
    requests.push({path, options, data});
    let body;
    if (path === '/api/config') body = {csrf_token: 'token', asr: status, questions: [{id: 'question-1', text: '什么是局部放电？', kind: 'domain_question'}], max_audio_bytes: 12 * 1024 * 1024};
    else if (path === '/api/records') body = {records, aggregate: {asr: {confirmed_runs: 0}, manual: {confirmed_runs: records.length}}};
    else if (path === '/api/audio') {
      const wav = Buffer.from(data.wav_base64, 'base64');
      assert.equal(wav.toString('ascii', 0, 4), 'RIFF');
      assert.equal(wav.readUInt32LE(24), 16000);
      assert.equal(options.headers['X-Voice-Lab-Token'], 'token');
      body = {audio_id: 'a'.repeat(32), sha256: 'hash', duration_seconds: .1, sample_rate: 16000, channels: 1, asr: {status: 'unconfigured', text: null, message: 'ASR 未配置'}};
    } else if (path === '/api/evaluate') {
      assert.equal(data.input_source, 'manual');
      assert.equal(data.manual_transcript, '什么是局放？');
      assert.equal(data.reference_confirmed, true);
      body = {created_at: 'test', input_source: 'manual', raw_asr_text: null, original_transcript: data.manual_transcript, enhanced_text: '什么是局部放电？', reference_text: data.reference_text, reference_confirmed: true, metrics: {eligible: false, reason: 'TEST STUB'},
              brain: {analysis: {normalization: {recognized_terms: []}, device_entities: [], intent: 'anomaly_procedure_explanation', operation_proposal: null}, result: {status: 'example_answer', answer: 'TEST STUB', citations: []}}, enhanced_entities_diagnostic: {entities: []}, executed_actions: []};
      records.push(body);
    } else throw new Error('Unexpected route ' + path);
    return {ok: true, json: async () => body};
  };
  await import('../voice_lab/static/app.js');
  assert.match(get('asr-status').textContent, /ASR 未配置/);
  get('question').value = 'question-1';
  get('copy-reference').events.click();
  assert.equal(get('reference').value, '什么是局部放电？');
  assert.equal(get('reference-confirmed').checked, false);
  await get('record-start').events.click();
  assert.equal(get('record-stop').disabled, false);
  await get('record-stop').events.click();
  assert.ok(stops > 0);
  assert.equal(get('record-start').disabled, false);
  assert.equal(get('input-source').value, 'manual');
  assert.equal(get('input-source').option.disabled, true);
  assert.match(get('raw-asr').textContent, /ASR 未配置/);
  get('manual').value = '什么是局放？'; get('reference-confirmed').checked = true;
  await get('evaluate').events.click();
  assert.equal(get('enhanced').textContent, '什么是局部放电？');
  assert.match(get('raw-asr').textContent, /无实际 ASR/);
  assert.match(get('original-input').textContent, /手动粘贴/);
  assert.equal(get('records').children.length, 1);
  get('reference').events.input(); assert.equal(get('reference-confirmed').checked, false);
  get('question').events.change();assert.equal(get('question-standard').textContent,'什么是局部放电？');
  get('reference').value='自定义参考';get('reference').events.input();assert.match(get('reference-kind').textContent,/自定义参考/);
  assert.equal(get('record-start').disabled,false);
  // WAV file upload follows its own provenance; the same file can be chosen again.
  get('wav-file').files = [{size: 46, name: 'one.wav', arrayBuffer: async () => pcmWav(new Float32Array([0]))}];
  await get('wav-file').events.change();
  assert.equal(requests.filter(r => r.path === '/api/audio').at(-1).data.capture_source, 'wav_upload');
  assert.equal(get('wav-file').value, '');
  assert.ok(requests.every(r => ['/api/config', '/api/records', '/api/audio', '/api/evaluate'].includes(r.path)));
});
