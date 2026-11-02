"""Loopback-only evaluation service. Deliberately has no robot control routes."""
import argparse
import base64
import binascii
import csv
from datetime import datetime
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import re
import secrets
import threading
from urllib.parse import urlsplit, parse_qs
import uuid

from inspection_brain.service import InspectionBrain, SHANGHAI
from inspection_brain.domain_v2.service import ElectricalBrainV2
from .asr import LocalASR
from .audio import decode_wav, MAX_BYTES
from .metrics import evaluate, aggregate, grouped_comparison, scoring_text, sample_statistics
from brain_v3.config import ProviderConfig, voice_lab_configuration
from brain_v3.engine import SemanticEngine
from brain_v3.schema import SCHEMA as SEMANTIC_SCHEMA
from brain_v3.store import SemanticStore

DEFAULT_STORAGE = Path(__file__).resolve().parents[1] / "runtime" / "voice_lab"
STATIC = Path(__file__).resolve().parent / "static"
ID = re.compile(r"^[0-9a-f]{32}$")
MAX_REQUEST = 17 * 1024 * 1024
DEMO_QUESTIONS = ["电流互感器和电压互感器有什么区别？", "变压器巡检一般检查哪些项目？",
                  "什么是局部放电？", "检查一号变压器需要哪些信息？", "一号主变最近有没有温度异常？"]


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")


def text_field(data, name, default="", maximum=2000):
    value = data.get(name, default)
    if not isinstance(value, str) or len(value) > maximum:
        raise ValueError(f"{name}须为不超过{maximum}字的文本")
    return value


def bool_field(data, name):
    value = data.get(name, False)
    if not isinstance(value, bool):
        raise ValueError(name + "须为布尔值")
    return value


