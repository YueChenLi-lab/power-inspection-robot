import base64
from datetime import datetime
import hashlib
import http.client
import io
import json
from pathlib import Path
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import wave

from inspection_brain.service import InspectionBrain
from voice_lab.asr import LocalASR, _worker
from voice_lab.audio import decode_wav
from voice_lab.metrics import character_error, evaluate, aggregate
from voice_lab.server import VoiceLab, LocalServer

NOW = datetime.fromisoformat("2026-10-08T12:00:00+08:00")


def wav_bytes(rate=16000, channels=1, frames=1600, width=2):
    stream = io.BytesIO()
    with wave.open(stream, "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(width)
        output.setframerate(rate)
        output.writeframes(b"\0" * frames * channels * width)
    return stream.getvalue()


class TestASR:
    """Test double only; never used by CLI/default server or published ASR measurements."""
    status = {"configured": True, "label": "UNIT TEST STUB", "engine": "test_stub"}
    def transcribe(self, pcm):
        return {"status": "ok", "text": "一号主变是什么？", "engine": "test_stub"}
    def close(self):
        pass


class ASRInterfaceTests(unittest.TestCase):
    class Pipe:
        def __init__(self):
            self.messages = []
            self.requests = iter([b"\0" * 16000, None])
            self.closed = False
        def send(self, value):
            self.messages.append(value)
        def recv(self):
            return next(self.requests)
        def close(self):
            self.closed = True

    def test_vosk_actual_interface_keeps_engine_segments(self):
        calls = []
        class Recognizer:
            def __init__(self, model, rate):
                calls.append(("recognizer", model, rate))
            def AcceptWaveform(self, chunk):
                calls.append(("chunk", len(chunk)))
                return True
            def Result(self):
                return '{"text":"电流互感器"}'
            def FinalResult(self):
                return '{"text":"是什么"}'
        module = SimpleNamespace(Model=lambda path: "test-model", KaldiRecognizer=Recognizer)
        pipe = self.Pipe()
        with patch.dict(sys.modules, {"vosk": module}):
            _worker(pipe, "vosk", {"model": "TEST MODEL PATH"})
        self.assertTrue(pipe.messages[0]["ready"])
        self.assertEqual(pipe.messages[1]["text"], "电流互感器 电流互感器 是什么")
        self.assertEqual(len(pipe.messages[1]["engine_results"]), 3)
        self.assertIn(("recognizer", "test-model", 16000), calls)
        self.assertEqual(sum(length for label, length in calls[1:] if label == "chunk"), 16000)
        self.assertTrue(pipe.closed)

    def test_sensevoice_cpu_stream_interface(self):
        calls = {}
        class Samples:
            def astype(self, dtype):
                calls["dtype"] = dtype
                return self
            def __truediv__(self, denominator):
                calls["scale"] = denominator
                return self
        class Stream:
            result = SimpleNamespace(text="什么是局部放电")
            def accept_waveform(self, rate, samples):
                calls["waveform_rate"] = rate
        recognizer = SimpleNamespace(create_stream=lambda: Stream(), decode_stream=lambda stream: calls.update(decoded=True))
        def factory(**kwargs):
            calls["config"] = kwargs
            return recognizer
        np = SimpleNamespace(float32="FLOAT32 TEST TYPE", frombuffer=lambda data, dtype: Samples())
        sherpa = SimpleNamespace(OfflineRecognizer=SimpleNamespace(from_sense_voice=factory))
        pipe = self.Pipe()
        with patch.dict(sys.modules, {"numpy": np, "sherpa_onnx": sherpa}):
            _worker(pipe, "sensevoice", {"model": "TEST MODEL", "tokens": "TEST TOKENS"})
        self.assertEqual(calls["config"]["provider"], "cpu")
        self.assertEqual(calls["config"]["language"], "zh")
        self.assertEqual(calls["waveform_rate"], 16000)
        self.assertEqual(calls["scale"], 32768)
        self.assertEqual(pipe.messages[1]["text"], "什么是局部放电")

    def test_model_load_failure_is_not_a_transcript(self):
        def fail(path):
            raise RuntimeError("TEST LOAD ERROR")
        pipe = self.Pipe()
        with patch.dict(sys.modules, {"vosk": SimpleNamespace(Model=fail)}):
            _worker(pipe, "vosk", {"model": "TEST"})
        self.assertFalse(pipe.messages[0]["ready"])
        self.assertNotIn("text", pipe.messages[0])
        self.assertTrue(pipe.closed)


class AudioTests(unittest.TestCase):
    def test_mono_stereo_and_resample(self):
        for rate in (8000, 16000, 44100, 48000):
            for channels in (1, 2):
                audio = decode_wav(wav_bytes(rate, channels, rate//10))
                self.assertEqual(len(audio.pcm16), 3200)
                self.assertAlmostEqual(audio.duration, .1)
                self.assertEqual(audio.pcm16, b"\0"*3200)

    def test_stereo_average_has_no_interleaving(self):
        payload = bytearray(wav_bytes(channels=2, frames=2))
        payload[44:] = struct.pack("<hhhh", 1000, -1000, 2000, 0)
        self.assertEqual(decode_wav(bytes(payload)).pcm16, struct.pack("<hh", 0, 1000))

    def test_bad_formats_bounds_and_truncation(self):
        original = wav_bytes()
        bad = [b"webm", original[:-1], original+b"junk", wav_bytes(width=1),
               wav_bytes(channels=3), wav_bytes(rate=96000), wav_bytes(frames=0),
               wav_bytes(frames=16000*61)]
        # Adjust RIFF length to conceal truncation; data frame check still rejects it.
        truncated = bytearray(original[:-2]); struct.pack_into("<I", truncated, 4, len(truncated)-8)
        bad.append(bytes(truncated))
        for payload in bad:
            with self.subTest(length=len(payload)), self.assertRaises(ValueError):
                decode_wav(payload)


class MetricTests(unittest.TestCase):
    def setUp(self):
        self.brain = InspectionBrain()

    def metrics(self, ref, text, confirmed=True, homophones=False):
        raw = self.brain.ask(text, now=NOW, apply_homophones=homophones)["analysis"]
        enhanced = raw["normalization"]["normalized_text"]
        after = self.brain.analyzer.analyze(enhanced, now=NOW)
        return evaluate(ref, text, enhanced, self.brain, raw, after, confirmed)

    def test_cer_definition(self):
        self.assertEqual(character_error("电流，互感器！", "电流互感器")["cer"], 0)
        self.assertEqual(character_error("电流", "电压")["cer"], .5)
        self.assertEqual(character_error("电", "电流互感器")["cer"], 4)
        self.assertIsNone(character_error("，", "电流")["cer"])
        self.assertEqual(character_error("01", "1")["cer"], .5)

    def test_distinct_terms_not_collapsed(self):
        m = self.metrics("电流互感器和电压互感器", "电流互感器和电流互感器")
        self.assertEqual(m["before"]["terms"]["accuracy"], .5)
        self.assertEqual(m["before"]["terms"]["extra"], 1)

    def test_alias_terms_and_character_scores_are_separate(self):
        m = self.metrics("什么是电流互感器？", "什么是CT？")
        self.assertEqual(m["before"]["terms"]["accuracy"], 1)
        self.assertGreater(m["before"]["characters"]["cer"], 0)
        self.assertEqual(m["after"]["characters"]["cer"], 0)

    def test_device_number_must_match_equipment_type(self):
        for text in ("二号变压器资料", "一号断路器资料"):
            m = self.metrics("一号变压器资料", text)
            self.assertEqual(m["before"]["device_numbers"]["accuracy"], 0)
        m = self.metrics("01号变压器资料", "1号变压器资料")
        self.assertEqual(m["before"]["device_numbers"]["accuracy"], 0)

    def test_homophone_entities_are_only_diagnostic(self):
        m = self.metrics("一号变压器是什么？", "一号变鸭器是什么？", homophones=True)
        self.assertEqual(m["before"]["device_numbers"]["accuracy"], 0)
        self.assertEqual(m["after"]["device_numbers"]["accuracy"], 1)
        raw = self.brain.ask("一号变鸭器是什么？", now=NOW, apply_homophones=True)["analysis"]
        self.assertEqual(raw["device_entities"], [])

    def test_no_denominator_no_claim(self):
        self.assertFalse(self.metrics("", "什么是电流互感器？")["eligible"])
        self.assertFalse(self.metrics("参考", "什么是电流互感器？", confirmed=False)["eligible"])
        m = self.metrics("你好", "你好")
        self.assertIsNone(m["before"]["terms"]["accuracy"])
        self.assertIsNone(m["before"]["device_numbers"]["accuracy"])


class LabTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.lab = VoiceLab(self.temp.name)

    def tearDown(self):
        self.lab.asr.close()
        self.temp.cleanup()

    def upload(self):
        self.payload = wav_bytes()
        return self.lab.upload({"wav_base64": base64.b64encode(self.payload).decode(),
                                "filename": "../录音.wav"})

    def test_upload_without_asr_never_fabricates(self):
        audio = self.upload()
        self.assertIsNone(audio["asr"]["text"])
        self.assertEqual(audio["asr"]["status"], "unconfigured")
        self.assertEqual(audio["original_filename"], "录音.wav")
        self.assertEqual((Path(self.temp.name)/"audio"/(audio["audio_id"]+".wav")).read_bytes(), self.payload)
        self.assertEqual(audio["sha256"], hashlib.sha256(self.payload).hexdigest())
        with self.assertRaises(ValueError):
            self.lab.evaluate({"input_source": "asr", "audio_id": audio["audio_id"],
                               "raw_asr_text": "试图伪造转写"})

    def test_manual_provenance_and_separate_asr_aggregate(self):
        audio = self.upload()
        row = self.lab.evaluate({"audio_id": audio["audio_id"], "input_source": "manual",
                                 "manual_transcript": "什么是CT？", "reference_text": "什么是电流互感器？",
                                 "reference_confirmed": True})
        self.assertIsNone(row["raw_asr_text"])
        self.assertEqual(row["original_transcript"], "什么是CT？")
        self.assertEqual(row["enhanced_text"], "什么是电流互感器？")
        report = aggregate(self.lab.records())
        self.assertEqual(report["asr"]["confirmed_runs"], 0)
        self.assertIsNone(report["asr"]["before"]["cer"])
        self.assertEqual(report["manual"]["confirmed_runs"], 1)
        # Persisted records survive a new server instance.
        second = VoiceLab(self.temp.name)
        self.assertEqual(second.records(), self.lab.records())
        second.asr.close()

    def test_asr_is_immutable_even_with_manual_edits(self):
        self.lab.asr = TestASR()
        audio = self.upload()
        request = {"audio_id": audio["audio_id"], "input_source": "asr",
                   "raw_asr_text": "前进", "manual_transcript": "前进", "enhanced_text": "前进",
                   "reference_text": "一号主变是什么？", "reference_confirmed": True}
        first = self.lab.evaluate(request)
        request["reference_text"] = "一号主变压器是什么？"
        second = self.lab.evaluate(request)
        self.assertNotEqual(first["record_id"], second["record_id"])
        self.assertEqual(first["original_transcript"], "一号主变是什么？")
        self.assertEqual(second["raw_asr_text"], "一号主变是什么？")
        self.assertEqual(self.lab.audio_metadata(audio["audio_id"]), audio)
        self.assertEqual(aggregate(self.lab.records())["asr"]["confirmed_runs"], 2)
        self.lab.asr = LocalASR(engine="none")

    def test_operations_are_proposals_never_executed(self):
        for text in ("前进", "去到一号变鸭器旁边", "关闭遇障停车", "变压器资料查询后左转"):
            row = self.lab.evaluate({"manual_transcript": text, "apply_homophones": True})
            self.assertEqual(row["original_transcript"], row["enhanced_text"])
            self.assertEqual(row["brain"]["analysis"]["intent"], "operation_proposal")
            self.assertFalse(row["brain"]["result"]["proposal"]["authorized"])
            self.assertEqual(row["executed_actions"], [])

    def test_strict_inputs_and_question_list(self):
        self.assertGreater(len(self.lab.config()["questions"]), 28)
        for data in ({"manual_transcript": "你好", "reference_confirmed": "false"},
                     {"manual_transcript": "你好", "question_id": "bogus"},
                     {"manual_transcript": "你好", "audio_id": "../secret"},
                     {"manual_transcript": "你好", "input_source": "robot"}):
            with self.assertRaises(ValueError):
                self.lab.evaluate(data)

    def test_csv_preserves_details_and_blocks_formula_cells(self):
        row = self.lab.evaluate({"manual_transcript": "=1+1", "reference_text": "=1+1"})
        import csv
        output = list(csv.DictReader(io.StringIO(self.lab.export_csv().decode("utf-8-sig"))))
        self.assertEqual(output[0]["original_transcript"], "'=1+1")
        self.assertEqual(json.loads(output[0]["details_json"])["original_transcript"], "=1+1")
        self.assertEqual(output[0]["record_id"], row["record_id"])


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.lab = VoiceLab(self.temp.name)
        self.server = LocalServer(self.lab, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        self.lab.asr.close()
        self.temp.cleanup()

    def request(self, method, path, data=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        body = json.dumps(data, ensure_ascii=False).encode() if data is not None else None
        combined = {"Content-Type": "application/json", "X-Voice-Lab-Token": self.lab.csrf}
        combined.update(headers or {})
        connection.request(method, path, body=body, headers=combined)
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def test_static_config_and_export_end_to_end(self):
        for path in ("/", "/app.js", "/audio.js", "/pcm-worklet.js", "/style.css"):
            status, headers, content = self.request("GET", path)
            self.assertEqual(status, 200)
            self.assertTrue(content)
            self.assertIn("Content-Security-Policy", headers)
        status, _, body = self.request("GET", "/api/config")
        self.assertFalse(json.loads(body)["asr"]["configured"])
        status, _, body = self.request("POST", "/api/audio", {"wav_base64": base64.b64encode(wav_bytes()).decode()})
        self.assertEqual(status, 200)
        audio = json.loads(body)
        self.assertIsNone(audio["asr"]["text"])
        status, _, body = self.request("POST", "/api/evaluate", {"audio_id": audio["audio_id"],
            "manual_transcript": "什么是局放？", "reference_text": "什么是局部放电？", "reference_confirmed": True})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["enhanced_text"], "什么是局部放电？")
        status, _, body = self.request("GET", "/api/export?format=json")
        self.assertEqual(len(json.loads(body)["records"]), 1)
        self.assertEqual(json.loads(body)["aggregate"]["asr"]["confirmed_runs"], 0)
        status, headers, body = self.request("GET", "/api/export?format=csv")
        self.assertEqual(status, 200)
        self.assertTrue(body.startswith(b"\xef\xbb\xbf"))
        self.assertIn("attachment", headers["Content-Disposition"])

    def test_token_origin_host_and_no_robot_routes(self):
        for headers in ({"X-Voice-Lab-Token": "bad"}, {"Origin": "http://evil.invalid"}, {"Host": "evil.invalid"}):
            self.assertEqual(self.request("POST", "/api/evaluate", {"manual_transcript": "前进"}, headers)[0], 403)
        self.assertEqual(self.request("POST", "/api/evaluate", {}, {"Content-Length": "1000000"})[0], 413)
        self.assertEqual(self.request("POST", "/api/evaluate", [], {})[0], 400)
        self.assertEqual(self.request("POST", "/api/robot/move", {"command": "forward"})[0], 404)
        self.assertEqual(self.request("GET", "/../../RobotTerminal/backend/interaction.py")[0], 404)
        self.assertEqual(self.request("GET", "/api/config", headers={"Host": "evil.invalid"})[0], 403)

    def test_actual_launcher_start_and_clean_stop(self):
        with socket.socket() as candidate:
            candidate.bind(("127.0.0.1", 0))
            port = candidate.getsockname()[1]
        root = Path(__file__).resolve().parents[1]
        process = subprocess.Popen([sys.executable, str(root/"run_voice_lab.py"),
                                    "--asr","none","--port", str(port), "--storage", str(Path(self.temp.name)/"cli")],
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            deadline = time.monotonic()+5
            while True:
                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=.5)
                try:
                    connection.request("GET", "/api/config")
                    response = connection.getresponse()
                    config = json.loads(response.read())
                    self.assertEqual(response.status, 200)
                    break
                except OSError:
                    if time.monotonic() > deadline or process.poll() is not None:
                        self.fail("实际启动脚本未在5秒内提供本地HTTP服务")
                    time.sleep(.05)
                finally:
                    connection.close()
            self.assertFalse(config["asr"]["configured"])
            self.assertEqual(config["asr"]["label"], "ASR 未配置")
            self.assertFalse(config["hardware_commands_enabled"])
            process.send_signal(signal.SIGINT)
            output, _ = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 0, output)
            self.assertIn(f"http://localhost:{port}/", output)
            self.assertIn("语音测试台已停止", output)
        finally:
            if process.poll() is None:
                process.terminate()
                process.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()
