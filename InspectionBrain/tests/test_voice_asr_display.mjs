// Deterministic DOM/fetch simulation using the user's reported response text.
// This does not claim to exercise a real Windows microphone or ASR model.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {pcmWav} from '../voice_lab/static/audio.js';

const transcript = '请查询2号主片高压套管的红外记录、红外测温记录，并与上周的结果比较。';
let instance = 0;
async function page({legacyConfig=false}={}) {
  class Element {
    constructor() { this.value=''; this.textContent=''; this.checked=false; this.disabled=false; this.children=[]; this.events={}; this.files=[]; this.option={}; }
    addEventListener(name, fn) { this.events[name]=fn; }
    querySelector() { return this.option; }
    append(child) { this.children.push(child); }
    replaceChildren() { this.children=[]; }
    removeAttribute(key) { delete this[key]; }
  }
  const html=readFileSync(new URL('../voice_lab/static/index.html',import.meta.url),'utf8');
  const ids=[...html.matchAll(/id="([^"]+)"/g)].map(m=>m[1]);
  assert.equal(new Set(ids).size,ids.length,'HTML result IDs must be unique');
  const elements=new Map(ids.map(id=>[id,new Element()]));
  const get=id=>{assert.ok(elements.has(id),`Missing HTML element ${id}`);return elements.get(id);};
  const requests=[],records=[];
  let sequence=0;
  let latestAudio;
  let response={audio_id:'audio-1',duration_seconds:11.112,sample_rate:16000,channels:1,sha256:'fixture-hash',
    asr:{status:'ok',engine:'sensevoice',text:transcript,inference_seconds:1.409}};
  let failAnalysis=false;
  const graph=()=>({connect(){},disconnect(){}});
  class Context {
    constructor(){this.sampleRate=48000;this.state='running';this.destination={};this.audioWorklet={addModule:async()=>{}};}
    async resume(){} async close(){this.state='closed';}
    createMediaStreamSource(){return graph();} createGain(){return {...graph(),gain:{value:1}};}
  }
  class Worklet {
    constructor(){this.port={postMessage:()=>{this.port.onmessage({data:{pcm:new Float32Array(4800)}});this.port.onmessage({data:{flushed:true}});}};}
    connect(){} disconnect(){}
  }
  globalThis.document={getElementById:get,createElement:()=>new Element()};
  globalThis.window={addEventListener(){},AudioWorkletNode:Worklet};
  globalThis.AudioContext=Context;globalThis.AudioWorkletNode=Worklet;
  const track={stop(){}};
  Object.defineProperty(globalThis,'navigator',{configurable:true,value:{mediaDevices:{getUserMedia:async()=>({getTracks:()=>[track],getAudioTracks:()=>[track]})}}});
  globalThis.fetch=async(path,options={})=>{
    const data=options.body?JSON.parse(options.body):null;requests.push({path,data});
    let body;
    if(path==='/api/config')body={csrf_token:'fixture-token',lexicon:{loaded_version:'electrical-v2.3',loaded_sha256:'c'.repeat(64),restart_required:false,path:'TEST FIXTURE'},asr:{configured:true,label:'SenseVoice',reason:'test fixture',model_id:'fixture-model',model_version:'fixture-version'},max_audio_bytes:12*1024*1024,questions:[{id:'q1',text:'标准题目',kind:'test'}]};
    else if(path==='/api/records')body={records,aggregate:{asr:{scored_unique_samples:records.some(r=>r.metrics.eligible)?1:0}},statistics:{record_count:records.length,independent_test_sample_count:records.some(r=>r.input_source==='asr')?1:0}};
    else if(path==='/api/audio'||path==='/api/retranscribe') {
      body=structuredClone(response);body.audio_id=`audio-${++sequence}`;
      latestAudio=body;
      if(path==='/api/audio')assert.equal(Buffer.from(data.wav_base64,'base64').toString('ascii',0,4),'RIFF');
    } else if(path==='/api/evaluate') {
      if(failAnalysis)return {ok:false,json:async()=>({error:'fixture domain analysis error'})};
      assert.equal(data.audio_id,`audio-${sequence}`);
      const key=JSON.stringify([data.audio_id,data.input_source,data.mode,data.manual_transcript,data.reference_text,data.reference_confirmed,data.apply_homophones,data.accepted_candidate_ids,data.rejected_candidate_ids]);
      body=records.find(r=>r.fixture_key===key);
      if(!body) {
        const original=data.input_source==='asr'?response.asr.text:data.manual_transcript;
        const metric=cer=>({characters:{cer},strict_characters:{cer},terms:{accuracy:.5,precision:.5,correct:1,expected:2,extra:0},device_numbers:{accuracy:1,correct:1,expected:1,extra:0}});
        body={fixture_key:key,record_id:`record-${records.length}`,derived_from_record_id:data.derived_from_record_id,created_at:'fixture',input_source:data.input_source,raw_asr_text:response.asr.text,audio:latestAudio,
          original_transcript:original,enhanced_text:original.replace('主片','主变'),reference_text:data.reference_text,reference_confirmed:data.reference_confirmed,
          metrics:data.mode==='score'&&data.reference_confirmed?{eligible:true,before:metric(.125),after:metric(.25)}:{eligible:false,reason:'未确认参考，不计分'},brain:{analysis:{lexicon_version:'electrical-v2.3',normalization:{recognized_terms:[]},device_entities:[],intent:'inspection_history'},result:{status:'undetermined',answer:'无现场资料',citations:[]}},enhanced_entities_diagnostic:{entities:[]},executed_actions:[]};
        records.push(body);
      }
    } else throw Error(`Unexpected route ${path}`);
    if (path==='/api/config' && legacyConfig) delete body.lexicon;
    return {ok:true,json:async()=>body};
  };
  await import(`../voice_lab/static/app.js?asr-display-test=${++instance}`);
  return {get,requests,records,html,setResponse(value){response=value;},failAnalysis(){failAnalysis=true;},async upload(){get('wav-file').files=[{size:46,name:'speech.wav',arrayBuffer:async()=>pcmWav(new Float32Array([0]))}];await get('wav-file').events.change();}};
}