class VoiceLab:
    def __init__(self, storage=DEFAULT_STORAGE, asr=None,domain_version="v2", *, semantic_config=None, semantic_provider=None,
                 semantic_configuration_error=None):
        self.storage = Path(storage)
        for folder in ("audio", "records"):
            (self.storage/folder).mkdir(parents=True, exist_ok=True)
        self.asr = asr or LocalASR(engine="none")
        self.brain = ElectricalBrainV2() if domain_version=="v2" else InspectionBrain()
        self.domain_version=domain_version
        self.semantic_engine = SemanticEngine(brain=self.brain if domain_version == "v2" else None,
                                              config=semantic_config or ProviderConfig(), provider=semantic_provider)
        self.semantic_store = SemanticStore(self.storage, self.semantic_engine)
        self.semantic_configuration_error = semantic_configuration_error
        self.started_at = datetime.now(SHANGHAI).isoformat()
        self.csrf = secrets.token_urlsafe(32)
        self.lock = threading.Lock()
        self.questions = [{"id": f"question-{i+1}", "text": text, "kind": "domain_question"}
                          for i, text in enumerate(DEMO_QUESTIONS)]
        self.questions += [{"id": "term-"+term.id, "text": term.standard_name,
                            "kind": term.category, "aliases": list(term.aliases)}
                           for term in self.brain.lexicon.terms]

    def config(self):
        return {"csrf_token": self.csrf, "asr": self.asr.status, "questions": self.questions,
                "max_audio_bytes": MAX_BYTES, "max_audio_seconds": 60,
                "mode": "local_offline_evaluation", "domain_version":self.domain_version,"hardware_commands_enabled": False,
                "workflow_version":"voice-workflow-v3", "process_id":os.getpid(),"started_at":self.started_at,
                "lexicon":self.lexicon_status(), "semantic_v3":{**self.semantic_engine.status(),
                                                               "configuration_error":self.semantic_configuration_error}}

    def semantic(self, data):
        source = text_field(data, "input_source", "manual", 20)
        if source not in ("asr", "manual", "windows_external"):
            raise ValueError("未知语义输入来源")
        audio_id = text_field(data, "audio_id", maximum=32)
        audio = self.audio_metadata(audio_id) if audio_id else None
        if source == "asr":
            if not audio or audio["asr"].get("status") != "ok" or not audio["asr"].get("text"):
                raise ValueError("没有有效ASR原文；可使用独立手动模式")
            original = audio["asr"]["text"]
        else:
            original = text_field(data, "manual_transcript")
        # Neither ASR reference answers nor user documents/asset records are sent.
        return self.semantic_store.analyze(original, source=source, audio=audio,
            mode=text_field(data, "mode", "v2_rules", 20),
            apply_homophones=bool_field(data, "apply_homophones"), dialogue_context=data.get("dialogue_context", []))

    def lexicon_status(self):
        normalizer=self.brain.normalizer
        if self.domain_version!='v2':return {'loaded_version':'legacy-v1','loaded_sha256':None,'restart_required':False}
        path=normalizer.path
        try:
            raw=path.read_bytes();disk_version=json.loads(raw)['lexicon_version'];disk_hash=hashlib.sha256(raw).hexdigest()
            error=None
        except (OSError,ValueError,KeyError) as exc:
            disk_version=disk_hash=None;error=str(exc)
        return {'path':str(path),'loaded_version':normalizer.version,'loaded_sha256':normalizer.sha256,
                'disk_version':disk_version,'disk_sha256':disk_hash,
                'restart_required':disk_hash!=normalizer.sha256,'error':error}

    def statistics(self, records):
        audios=[json.loads(p.read_text()) for p in (self.storage/'audio').glob('*.json')]
        return sample_statistics(records,audios)

    def upload(self, data):
        encoded = text_field(data, "wav_base64", maximum=MAX_REQUEST)
        try:
            payload = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("音频base64无效") from exc
        audio = decode_wav(payload)
        source = text_field(data, "capture_source", "wav_upload", 40)
        if source not in ("wav_upload", "browser_microphone"):
            raise ValueError("未知录音来源")
        name = text_field(data, "filename", "recording.wav", 200)
        audio_id = uuid.uuid4().hex
        # Save original bytes first; ASR only receives a separate mono resampling.
        with (self.storage/"audio"/(audio_id+".wav")).open("xb") as destination:
            destination.write(payload)
        asr = self.asr.transcribe(audio.pcm16)
        metadata = {"audio_id": audio_id, "created_at": datetime.now(SHANGHAI).isoformat(),
                    "original_filename": Path(name.replace("\\", "/")).name,
                    "capture_source": source, "sha256": hashlib.sha256(payload).hexdigest(),
                    "bytes": len(payload), "duration_seconds": audio.duration,
                    "sample_rate": audio.sample_rate, "channels": audio.channels,
                    "asr_input_sample_rate": 16000, "asr": asr}
        if data.get("retranscribed_from_audio_id"):metadata["retranscribed_from_audio_id"]=data["retranscribed_from_audio_id"]
        with (self.storage/"audio"/(audio_id+".json")).open("xb") as destination:
            destination.write(json_bytes(metadata))
        return metadata

    def audio_metadata(self, audio_id):
        if not ID.fullmatch(audio_id):
            raise ValueError("audio_id无效")
        path = self.storage/"audio"/(audio_id+".json")
        if not path.is_file():
            raise ValueError("录音不存在")
        return json.loads(path.read_text(encoding="utf-8"))

    def evaluate(self, data):
        mode=text_field(data,'mode','legacy',20)
        if mode not in ('legacy','analysis','score'):raise ValueError('mode须为analysis、score或legacy')
        source = text_field(data, "input_source", "manual", 20)
        if source not in ("asr", "manual", "windows_external"):
            raise ValueError("input_source须为asr、manual或windows_external")
        audio_id = text_field(data, "audio_id", maximum=32)
        audio = self.audio_metadata(audio_id) if audio_id else None
        if source == "asr":
            if not audio or audio["asr"]["status"] != "ok" or not audio["asr"]["text"]:
                raise ValueError("没有有效ASR原始转写，请使用手动粘贴模式")
            # Ignore any client-supplied raw/enhanced ASR text. Stored output is authoritative.
            original = audio["asr"]["text"]
        else:
            original = text_field(data, "manual_transcript")
        reference = text_field(data, "reference_text")
        confirmed = bool_field(data, "reference_confirmed")
        if mode=='analysis':confirmed=False
        if mode=='score' and (not confirmed or not scoring_text(reference)):
            raise ValueError('未计分：尚未确认有效人工标准文本；无需重新录音，校对并勾选确认后评分')
        apply_homophones = bool_field(data, "apply_homophones")
        question_id = text_field(data, "question_id", maximum=100)
        if question_id and question_id not in {q["id"] for q in self.questions}:
            raise ValueError("题目不存在")
        question=next((q for q in self.questions if q["id"]==question_id),None)
        is_standard=question is not None and reference==question["text"]
        binding={"status":("question_confirmed" if is_standard else "custom_confirmed") if confirmed and reference.strip() else "unconfirmed",
                 "selected_question_id":question_id,"standard_text":question["text"] if question else None,
                 "reference_kind":"question" if is_standard else "custom"}
        derived_from=text_field(data,"derived_from_record_id",maximum=32)
        if derived_from and (not ID.fullmatch(derived_from) or not (self.storage/"records"/(derived_from+".json")).is_file()):
            raise ValueError("原历史记录不存在")
        parent=json.loads((self.storage/'records'/(derived_from+'.json')).read_text()) if derived_from else None
        if parent and (parent['input_source']!=source or parent['original_transcript']!=original or ((parent.get('audio') or {}).get('audio_id') or '')!=audio_id or (parent.get('audio') or {}).get('sha256')!=(audio or {}).get('sha256')):
            raise ValueError('关联的原分析必须属于同一音频、来源和原始转写')
        now = datetime.now(SHANGHAI)
        candidate_fields={}
        for key in ("accepted_candidate_ids","rejected_candidate_ids"):
            values=data.get(key,[])
            if not isinstance(values,list) or len(values)>100 or any(not isinstance(v,str) or len(v)>40 for v in values):raise ValueError("候选ID清单无效")
            candidate_fields[key]=values
        config={'apply_homophones':apply_homophones,**{k:sorted(set(v)) for k,v in candidate_fields.items()}}
        config_hash=hashlib.sha256(json_bytes(config)).hexdigest()
        asr=(audio or {}).get('asr',{}) if source=='asr' else {}
        identity={'input_source':source,'original_transcript':original,'audio_id':audio_id,'audio_sha256':(audio or {}).get('sha256'),
                  'model_id':asr.get('model_id'),'model_version':asr.get('model_version'),
                  'external_engine':data.get('external_asr_engine') if source=='windows_external' else None,
                  'external_version':data.get('external_asr_version') if source=='windows_external' else None,
                  'lexicon_sha256':getattr(self.brain.normalizer,'sha256',None),'domain_version':self.domain_version,
                  'semantic_version':'electrical-semantics-v2.3' if self.domain_version=='v2' else 'legacy-v1','configuration':config}
        analysis_key=hashlib.sha256(json_bytes(identity)).hexdigest()
        evaluation_key=hashlib.sha256(json_bytes({'analysis_key':analysis_key,'reference':reference,'confirmed':confirmed,
                                                'question_id':question_id,'mode':mode})).hexdigest()
        # The same request is idempotent across refreshes and process restarts.
        with self.lock:
            for p in (self.storage/'records').glob('*.json'):
                saved=json.loads(p.read_text())
                if saved.get('evaluation_key')==evaluation_key:return saved
        reuse=bool(parent and mode=='score' and parent.get('analysis_key')==analysis_key)
        if reuse:
            result=parent['brain'];now_analysis=datetime.fromisoformat(result['analysis']['reference_time'])
        else:
            now_analysis=now
            result = self.brain.ask(original, now=now, apply_homophones=apply_homophones,**(candidate_fields if self.domain_version=="v2" else {}))
        raw_analysis = result["analysis"]
        enhanced = raw_analysis["normalization"]["normalized_text"]
        # Diagnostic comparison only: never changes original intent/identity/permissions.
        enhanced_analysis = self.brain.analyzer.analyze(enhanced, now=now_analysis)
        metrics = evaluate(reference, original, enhanced, self.brain, raw_analysis,
                           enhanced_analysis, confirmed)
        record = {"record_id": uuid.uuid4().hex, "created_at": now.isoformat(),
                  "question_id": question_id if is_standard else "", "input_source": source,
                  "reference_binding":binding,"derived_from_record_id":derived_from or None,
                  "external_asr_engine":text_field(data,"external_asr_engine",maximum=100) if source=="windows_external" else None,
                  "external_asr_version":text_field(data,"external_asr_version",maximum=100) if source=="windows_external" else None,
                  "raw_asr_text": audio["asr"]["text"] if audio else None,
                  "original_transcript": original, "enhanced_text": enhanced,
                  "cleaned_display_text":raw_analysis.get("cleaned_display_text",enhanced),
                  "candidate_decisions":candidate_fields,
                  "reference_text": reference, "reference_confirmed": confirmed,
                  "apply_homophones": apply_homophones, "audio": audio,
                  "brain": result,
                  "enhanced_entities_diagnostic": {"status": "text_candidates_only_not_verified_asset_identity",
                                                     "entities": enhanced_analysis["device_entities"]},
                  "metrics": metrics, "executed_actions": [], "hardware_commands_enabled": False}
        record.update(evaluation_stage='score' if metrics['eligible'] else 'analysis',analysis_key=analysis_key,evaluation_key=evaluation_key,
                      analysis_run_id=(parent.get('analysis_run_id') or parent['record_id']) if reuse else record['record_id'])
        record['provenance']={k:v for k,v in identity.items() if k not in ('original_transcript','configuration')}
        record['provenance'].update(lexicon_version=getattr(self.brain.normalizer,'version','legacy-v1'),
                                    analysis_config_hash=config_hash,configuration=config,analysis_run_id=record['analysis_run_id'])
        cleaned_analysis=self.brain.analyzer.analyze(record["cleaned_display_text"],now=now_analysis)
        record["cleaned_display_metrics"]=evaluate(reference,original,record["cleaned_display_text"],self.brain,raw_analysis,cleaned_analysis,confirmed)
        with self.lock:
            for p in (self.storage/'records').glob('*.json'):
                saved=json.loads(p.read_text())
                if saved.get('evaluation_key')==evaluation_key:return saved
            with (self.storage/"records"/(record["record_id"]+".json")).open("xb") as destination:
                destination.write(json_bytes(record))
        return record

    def retranscribe(self,data):
        audio_id=text_field(data,"audio_id",maximum=32)
        original=self.audio_metadata(audio_id)
        payload=(self.storage/"audio"/(audio_id+".wav")).read_bytes()
        if hashlib.sha256(payload).hexdigest()!=original["sha256"]:raise ValueError("原音频哈希不符，拒绝推理")
        result=self.upload({"wav_base64":base64.b64encode(payload).decode(),"filename":original["original_filename"],"capture_source":original["capture_source"],"retranscribed_from_audio_id":audio_id})
        return result

    def import_export(self,path):
        raw=Path(path).read_bytes()
        data=json.loads(raw.decode("utf-8-sig"))
        records=data["records"] if isinstance(data,dict) else data
        if not isinstance(records,list):raise ValueError("导出格式无效")
        with self.lock:
            for row in records:
                record_id=row.get("record_id","")
                if not ID.fullmatch(record_id) or not isinstance(row.get("original_transcript"),str) or "metrics" not in row:
                    raise ValueError("历史记录格式无效")
                target=self.storage/"records"/(record_id+".json")
                if target.exists():
                    if json.loads(target.read_text())!=row:raise ValueError("记录ID冲突，拒绝覆盖")
                    continue
                with target.open("xb") as output:output.write(json_bytes(row))
            folder=self.storage/"imports";folder.mkdir(exist_ok=True)
            copy=folder/(hashlib.sha256(raw).hexdigest()+".json")
            if not copy.exists():
                with copy.open("xb") as output:output.write(raw)
        return len(records)

    def records(self):
        with self.lock:
            rows = [json.loads(p.read_text(encoding="utf-8"))
                    for p in (self.storage/"records").glob("*.json")]
            return sorted(rows, key=lambda row: (row["created_at"], row["record_id"]))

    def export_csv(self):
        stream = io.StringIO(newline="")
        writer = csv.writer(stream)
        columns = ["record_id", "created_at", "question_id", "input_source", "raw_asr_text",
                   "original_transcript", "enhanced_text", "reference_text", "reference_confirmed",
                   "asr_engine", "audio_id", "audio_sha256", "intent", "metrics_eligible",
                   "before_cer", "after_cer", "before_term_accuracy", "after_term_accuracy",
                   "before_device_number_accuracy", "after_device_number_accuracy", "details_json"]
        columns += ["cleaned_display_text","before_strict_cer","after_strict_cer","before_numeric_accuracy","after_numeric_accuracy","reference_kind","lexicon_version","model_version"]
        writer.writerow(columns)
        def safe(value):
            # Preserve exact text in JSON export; protect spreadsheet users against formula cells.
            text = "" if value is None else str(value)
            return "'"+text if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")) else text
        for row in self.records():
            audio = row["audio"] or {}
            metrics = row["metrics"]
            values = [row.get(key) for key in columns[:9]]
            values += [(audio.get("asr") or {}).get("engine"), audio.get("audio_id"), audio.get("sha256"),
                       row["brain"]["analysis"]["intent"], metrics["eligible"]]
            for kind, key in (("characters", "cer"), ("terms", "accuracy"), ("device_numbers", "accuracy")):
                for stage in ("before", "after"):
                    values.append(metrics[stage][kind][key] if metrics["eligible"] else None)
            values.append(json.dumps(row, ensure_ascii=False))
            values += [row.get("cleaned_display_text"),
                       metrics["before"].get("strict_characters",{}).get("cer") if metrics["eligible"] else None,
                       metrics["after"].get("strict_characters",{}).get("cer") if metrics["eligible"] else None,
                       metrics["before"].get("numeric_slots",{}).get("accuracy") if metrics["eligible"] else None,
                       metrics["after"].get("numeric_slots",{}).get("accuracy") if metrics["eligible"] else None,
                       row.get("reference_binding",{}).get("reference_kind"),row["brain"]["analysis"].get("lexicon_version"),
                       (audio.get("asr") or {}).get("model_version")]
            writer.writerow([safe(value) for value in values])
        return ("\ufeff"+stream.getvalue()).encode("utf-8")


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, lab, port=8890):
        self.lab = lab
        super().__init__(("127.0.0.1", port), Handler)
        actual_port = self.server_address[1]
        self.hosts = {f"localhost:{actual_port}", f"127.0.0.1:{actual_port}"}


