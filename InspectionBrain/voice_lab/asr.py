"""Opt-in CPU ASR workers. No production imports, downloads or hardware access."""
import importlib.util
import json
import multiprocessing
import os
from pathlib import Path
import platform
import threading
import time


def pcm_segments(pcm,maximum_seconds=20):
    """Non-overlapping segments, favoring quiet cuts; every input sample is retained."""
    from array import array
    rows=[];offset=0;limit=maximum_seconds*16000*2
    while offset<len(pcm):
        end=min(offset+limit,len(pcm))
        if end<len(pcm):
            # Quiet 100ms window in the final 3s; never drop any frame as VAD would.
            candidates=[]
            for position in range(max(offset+16000*2,end-3*16000*2),end-3200,1600):
                values=array('h');values.frombytes(pcm[position:position+3200])
                energy=sum(abs(v) for v in values)/len(values)
                candidates.append((energy,position+1600))
            quiet=min(candidates,default=(99999,end))
            if quiet[0]<400:end=quiet[1]
        rows.append((offset//2/16000,end//2/16000,pcm[offset:end]))
        offset=end
    return rows


def _worker(pipe, engine, config):
    try:
        if config.get("enforce_limits"):
            os.environ["OPENBLAS_NUM_THREADS"]="1"
            os.environ["OMP_NUM_THREADS"]=str(config.get("threads",2))
            import resource
            limit=config.get("memory_mb",4096)*1024*1024
            resource.setrlimit(resource.RLIMIT_AS,(limit,limit))
        if engine == "vosk":
            import vosk
            model = vosk.Model(config["model"])
        else:
            import numpy as np
            import sherpa_onnx
            recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
                model=config["model"], tokens=config["tokens"], num_threads=config.get("threads",2),
                sample_rate=16000, language="zh", use_itn=True, provider="cpu")
        pipe.send({"ready": True})
        while True:
            pcm = pipe.recv()
            if pcm is None:
                break
            try:
                started=time.perf_counter()
                if engine == "vosk":
                    recognizer = vosk.KaldiRecognizer(model, 16000)
                    segments = []
                    for offset in range(0, len(pcm), 8000):
                        if recognizer.AcceptWaveform(pcm[offset:offset+8000]):
                            segments.append(json.loads(recognizer.Result()))
                    segments.append(json.loads(recognizer.FinalResult()))
                    text = " ".join(segment.get("text", "") for segment in segments).strip()
                    result = {"text": text, "engine_results": segments}
                else:
                    segments=[]
                    for start,end,chunk in pcm_segments(pcm):
                        samples = np.frombuffer(chunk, dtype="<i2").astype(np.float32) / 32768.0
                        stream = recognizer.create_stream()
                        stream.accept_waveform(16000, samples)
                        recognizer.decode_stream(stream)
                        segments.append({"start_seconds":start,"end_seconds":end,"text":stream.result.text})
                    result={"text":" ".join(s["text"] for s in segments if s["text"]),"segments":segments,
                            "segmentation_policy":"contiguous_pause_favored_no_vad_no_text_dedup",
                            "warnings":["长音频分段边界可能影响词语；已保留各段顺序和原输出，请人工核对"] if len(segments)>1 else []}
                result["inference_seconds"]=time.perf_counter()-started
                pipe.send({"ok": True, **result})
            except Exception as exc:
                pipe.send({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
    except Exception as exc:
        pipe.send({"ready": False, "error": f"{type(exc).__name__}: {exc}"})
    finally:
        pipe.close()


class LocalASR:
    def __init__(self, engine="auto", vosk_model=None, sensevoice_model=None,
                 sensevoice_tokens=None, load_timeout=30, inference_timeout=45,threads=2,memory_mb=4096):
        self.lock = threading.Lock()
        self.process = self.pipe = None
        self.timeout = inference_timeout
        self.status = {"configured": False, "label": "ASR 未配置", "engine": None,
                       "reason": "未发现同时可用的本地ASR库与模型；不会下载模型或伪造转写。"}
        available = {name: importlib.util.find_spec(name) is not None
                     for name in ("vosk", "sherpa_onnx", "numpy")}
        self.status["libraries"] = available
        self.status.update(provider="cpu",python_environment=os.sys.executable,python_version=platform.python_version(),
                           sample_rate=16000,threads=threads,memory_limit_mb=memory_mb,
                           model_id=None,model_version=None)
        if engine == "none":
            self.status["reason"] = "已显式关闭ASR；支持WAV上传及手动粘贴转写。"
            return
        # Explicit paths only. Never read production configuration or connect to its ASR worker.
        candidates = []
        if engine in ("auto", "vosk") and available["vosk"] and vosk_model and Path(vosk_model).is_dir():
            candidates.append(("vosk", {"model": str(Path(vosk_model).resolve())}))
        if engine in ("auto", "sensevoice") and available["sherpa_onnx"] and available["numpy"] and sensevoice_model and sensevoice_tokens:
            if Path(sensevoice_model).is_file() and Path(sensevoice_tokens).is_file():
                candidates.append(("sensevoice", {"model": str(Path(sensevoice_model).resolve()),
                                                  "tokens": str(Path(sensevoice_tokens).resolve())}))
        errors = []
        for name, config in candidates:
            config.update(threads=threads,memory_mb=memory_mb,enforce_limits=True)
            context = multiprocessing.get_context("spawn")
            parent, child = context.Pipe()
            self.pipe = parent
            self.process = context.Process(target=_worker, args=(child, name, config), daemon=True)
            self.process.start()
            child.close()
            try:
                result = parent.recv() if parent.poll(load_timeout) else {"ready": False, "error": "模型加载超时"}
            except (EOFError, OSError) as exc:
                result = {"ready": False, "error": str(exc)}
            if result.get("ready"):
                self.status.update(configured=True, label="本地离线ASR已就绪", engine=name,
                                   model_id=Path(config["model"]).parent.name if name=="sensevoice" else Path(config["model"]).name,
                                   model_version="2024-07-17-int8" if "2024-07-17" in config["model"] and "int8" in config["model"] else "user_supplied_unversioned",
                                   reason="仅用于此测试台；CPU推理，未连接原语音服务。")
                return
            errors.append(name + ": " + result.get("error", "模型加载失败"))
            self.close()
        if errors:
            self.status["reason"] = "；".join(errors)

    def transcribe(self, pcm16):
        with self.lock:
            if not self.status["configured"]:
                return {"status": "unconfigured", "text": None, "engine": self.status["engine"],
                        "message": self.status["label"] + "：" + self.status["reason"]}
            try:
                self.pipe.send(pcm16)
                if not self.pipe.poll(self.timeout):
                    raise TimeoutError("离线ASR推理超时")
                result = self.pipe.recv()
                if not result.get("ok"):
                    return {"status": "error", "text": None, "engine": self.status["engine"],
                            "message": result.get("error", "ASR失败")}
                return {"status": "ok" if result["text"] else "empty", "text": result["text"],
                        "engine": self.status["engine"], "engine_results": result.get("engine_results"),
                        "segments":result.get("segments"),"inference_seconds":result.get("inference_seconds"),
                        "warnings":result.get("warnings",[]),"model_id":self.status["model_id"],"model_version":self.status["model_version"],
                        "provider":"cpu","sample_rate":16000,"input_seconds":len(pcm16)/32000}
            except (EOFError, OSError, TimeoutError) as exc:
                self.close()
                self.status.update(configured=False, label="ASR 未配置", reason=str(exc))
                return {"status": "error", "text": None, "engine": self.status["engine"], "message": str(exc)}

    def close(self):
        if self.process:
            if self.process.is_alive():
                self.process.terminate()
            self.process.join(timeout=2)
            self.process.close()
            self.process = None
        if self.pipe:
            self.pipe.close()
            self.pipe = None
