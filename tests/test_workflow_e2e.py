"""Actual local command-line coordinator scenario; not a live-agent benchmark."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]


class WorkflowE2E(unittest.TestCase):
    def test_real_persistence_repair_resume_and_root_gate(self):
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)/'project'
            result=subprocess.run([sys.executable,'-S','-B',str(ROOT/'examples/workflow_demo.py'),'--output',str(out)],capture_output=True,text=True,timeout=90)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            report=json.loads((out/'demo-result.json').read_text())
            for flag in ('initial_bug_reproduced','repair_verified','child_only_completion_blocked',
                         'sqlite_reopened_between_commands','final_root_verified','post_run_source_drift_rejected'):
                self.assertTrue(report[flag],flag)
            self.assertIn('No LLM',report['scope'])


if __name__=='__main__':unittest.main()
