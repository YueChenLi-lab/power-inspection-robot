"""Run without installing dependencies: python3 InspectionBrain/run_voice_lab.py."""
import os
from pathlib import Path
import subprocess
import sys

if __name__ == "__main__":
    environment=Path(__file__).resolve().parent/".venv-asr"
    interpreter=environment/"bin"/"python"
    explicitly_disabled=any(arg=="--asr=none" for arg in sys.argv) or any(sys.argv[i:i+2]==["--asr","none"] for i in range(len(sys.argv)-1))
    if interpreter.is_file() and Path(sys.prefix).resolve()!=environment.resolve() and not explicitly_disabled:
        try:
            probe=subprocess.run([str(interpreter),"-c","import sherpa_onnx,numpy"],capture_output=True,timeout=5)
            if probe.returncode==0:os.execv(str(interpreter),[str(interpreter),str(Path(__file__).resolve()),*sys.argv[1:]])
            print("独立ASR环境不可用；回退当前Python，页面仍可手动测试。",flush=True)
        except (OSError,subprocess.TimeoutExpired):
            print("无法启动独立ASR环境；回退当前Python。",flush=True)
    from voice_lab.server import main
    main()
