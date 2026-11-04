"""Exercise greenfield intake, real HTTP persistence, packaging and process restart."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BuilderE2E(unittest.TestCase):
    def test_real_http_build_cumulative_regressions_and_resume(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            env = os.environ.copy(); env['HARRTEST_STATE_HOME'] = str(base / 'private-state')
            result = subprocess.run([sys.executable, '-S', '-B', str(ROOT / 'examples/builder_demo.py'),
                                     '--output', str(base / 'new-project')],
                                    capture_output=True, text=True, timeout=90, env=env)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads((base / 'new-project/demo-result.json').read_text(encoding='utf-8'))
            for flag in ('greenfield_intake_preserved', 'three_running_milestones',
                         'persistence_failure_reproduced', 'earlier_regression_gate_enforced',
                         'clean_package_executed', 'resume_selected_next_milestone',
                         'stale_final_source_rejected', 'root_goal_verified'):
                self.assertTrue(report[flag], flag)
            self.assertEqual(report['paid_model_calls'], 0)
            self.assertEqual(report['fresh_checks_reused'], 3)
            self.assertIn('Not autonomous LLM', report['scope'])


if __name__ == '__main__': unittest.main()
