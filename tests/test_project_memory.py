"""Local persisted context tests: no agents, web or paid models involved."""
from pathlib import Path
from unittest import mock
import hashlib
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from project_memory import Memory


class ProjectMemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.state = self.root / 'private'
        self.env = mock.patch.dict(os.environ, {'HARRTEST_STATE_HOME': str(self.state)})
        self.env.start()
        self.project = self.root / 'target'
        self.project.mkdir()
        (self.project/'ROOT_GOAL.md').write_text('Build a real service and preserve all saved results after restart.\n')
        (self.project/'README.md').write_text('Service reads and writes local state.\n')
        (self.project/'src').mkdir()
        (self.project/'src'/'api.py').write_text('def persist():\n    return True\n')
        (self.project/'.env').write_text('API_SECRET=very-secret\n')
        self.memory = Memory(self.project)
        self.memory.bootstrap('ROOT_GOAL.md')

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_private_folder_outside_project_and_installed_skill(self):
        self.assertFalse(self.memory.directory.is_relative_to(self.project))
        self.assertTrue((self.memory.directory/'project-brief-main.md').is_file())
        self.assertFalse(any(self.project.glob('**/memory.sqlite')))

    def test_exact_goal_survives_new_process_instance(self):
        restarted = Memory(self.project)
        self.assertEqual(self.memory.goal()['sha256'], restarted.goal()['sha256'])
        self.assertIn('after restart', restarted.summary()['goal']['text'])
        self.assertEqual(restarted.bootstrap('ROOT_GOAL.md')['status'], 'UNCHANGED')

    def test_changes_do_not_silently_replace_original_goal(self):
        (self.project/'ROOT_GOAL.md').write_text('Build a different service and delete all old work.')
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.memory.bootstrap('ROOT_GOAL.md')
        new = self.memory.bootstrap('ROOT_GOAL.md', revise=True)
        self.assertEqual(new['revision'], 2)

    def test_source_bound_notes_stale_after_code_change(self):
        self.memory.note('main', 'architecture', 'All public persistence routes live in src/api.py', 'src/api.py', 2)
        self.assertTrue(self.memory.summary()['notes'][0]['current'])
        (self.project/'src/api.py').write_text('def persist():\n    return False\n')
        self.assertFalse(Memory(self.project).summary()['notes'][0]['current'])
        pack = self.memory.pack('main', 'implement public persistence and restart testing')
        self.assertEqual(pack['notes'][0]['source_status'], 'STALE_RECHECK_BEFORE_USE')

    def test_scoped_pack_excludes_unrelated_secret_file(self):
        self.memory.note('main','architecture', 'The API handles writing durable data','src/api.py',2)
        pack=self.memory.pack('main', 'Write a durable persistence API handler',scopes=['src'])
        self.assertIn('after restart', pack['original_goal'])
        self.assertNotIn('very-secret',json.dumps(pack))
        self.assertFalse(any(x['path']=='.env' for x in pack['recommended_files']))
        self.assertFalse(any('def persist' in x.get('text','') for x in pack['notes']))

    def test_checkpoint_evidence_and_historical_status(self):
        (self.project/'results.txt').write_text('Real running result observed; child gate passed.')
        self.memory.checkpoint('main','API validated','VERIFIED_CHILD','Executed real API and examined output', 'results.txt')
        report=self.memory.summary()
        self.assertTrue(report['checkpoints'][0]['evidence_current'])
        self.assertTrue(report['memory_is_not_root_gate'])
        (self.project/'results.txt').write_text('changed')
        self.assertFalse(self.memory.summary()['checkpoints'][0]['evidence_current'])

    def test_disallow_ungrounded_architecture_notes(self):
        with self.assertRaises(ValueError):
            self.memory.note('main','architecture','Claim with no real source','.env')

    def test_context_budget_fails_closed_instead_of_dropping_goal(self):
        (self.project/'ROOT_GOAL.md').write_text('Preserve all behavior ' * 200)
        self.memory.bootstrap('ROOT_GOAL.md', revise=True)
        with self.assertRaisesRegex(ValueError,'Original goal too long'):
            self.memory.pack('main','implement durable behavior', budget=2500)

    def test_reviewer_selection_validated_and_stale_rejected(self):
        saved=self.memory.note('main','architecture','API persistence is implemented here','src/api.py',2)
        goal=self.memory.goal()
        task='Implement durable data persistence and reload'
        selection=self.root/'selection.json'
        selection.write_text(json.dumps({'goal_sha256':goal['sha256'],'task':task,'role':'implement',
                                         'note_ids':[saved['id']]}))
        self.assertEqual(self.memory.pack('main',task, selection=selection)['notes'][0]['id'],saved['id'])
        (self.project/'src/api.py').write_text('a totally different implementation')
        with self.assertRaisesRegex(ValueError,'stale'):
            self.memory.pack('main',task, selection=selection)

    def test_separate_projects_not_confused(self):
        another=self.root/'second'
        another.mkdir()
        (another/'ROOT_GOAL.md').write_text('Deploy a completely different business application.')
        memory=Memory(another)
        memory.bootstrap('ROOT_GOAL.md')
        self.assertNotEqual(memory.directory,self.memory.directory)
        self.assertNotEqual(memory.goal()['sha256'],self.memory.goal()['sha256'])

    def test_can_bootstrap_from_sealed_root_request(self):
        request=self.project/'.runtime-proof/root-goals/mission/original-request.txt'
        request.parent.mkdir(parents=True)
        request.write_text('Build original working feature with protected acceptance gates.')
        r=self.memory.bootstrap('.runtime-proof/root-goals/mission/original-request.txt',goal_id='mission')
        self.assertEqual(r['status'],'GOAL_REGISTERED')
        self.assertIn('original working feature',self.memory.goal('mission')['text'])

    def test_reject_no_evidence_for_verified_checkpoint(self):
        with self.assertRaisesRegex(ValueError, 'require raw'):
            self.memory.checkpoint('main','API verified','VERIFIED_CHILD','actual endpoint worked','')


if __name__ == '__main__':
    unittest.main()
