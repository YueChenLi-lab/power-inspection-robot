// DOM/fetch simulation, NOT Windows Chrome or microphone acceptance.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {setupV3} from '../voice_lab/static/v3.js';
import {pcmWav} from '../voice_lab/static/audio.js';

const html=await readFile(new URL('../voice_lab/static/index.html',import.meta.url),'utf8');
function fixture({configured=true,fail=false,status='validated_candidate',stale=false}={}) {
  const ids=[...html.matchAll(/id="([^"]+)"/g)].map(m=>m[1]);
  assert.equal(new Set(ids).size,ids.length);
  class Element {constructor(){this.textContent='';this.value='';this.disabled=false;this.events={};}addEventListener(name,fn){this.events[name]=fn;}}
  const elements=new Map(ids.map(id=>[id,new Element()]));
  const get=id=>{assert.ok(elements.has(id),id);return elements.get(id);};
  const requests=[];
  let input={input_source:'asr',audio_id:'original-audio',manual_transcript:'',apply_homophones:false};
  const original='请查询2号主变的测温记录，并与上周比较。';
  get('raw-asr').textContent=original;get('reference').value='人工参考保留';
  const result={original_request:original,v2:{analysis:{intents:[{type:'thermometry_history'},{type:'temperature_comparison'}]}},
    provider:{provider:'mock',is_real_llm:false,model:'mock-script',model_version:'1'},llm_inference_seconds:.004,
    status,lexicon_version:'electrical-v2.3',lexicon_sha256:'c'.repeat(64),
    v3:{semantic:{original_request:original},structured_task_draft:{executable:false}},
    structured_task_draft:{executable:false},validation:{valid:true,errors:[]},model_candidate:{original_request:original},fallback_used:false};
  if(status==='provider_unavailable') {result.provider={provider:'rules',is_real_llm:false,model:'rules-v2'};result.v3=null;result.structured_task_draft=null;result.validation=null;result.error='未连接LLM';result.llm_inference_seconds=null;}
  const api=async(path,payload)=>{
    requests.push({path,payload});
    if(fail)throw Error('测试服务异常');
    if(path==='/api/semantic'){if(stale)input={...input,audio_id:'another-audio'};return {input_source:'asr',original_transcript:original,provenance:{audio_id:'original-audio',audio_sha256:'h'.repeat(64)},result};}
    assert.equal(path,'/api/semantic/records');return {summary:{unique_asr_audio_sha256_count:1,semantic_accuracy:null}};
  };
  setupV3({config:configured?{semantic_v3:{provider:result.provider}}:{},api,getCurrentInput:()=>input,document:{getElementById:get}});
  return {get,requests,result,original,setInput(value){input=value;}};
}

test('v3 defaults to rules and sends authoritative audio ID without a reference; raw and v2 UI remain unchanged',async()=>{
  const p=fixture();assert.equal(p.get('v3-mode').value,'v2_rules');assert.equal(p.requests.length,0);
  p.get('v3-mode').value='v3_llm';await p.get('v3-analyze').events.click();
  const request=p.requests[0];assert.equal(request.payload.audio_id,'original-audio');
  assert.equal(request.payload.mode,'v3_llm');assert.ok(!('reference_text' in request.payload));assert.ok(!('raw_asr_text' in request.payload));
  assert.equal(p.get('raw-asr').textContent,p.original);assert.equal(p.get('reference').value,'人工参考保留');
  assert.match(p.get('v3-status').textContent,/Mock脚本（非真实LLM）/);
  assert.match(p.get('v3-status').textContent,/0\.004秒/);assert.match(p.get('v3-status').textContent,/electrical-v2.3/);
  assert.match(p.get('v3-draft').textContent,/"executable": false/);
  assert.match(p.get('v3-summary').textContent,/"semantic_accuracy": null/);
});
test('unavailable model is explicit; auto fallback never looks like LLM success',async()=>{
  const p=fixture({status:'provider_unavailable'});p.get('v3-mode').value='auto_fallback';
  p.result.fallback_used=true;p.result.fallback_success=true;p.result.fallback={semantic:{origin:'rules_v2'}};p.result.structured_task_draft={reasoning_source:'rules_v2',executable:false};
  await p.get('v3-analyze').events.click();
  assert.match(p.get('v3-status').textContent,/未连接LLM/);assert.match(p.get('v3-status').textContent,/已明确使用v2/);
  assert.match(p.get('v3-draft').textContent,/rules_v2/);
});
test('failed validation is shown separately from untrusted model candidate',async()=>{
  const p=fixture();p.result.status='validation_rejected';p.result.validation={valid:false,errors:['设备编号被修改']};
  p.result.structured_task_draft=null;p.result.v3={status:'clarification_required'};
  p.result.model_candidate={forged:'不可信设备'};
  await p.get('v3-analyze').events.click();assert.match(p.get('v3-validation').textContent,/设备编号被修改/);
  assert.match(p.get('v3-candidate').textContent,/不可信设备/);assert.match(p.get('v3-draft').textContent,/没有通过校验/);
});
test('old service, request failure, and changing audio keep old v2/ref/ASR usable',async()=>{
  const old=fixture({configured:false});assert.equal(old.get('v3-analyze').disabled,true);assert.match(old.get('v3-provider-status').textContent,/重启InspectionBrain/);
  for(const config of [{fail:true},{stale:true}]){
    const p=fixture(config);await p.get('v3-analyze').events.click();
    assert.match(p.get('v3-status').textContent,/对照失败/);assert.equal(p.get('raw-asr').textContent,p.original);
    assert.equal(p.get('reference').value,'人工参考保留');assert.equal(p.get('v3-analyze').disabled,false);
  }
});

