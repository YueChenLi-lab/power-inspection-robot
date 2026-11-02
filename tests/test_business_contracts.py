from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from InspectionOS.app import Application
from InspectionOS.skills.contracts import validate
from InspectionOS.skills.mock.alarm_query import AlarmQuerySkill
from InspectionOS.skills.mock.temperature_query import TemperatureQuerySkill
from InspectionOS.skills.mock.reinspection import ReinspectionSkill
from InspectionOS.skills.mock.validation import BusinessValidationError

REQUEST={'device_id':'MOCK-CB-3','start':'2026-10-26T00:00:00+08:00','end':'2026-11-02T00:00:00+08:00'}


class BusinessContractTests(unittest.TestCase):
    def test_schema_valid_but_cross_fields_wrong(self):
        mutations=[lambda r:r.update(device_id='MOCK-TR-1'),
                   lambda r:r['records'][0].update(device_id='MOCK-TR-1'),
                   lambda r:r['records'][0].update(timestamp='2026-11-03T00:00:00+08:00'),
                   lambda r:r['records'][0].update(source='real'),
                   lambda r:r['records'][0].pop('timestamp')]
        with tempfile.TemporaryDirectory() as d,Application(Path(d)/'db') as app:
            for mutate in mutations:
                result=AlarmQuerySkill().execute(REQUEST);mutate(result)
                validate(result,AlarmQuerySkill.spec.output_schema) # Schema really passes.
                with self.assertRaises(BusinessValidationError):app.registry.validate_output('mock.alarm_query',REQUEST,result)

    def test_normal_single_and_multi_device_for_all_skills(self):
        with tempfile.TemporaryDirectory() as d,Application(Path(d)/'db') as app:
            for cls in (AlarmQuerySkill,TemperatureQuerySkill,ReinspectionSkill):
                for payload in (REQUEST,{'device_ids':['MOCK-CB-3','MOCK-TR-1'],'compare':True}):
                    app.registry.validate_input(cls.spec.skill_id,payload)
                    result=cls().execute(payload)
                    app.registry.validate_output(cls.spec.skill_id,payload,result)
                    expected=set(payload.get('device_ids',[payload.get('device_id')]))
                    self.assertEqual({r['device_id'] for r in result['records']},expected)

    def test_missing_mock_label_unknown_extra_device_and_invalid_input(self):
        with tempfile.TemporaryDirectory() as d,Application(Path(d)/'db') as app:
            for key in ('source','is_mock'):
                result=AlarmQuerySkill().execute(REQUEST);result.pop(key)
                with self.assertRaises(ValueError):app.registry.validate_output('mock.alarm_query',REQUEST,result)
            result=AlarmQuerySkill().execute(REQUEST)
            result['device_id']='UNREQUESTED'
            with self.assertRaises(BusinessValidationError):app.registry.validate_output('mock.alarm_query',REQUEST,result)
            for p in ({},{'device_ids':[]},{'device_id':'MOCK-CB-3','device_ids':['MOCK-TR-1']},
                      {**REQUEST,'start':'bad'},{**REQUEST,'end':'2026-10-26T00:00:00+08:00'}):
                with self.assertRaises(ValueError):app.registry.validate_input('mock.alarm_query',p)

    def test_business_invalid_output_never_succeeds(self):
        class Wrong(AlarmQuerySkill):
            def execute(self,payload):
                result=super().execute(payload);result['device_id']='MOCK-TR-1';return result
        with tempfile.TemporaryDirectory() as d,Application(Path(d)/'db') as app:
            from dataclasses import replace
            wrong=Wrong();wrong.spec=replace(wrong.spec,skill_id='mock.wrong');app.registry.register(wrong)
            app.manager.create('mock.wrong',REQUEST,idempotency_key='bad',max_attempts=1)
            result=app.worker.run_once()
            self.assertEqual(result['status'],'FAILED');self.assertIn('BusinessValidationError',result['error'])
