"""Corporate root inventory and production-install boundaries.

The journey guard validates declared evidence only. Full schema-4 sealing and
semantic-quality enforcement are exercised by test_corporate.py.
"""
import copy
import contextlib
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import goal_guard
import install
import proof
import corporate


class CorporateCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        evidence = self.base / 'observed.json'
        evidence.write_text('{"result":12}', encoding='utf-8')
        self.contract = {
            'schema': 1, 'scope': 'root', 'source_sha256': 'a' * 64,
            'root_request_sha256': 'b' * 64,
            'requirements': [{'id': 'R1', 'target': 'ledger-cli', 'mode': 'live',
                              'journeys': [{'id': 'update', 'steps': ['load', 'compute', 'save']}]}],
        }
        self.events = {'schema': 1, 'events': [
            {'requirement_id': 'R1', 'journey_id': 'update', 'step_id': step,
             'run_id': 'first', 'source_sha256': 'a' * 64, 'target': 'ledger-cli',
             'mode': 'live', 'status': 'PASS', 'passed': True, 'observer': 'external-test',
             'evidence_file': 'observed.json',
             'evidence_sha256': hashlib.sha256(evidence.read_bytes()).hexdigest()}
            for step in ['load', 'compute', 'save']
        ]}

    def root(self, schema=4):
        return {'schema': schema, 'protocol': 'corporate-v1' if schema == 4 else 'golden-v1',
                'request_sha256': 'b' * 64, 'requirements': [{'id': 'R1'}]}

    def assess(self, root=None):
        return goal_guard.assess(self.contract, self.events, self.base,
                                 self.root() if root is None else root)

    def test_all_supported_root_inventory_schemas_accept_complete_evidence(self):
        for schema in (2, 3, 4):
            with self.subTest(schema=schema):
                self.assertTrue(self.assess(self.root(schema))['passed'])

    def test_future_root_schema_stays_unverified(self):
        self.assertFalse(self.assess(self.root(5))['passed'])

    def test_schema4_still_requires_the_entire_original_inventory(self):
        root = self.root()
        root['requirements'].append({'id': 'R2'})
        result = self.assess(root)
        self.assertFalse(result['passed'])
        self.assertIn('every original root requirement', result['errors'][0])

    def test_schema4_request_identity_is_not_relaxed(self):
        root = self.root()
        root['request_sha256'] = 'c' * 64
        self.assertFalse(self.assess(root)['passed'])

    def test_schema4_missing_latest_step_remains_unverified(self):
        self.events['events'].append({**self.events['events'][0], 'run_id': 'later'})
        self.assertFalse(self.assess()['passed'])

    def test_schema4_stale_source_and_modified_evidence_are_rejected(self):
        for mutation in ('source', 'bytes'):
            with self.subTest(mutation=mutation):
                events = copy.deepcopy(self.events)
                if mutation == 'source':
                    events['events'][1]['source_sha256'] = 'c' * 64
                else:
                    events['events'][1]['evidence_sha256'] = 'c' * 64
                self.assertFalse(goal_guard.assess(self.contract, events, self.base,
                                                  self.root())['passed'])

    def test_guard_cli_accepts_schema4_then_rejects_incomplete_evidence(self):
        for name, value in [('contract.json', self.contract), ('events.json', self.events),
                            ('root.json', self.root())]:
            (self.base / name).write_text(json.dumps(value), encoding='utf-8')
        argv = [sys.executable, '-B', str(ROOT / 'scripts/goal_guard.py'),
                '--contract', str(self.base / 'contract.json'),
                '--events', str(self.base / 'events.json'),
                '--root-contract', str(self.base / 'root.json')]
        complete = subprocess.run(argv, capture_output=True, text=True)
        self.assertEqual(complete.returncode, 0, complete.stderr + complete.stdout)
        self.assertTrue(json.loads(complete.stdout)['passed'])
        self.events['events'].pop()
        (self.base / 'events.json').write_text(json.dumps(self.events), encoding='utf-8')
        incomplete = subprocess.run(argv, capture_output=True, text=True)
        self.assertEqual(incomplete.returncode, 1, incomplete.stderr + incomplete.stdout)
        self.assertFalse(json.loads(incomplete.stdout)['passed'])

    def skill_source(self):
        source = self.base / 'source'
        contents = {
            'SKILL.md': 'production skill',
            'VERSION': '5.0.0\n',
            'scripts/corporate.py': 'production Corporate verifier',
            'scripts/corporate_benchmark.py': 'INDEPENDENT_ACCEPTANCE_ORACLE',
            'tests/test_corporate_benchmark.py': 'INDEPENDENT_ACCEPTANCE_ORACLE',
            'assets/corporate/cases.json': 'INDEPENDENT_ACCEPTANCE_ORACLE',
            'assets/templates/root-contract-v4.json': '{"schema":4}',
            'references/corporate-workflow.md': 'production workflow',
            'assets/corporate.json': 'unrelated valid asset',
            'notes/corporate/notes.txt': 'unrelated valid reference',
            'examples/scripts/corporate_benchmark.py': 'unrelated example',
            'output/private.json': 'private output',
        }
        for rel, content in contents.items():
            path = source / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding='utf-8')
        return source

    def test_production_install_excludes_only_scoped_benchmark_inputs(self):
        source = self.skill_source()
        project = self.base / 'project'
        project.mkdir()
        with patch.object(install, 'SOURCE', source):
            result = install.install('copilot', 'project', project, self.base / 'home')
        target = Path(result['installed'])
        for rel in ['scripts/corporate.py', 'assets/templates/root-contract-v4.json',
                    'references/corporate-workflow.md', 'assets/corporate.json',
                    'notes/corporate/notes.txt', 'examples/scripts/corporate_benchmark.py']:
            self.assertEqual((target / rel).read_bytes(), (source / rel).read_bytes())
        self.assertFalse((target / 'scripts/corporate_benchmark.py').exists())
        self.assertFalse((target / 'tests/test_corporate_benchmark.py').exists())
        self.assertFalse((target / 'assets/corporate').exists())
        self.assertFalse((target / 'output').exists())
        self.assertFalse(any(b'INDEPENDENT_ACCEPTANCE_ORACLE' in p.read_bytes()
                             for p in target.rglob('*') if p.is_file()))

    def test_instruction_update_preserves_project_rules_and_existing_hooks(self):
        source = self.skill_source()
        project = self.base / 'project'
        project.mkdir()
        instructions = project / '.github/copilot-instructions.md'
        instructions.parent.mkdir()
        before = ('Keep our namespace and public API.\n\n' + install.START +
                  '\nOld generated guidance.\n' + install.END + '\n\nKeep our test command.\n')
        instructions.write_text(before, encoding='utf-8')
        hooks = project / '.github/hooks/organization.json'
        hooks.parent.mkdir()
        hooks.write_text('{"organization_policy":"preserve"}', encoding='utf-8')
        with patch.object(install, 'SOURCE', source):
            first = install.install('copilot', 'project', project, self.base / 'home',
                                    instructions=True)
            target = Path(first['installed'])
            # Verify the exact recursive replacement boundary before update.
            self.assertEqual(target.resolve().parent, (project / '.github/skills').resolve())
            self.assertEqual(target.resolve().name, 'harrtest')
            second = install.install('copilot', 'project', project, self.base / 'home',
                                     instructions=True, update=True)
        merged = instructions.read_text(encoding='utf-8')
        self.assertEqual(merged.count(install.START), 1)
        self.assertEqual(merged.count(install.END), 1)
        self.assertIn('Keep our namespace and public API.', merged)
        self.assertIn('Keep our test command.', merged)
        self.assertIn(install.instruction_block(target), merged)
        self.assertEqual(hooks.read_text(), '{"organization_policy":"preserve"}')
        self.assertFalse(second['hook_installed'])
        self.assertEqual((project / '.gitignore').read_text().count('/.runtime-proof/'), 1)
        instruction_backups = [p for p in first['backups'] if 'copilot-instructions' in p]
        self.assertEqual(len(instruction_backups), 1)
        self.assertEqual(Path(instruction_backups[0]).read_text(), before)

    def test_actual_ci_archive_uses_the_installer_production_boundary(self):
        # Exercise the actual archive step in a temporary checkout with evaluator
        # inputs present; do not prefilter them through the production installer.
        staging = self.base / 'archive-source'
        shutil.copytree(ROOT, staging, ignore=install.PACKAGE_IGNORES)
        workflow = (ROOT / '.github/workflows/verify.yml').read_text(encoding='utf-8')
        body = workflow.split("          python - <<'PY'\n", 1)[1].split('\n          PY', 1)[0]
        result = subprocess.run([sys.executable, '-B', '-c', textwrap.dedent(body)],
                                cwd=staging, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        with ZipFile(staging / 'skill.zip') as archive:
            names = set(archive.namelist())
            self.assertIn('harrtest/scripts/corporate.py', names)
            self.assertIn('harrtest/scripts/team_v2.py', names)
            self.assertIn('harrtest/assets/templates/root-contract-v4.json', names)
            self.assertIn('harrtest/references/corporate-workflow.md', names)
            self.assertNotIn('harrtest/scripts/corporate_benchmark.py', names)
            self.assertNotIn('harrtest/tests/test_corporate_benchmark.py', names)
            self.assertFalse(any(name.startswith('harrtest/assets/corporate/') for name in names))


class AbsentSourceCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name).resolve()
        (self.project / 'src').mkdir()
        (self.project / 'checks').mkdir()
        (self.project / 'src/old.py').write_text('value = 12\n', encoding='utf-8')
        self.checker = self.project / 'checks/check.py'
        self.checker.write_text(
            "import json,runpy\nfrom pathlib import Path\n"
            "target=Path('src/old.py')\n"
            "if not target.exists(): target=Path('src/new.py')\n"
            "value=runpy.run_path(str(target))['value']\n"
            "print(json.dumps({'sum':value}))\n", encoding='utf-8')
        self.contract = proof.load(ROOT / 'examples/cli-contract.json')
        self.contract['source_paths'] = ['src/old.py', 'src/new.py', 'checks']
        self.contract['absent_source_paths'] = ['src/old.py', 'src/new.py']
        self.contract['checks'][0]['command'] = ['{python}', '-B', 'checks/check.py']
        self.task = self.project / '.runtime-proof/cli-demo'
        self.task.mkdir(parents=True)

    def seal(self):
        proof.validate_contract(self.contract)
        proof.save(self.task / 'context.json', {'project': str(self.project)})
        proof.save(self.task / 'contract.json', self.contract)
        proof.save(self.task / 'seal.json', {'contract_hash': proof.digest(self.contract),
                                            'engine_hash': proof.engine_hash(self.contract)})

    def run_check(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return proof.run_check(self.task, 'addition')

    def verify_completed(self):
        proof.update_step(self.task, 'T01', 'VERIFIED',
                          'Observed actual arithmetic from the current source manifest after the file operation.')
        self.assertTrue(proof.verify(self.task)['passed'])

    def verify_corporate_execution(self, receipt, *, latest=False):
        location = (self.task / 'runs' / receipt['check_id'] /
                    receipt['run_id'] / 'receipt.json')
        ref = corporate.execution_reference(self.project, location.relative_to(self.project).as_posix())
        observed = corporate.execution(self.project, ref, receipt['source_before'], latest=latest)
        self.assertTrue(observed['passed'])
        self.assertEqual(observed['receipt']['source_after'], receipt['source_before'])
        return ref

    def test_file_level_rename_has_real_baseline_candidate_and_matching_corporate_identity(self):
        self.seal()
        baseline = self.run_check()
        self.assertTrue(baseline['passed'])
        self.assertIsNone(baseline['source_before']['files']['src/new.py'])
        self.assertEqual(baseline['source_before'], corporate.source_snapshot(
            self.project, self.contract['source_paths']))
        baseline_ref = self.verify_corporate_execution(baseline, latest=True)
        old = (self.project / 'src/old.py').resolve(strict=True)
        new = (self.project / 'src/new.py').resolve()
        self.assertEqual(old.parent, (self.project / 'src').resolve())
        self.assertEqual(new.parent, old.parent)
        old.rename(new)
        self.assertFalse(proof.verify(self.task)['passed'])
        candidate = self.run_check()
        self.assertTrue(candidate['passed'])
        self.assertIsNone(candidate['source_after']['files']['src/old.py'])
        self.assertEqual(candidate['source_after'], corporate.source_snapshot(
            self.project, self.contract['source_paths']))
        self.verify_corporate_execution(candidate, latest=True)
        # Corporate retains the immutable baseline run even after a later check
        # supersedes it; candidate/latest evidence cannot reuse that old run.
        self.assertTrue(corporate.execution(self.project, baseline_ref,
                                           baseline['source_before'])['passed'])
        with self.assertRaisesRegex(ValueError, 'newer check attempt'):
            corporate.execution(self.project, baseline_ref, baseline['source_before'], latest=True)
        self.assertNotEqual(baseline['source_before']['digest'], candidate['source_after']['digest'])
        self.verify_completed()

    def test_explicit_deletion_keeps_absence_and_real_candidate_evidence(self):
        retired = self.project / 'src/retired.py'
        retired.write_text('deprecated = True\n', encoding='utf-8')
        self.contract['source_paths'] = ['src/old.py', 'src/retired.py', 'checks']
        self.contract['absent_source_paths'] = ['src/retired.py']
        self.seal()
        baseline = self.run_check()
        self.assertTrue(baseline['passed'])
        self.verify_corporate_execution(baseline, latest=True)
        retired.unlink()
        candidate = self.run_check()
        self.assertTrue(candidate['passed'])
        self.assertIsNone(candidate['source_before']['files']['src/retired.py'])
        self.assertEqual(candidate['source_before'], corporate.source_snapshot(
            self.project, self.contract['source_paths']))
        self.verify_corporate_execution(candidate, latest=True)
        self.verify_completed()

    def test_missing_root_without_explicit_opt_in_keeps_legacy_failure(self):
        self.contract.pop('absent_source_paths')
        proof.validate_contract(self.contract)
        with self.assertRaisesRegex(proof.ProofError, 'Missing path'):
            proof.snapshot(self.project, self.contract)

    def test_missing_unlisted_root_is_not_implicitly_optional(self):
        self.contract['absent_source_paths'] = ['src/old.py']
        with self.assertRaisesRegex(proof.ProofError, 'Missing path'):
            proof.snapshot(self.project, self.contract)

    def test_absent_scopes_must_be_unique_explicit_source_subsets(self):
        for bad in [None, 'src/new.py', [None], ['src/new.py', 'src/new.py'],
                    ['src/unlisted.py'], ['../outside'], ['/absolute'], ['C:/outside'],
                    ['src\\new.py'], ['src//new.py'], ['src/new.py/'], ['.'],
                    ['.runtime-proof/private.json'], ['.git/config'], ['src/new\x00.py']]:
            with self.subTest(absent_source_paths=bad):
                contract = copy.deepcopy(self.contract)
                contract['absent_source_paths'] = bad
                with self.assertRaises(proof.ProofError):
                    proof.validate_contract(contract)

    def test_absence_is_not_a_source_free_acceptance_scope(self):
        contract = {**self.contract, 'source_paths': ['src/new.py'],
                    'absent_source_paths': ['src/new.py']}
        with self.assertRaisesRegex(proof.ProofError, 'no files'):
            proof.snapshot(self.project, contract)

    def test_creating_an_optional_root_during_execution_still_fails(self):
        self.checker.write_text(self.checker.read_text() +
                               "Path('src/new.py').write_text('value = 99\\n')\n", encoding='utf-8')
        self.seal()
        result = self.run_check()
        self.assertFalse(result['passed'])
        self.assertIsNone(result['source_before']['files']['src/new.py'])
        self.assertIsNotNone(result['source_after']['files']['src/new.py'])
        self.assertIn('Source changed during this execution', result['errors'])

    def test_deleting_an_optional_root_during_execution_still_fails(self):
        self.checker.write_text(self.checker.read_text() +
                               "Path('src/old.py').unlink()\n", encoding='utf-8')
        self.seal()
        result = self.run_check()
        self.assertFalse(result['passed'])
        self.assertIsNotNone(result['source_before']['files']['src/old.py'])
        self.assertIsNone(result['source_after']['files']['src/old.py'])
        self.assertIn('Source changed during this execution', result['errors'])


if __name__ == '__main__':
    unittest.main()
