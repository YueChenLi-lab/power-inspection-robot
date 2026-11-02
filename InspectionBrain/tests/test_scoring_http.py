"""Real WAV + real CPU ASR + loopback HTTP. No Windows browser automation claim."""
import base64
import hashlib
import http.client
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest

from voice_lab.asr import LocalASR
from voice_lab.server import VoiceLab, LocalServer

ROOT=Path(__file__).resolve().parents[1]
MODEL=ROOT/'models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17'
WAV=ROOT/'runtime/voice_lab/audio/2cd65701e7a44ff88e1c5a1202f997dc.wav'


class ScoringHTTPTests(unittest.TestCase):
    def start(self,asr):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.lab=VoiceLab(self.temp.name,asr);self.addCleanup(asr.close)
        self.server=LocalServer(self.lab,0)
        thread=threading.Thread(target=self.server.serve_forever,kwargs={'poll_interval':.01},daemon=True);thread.start()
        def stop():self.server.shutdown();self.server.server_close();thread.join(2)
        self.addCleanup(stop)
    def request(self,path,data=None,expected=200):
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_address[1],timeout=60)
        conn.request('GET' if data is None else 'POST',path,json.dumps(data).encode() if data is not None else None,
                     {'Content-Type':'application/json','X-Voice-Lab-Token':self.lab.csrf})
        response=conn.getresponse();raw=response.read();conn.close()
        self.assertEqual(response.status,expected,raw.decode())
        return json.loads(raw) if response.headers.get_content_type()=='application/json' else raw
    def test_missing_model_manual_flow_and_static_page(self):
        self.start(LocalASR('none'))
        html=self.request('/').decode()
        self.assertIn('score-stage',html);self.assertIn('version-status',html)
        self.assertIn('评分并保存',html)
        a=self.request('/api/evaluate',{'mode':'analysis','manual_transcript':'什么是局部放电？'})
        self.assertFalse(a['metrics']['eligible'])
        self.request('/api/evaluate',{'mode':'score','manual_transcript':'什么是局部放电？','reference_text':'什么是局部放电？','reference_confirmed':False},400)
        b=self.request('/api/evaluate',{'mode':'score','manual_transcript':'什么是局部放电？','reference_text':'什么是局部放电？',
                                      'reference_confirmed':True,'derived_from_record_id':a['record_id']})
        self.assertTrue(b['metrics']['eligible'])
        self.assertEqual(self.request('/api/records')['statistics']['independent_test_sample_count'],0)

    @unittest.skipUnless(importlib.util.find_spec('sherpa_onnx') and WAV.is_file() and (MODEL/'model.int8.onnx').is_file(),
                         '需独立 ASR 环境、本地模型及已有真实 WAV；不使用文本伪造推理')
    def test_real_user_wav_scoring_upgrade_and_unique_sample(self):
        raw=WAV.read_bytes();digest=hashlib.sha256(raw).hexdigest()
        self.assertEqual(digest,'a7582a831e6a040d37d98f692e3692b4599ba17c97281099a902c178e3b2f84f')
        asr=LocalASR('sensevoice',sensevoice_model=MODEL/'model.int8.onnx',sensevoice_tokens=MODEL/'tokens.txt')
        self.assertTrue(asr.status['configured'],asr.status);self.start(asr)
        config=self.request('/api/config')
        self.assertEqual(config['lexicon']['loaded_version'],'electrical-v2.3')
        self.assertFalse(config['lexicon']['restart_required'])
        first=self.request('/api/audio',{'wav_base64':base64.b64encode(raw).decode(),'filename':'EXISTING_REAL_USER.wav','capture_source':'wav_upload'})
        self.assertEqual(first['asr']['status'],'ok');self.assertEqual(first['asr']['engine'],'sensevoice')
        self.assertTrue(first['asr']['text']);self.assertEqual(first['sha256'],digest)
        self.assertAlmostEqual(first['duration_seconds'],8.992)
        payload={'mode':'analysis','input_source':'asr','audio_id':first['audio_id']}
        a=self.request('/api/evaluate',payload)
        self.assertEqual(a['raw_asr_text'],first['asr']['text']);self.assertFalse(a['metrics']['eligible'])
        self.assertIsNone(a['metrics']['before']);self.assertIsNone(a['metrics']['after'])
        self.assertIn('temperature_comparison',[i['type'] for i in a['brain']['analysis']['intents']])
        self.assertEqual(self.request('/api/evaluate',payload)['record_id'],a['record_id'])
        self.assertEqual(len(self.request('/api/records')['records']),1)
        # A deliberately labelled fixed reference tests the scoring protocol only.
        # It is NOT asserted to be the person's actual spoken ground truth.
        reference='评分接口固定测试参考：请查询2号主变高压套管的红外测温记录，并与上周的结果比较。'
        score={**payload,'mode':'score','derived_from_record_id':a['record_id'],'reference_text':reference,'reference_confirmed':True}
        self.request('/api/evaluate',{**score,'reference_confirmed':False},400)
        b=self.request('/api/evaluate',score)
        self.assertTrue(b['metrics']['eligible']);self.assertIsInstance(b['metrics']['before']['strict_characters']['cer'],float)
        self.assertEqual(b['derived_from_record_id'],a['record_id']);self.assertEqual(b['analysis_run_id'],a['analysis_run_id'])
        self.assertEqual(self.request('/api/evaluate',score)['record_id'],b['record_id'])
        records=self.request('/api/records');self.assertEqual(records['statistics']['record_count'],2)
        self.assertEqual(records['statistics']['analysis_run_count'],1)
        self.assertEqual(records['statistics']['independent_test_sample_count'],1)
        self.assertEqual(records['statistics']['confirmed_reference_unique_audio_count'],1)
        self.assertEqual(records['aggregate']['sensevoice_asr']['scored_unique_samples'],1)
        variant=self.request('/api/evaluate',{**payload,'apply_homophones':True,'derived_from_record_id':b['record_id']})
        scored_variant=self.request('/api/evaluate',{**score,'apply_homophones':True,'derived_from_record_id':variant['record_id']})
        self.assertEqual(scored_variant['raw_asr_text'],first['asr']['text'])
        second=self.request('/api/retranscribe',{'audio_id':first['audio_id']})
        self.assertEqual(second['sha256'],digest)
        self.request('/api/evaluate',{**payload,'audio_id':second['audio_id']})
        exported=self.request('/api/export?format=json')
        self.assertEqual(exported['statistics']['independent_test_sample_count'],1)
        self.assertEqual(exported['statistics']['unique_audio_sha256_count'],1)
        self.assertEqual(exported['aggregate']['asr']['scored_unique_samples'],1)
        self.assertEqual((Path(self.temp.name)/'audio'/(first['audio_id']+'.wav')).read_bytes(),raw)
        report={'test_kind':'real_existing_user_WAV_CPU_SenseVoice_HTTP','windows_chrome_tested':False,
                'original_record_id':'9bf3bee5bf3e48e3b60a3a33d6966bc5','original_audio_id':WAV.stem,'input_sha256':digest,
                'model':asr.status,'lexicon':config['lexicon'],'inferences':[first,second],
                'unscored_record':a,'scored_record':b,'configuration_variant':scored_variant,'statistics':exported['statistics'],
                'scoring_reference_kind':'fixed_protocol_test_fixture_NOT_human_audio_ground_truth',
                'real_ASR_CER_quality_reported':False,'quality_improvement_claimed':False}
        (ROOT/'reports/scoring_real_user_wav_http.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