test('full app upload flows into v3 panel through current saved audio, not copied JSON or reference',async()=>{
  class Element {
    constructor(){this.value='';this.checked=false;this.disabled=false;this.textContent='';this.children=[];this.events={};this.files=[];this.option={};this.bindings={};}
    addEventListener(type,fn){this.events[type]=fn;this.bindings[type]=(this.bindings[type] || 0)+1;}querySelector(){return this.option;}
    append(value){this.children.push(value);}replaceChildren(){this.children=[];}removeAttribute(key){delete this[key];}
  }
  const elements=new Map([...html.matchAll(/id="([^"]+)"/g)].map(m=>[m[1],new Element()]));
  const get=id=>{assert.ok(elements.has(id),id);return elements.get(id);};
  globalThis.document={getElementById:get,createElement:()=>new Element()};
  globalThis.window={addEventListener(){}};
  const original='请查询2号主变高压套管测温记录，与上周比较。';
  const requests=[];
  globalThis.fetch=async(path,options={})=>{
    const payload=options.body?JSON.parse(options.body):undefined;requests.push({path,payload});let body;
    if(path==='/api/config')body={csrf_token:'TEST_TOKEN',asr:{configured:true,label:'SenseVoice',reason:'TEST_FIXTURE'},questions:[],max_audio_bytes:12000000,semantic_v3:{provider:{provider:'mock',is_real_llm:false}}};
    else if(path==='/api/records')body={records:[],aggregate:{},statistics:{}};
    else if(path==='/api/audio')body={audio_id:'current-real-audio',sha256:'a'.repeat(64),duration_seconds:8.992,sample_rate:16000,channels:1,asr:{status:'ok',engine:'sensevoice',text:original,inference_seconds:1.014}};
    else if(path==='/api/semantic')body={input_source:'asr',original_transcript:original,provenance:{audio_id:'current-real-audio',audio_sha256:'a'.repeat(64)},result:{provider:{provider:'mock',is_real_llm:false,model:'mock-script',model_version:'1'},v2:{analysis:{intents:[]}},v3:{semantic:{original_request:original}},structured_task_draft:{executable:false},status:'validated_candidate',validation:{valid:true,errors:[]},llm_inference_seconds:.001,lexicon_version:'electrical-v2.3'}};
    else if(path==='/api/semantic/records')body={summary:{unique_asr_audio_sha256_count:1,semantic_accuracy:null}};
    else throw Error('Unexpected route '+path);
    return {ok:true,json:async()=>body};
  };
  await import('../voice_lab/static/app.js?v3-integration');
  get('reference').value='人工参考绝不进入LLM';
  get('wav-file').files=[{size:46,name:'voice.wav',arrayBuffer:async()=>pcmWav(new Float32Array([0]))}];
  await get('wav-file').events.change();
  assert.equal(get('raw-asr').textContent,original);assert.equal(get('input-source').value,'asr');
  get('v3-mode').value='v3_llm';await get('v3-analyze').events.click();
  const payload=requests.find(r=>r.path==='/api/semantic').payload;
  assert.equal(payload.audio_id,'current-real-audio');assert.equal(payload.input_source,'asr');assert.equal(payload.manual_transcript,'');
  assert.ok(!('reference_text' in payload));assert.equal(get('reference').value,'人工参考绝不进入LLM');
  assert.match(get('v3-original').textContent,/current-real-audio/);assert.match(get('v3-status').textContent,/Mock/);
  await get('refresh').events.click();await get('refresh').events.click();
  assert.equal(get('v3-mode').value,'v3_llm','Refreshing v2 history must not reset v3 mode');
  assert.equal(get('v3-analyze').bindings.click,1,'Bind exactly once; real browser listeners accumulate');
  get('manual').value='另一个输入';get('manual').events.input();
  assert.match(get('v3-status').textContent,/当前输入已更新/);assert.match(get('v3-draft').textContent,/等待重新对照/);
  assert.equal(get('raw-asr').textContent,original);assert.equal(get('reference').value,'人工参考绝不进入LLM');
});
