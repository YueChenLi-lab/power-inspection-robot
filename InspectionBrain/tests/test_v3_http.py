"""Actual loopback HTTP transport and existing real WAV; fake LLM clearly labelled."""
import base64
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import http.client
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest

from brain_v3.config import ProviderConfig
from brain_v3.engine import SemanticEngine
from brain_v3.providers import OpenAICompatibleProvider, ProviderError
from voice_lab.asr import LocalASR
from voice_lab.server import VoiceLab, LocalServer

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT/"models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17"
WAV = ROOT/"runtime/voice_lab/audio/2cd65701e7a44ff88e1c5a1202f997dc.wav"


class SemanticHTTPTests(unittest.TestCase):
    def start_lab(self, asr=None, config=None):
        folder = tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        asr = asr or LocalASR("none");self.addCleanup(asr.close)
        self.lab = VoiceLab(folder.name, asr, semantic_config=config)
        self.server = LocalServer(self.lab, 0)
        self.run_server(self.server)

    def run_server(self, server):
        t = threading.Thread(target=server.serve_forever,kwargs={"poll_interval":.01},daemon=True);t.start()
        def stop():server.shutdown();server.server_close();t.join(2)
        self.addCleanup(stop)

    def request(self, path, data=None, expected=200, token=True):
        c=http.client.HTTPConnection("127.0.0.1",self.server.server_address[1],timeout=60)
        headers={"Content-Type":"application/json"}
        if token:headers["X-Voice-Lab-Token"]=self.lab.csrf
        c.request("GET" if data is None else "POST",path,json.dumps(data).encode() if data is not None else None,headers)
        r=c.getresponse();body=r.read();c.close();self.assertEqual(r.status,expected,body)
        return json.loads(body) if r.headers.get_content_type()=="application/json" else body

    def fake_llm(self, behavior="ok", mutate=None, timeout=2, limit=262144):
        calls=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(inner):
                raw=inner.rfile.read(int(inner.headers["Content-Length"]))
                request=json.loads(raw);calls.append({"path":inner.path,"payload":request})
                semantic=json.loads(request["messages"][1]["content"])
                candidate=deepcopy(semantic["evidence"])
                candidate["structured_task_draft"]["reasoning_source"]="llm_candidate"
                if mutate:mutate(candidate)
                if behavior=="redirect":
                    inner.send_response(307);inner.send_header("Location","/elsewhere");inner.end_headers();return
                if behavior=="slow":time.sleep(.3)
                message={"content":json.dumps(candidate,ensure_ascii=False)}
                if behavior=="tools":message["tool_calls"]=[{"id":"forbidden"}]
                body=json.dumps({"model":"HTTP_PROTOCOL_STUB_NOT_REAL_LLM","choices":[{"message":message,"finish_reason":"length" if behavior=="truncated" else "stop"}]}).encode()
                if behavior=="invalid":body=b"not JSON"
                inner.send_response(200);inner.send_header("Content-Length",str(len(body)));inner.end_headers()
                try:inner.wfile.write(body)
                except (BrokenPipeError,ConnectionResetError):pass
        s=ThreadingHTTPServer(("127.0.0.1",0),Handler);s.daemon_threads=True;self.run_server(s)
        config=ProviderConfig(provider="openai_compatible",enabled=True,base_url=f"http://127.0.0.1:{s.server_address[1]}/v1",
                              model="HTTP_PROTOCOL_STUB_NOT_REAL_LLM",api_key="TEST_KEY_ONLY",timeout_seconds=timeout,max_response_bytes=limit)
        return config,calls

    def test_default_v2_and_manual_outage_fallback_do_not_change_voice_records(self):
        self.start_lab()
        cfg=self.request("/api/config")
        self.assertEqual(cfg["semantic_v3"]["default_mode"],"v2_rules")
        self.assertEqual(cfg["semantic_v3"]["provider"]["provider"],"rules")
        self.assertIn(b'id="v3-mode"',self.request("/"))
        self.assertIn(b"setupV3",self.request("/v3.js"))
        schema=self.request("/api/semantic/schema");self.assertEqual(schema["$schema"],"https://json-schema.org/draft/2020-12/schema")
        payload={"input_source":"manual","manual_transcript":"制定巡检计划，但不要启动导航","mode":"auto_fallback"}
        r=self.request("/api/semantic",payload)
        self.assertTrue(r["result"]["fallback_success"])
        self.assertFalse(r["result"]["structured_task_draft"]["executable"])
        self.assertEqual(self.request("/api/records")["records"],[])
        self.assertEqual(self.request("/api/semantic/records")["summary"]["unique_asr_audio_sha256_count"],0)
        old=self.request("/api/evaluate",{"mode":"analysis","manual_transcript":"什么是局部放电？"})
        self.assertFalse(old["metrics"]["eligible"])
        self.request("/api/semantic",payload,403,token=False)
        for endpoint in ("/api/navigate","/api/execute","/api/chassis","/api/switchgear"):
            self.request(endpoint,{},404)

    def test_compatible_provider_actual_http_contract_no_reference_and_no_key_in_records(self):
        config,calls=self.fake_llm();self.start_lab(config=config)
        r=self.request("/api/semantic",{"input_source":"manual","manual_transcript":"不是2号断路器，是3号断路器","mode":"v3_llm",
                                        "reference_text":"PRIVATE_REFERENCE_MUST_NOT_LEAK","equipment_registry":"PRIVATE_ASSET_DATA"})
        self.assertTrue(r["result"]["validation"]["valid"])
        self.assertEqual(calls[0]["path"],"/v1/chat/completions")
        payload=json.dumps(calls[0]["payload"])
        self.assertNotIn("PRIVATE_REFERENCE",payload);self.assertNotIn("PRIVATE_ASSET",payload)
        self.assertNotIn("tools",calls[0]["payload"])
        exported=self.request("/api/semantic/export")
        self.assertNotIn("TEST_KEY_ONLY",json.dumps(exported)+json.dumps(self.request("/api/config")))
        self.assertEqual(exported["records"][0]["provenance"]["provider_configuration_sha256"],config.sha256)
        # Only a protocol fixture, NEVER evidence that a real text model was used.
        self.assertEqual(r["result"]["provider"]["model"],"HTTP_PROTOCOL_STUB_NOT_REAL_LLM")

    def test_remote_hallucinated_device_rejected_then_v2_fallback(self):
        config,_=self.fake_llm(mutate=lambda c:c["equipment_entities"][1].update(device_number="2"))
        self.start_lab(config=config)
        r=self.request("/api/semantic",{"manual_transcript":"不是2号断路器，是3号断路器","mode":"auto_fallback"})
        self.assertEqual(r["result"]["status"],"validation_rejected")
        self.assertTrue(r["result"]["fallback_success"])
        self.assertFalse(r["result"]["structured_task_draft"]["authorized"])

    def test_decode_tool_truncation_size_redirect_and_timeout_errors_are_clear(self):
        for behavior,timeout,limit in (("invalid",2,262144),("tools",2,262144),("truncated",2,262144),("ok",2,1024),("redirect",2,262144),("slow",.1,262144)):
            with self.subTest(behavior=behavior):
                config,calls=self.fake_llm(behavior,timeout=timeout,limit=limit)
                r=SemanticEngine(config=config).analyze("制定巡检计划",mode="auto_fallback")
                self.assertEqual(r["status"],"provider_unavailable")
                self.assertTrue(r["fallback_success"]);self.assertTrue(r["error"])
                self.assertEqual(len(calls),1)

    @unittest.skipUnless(importlib.util.find_spec("sherpa_onnx") and WAV.is_file() and (MODEL/"model.int8.onnx").is_file(),
                         "需已有真实WAV、SenseVoice模型及独立ASR环境；不会伪造真实推理")
    def test_real_wav_sensevoice_v2_mock_validation_and_dedup_http(self):
        asr=LocalASR("sensevoice",sensevoice_model=MODEL/"model.int8.onnx",sensevoice_tokens=MODEL/"tokens.txt")
        self.assertTrue(asr.status["configured"],asr.status)
        self.start_lab(asr,ProviderConfig(provider="mock"))
        audio=self.request("/api/audio",{"wav_base64":base64.b64encode(WAV.read_bytes()).decode(),"filename":"EXISTING_REAL_USER.wav"})
        self.assertEqual(audio["asr"]["status"],"ok");self.assertEqual(audio["asr"]["engine"],"sensevoice")
        self.assertEqual(audio["sha256"],"a7582a831e6a040d37d98f692e3692b4599ba17c97281099a902c178e3b2f84f")
        p={"audio_id":audio["audio_id"],"input_source":"asr","mode":"v3_llm","manual_transcript":"CLIENT_FORGERY_IGNORED"}
        first=self.request("/api/semantic",p)
        self.assertEqual(first["original_transcript"],audio["asr"]["text"])
        self.assertTrue(first["result"]["validation"]["valid"])
        self.assertFalse(first["result"]["provider"]["is_real_llm"])
        self.assertEqual(first["result"]["lexicon_version"],"electrical-v2.3")
        repeat=self.request("/api/semantic",p);self.assertEqual(repeat["record_id"],first["record_id"])
        variant=self.request("/api/semantic",{**p,"apply_homophones":True})
        self.assertEqual(variant["original_transcript"],first["original_transcript"])
        export=self.request("/api/semantic/export")
        self.assertEqual(export["summary"]["analysis_run_count"],2)
        self.assertEqual(export["summary"]["unique_asr_audio_sha256_count"],1)
        self.assertIsNone(export["summary"]["semantic_accuracy"])
        self.assertEqual(self.request("/api/records")["records"],[])
        report={"kind":"REAL_EXISTING_WAV_SENSEVOICE_HTTP_V3_MOCK", "windows_chrome_tested":False,"real_llm_connected":False,
                "audio":audio,"semantic_records":export,"source_original_audio_id":WAV.stem,
                "human_semantic_gold_available":False,"semantic_accuracy_claimed":False,"asr_cer_improvement_claimed":False}
        (ROOT/"reports/v3_real_wav_http.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")


if __name__ == "__main__":unittest.main()
