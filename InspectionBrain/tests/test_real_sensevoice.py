import base64
import hashlib
import http.client
import importlib.util
import json
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from voice_lab.asr import LocalASR,pcm_segments
from voice_lab.server import LocalServer,VoiceLab

ROOT=Path(__file__).resolve().parents[1]
MODEL=ROOT/"models"/"sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17"


class SegmentationTests(unittest.TestCase):
    def test_contiguous_segments_never_drop_or_duplicate_samples(self):
        pcm=b'\x01\x00'*(16000*45+13)
        segments=pcm_segments(pcm)
        self.assertGreater(len(segments),1)
        self.assertEqual(b''.join(row[2] for row in segments),pcm)
        self.assertEqual(segments[0][0],0)
        self.assertAlmostEqual(segments[-1][1],len(pcm)/32000)
        for previous,current in zip(segments,segments[1:]):self.assertEqual(previous[1],current[0])


@unittest.skipUnless(importlib.util.find_spec('sherpa_onnx') and (MODEL/'test_wavs/zh.wav').is_file(),"需独立.venv-asr及官方模型；不能用手动文本替代真实模型测试")
class RealSenseVoiceTests(unittest.TestCase):
    def test_system_python_launcher_selects_isolated_environment(self):
        with socket.socket() as candidate:
            candidate.bind(('127.0.0.1',0));port=candidate.getsockname()[1]
        with tempfile.TemporaryDirectory() as folder:
            process=subprocess.Popen([sys._base_executable,str(ROOT/'run_voice_lab.py'),'--port',str(port),
                                      '--storage',folder,'--import-export',str(ROOT.parent/'voice-evaluation.json')],
                                     stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
            try:
                deadline=time.monotonic()+35
                while True:
                    connection=http.client.HTTPConnection('127.0.0.1',port,timeout=1)
                    try:
                        connection.request('GET','/api/config');response=connection.getresponse();config=json.loads(response.read());break
                    except OSError:
                        if time.monotonic()>deadline or process.poll() is not None:self.fail('启动器未提供实际ASR服务')
                        time.sleep(.1)
                    finally:connection.close()
                self.assertTrue(config['asr']['configured'],config)
                self.assertEqual(config['asr']['engine'],'sensevoice')
                self.assertEqual(config['domain_version'],'v2')
                self.assertIn('.venv-asr',config['asr']['python_environment'])
                connection=http.client.HTTPConnection('127.0.0.1',port,timeout=2)
                connection.request('GET','/api/records');records=json.loads(connection.getresponse().read());connection.close()
                self.assertEqual(len(records['records']),9)
                self.assertEqual(records['aggregate']['manual']['confirmed_runs'],0)
                process.send_signal(signal.SIGINT);output,_=process.communicate(timeout=5)
                self.assertEqual(process.returncode,0,output)
            finally:
                if process.poll() is None:process.terminate();process.communicate(timeout=5)
    def test_real_wav_http_repeated_inference_and_export(self):
        original=(MODEL/'test_wavs/zh.wav').read_bytes()
        asr=LocalASR('sensevoice',sensevoice_model=MODEL/'model.int8.onnx',sensevoice_tokens=MODEL/'tokens.txt')
        self.assertTrue(asr.status['configured'],asr.status)
        with tempfile.TemporaryDirectory() as folder:
            lab=VoiceLab(folder,asr)
            server=LocalServer(lab,0)
            thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01},daemon=True);thread.start()
            def request(path,data=None):
                connection=http.client.HTTPConnection('127.0.0.1',server.server_address[1],timeout=60)
                connection.request('GET' if data is None else 'POST',path,
                                   body=json.dumps(data).encode() if data is not None else None,
                                   headers={'Content-Type':'application/json','X-Voice-Lab-Token':lab.csrf})
                response=connection.getresponse();payload=json.loads(response.read());connection.close()
                self.assertEqual(response.status,200,payload);return payload
            try:
                config=request('/api/config');self.assertEqual(config['asr']['engine'],'sensevoice')
                first=request('/api/audio',{'wav_base64':base64.b64encode(original).decode(),'filename':'OFFICIAL_zh.wav','capture_source':'wav_upload'})
                self.assertEqual(first['asr']['status'],'ok',first)
                self.assertGreater(len(first['asr']['text']),5)
                second=request('/api/retranscribe',{'audio_id':first['audio_id']})
                self.assertEqual(second['sha256'],first['sha256'])
                self.assertEqual(second['asr']['text'],first['asr']['text'])
                self.assertNotEqual(second['audio_id'],first['audio_id'])
                self.assertEqual(lab.audio_metadata(second['audio_id'])['retranscribed_from_audio_id'],first['audio_id'])
                rows=[]
                for audio in (first,second):
                    row=request('/api/evaluate',{'audio_id':audio['audio_id'],'input_source':'asr',
                                                'raw_asr_text':'这不是模型结果，必须忽略','reference_text':'','reference_confirmed':False})
                    self.assertEqual(row['original_transcript'],audio['asr']['text'])
                    self.assertFalse(row['metrics']['eligible'])
                    self.assertEqual(row['executed_actions'],[])
                    self.assertIn('cleaned_display_text',row)
                    self.assertTrue((Path(folder)/'audio'/(audio['audio_id']+'.wav')).read_bytes()==original)
                    rows.append(row)
                exported=request('/api/export?format=json')
                self.assertEqual(len(exported['records']),2)
                report={'demo_type':'official_real_speech_WAV_loopback_HTTP_integration',
                        'source':'official sherpa-onnx model archive test_wavs/zh.wav',
                        'user_electrical_audio':False,'windows_microphone_tested':False,
                        'input_sha256':hashlib.sha256(original).hexdigest(),'model_status':asr.status,
                        'inferences':[first,second],'evaluations':rows,'exported_aggregate':exported['aggregate'],
                        'asr_quality_improvement_claimed':False,'reference_confirmed':False}
                # Preserve the previous round's report; this execution is a new validation.
                (ROOT/'reports/scoring_official_http_real_asr_demo.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
            finally:
                server.shutdown();server.server_close();thread.join(2);asr.close()