class Handler(BaseHTTPRequestHandler):
    server_version = "InspectionBrainVoiceLab/0.1"

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def respond(self, status, value, mime="application/json; charset=utf-8", filename=None):
        body = value if isinstance(value, bytes) else json_bytes(value)
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.send_header("Permissions-Policy", "microphone=(self), camera=()")
        if filename:
            self.send_header("Content-Disposition", 'attachment; filename="'+filename+'"')
        self.end_headers()
        self.wfile.write(body)

    def local_request(self):
        if self.headers.get("Host") not in self.server.hosts:
            self.respond(403, {"error": "仅允许localhost/127.0.0.1访问"})
            return False
        origin = self.headers.get("Origin")
        if origin and origin not in {"http://"+host for host in self.server.hosts}:
            self.respond(403, {"error": "不允许跨来源请求"})
            return False
        return True

    def do_GET(self):
        if not self.local_request():
            return
        parsed = urlsplit(self.path)
        static = {"/": ("index.html", "text/html; charset=utf-8"),
                  "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                  "/v3.js": ("v3.js", "text/javascript; charset=utf-8"),
                  "/audio.js": ("audio.js", "text/javascript; charset=utf-8"),
                  "/pcm-worklet.js": ("pcm-worklet.js", "text/javascript; charset=utf-8"),
                  "/style.css": ("style.css", "text/css; charset=utf-8")}
        if parsed.path in static:
            name, mime = static[parsed.path]
            self.respond(200, (STATIC/name).read_bytes(), mime)
        elif parsed.path == "/api/config":
            self.respond(200, self.server.lab.config())
        elif parsed.path == "/api/semantic/schema":
            self.respond(200, SEMANTIC_SCHEMA)
        elif parsed.path in ("/api/semantic/records", "/api/semantic/export"):
            self.respond(200, self.server.lab.semantic_store.export(),
                         filename="semantic-evaluation.json" if parsed.path.endswith("export") else None)
        elif parsed.path == "/api/records":
            records = self.server.lab.records()
            self.respond(200, {"records": records, "aggregate": aggregate(records),"comparison_groups":grouped_comparison(records),
                               "statistics":self.server.lab.statistics(records),'lexicon':self.server.lab.lexicon_status()})
        elif parsed.path == "/api/export":
            kind = parse_qs(parsed.query).get("format", ["json"])[0]
            if kind == "csv":
                self.respond(200, self.server.lab.export_csv(), "text/csv; charset=utf-8", "voice-evaluation.csv")
            elif kind == "json":
                records = self.server.lab.records()
                self.respond(200, json_bytes({"schema_version": 1, "records": records,
                                              "aggregate": aggregate(records),"comparison_groups":grouped_comparison(records),
                                              "statistics":self.server.lab.statistics(records)}), filename="voice-evaluation.json")
            else:
                self.respond(400, {"error": "导出格式须为json或csv"})
        else:
            self.respond(404, {"error": "接口不存在"})

    def do_POST(self):
        if not self.local_request():
            return
        if not secrets.compare_digest(self.headers.get("X-Voice-Lab-Token", ""), self.server.lab.csrf):
            self.respond(403, {"error": "测试台令牌无效，请刷新页面"})
            return
        if self.headers.get_content_type() != "application/json" or self.headers.get("Transfer-Encoding"):
            self.respond(415, {"error": "仅接受有长度的application/json"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            limit = MAX_REQUEST if self.path == "/api/audio" else 64 * 1024
            if not 0 < length <= limit:
                self.respond(413, {"error": "请求体超出限制或为空"})
                return
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError("请求体截断")
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("请求须为JSON对象")
            if self.path == "/api/audio":
                result = self.server.lab.upload(data)
            elif self.path == "/api/evaluate":
                result = self.server.lab.evaluate(data)
            elif self.path == "/api/semantic":
                result = self.server.lab.semantic(data)
            elif self.path == "/api/retranscribe":
                result=self.server.lab.retranscribe(data)
            else:
                self.respond(404, {"error": "接口不存在；测试台无控制接口"})
                return
            self.respond(200, result)
        except (ValueError, UnicodeError, TimeoutError) as exc:
            self.respond(400, {"error": str(exc)})
        except Exception:
            self.respond(500, {"error": "本地测试服务异常；原ASR与原音频不会被覆盖"})


def main(argv=None):
    parser = argparse.ArgumentParser(description="InspectionBrain独立本地语音测试台（仅loopback）")
    parser.add_argument("--port", type=int, default=8890)
    parser.add_argument("--storage", type=Path, default=DEFAULT_STORAGE)
    parser.add_argument("--asr", choices=("auto", "none", "vosk", "sensevoice"), default="auto")
    parser.add_argument("--vosk-model", type=Path)
    folder=Path(__file__).resolve().parents[1]/"models"/"sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17"
    parser.add_argument("--sensevoice-model", type=Path,default=folder/"model.int8.onnx")
    parser.add_argument("--sensevoice-tokens", type=Path,default=folder/"tokens.txt")
    parser.add_argument("--domain-version",choices=("v1","v2"),default="v2")
    parser.add_argument("--import-export",type=Path)
    parser.add_argument("--semantic-provider", choices=("rules", "mock", "openai_compatible"),
                        help="独立v3对照Provider；默认rules。Mock不是实际LLM")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("port须为1～65535")
    asr = LocalASR(args.asr, args.vosk_model, args.sensevoice_model, args.sensevoice_tokens)
    server = None
    try:
        semantic_config, semantic_error = voice_lab_configuration()
        if semantic_error:print(semantic_error,flush=True)
        if args.semantic_provider:
            from dataclasses import replace
            semantic_config = replace(semantic_config, provider=args.semantic_provider)
        lab = VoiceLab(args.storage, asr,args.domain_version, semantic_config=semantic_config,
                       semantic_configuration_error=semantic_error)
        if args.import_export:print(f"已导入{lab.import_export(args.import_export)}条历史记录，原记录不覆盖。",flush=True)
        server = LocalServer(lab, args.port)
        print(f"Windows浏览器地址：http://localhost:{args.port}/", flush=True)
        print(asr.status["label"]+"："+asr.status["reason"], flush=True)
        print(f"本地录音与评测目录：{args.storage.resolve()}；Ctrl+C停止。", flush=True)
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print("语音测试台已停止。", flush=True)
    finally:
        if server:
            server.server_close()
        asr.close()
