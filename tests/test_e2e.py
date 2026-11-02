import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from InspectionOS.simulation.scenario_runner import run_scenario


class EndToEndTests(unittest.TestCase):
    def test_a_cli_brain_to_evidence_and_sync(self):
        with tempfile.TemporaryDirectory() as d:
            cmd=[sys.executable,'-m','InspectionOS','--db',str(Path(d)/'local.db'),'--idempotency-key','fixed','--provider','mock']
            result=subprocess.run(cmd,capture_output=True,text=True,check=True)
            report=json.loads(result.stdout)
            self.assertEqual(report['mission']['status'],'SUCCEEDED')
            self.assertTrue(report['mission']['result']['is_mock']);self.assertFalse(report['hardware_commands_enabled'])
            self.assertEqual(report['sync']['pending'],0)
            second=json.loads(subprocess.run(cmd,capture_output=True,text=True,check=True).stdout)
            self.assertEqual(second['mission']['mission_id'],report['mission']['mission_id'])
            self.assertEqual(second['mission']['attempts'],1)

    def test_b_weak_network_and_c_inflight_crash(self):
        for name in ('E2','E3','E6'):
            with tempfile.TemporaryDirectory() as d:
                self.assertTrue(run_scenario(name,d)['passed'])