test('reported response already reaches raw ASR via the existing upload path',async()=>{
  const p=await page();await p.upload();
  assert.equal(p.get('raw-asr').textContent,transcript);
  assert.equal(p.get('input-source').value,'asr');
});

test('successful WAV displays model/time and three stages; quick analysis uses audio ID without a confirmed reference',async()=>{
  const p=await page();p.get('question').value='q1';p.get('question').events.change();
  assert.ok(p.html.indexOf('id="raw-asr"')<p.html.indexOf('id="manual"'),'Raw ASR must be visible in the upload area');
  await p.upload();
  assert.match(p.get('asr-status').textContent,/sensevoice/i);
  assert.match(p.get('asr-status').textContent,/fixture-model/);
  assert.match(p.get('asr-status').textContent,/1\.409/);
  assert.match(p.get('upload-stage').textContent,/上传成功/);
  assert.match(p.get('recognition-stage').textContent,/识别成功/);
  assert.match(p.get('analysis-stage').textContent,/尚未分析/);
  assert.equal(p.get('analyze-asr').disabled,false);
  await p.get('evaluate').events.click(); // Keep the scoring confirmation gate.
  assert.equal(p.requests.filter(r=>r.path==='/api/evaluate').length,0);
  p.get('manual').value='不能代替模型输出';p.get('input-source').value='manual';
  await p.get('analyze-asr').events.click();
  const request=p.requests.find(r=>r.path==='/api/evaluate').data;
  assert.equal(request.manual_transcript,'');assert.equal(request.reference_text,'');
  assert.equal(request.reference_confirmed,false);assert.equal(request.question_id,'');
  assert.equal(p.get('reference').value,'标准题目');
  assert.equal(p.get('raw-asr').textContent,transcript);
  assert.match(p.get('analysis-stage').textContent,/领域分析成功/);
  assert.match(p.get('enhanced').textContent,/主变/);
  assert.equal(p.records[0].original_transcript,transcript);
  assert.ok(p.requests.every(r=>['/api/config','/api/records','/api/audio','/api/evaluate'].includes(r.path)));
});

test('recording and retranscription update the same display and bind analysis to the latest audio',async()=>{
  const p=await page();await p.get('record-start').events.click();await p.get('record-stop').events.click();
  assert.equal(p.get('raw-asr').textContent,transcript);
  assert.equal(p.requests.find(r=>r.path==='/api/audio').data.capture_source,'browser_microphone');
  await p.get('retranscribe').events.click();
  assert.equal(p.requests.find(r=>r.path==='/api/retranscribe').data.audio_id,'audio-1');
  assert.match(p.get('audio-status').textContent,/audio-2/);
  await p.get('analyze-asr').events.click();
  assert.equal(p.requests.find(r=>r.path==='/api/evaluate').data.audio_id,'audio-2');
});

test('optional metadata cannot block raw text; domain failure preserves successful recognition',async()=>{
  const p=await page();p.setResponse({asr:{status:'ok',engine:'sensevoice',text:transcript}});
  await p.upload();assert.equal(p.get('raw-asr').textContent,transcript);
  assert.equal(p.get('analyze-asr').disabled,false);
  p.failAnalysis();await p.get('analyze-asr').events.click();
  assert.equal(p.get('raw-asr').textContent,transcript);
  assert.match(p.get('recognition-stage').textContent,/识别成功/);
  assert.match(p.get('analysis-stage').textContent,/领域分析失败/);
});

