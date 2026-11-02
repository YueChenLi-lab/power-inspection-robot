import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createUI,formatRate,requestFromState,annotationValue,makeClient} from '../InspectionBrain/evaluation_lab/static/app.js';

const html=await readFile(new URL('../InspectionBrain/evaluation_lab/static/index.html',import.meta.url),'utf8');
class Element {
  constructor(tag,doc) {this.tagName=tag;this.doc=doc;this.children=[];this.dataset={};this.listeners={};this.nodeType=1;this.value='';this.checked=false;this.disabled=false;this.hidden=false;this._text='';}
  set id(v) {this._id=v;this.doc.ids.set(v,this);} get id(){return this._id;}
  set textContent(v) {this._text=String(v);this.children=[];} get textContent(){return this._text+this.children.map(n=>n.textContent).join('');}
  set innerHTML(v){throw new Error('dynamic HTML injection prohibited');}
  append(...items){this.children.push(...items);} replaceChildren(...items){this._text='';this.children=[...items];}
  addEventListener(name,fn){(this.listeners[name]??=[]).push(fn);} async fire(name){for(const fn of this.listeners[name]||[]) await fn();}
  setAttribute(k,v){this[k]=v;}
  querySelectorAll(tag){return this.children.flatMap(n=>[...(n.tagName===tag?[n]:[]),...n.querySelectorAll(tag)]);}
}
class Document {
  constructor(){this.ids=new Map();for(const [,id] of html.matchAll(/id="([^"]+)"/g)){const n=this.createElement('div');n.id=id;}this.tabs=['evaluate','batch','statistics','history'].map(v=>{const n=this.createElement('button');n.dataset.tab=v;return n;});this.getElementById('provider').value='ollama';}
  createElement(tag){return new Element(tag,this);} getElementById(id){assert.ok(this.ids.has(id),`missing DOM ID ${id}`);return this.ids.get(id);}
  querySelectorAll(q){return q==='[data-tab]'?this.tabs:q==='.page'?[...this.ids.values()].filter(n=>n.id.startsWith('page-')):[];}
}
const cases=[{case_id:'T1',category:'设备纠正',original_request:'不是2号断路器，是3号断路器',annotation_status:'pending'}];
const record={evaluation_id:'r1',case_id:'T1',source:'MOCK',model_name:'mock-script',model_version:'fixture',original_request:cases[0].original_request,reference_time:'2026-11-02T12:00:00+08:00',outcome:'ACCEPTED',raw_response:'<img src=x onerror=alert(1)>',parsed_json:{ok:true},latency:{total_ms:10},token_metrics:{eval_count:null},request_result:{complete:true},parse_result:{passed:true},schema_result:{passed:true},evidence_result:{passed:true},validator_result:{valid:true},safety_result:{authorized:false,executable:false,hardware_commands_enabled:false},task_draft:{executable:false},timestamp:'2026-11-02',reasoning_redacted:false};
function fixture(){const calls=[],doc=new Document();let response=structuredClone(record),failure=null;let config={csrf_token:'local-token',provider:'ollama',schema_version:'schema-v3',prompt_version:'p1',configuration:{},default_model:'installed',last_request_time:null,status:{connected:true,version:'fixture-version',models:[{name:'installed',digest:'digest'}],error:null}};
 const fetcher=async(path,options={})=>{calls.push([path,options]);if(path==='/api/evaluate'&&failure)return {ok:false,json:async()=>({error:failure})};const body=options.body?JSON.parse(options.body):null;let result;
 if(path==='/api/config'||path==='/api/models/check')result=config;
 else if(path==='/api/dataset')result={cases};
 else if(path==='/api/evaluate')result=response;
 else if(path==='/api/batches')result={batch_id:'b1',status:'COMPLETED',completed:1,total:1,evaluation_ids:['r1']};
 else if(path.startsWith('/api/records/'))result=response;
 else if(path.startsWith('/api/records?'))result={records:[response]};
 else if(path==='/api/statistics')result={groups:[]};
 else if(path.startsWith('/api/annotations/'))result=body;
 else throw new Error('unexpected endpoint '+path);
 return {ok:true,json:async()=>structuredClone(result)};
 };
 return {doc,calls,ui:createUI(doc,fetcher,async()=>{}),setResponse:r=>response=r,setFailure:e=>failure=e};}

test('conditional rate denominators and explicit annotation booleans',()=>{assert.equal(formatRate({value:null}),'未评 / 无样本');assert.equal(formatRate({value:.5,numerator:1,denominator:2}),'50.0% (1/2)');assert.equal(annotationValue('false'),false);assert.equal(annotationValue(''),null);});
test('edited preset becomes manual input and never sends expected annotations',()=>{const selectedCase={...cases[0],expected:{gold:'private'}};assert.deepEqual(requestFromState({provider:'ollama',model:'installed',text:'edited',reference:'',selectedCase}),{provider:'ollama',model:'installed',original_request:'edited'});const request=requestFromState({provider:'mock',model:'',text:selectedCase.original_request,selectedCase});assert.equal(request.case_id,'T1');assert.ok(!('expected' in request));});
test('single run uses backend token, displays layers safely and keeps immutable safety labels',async()=>{const f=fixture();await f.ui.init();await f.ui.checkModels();assert.equal(f.doc.getElementById('model').value,'installed');f.doc.getElementById('provider').value='mock';f.doc.getElementById('case').value='T1';await f.doc.getElementById('case').fire('change');await f.ui.run();const [path,options]=f.calls.find(([p])=>p==='/api/evaluate');assert.equal(options.headers['X-Evaluation-Token'],'local-token');assert.equal(JSON.parse(options.body).case_id,'T1');assert.equal(f.doc.getElementById('outcome').textContent,'ACCEPTED');assert.ok(f.doc.getElementById('layers').textContent.includes('<img src=x onerror=alert(1)>'));assert.equal(f.doc.getElementById('run').disabled,false);assert.ok(html.includes('authorized = false'));assert.ok(!f.calls.some(([p])=>p.startsWith('http')));});
test('real provider errors remain errors, never become a Mock success',async()=>{const f=fixture();await f.ui.init();f.doc.getElementById('input').value='test';f.setResponse({...record,source:'REAL LLM',outcome:'PROVIDER_ERROR',request_result:{complete:false,error:'offline'},parse_result:{passed:null},task_draft:null});await f.ui.run();assert.equal(f.doc.getElementById('outcome').textContent,'PROVIDER_ERROR');assert.ok(f.doc.getElementById('result-source').textContent.includes('REAL LLM'));assert.equal(f.doc.getElementById('notice').dataset.error,'true');assert.equal(f.calls.filter(([p])=>p==='/api/evaluate').length,1);});
test('batch progress uses persisted IDs; history and human annotations are explicit',async()=>{const f=fixture();await f.ui.init();await f.ui.runBatch();assert.equal(f.doc.getElementById('batch-progress').value,1);assert.ok(f.doc.getElementById('batch-results').textContent.includes('MOCK'));await f.ui.history();assert.ok(f.doc.getElementById('export-csv').href.includes('format=csv'));await f.ui.openAnnotation('r1');assert.equal(f.doc.getElementById('annotation-confirmed').checked,false);f.doc.getElementById('annotator').value='reviewer';f.doc.getElementById('annotation-confirmed').checked=true;f.doc.getElementById('annotation-evidence').value='false';f.doc.getElementById('dimension-intents').value='true';await f.ui.saveAnnotation();const data=JSON.parse(f.calls.find(([p])=>p==='/api/annotations/r1')[1].body);assert.equal(data.evidence_consistent,false);assert.equal(data.semantic_dimensions.intents,true);assert.equal(data.confirmed,true);});
test('empty dashboard makes no invented metrics and backend errors are surfaced',async()=>{const f=fixture();await f.ui.init();await f.ui.statistics();assert.ok(f.doc.getElementById('statistics').textContent.includes('暂无记录'));const api=makeClient(async()=>({ok:false,json:async()=>({error:'busy'})}));await assert.rejects(api('/api/evaluate',{}),/busy/);});

test('HTTP failure clears a previous accepted result instead of reusing stale success',async()=>{const f=fixture();await f.ui.init();f.doc.getElementById('input').value='test';await f.ui.run();assert.equal(f.doc.getElementById('outcome').textContent,'ACCEPTED');f.setFailure('backend unavailable');await assert.rejects(f.ui.run(),/backend unavailable/);assert.equal(f.doc.getElementById('outcome').textContent,'请求未完成');assert.equal(f.doc.getElementById('layers').children.length,0);assert.equal(f.doc.getElementById('run').disabled,false);});
