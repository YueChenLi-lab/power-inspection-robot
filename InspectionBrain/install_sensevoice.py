"""Explicit local installer: official PyPI wheels + official sherpa ASR release only."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import urllib.request
import venv
import zipfile

ROOT=Path(__file__).resolve().parent
MODEL_ID="sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17"
MODEL_URL=f"https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/{MODEL_ID}.tar.bz2"
MODEL_SHA256="7d1efa2138a65b0b488df37f8b89e3d91a60676e416f515b952358d83dfd347e"


def download(url,destination,expected=None):
    if destination.exists() and expected and hashlib.sha256(destination.read_bytes()).hexdigest()==expected:return
    part=destination.with_suffix(destination.suffix+".part")
    digest=hashlib.sha256();count=0
    with urllib.request.urlopen(url,timeout=45) as source,part.open("wb") as output:
        while chunk:=source.read(1024*1024):
            count+=len(chunk)
            if count>350*1024*1024:raise ValueError("下载超出350MiB限制")
            output.write(chunk);digest.update(chunk)
    if expected and digest.hexdigest()!=expected:raise ValueError("官方SHA256不匹配，拒绝使用下载文件")
    part.replace(destination)
    print(destination.name,count,"bytes",digest.hexdigest(),flush=True)


def main():
    downloads=ROOT/"downloads";downloads.mkdir(exist_ok=True)
    models=ROOT/"models";models.mkdir(exist_ok=True)
    environment=ROOT/".venv-asr"
    venv.EnvBuilder(with_pip=False,symlinks=True).create(environment)
    python=environment/"bin"/"python"
    # Ubuntu lacks ensurepip. Bootstrap pip from an official hash-checked wheel inside this venv.
    with urllib.request.urlopen("https://pypi.org/pypi/pip/json",timeout=30) as response:metadata=json.load(response)
    wheel=next(item for item in metadata["urls"] if item["filename"].endswith("py3-none-any.whl"))
    target=downloads/wheel["filename"]
    download(wheel["url"],target,wheel["digests"]["sha256"])
    site=Path(subprocess.check_output([str(python),"-c","import sysconfig;print(sysconfig.get_path('purelib'))"],text=True).strip())
    with zipfile.ZipFile(target) as archive:
        for member in archive.namelist():
            if Path(member).is_absolute() or ".." in Path(member).parts:raise ValueError("wheel路径无效")
        archive.extractall(site)
    subprocess.run([str(python),"-m","pip","install","--disable-pip-version-check","--no-cache-dir",
                    "--index-url","https://pypi.org/simple","--only-binary=:all:",
                    "--report",str(ROOT/"reports"/"asr_pip_install.json"),"sherpa-onnx==1.13.8","numpy==2.5.3"],check=True)
    archive_path=downloads/(MODEL_ID+".tar.bz2")
    download(MODEL_URL,archive_path,MODEL_SHA256)
    with tarfile.open(archive_path,"r:bz2") as archive:
        members=archive.getmembers()
        if sum(m.size for m in members)>600*1024*1024:raise ValueError("模型解压超出限制")
        for member in members:
            path=Path(member.name)
            if path.is_absolute() or ".." in path.parts or path.parts[0]!=MODEL_ID or not (member.isfile() or member.isdir()):raise ValueError("模型归档含不安全路径/链接")
        archive.extractall(models,filter="data")
    folder=models/MODEL_ID
    records=[{"path":str(p.relative_to(ROOT)),"bytes":p.stat().st_size,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()}
             for p in folder.rglob('*') if p.is_file()]
    manifest={"model_id":MODEL_ID,"model_version":"2024-07-17-int8","provider":"cpu","source":MODEL_URL,
              "archive_sha256":MODEL_SHA256,"archive_bytes":archive_path.stat().st_size,
              "license_text":(folder/"LICENSE").read_text(),"files":records,
              "python":str(python),"python_version":subprocess.check_output([str(python),"--version"],text=True).strip(),
              "dependencies":subprocess.check_output([str(python),"-m","pip","freeze"],text=True).splitlines(),
              "pip_bootstrap":{"source":wheel["url"],"sha256":wheel["digests"]["sha256"]},
              "status":"downloaded_not_yet_inference_verified"}
    (ROOT/"reports"/"sensevoice_installation.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n")
    print('Installed isolated environment and official model. Actual inference must be checked next.',flush=True)


if __name__=="__main__":
    try:main()
    except Exception as error:
        (ROOT/"reports"/"sensevoice_install_failure.json").write_text(json.dumps({"error_type":type(error).__name__,"error":str(error),"command":"python3 InspectionBrain/install_sensevoice.py","model_url":MODEL_URL},ensure_ascii=False,indent=2)+"\n")
        raise