test('ASR error or empty success never reuses prior transcription or enables quick analysis',async()=>{
  const p=await page();await p.upload();
  for(const asr of [{status:'error',text:null,message:'decode failed'},{status:'unconfigured',text:null,message:'ASR 未配置'},{status:'ok',engine:'sensevoice',text:'',inference_seconds:.1}]) {
    p.setResponse({duration_seconds:1,sample_rate:16000,channels:1,asr});await p.upload();
    assert.notEqual(p.get('raw-asr').textContent,transcript);
    assert.match(p.get('upload-stage').textContent,/上传成功/);
    assert.doesNotMatch(p.get('recognition-stage').textContent,/识别成功/);
    assert.equal(p.get('input-source').value,'manual');
    assert.equal(p.get('analyze-asr').disabled,true);
    assert.equal(p.get('manual').disabled,false);
  }
});

test('analysis upgrades to scoring without recording again; reference and audio stay intact and aggregates refresh',async()=>{
  const p=await page();await p.upload();
  assert.match(p.get('version-status').textContent,/electrical-v2\.3/);
  assert.match(p.get('version-status').textContent,/cccc/);
  await p.get('analyze-asr').events.click();
  assert.match(p.get('score-stage').textContent,/未计分：尚未确认人工标准文本/);
  assert.doesNotMatch(p.get('metrics').textContent,/12\.50%/);
  const analysis=p.records[0],playback=p.get('playback').src;
  p.get('reference').value='人工测试参考（仅测试前端评分展示）';p.get('reference').events.input();
  await p.get('evaluate').events.click();assert.equal(p.records.length,1);
  p.get('reference-confirmed').checked=true;p.get('reference-confirmed').events.change();
  await p.get('evaluate').events.click();
  const request=p.requests.filter(r=>r.path==='/api/evaluate').at(-1).data;
  assert.equal(request.mode,'score');assert.equal(request.derived_from_record_id,analysis.record_id);
  assert.equal(request.audio_id,analysis.audio.audio_id);
  assert.match(p.get('score-stage').textContent,/评分完成/);
  assert.match(p.get('metrics').textContent,/12\.50%/);assert.match(p.get('metrics').textContent,/25\.00%/);
  assert.equal(p.get('raw-asr').textContent,transcript);assert.equal(p.get('playback').src,playback);
  assert.equal(p.get('reference').value,'人工测试参考（仅测试前端评分展示）');
  assert.equal(p.requests.filter(r=>r.path==='/api/audio').length,1);
  assert.equal(p.requests.filter(r=>r.path==='/api/retranscribe').length,0);
  assert.equal(JSON.parse(p.get('sample-statistics').textContent).independent_test_sample_count,1);
  assert.equal(JSON.parse(p.get('aggregate').textContent).asr.scored_unique_samples,1);
});

test('repeated analysis, refresh, score and switch changes keep one independent sample',async()=>{
  const p=await page();await p.upload();await p.get('analyze-asr').events.click();
  await p.get('analyze-asr').events.click();assert.equal(p.records.length,1);
  await p.get('refresh').events.click();assert.equal(p.records.length,1);
  p.get('reference').value='已核实的测试参考';p.get('reference-confirmed').checked=true;
  await p.get('evaluate').events.click();await p.get('evaluate').events.click();
  assert.equal(p.records.length,2);
  await p.get('analyze-asr').events.click();assert.equal(p.records.length,2);
  p.get('homophones').checked=true;p.get('homophones').events.change();
  assert.equal(p.get('reference-confirmed').checked,true);
  await p.get('analyze-asr').events.click();assert.equal(p.records.length,3);
  assert.match(p.get('score-stage').textContent,/可直接评分/);
  await p.get('evaluate').events.click();
  assert.equal(p.records.length,4);assert.equal(p.get('reference').value,'已核实的测试参考');
  assert.equal(JSON.parse(p.get('sample-statistics').textContent).independent_test_sample_count,1);
});

test('model failure still permits manual analysis and explicit confirmed scoring',async()=>{
  const p=await page();p.setResponse({asr:{status:'error',text:null,message:'fixture model failed'}});await p.upload();
  p.get('manual').value='什么是局部放电？';p.get('manual').events.input();
  assert.equal(p.get('analyze-text').disabled,false);
  await p.get('analyze-text').events.click();
  assert.equal(p.records[0].input_source,'manual');assert.equal(p.records[0].raw_asr_text,null);
  assert.match(p.get('metrics').textContent,/未计分/);
  p.get('reference').value='什么是局部放电？';p.get('reference-confirmed').checked=true;
  await p.get('evaluate').events.click();assert.match(p.get('score-stage').textContent,/评分完成/);
  assert.equal(JSON.parse(p.get('sample-statistics').textContent).independent_test_sample_count,0);
});

test('a server without runtime version metadata is explicitly identified, not labelled as the disk version',async()=>{
  const p=await page({legacyConfig:true});
  assert.match(p.get('version-status').textContent,/服务未提供词库自检信息/);
  assert.match(p.get('version-status').textContent,/重启 InspectionBrain/);
  assert.doesNotMatch(p.get('version-status').textContent,/electrical-v2\.3/);
  await p.upload();assert.equal(p.get('raw-asr').textContent,transcript);
});
