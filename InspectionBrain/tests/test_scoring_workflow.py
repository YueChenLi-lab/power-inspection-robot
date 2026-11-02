from datetime import datetime
import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from inspection_brain.domain_v2.service import ElectricalBrainV2
from voice_lab.server import VoiceLab
from voice_lab.metrics import aggregate, sample_statistics, grouped_comparison
from tests.test_voice_lab import wav_bytes

ROOT = Path(__file__).resolve().parents[1]
RAW = "请查询2号主变电压高套管的红外测温记录，并与上周的结果比较。"
NOW = datetime.fromisoformat("2026-10-09T14:34:50+08:00")


class HistorySemanticsTests(unittest.TestCase):
    def setUp(self): self.brain = ElectricalBrainV2()
    def test_actual_record_without_reference_leakage(self):
        saved = json.loads((ROOT/'runtime/voice_lab/records/9bf3bee5bf3e48e3b60a3a33d6966bc5.json').read_text())
        self.assertEqual(saved['original_transcript'], RAW)
        self.assertFalse(saved['metrics']['eligible'])
        for enabled in (False, True):
            r=self.brain.ask(saved['original_transcript'],now=NOW,apply_homophones=enabled)
            a=r['analysis']; kinds={i['type'] for i in a['intents']}
            self.assertTrue({'thermometry_history','temperature_comparison'} <= kinds)
            self.assertNotIn('temperature_alarm_query',kinds)
            self.assertEqual(a['raw_transcript'],RAW)
            self.assertNotIn('voltage',[t['term_id'] for t in a['normalization']['recognized_terms']])
            c=next(c for c in a['normalization']['homophone_candidates'] if c['surface']=='电压高套管')
            self.assertEqual(c['replacement'],'高压套管');self.assertFalse(c['applied'])
            self.assertTrue(c['display_confirmation_allowed'])
            self.assertEqual(a['device_entities'][0]['device_number'],'2')
            self.assertEqual(a['inspection_parts'][0]['standard_name'],'套管')
            self.assertEqual(a['measurement_methods'],['infrared_thermometry'])
            baseline=a['comparison_constraints']['baseline']
            self.assertEqual(baseline['start'],'2026-09-28T00:00:00+08:00')
            self.assertEqual(baseline['end'],'2026-10-05T00:00:00+08:00')
            self.assertFalse(a['comparison_constraints']['target']['resolved'])
            self.assertEqual(r['result']['status'],'undetermined');self.assertIsNone(r['result']['site_conclusion'])
            self.assertEqual(r['executed_actions'],[])
    def test_unseen_word_order_and_number_not_repaired(self):
        for text in ('比较上周与今天02号主变的红外测温记录','查询7号变压器高压套管历史温度记录，与上周对比'):
            a=self.brain.ask(text,now=NOW)['analysis']
            self.assertIn('temperature_comparison',[i['type'] for i in a['intents']])
            self.assertNotIn('voltage',[t['term_id'] for t in a['normalization']['recognized_terms']])
        a=self.brain.ask('查询02号主变电压高套管记录，读数685℃',now=NOW,apply_homophones=True)['analysis']
        self.assertEqual(a['device_entities'][0]['device_number'],'02')
        self.assertIn('685℃',a['term_normalized_text'])
    def test_confusion_context_and_operation_protection(self):
        for text in ('小说标题电压高套管','电压高套管是什么网名','操作2号主变电压高套管'):
            a=self.brain.ask(text,now=NOW,apply_homophones=True)['analysis']
            self.assertIn('电压高套管',a['term_normalized_text'])
            candidates=a['normalization']['homophone_candidates']
            self.assertTrue(candidates);self.assertFalse(candidates[0]['display_confirmation_allowed'])
    def test_temperature_intents_are_distinct(self):
        cases={'查询2号主变红外测温记录':'thermometry_history','2号主变温度有没有异常':'temperature_anomaly_query',
               '查询2号主变温度告警记录':'temperature_alarm_query','查询2号主变当前温度':'temperature_measurement_query'}
        for text,expected in cases.items():
            with self.subTest(text=text):self.assertEqual(self.brain.ask(text,now=NOW)['analysis']['intent'],expected)
    def test_week_boundary_uses_explicit_shanghai_timezone(self):
        # UTC Sunday is already Monday in Shanghai: both target and baseline must agree.
        a=self.brain.ask('对比今天2号主变红外测温记录与上周',now=datetime.fromisoformat('2026-10-04T17:00:00+00:00'))['analysis']
        self.assertEqual(a['comparison_constraints']['baseline']['start'],'2026-09-28T00:00:00+08:00')
        self.assertEqual(a['comparison_constraints']['target']['start'],'2026-10-05T00:00:00+08:00')


class FixtureASR:
    status={'configured':True,'engine':'workflow_test_stub','model_id':'fixture','model_version':'1'}
    def transcribe(self, pcm): return {**self.status,'status':'ok','text':RAW}
    def close(self): pass


class ScoringWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.lab=VoiceLab(self.temp.name,FixtureASR())
        self.audio=self.lab.upload({'wav_base64':base64.b64encode(wav_bytes()).decode()})
        self.base={'audio_id':self.audio['audio_id'],'input_source':'asr','mode':'analysis'}
    def tearDown(self):self.lab.asr.close();self.temp.cleanup()
    def test_analysis_then_score_links_and_reuses_analysis(self):
        analysis=self.lab.evaluate(self.base)
        self.assertFalse(analysis['metrics']['eligible'])
        original=(Path(self.temp.name)/'records'/(analysis['record_id']+'.json')).read_bytes()
        score=self.lab.evaluate({**self.base,'mode':'score','derived_from_record_id':analysis['record_id'],
            'reference_text':'固定测试参考，不用于真实ASR质量结论','reference_confirmed':True})
        self.assertTrue(score['metrics']['eligible']);self.assertEqual(score['derived_from_record_id'],analysis['record_id'])
        self.assertEqual(score['analysis_run_id'],analysis['analysis_run_id'])
        self.assertEqual(score['audio'],analysis['audio']);self.assertEqual(score['raw_asr_text'],RAW)
        self.assertEqual(original,(Path(self.temp.name)/'records'/(analysis['record_id']+'.json')).read_bytes())
        self.assertEqual(sample_statistics(self.lab.records())['analysis_run_count'],1)
    def test_duplicate_clicks_and_restart_do_not_append(self):
        a=self.lab.evaluate(self.base);b=self.lab.evaluate(self.base)
        self.assertEqual(a['record_id'],b['record_id'])
        fresh=VoiceLab(self.temp.name,FixtureASR())
        self.assertEqual(fresh.evaluate(self.base)['record_id'],a['record_id'])
        self.assertEqual(len(fresh.records()),1)
    def test_configuration_variants_and_retranscription_share_sample(self):
        self.lab.evaluate(self.base)
        self.lab.evaluate({**self.base,'apply_homophones':True})
        second=self.lab.retranscribe({'audio_id':self.audio['audio_id']})
        self.lab.evaluate({**self.base,'audio_id':second['audio_id']})
        s=sample_statistics(self.lab.records())
        self.assertEqual(s['record_count'],3);self.assertEqual(s['independent_test_sample_count'],1)
        self.assertEqual(s['unique_audio_sha256_count'],1)
        self.assertEqual(len(grouped_comparison(self.lab.records())),2)
    def test_unconfirmed_score_is_rejected_and_manual_still_works(self):
        for reference,confirmed in (('',True),('测试参考',False),('，。',True)):
            with self.assertRaises(ValueError):self.lab.evaluate({**self.base,'mode':'score','reference_text':reference,'reference_confirmed':confirmed})
        r=self.lab.evaluate({'mode':'analysis','manual_transcript':'什么是局部放电？'})
        self.assertFalse(r['metrics']['eligible']);self.assertEqual(r['input_source'],'manual')
        self.assertEqual(sample_statistics(self.lab.records())['independent_test_sample_count'],0)
    def test_scored_statistics_deduplicate_hash_and_preserve_runs(self):
        for enabled in (False,True):
            self.lab.evaluate({**self.base,'mode':'score','reference_text':'人工测试参考','reference_confirmed':True,'apply_homophones':enabled})
        rows=self.lab.records();s=sample_statistics(rows)
        self.assertEqual(s['confirmed_reference_unique_audio_count'],1)
        summary=aggregate(rows)['asr']
        self.assertEqual(summary['confirmed_runs'],2);self.assertEqual(summary['scored_unique_samples'],1)
        self.assertEqual(summary['before']['reference_characters'],len('人工测试参考'))
    def test_version_check_loaded_hash_and_disk_drift(self):
        status=self.lab.config()['lexicon']
        p=Path(status['path']);self.assertEqual(status['loaded_sha256'],hashlib.sha256(p.read_bytes()).hexdigest())
        self.assertEqual(status['loaded_version'],'electrical-v2.3');self.assertFalse(status['restart_required'])
        with tempfile.TemporaryDirectory() as folder:
            other=Path(folder)/'changed.json';other.write_text('{"lexicon_version":"changed"}')
            self.lab.brain.normalizer.path=other
            changed=self.lab.config()['lexicon']
        self.assertTrue(changed['restart_required']);self.assertEqual(changed['loaded_version'],'electrical-v2.3')
    def test_cannot_link_another_audio_as_parent(self):
        a=self.lab.evaluate(self.base)
        other=self.lab.upload({'wav_base64':base64.b64encode(wav_bytes(frames=100)).decode()})
        with self.assertRaises(ValueError):self.lab.evaluate({**self.base,'audio_id':other['audio_id'],'mode':'score',
            'derived_from_record_id':a['record_id'],'reference_text':'参考','reference_confirmed':True})
