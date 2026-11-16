"""Executable evaluator controls; these are not live-model quality results."""
import copy
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import corporate_benchmark as bench


class CorporateBenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.old = self.root / "old"
        self.new = self.root / "new"
        for directory, version in [(self.old, "4.1.0"), (self.new, "5.0.0")]:
            directory.mkdir()
            (directory / "VERSION").write_text(version)
            (directory / "SKILL.md").write_text("---\nname: harrtest\ndescription: Test fixture package\n---\n")
            (directory / "scripts").mkdir()
            (directory / "scripts/tool.py").write_text("print('tool')\n")
            (directory / "scripts/corporate_benchmark.py").write_text("DO NOT EXPOSE ORACLES\n")
            (directory / "assets/corporate").mkdir(parents=True)
            (directory / "assets/corporate/cases.json").write_text("DO NOT EXPOSE CASES\n")
            (directory / "references").mkdir()
            for guide in ['cli-agent-validation.md','web-validation.md','simulation-validation.md']:
                (directory/'references'/guide).write_text('Production workflow guide\n')
        self.experiment = self.root / "experiment"
        self.fake_probe = {"tools": {"python":sys.executable,"node":shutil.which("node"),"copilot":"fixture-only"},
                           "blocked":[], "assurance":"unit-test substitution, not a capability observation"}
        tools_path=Path(os.environ.get('HARRTEST_BENCH_TOOLS') or ROOT/'output/v5-corporate/evaluation-tools.json')
        if tools_path.is_file():
            tools=bench.load(tools_path)
            for key in ['tsc','node_types']:
                if tools.get(key):self.fake_probe['tools'][key]=tools[key]

    def freeze(self,kind='development'):
        with patch.object(bench, "preflight", return_value=self.fake_probe):
            return bench.freeze(self.experiment,self.old,self.new,["weak-observed","normal-observed"],kind=kind)

    def attempt(self, case):
        self.freeze()
        return bench.prepare(self.experiment,case,"plain","weak-observed",1)

    def test_corporate_editor_guard_profile_is_frozen_only_for_v5_development(self):
        shutil.copy2(ROOT / 'scripts/copilot_guard.py', self.new / 'scripts/copilot_guard.py')
        with patch.object(bench, 'preflight', return_value=self.fake_probe):
            with self.assertRaisesRegex(ValueError, 'guarded development trial'):
                bench.freeze(self.experiment, self.old, self.new, ['weak-observed', 'normal-observed'],
                             kind='acceptance', corporate_guard_goal='mission')
            plan = bench.freeze(self.experiment, self.old, self.new, ['weak-observed', 'normal-observed'],
                                corporate_guard_goal='mission')
        self.assertEqual(plan['corporate_guard_goal'], 'mission')
        self.assertTrue((self.experiment / 'packages/v5/scripts/copilot_guard.py').is_file())
        with self.assertRaisesRegex(ValueError, 'requires the V5 package'):
            bench.prepare(self.experiment, 'py-batch-atomicity', 'plain', 'weak-observed', 1)
        slot = bench.prepare(self.experiment, 'py-batch-atomicity', 'v5', 'weak-observed', 1)
        meta = bench.load(slot / 'attempt.json')
        self.assertTrue(meta['prompt'].startswith('$harrtest\n' + meta['case']['request']))

    def test_corpus_has_distinct_development_and_held_cases(self):
        rows=bench.cases()
        self.assertEqual(len(rows),16)
        self.assertEqual(len({row['id'] for row in rows}),16)
        for split in ['development','acceptance']:
            self.assertEqual(sum(x['split']==split for x in rows),8)
        splits = {row['id']: row['split'] for row in rows}
        self.assertEqual(splits['py-batch-atomicity'], 'development')
        self.assertEqual(splits['py-monthly-report-utc'], 'acceptance')
        self.assertNotIn('py-event-idempotency', splits)
        self.assertEqual(splits['cs-credit-validation'], 'development')
        self.assertEqual(splits['cs-build-dependency-plan'], 'acceptance')
        self.assertNotIn('cs-refund-boundary', splits)
        self.assertEqual(splits['cs-atomic-transfer'], 'development')
        self.assertEqual(splits['ts-explicit-config'], 'development')
        self.assertEqual(splits['cs-stock-snapshot'], 'acceptance')
        self.assertEqual(splits['ts-triage-queue'], 'acceptance')
        self.assertNotIn('cs-tenant-lookup', splits)
        self.assertNotIn('ts-explicit-limit', splits)

    def test_pin_does_not_expose_evaluator_or_corpus(self):
        self.freeze()
        pinned=self.experiment/'packages/v5'
        self.assertTrue((pinned/'scripts/tool.py').is_file())
        self.assertFalse((pinned/'scripts/corporate_benchmark.py').exists())
        self.assertFalse((pinned/'assets/corporate').exists())
        for guide in ['cli-agent-validation.md','web-validation.md','simulation-validation.md']:
            self.assertTrue((pinned/'references'/guide).is_file())

    def test_declared_toolchain_content_change_invalidates_experiment(self):
        compiler=self.root/'compiler-marker';compiler.write_text('compiler version1')
        dependency=self.root/'compiler-config';dependency.write_text('runtime config1')
        self.fake_probe['tools'].update(cxx=[str(compiler)],identity_files=[str(dependency)])
        self.freeze();compiler.write_text('compiler version2')
        with self.assertRaisesRegex(ValueError,'toolchain/transport dependency changed'):
            bench.frozen(self.experiment)
        compiler.write_text('compiler version1');dependency.write_text('runtime config2')
        with self.assertRaisesRegex(ValueError,'toolchain/transport dependency changed'):
            bench.frozen(self.experiment)

    def test_protocol_change_invalidates_attempt_before_generation(self):
        self.freeze()
        p=self.experiment/'protocol.json';data=bench.load(p);data['models'][0]='other'
        bench.save(p,data)
        with self.assertRaisesRegex(ValueError,'Protocol was changed'):
            bench.prepare(self.experiment,'py-retry-recovery','plain','other',1)

    def test_package_change_invalidates_attempt(self):
        self.freeze()
        (self.experiment/'packages/v5/scripts/tool.py').write_text('changed')
        with self.assertRaisesRegex(ValueError,'package changed'):
            bench.frozen(self.experiment)

    def test_concrete_distinct_models_and_realistic_cap_required(self):
        for models in [('auto','normal'),('same','same')]:
            with self.assertRaises(ValueError):
                bench.freeze(self.experiment,self.old,self.new,list(models))
        with self.assertRaises(ValueError):
            bench.freeze(self.experiment,self.old,self.new,['a','b'],credits=1)

    def test_missing_attempts_stay_in_denominator(self):
        self.freeze();result=bench.summarize(self.experiment)
        self.assertEqual(len(result['attempts']),96)
        for arm in bench.ARMS:
            self.assertEqual(result['counts'][arm]['missing'],32)
            self.assertEqual(result['counts'][arm]['denominator'],32)
        self.assertFalse(result['release_qualified'])

    def test_attempt_cannot_be_silently_overwritten(self):
        p=self.attempt('py-retry-recovery')
        with self.assertRaises(FileExistsError):
            bench.prepare(self.experiment,'py-retry-recovery','plain','weak-observed',1)
        self.assertEqual(bench.load(p/'attempt.json')['arm'],'plain')

    def test_plain_settings_are_local_and_do_not_turn_off_hooks(self):
        p=self.attempt('py-retry-recovery')
        settings=bench.load(p/'work/.github/copilot/settings.local.json')
        self.assertEqual(settings['disabledSkills'],['harrtest'])
        self.assertNotIn('disableAllHooks',settings)

    def test_generation_needs_explicit_authorization(self):
        p=self.attempt('py-retry-recovery')
        with self.assertRaisesRegex(ValueError,'explicit'):
            bench.run_attempt(p)

    def test_observed_inventory_not_config_is_required(self):
        work=self.root/'work'
        self.assertFalse(bench.skill_isolation([{'name':'harrtest','enabled':True}],work,'plain'))
        self.assertTrue(bench.skill_isolation([{'name':'harrtest','enabled':False}],work,'plain'))
        self.assertFalse(bench.skill_isolation([{'name':'harrtest','enabled':True,'path':str(self.old)}],work,'v5'))
        expected={'name':'harrtest','enabled':True,'path':str(work/'.github/skills/harrtest/SKILL.md')}
        self.assertTrue(bench.skill_isolation({'skills':[expected]},work,'v5'))

    def test_real_python_baseline_fails_duplicate_across_processes(self):
        p=self.attempt('py-retry-recovery')
        result=bench.evaluate_attempt(p)
        checks = {check['check']: check for check in result['checks']}
        self.assertTrue(checks['ordinary-persistence']['passed'])
        self.assertTrue(checks['partial-interruption']['passed'])
        self.assertFalse(checks['retry-after-committed-prefix']['passed'])
        self.assertEqual(checks['retry-after-committed-prefix']['observed']['balance'], 15)
        self.assertTrue(result['unchanged_by_evaluator'])
        self.assertFalse(result['complete_quality_passed'])

    def test_independent_oracle_accepts_known_positive_control(self):
        # Disposable evaluator unit control only; never enters a live arm or claim.
        p=self.attempt('py-retry-recovery');core=p/'work/rules.py'
        text=core.read_text();text=text.replace("    for event in x['events']:\n", "    for event in x['events']:\n        if event['id'] in state['seen']:\n            continue\n")
        core.write_text(text)
        result=bench.evaluate_attempt(p)
        self.assertTrue(result['functional_passed'])
        self.assertTrue(result['documented_contract_and_adapter_preserved'])
        self.assertFalse(result['complete_quality_passed'])

    def test_contract_edit_is_detected_despite_correct_function(self):
        p=self.attempt('py-retry-recovery');(p/'work/ARCHITECTURE.md').write_text('relaxed contract')
        result=bench.evaluate_attempt(p)
        self.assertFalse(result['documented_contract_and_adapter_preserved'])

    def test_extended_existing_tests_do_not_fail_architecture_on_byte_changes(self):
        p=self.attempt('py-retry-recovery');test=p/'work/check_existing.py'
        test.write_text(test.read_text()+'\nassert len([1,2,3]) == 3\n')
        result=bench.evaluate_attempt(p)
        self.assertTrue(result['existing_tests_changed'])
        self.assertTrue(result['documented_contract_and_adapter_preserved'])
        self.assertIn('Independent',result['test_oracle_preservation'])

    def test_deleted_or_trivially_weakened_test_does_not_pass_architecture(self):
        p=self.attempt('py-retry-recovery');test=p/'work/check_existing.py'
        test.write_text('assert True\n')
        self.assertFalse(bench.evaluate_attempt(p)['documented_contract_and_adapter_preserved'])
        test.unlink()
        self.assertFalse(bench.evaluate_attempt(p)['documented_contract_and_adapter_preserved'])

    def test_actual_shell_policy_edit_is_invalid_even_with_exit_zero(self):
        p=self.attempt('py-retry-recovery');work=p/'work'
        with patch.object(bench.Path,'home',return_value=self.root/'no-user-configuration'):
            before=bench.configuration_inputs(work)
            target=work/'.github/copilot/settings.local.json'
            run=bench.command([sys.executable,'-c','import pathlib,sys;pathlib.Path(sys.argv[1]).write_text("{}")',str(target)],work)
            self.assertEqual(run['exit_code'],0)
            outcome=bench.validate_generation_inputs(before,bench.configuration_inputs(work),{'status':'COMPLETED'})
        self.assertEqual(outcome['status'],'INVALID')
        self.assertIn(str(target),outcome['configuration_drift'])

    def test_python_import_cache_keeps_skill_identity_and_configuration_stable(self):
        self.freeze()
        attempt = bench.prepare(self.experiment, 'py-retry-recovery', 'v5', 'weak-observed', 1)
        work = attempt / 'work'
        package = work / '.github/skills/harrtest'
        scripts = package / 'scripts'
        environment = dict(os.environ)
        environment.pop('PYTHONDONTWRITEBYTECODE', None)
        environment.pop('PYTHONPYCACHEPREFIX', None)
        with patch.object(bench.Path, 'home', return_value=self.root / 'no-user-configuration'):
            before = bench.configuration_inputs(work)
            package_before = bench.tree(package, skill=True)
            run = bench.command([sys.executable, '-c', 'import tool'], scripts, env=environment)
            self.assertEqual(run['exit_code'], 0, run['stderr'])
            self.assertEqual(len(list((scripts / '__pycache__').glob('tool.*.pyc'))), 1)
            self.assertEqual(bench.tree(package, skill=True), package_before)
            result = bench.validate_generation_inputs(before, bench.configuration_inputs(work), {'status': 'COMPLETED'})
            self.assertEqual(result['status'], 'COMPLETED')

            for target in [scripts / 'tool.py', scripts / 'tool.cpython-313.pyc',
                           scripts / '__pycache__/unrelated.py',
                           scripts / '__pycache__/nosource.cpython-313.pyc',
                           package / '.other/tool.cpython-313.pyc']:
                with self.subTest(path=target.relative_to(package)):
                    original = target.read_bytes() if target.exists() else None
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(b'mutated')
                    result = bench.validate_generation_inputs(before, bench.configuration_inputs(work), {'status': 'COMPLETED'})
                    self.assertEqual(result['status'], 'INVALID')
                    self.assertIn(str(target), result['configuration_drift'])
                    self.assertNotEqual(bench.tree(package, skill=True), package_before)
                    if original is None:
                        target.unlink()
                    else:
                        target.write_bytes(original)

    def test_existing_check_can_use_private_workspace_scratch_in_every_arm(self):
        self.freeze()
        outside = {key: os.environ.get(key) for key in ('TEMP', 'TMP', 'TMPDIR')}
        for arm in bench.ARMS:
            with self.subTest(arm=arm):
                attempt = bench.prepare(self.experiment, 'py-retry-recovery', arm, 'weak-observed', 1)
                workspace = attempt / 'work'
                before = bench.tree(workspace)
                environment = bench.generation_environment(workspace, {})
                scratch = workspace / '.runtime-proof' / 'scratch'
                probe = ('from pathlib import Path; import tempfile; '
                         'tmp = tempfile.TemporaryDirectory(); print(Path(tmp.name).parent)')
                result = bench.command([sys.executable, '-c', probe], workspace, env=environment)
                self.assertEqual(result['exit_code'], 0, result['stderr'])
                self.assertEqual(Path(result['stdout'].strip()).resolve(), scratch.resolve())
                check = bench.command([sys.executable, 'check_existing.py'], workspace, env=environment)
                self.assertEqual(check['exit_code'], 0, check['stderr'])
                self.assertEqual(bench.tree(workspace), before)
                self.assertEqual({key: os.environ.get(key) for key in outside}, outside)

    def test_python_invalid_batch_really_preserves_disk_state_only_after_fix(self):
        p=self.attempt('py-batch-atomicity')
        result=bench.evaluate_attempt(p)
        by_id={x['check']:x for x in result['checks']}
        self.assertTrue(by_id['invalid-batch']['passed'])
        self.assertFalse(by_id['state-unchanged']['passed'])
        self.assertEqual(by_id['state-unchanged']['observed']['balance'],8)

    def test_batch_optional_control_validates_type_before_writing(self):
        attempt = self.attempt('py-batch-atomicity')
        core = attempt / 'work/rules.py'
        amount_only = core.read_text(encoding='utf-8').replace(
            "    for event in x['events']:\n",
            "    for event in x['events']:\n        if event['amount'] < 0:\n            raise ValueError('negative amount')\n"
            "    for event in x['events']:\n", 1)
        core.write_text(amount_only, encoding='utf-8')
        result = bench.evaluate_attempt(attempt)
        checks = {row['check']: row for row in result['checks']}
        self.assertTrue(checks['state-unchanged']['passed'])
        self.assertTrue(checks['control-field-false-is-valid']['passed'])
        checkpoint = checks['control-field-true-commits-then-interrupts']
        self.assertTrue(checkpoint['passed'])
        self.assertEqual(checkpoint['observed'], 'RUNTIME_ERROR')
        self.assertEqual(checkpoint['persisted_observed'], {'balance': 12, 'seen': ['old', 'prefix', 'flagged']})
        self.assertEqual(checkpoint['persisted_sha256'],
                         bench.sha(Path(result['evidence_directory']) / 'control-field-true.json'))
        for label in ('string', 'integer', 'null'):
            check = checks[f'control-field-{label}']
            self.assertFalse(check['passed'])
            self.assertNotEqual(check['input_file_sha256_before'], check['input_file_sha256_after'])
        complete = amount_only.replace("        if event['amount'] < 0:\n",
            "        if 'fail_after' in event and not isinstance(event['fail_after'], bool):\n"
            "            raise ValueError('fail_after must be a bool')\n"
            "        if event['amount'] < 0:\n", 1)
        core.write_text(complete, encoding='utf-8')
        self.assertTrue(bench.evaluate_attempt(attempt)['automated_artifact_passed'])
        core.write_text(complete.replace("RuntimeError('injected interruption')", "ValueError('injected interruption')"),
                        encoding='utf-8')
        wrong_error = next(row for row in bench.evaluate_attempt(attempt)['checks']
                           if row['check'] == 'control-field-true-commits-then-interrupts')
        self.assertEqual(wrong_error['persisted_observed'], wrong_error['persisted_expected'])
        self.assertEqual(wrong_error['observed'], 'VALUE_ERROR')
        self.assertFalse(wrong_error['passed'])

    def test_monthly_report_baseline_preserves_existing_checks_but_fails_utc_boundaries(self):
        attempt = self.attempt('py-monthly-report-utc')
        result = bench.evaluate_attempt(attempt)
        checks = {row['check']: row for row in result['checks']}
        self.assertTrue(all(row['passed'] for name, row in checks.items() if name.startswith('preservation')))
        self.assertFalse(checks['utc-march-in-ledger-order']['passed'])
        self.assertEqual(checks['utc-march-in-ledger-order']['observed'], {'ids': ['first', 'west'], 'total_cents': 1299})
        self.assertFalse(checks['timestamp-naive']['passed'])
        self.assertFalse(checks['month-year-zero']['passed'])
        self.assertFalse(checks['timestamp-year-zero']['passed'])
        self.assertEqual(result['automated_artifact_layers']['security']['status'], 'FAIL')
        self.assertFalse(result['automated_artifact_passed'])

    def test_monthly_report_oracle_checks_read_only_ledgers_and_real_validation_errors(self):
        # Disposable oracle controls. No solution enters the benchmark workspace templates.
        attempt = self.attempt('py-monthly-report-utc')
        core = attempt / 'work/rules.py'
        source = core.read_text(encoding='utf-8')
        reference = '''def summarize(entries, month):
    if not isinstance(month, str) or not re.fullmatch(r'[0-9]{4}-(0[1-9]|1[0-2])', month) or month.startswith('0000'):
        raise ValueError('invalid query month')
    selected = []
    for entry in entries:
        stamp = entry.get('recorded_at')
        if not isinstance(stamp, str) or not re.fullmatch(
            r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(Z|[+-](0[0-9]|1[0-9]|2[0-3]):[0-5][0-9])', stamp
        ):
            raise ValueError('invalid timestamp shape')
        try:
            utc = datetime.fromisoformat(stamp.replace('Z', '+00:00')).astimezone(timezone.utc)
        except OverflowError as error:
            raise ValueError('out-of-range UTC date') from error
        if f'{utc.year:04d}-{utc.month:02d}' == month:
            selected.append(entry)
    return {'ids': [entry['id'] for entry in selected],
            'total_cents': sum(entry['amount_cents'] for entry in selected)}


'''
        candidate = ('import re\nfrom datetime import datetime, timezone\n' + source[:source.index('def summarize')]
                     + reference + source[source.index('def evaluate'):].replace("request['month']", "request.get('month')"))
        core.write_text(candidate, encoding='utf-8')
        result = bench.evaluate_attempt(attempt)
        self.assertTrue(result['automated_artifact_passed'])
        self.assertTrue(result['unchanged_by_evaluator'])
        security = result['automated_artifact_layers']['security']
        self.assertEqual(security['status'], 'PASS')
        self.assertIn('month-year-zero', security['rejection_checks'])
        self.assertIn('timestamp-year-zero', security['rejection_checks'])
        self.assertIn('timestamp-utc-underflow', security['rejection_checks'])
        self.assertIn('timestamp-utc-overflow', security['rejection_checks'])
        for label in ('accept-first-supported-year', 'accept-last-supported-year'):
            self.assertTrue(next(row for row in result['checks'] if row['check'] == label)['passed'])
        changed = candidate.replace("        return json.dumps(summarize(entries, request.get('month')))",
            "        if request.get('month') == '2025-13':\n            return 'VALUE_ERROR'\n"
            "        result = summarize(entries, request.get('month'))\n"
            "        Path(request['ledger']).write_text(json.dumps(entries, indent=2), encoding='utf-8')\n"
            "        return json.dumps(result)")
        core.write_text(changed, encoding='utf-8')
        result = bench.evaluate_attempt(attempt)
        checks = {row['check']: row for row in result['checks']}
        report = checks['utc-march-in-ledger-order']
        self.assertEqual(report['observed'], report['expected'])
        self.assertFalse(report['passed'])
        self.assertNotEqual(report['input_file_sha256_before'], report['input_file_sha256_after'])
        self.assertEqual(checks['month-out-of-range']['observed'], 'VALUE_ERROR')
        self.assertEqual(checks['month-out-of-range']['execution']['exit_code'], 0)
        self.assertFalse(checks['month-out-of-range']['passed'])
        self.assertEqual(result['automated_artifact_layers']['security']['status'], 'FAIL')

    @unittest.skipUnless(shutil.which('node'),'Node required for actual TypeScript runtime')
    def test_real_typescript_explicit_values_fail_baseline(self):
        p=self.attempt('ts-explicit-config');result=bench.evaluate_attempt(p)
        self.assertTrue(all(x['passed'] for x in result['checks'] if x['check'].startswith('preservation')))
        self.assertFalse(result['functional_passed'])
        self.assertEqual(next(x for x in result['checks'] if x['check']=='target-0')['observed']['enabled'],True)

    def test_command_timeout_is_not_a_success(self):
        result=bench.command([sys.executable,'-c','import time; time.sleep(1)'],self.root,.05)
        self.assertTrue(result['timed_out']);self.assertIsNone(result['exit_code'])

    def test_duplicate_json_keys_rejected(self):
        p=self.root/'bad.json';p.write_text('{"a":1,"a":2}')
        with self.assertRaises(ValueError):bench.load(p)

    def test_nested_json_types_cannot_false_accept_boolean_as_integer(self):
        self.assertFalse(bench.same_value({'enabled':0,'limit':False},{'enabled':False,'limit':0}))
        self.assertFalse(bench.same_value([{'accepted':1}],[{'accepted':True}]))
        self.assertTrue(bench.same_value({'enabled':False,'limit':0},{'enabled':False,'limit':0}))

    def test_requested_parent_must_match_actual_header_and_workspace(self):
        parent=str(uuid.uuid4());header={'sessionId':parent,'context':{'cwd':str(self.root)}}
        self.assertTrue(bench.parent_identity_matches(parent,{'id':parent},[header],self.root))
        self.assertFalse(bench.parent_identity_matches(str(uuid.uuid4()),{'id':parent},[header],self.root))
        self.assertFalse(bench.parent_identity_matches(parent,{'id':parent},[header],self.root/'other'))
        self.assertFalse(bench.parent_identity_matches(parent,{'id':parent},[],self.root))

    def test_redaction_cannot_destroy_nonsensitive_list_structure(self):
        p=self.attempt('py-log-redaction');core=p/'work/rules.py';text=core.read_text()
        text=text.replace("return json.dumps(x['data'], sort_keys=True)",
                          "return json.dumps({'user': x['data']['user'], 'nested': {'safe': x['data']['nested']['safe']}, 'items': 'CORRUPTED_NONSECRET_STRUCTURE'})")
        core.write_text(text)
        result=bench.evaluate_attempt(p)
        self.assertFalse(next(x for x in result['checks'] if x['check']=='nested-secret')['passed'])
        self.assertFalse(result['functional_passed'])
        self.assertFalse(result['automated_artifact_passed'])

    def test_redaction_removal_and_replacement_both_preserve_literal_structure(self):
        p=self.attempt('py-log-redaction');core=p/'work/rules.py';original=core.read_text()
        for replacement in [False,True]:
            helper="""def clean(value):
    if isinstance(value, list): return [clean(item) for item in value]
    if isinstance(value, dict):
        return {key: ('[MASKED]' if key in {'password', 'token', 'api_key'} else clean(item)) for key, item in value.items()} if REPLACE else {key: clean(item) for key, item in value.items() if key not in {'password', 'token', 'api_key'}}
    return value

""".replace('REPLACE',str(replacement))
            core.write_text(helper+original.replace("return json.dumps(x['data'], sort_keys=True)","return json.dumps(clean(x['data']), sort_keys=True)"))
            result=bench.evaluate_attempt(p)
            self.assertTrue(result['functional_passed'])
            self.assertTrue(result['automated_artifact_passed'])

    def test_reasoning_pin_uses_actor_state_and_rejects_later_high_transition(self):
        parent=str(uuid.uuid4())
        events=[{'type':'session.start','data':{'sessionId':parent,'reasoningEffort':'low'}},
                {'type':'subagent.started','agentId':'worker','data':{}},
                {'type':'subagent.configured','agentId':'worker','data':{'reasoningEffort':'low'}},
                {'type':'model.call_start','agentId':'worker','data':{'reasoningEffort':None}}]
        self.assertEqual(bench.reasoning_pin_observation(events)['status'],'PASS')
        events.append({'type':'session.model_change','agentId':'worker','data':{'reasoningEffort':'high'}})
        self.assertEqual(bench.reasoning_pin_observation(events)['status'],'FAIL')
        self.assertEqual(bench.reasoning_pin_observation(events)['actors'][parent],'low')

    def test_reasoning_pin_does_not_lend_parent_effort_to_unknown_child(self):
        events=[{'type':'session.start','data':{'sessionId':'parent','reasoningEffort':'low'}},
                {'type':'subagent.started','agentId':'worker','data':{}},
                {'type':'model.call_start','agentId':'worker','data':{'reasoningEffort':None}}]
        self.assertEqual(bench.reasoning_pin_observation(events)['status'],'UNVERIFIED')

    @unittest.skipUnless(shutil.which('node'), 'Node required for actual hook code')
    def test_native_task_arg_pin_changes_only_explicit_overrides_and_keeps_permissions(self):
        test = r'''
const pins = {model: 'weak', effort: 'low', models: new Set(['weak', 'usual'])};
const audit = [];
const record = row => audit.push(row);
const original = Object.freeze({model: 'usual', reasoning_effort: 'high', prompt: 'private case prompt',
                                agent_type: 'general-purpose', mode: 'sync', name: 'worker'});
const apply = (toolName, toolArgs) => pinNativeTaskArguments({toolName, toolArgs, toolCallId: 'native-1'}, pins, record);
assert.deepEqual(apply('task', original), {modifiedArgs: {...original, model: 'weak', reasoning_effort: 'low'}});
assert.equal(original.model, 'usual');
assert.equal(original.reasoning_effort, 'high');
assert.deepEqual(audit, [{tool: 'task', toolCallId: 'native-1', overrides: {
  model: {requested: 'usual', applied: 'weak'}, reasoning_effort: {requested: 'high', applied: 'low'}
}}]);
assert.equal(apply('task', {model: 'weak', reasoning_effort: 'low'}), undefined);
assert.equal(apply('task', {prompt: 'only'}), undefined);
assert.equal(apply('view', original), undefined);
assert.equal(apply('task', ['high']), undefined);
assert.equal(audit.length, 1);
assert.deepEqual(apply('task', {model: 'sensitive-value', reasoning_effort: {value: 'sensitive-value'}}),
                 {modifiedArgs: {model: 'weak', reasoning_effort: 'low'}});
assert.deepEqual(audit[1].overrides, {
  model: {requested: '[unrecognized]', applied: 'weak'}, reasoning_effort: {requested: '[unrecognized]', applied: 'low'}
});
'''
        runner = self.root / 'native-task-pin-test.mjs'
        runner.write_text("import assert from 'node:assert/strict';\n" + bench.TASK_PIN_HOOK + test, encoding='utf-8')
        result = bench.command([shutil.which('node'), str(runner)], self.root, 15)
        self.assertEqual(result['exit_code'], 0, result['stderr'])

    @unittest.skipUnless(shutil.which('node'), 'Node required for actual permission callback code')
    def test_sdk_permission_keeps_credential_test_text_and_distinguishes_denials(self):
        test = r'''
const workspace = path.resolve('work');
const config = {workspace, readRoots: [path.resolve('tools')], exactReadFiles: [path.resolve('host/events.jsonl')]};
const rows = [];
const decide = (request, invocation={}) => benchmarkPermission({toolCallId:'test', ...request}, invocation, config,
                                                             row=>rows.push(row));
const shell = (fullCommandText, possiblePaths=[], extra={}) => decide({kind:'shell', fullCommandText, possiblePaths, ...extra});
const narrative = "@'\n# Contract requires credentials to be omitted.\nFAIL: redact leaks credential values.\n'@ | Set-Content .runtime-proof/credential-evidence.md";
assert.equal(shell(narrative, ['.runtime-proof/credential-evidence.md']).kind, 'approve-once');
assert.equal(shell(narrative, [{path:'.runtime-proof/credential-evidence.md'}]).kind, 'approve-once');
assert.equal(shell(narrative, ['../work-neighbor/credential-evidence.md']).kind, 'reject');
assert.equal(rows.at(-1).reason, 'path-outside-scope');
assert.equal(shell(narrative, [{}]).kind, 'reject');
assert.equal(rows.at(-1).reason, 'path-outside-scope');
assert.equal(shell('Get-Content $target', ['.git-credentials']).kind, 'reject');
assert.equal(rows.at(-1).reason, 'protected-shell-path');
for (const command of ['git credential fill', 'git credential-manager erase', 'git-credential-manager get',
                       'git config credential.helper store', 'gh auth token', 'cmdkey /list', 'Get-StoredCredential',
                       'Get-Content .git-credentials', 'Get-Content .ssh/id_rsa', 'Get-Content .copilot/settings.json',
                       'git push', 'npm install --global foo', 'Invoke-WebRequest example.invalid',
                       'curl example.invalid', 'wget example.invalid']) {
  assert.equal(shell(command).kind, 'reject', command);
  assert.equal(rows.at(-1).reason, 'blocked-shell-pattern');
}
assert.equal(shell(narrative, [], {managedApprovalRequired:true}).kind, 'no-result');
assert.equal(shell(narrative, [], {requestSandboxBypass:true}).kind, 'no-result');
assert.equal(decide({kind:'read',path:'rules.py'}, {managedSettingsEnabled:true}).kind, 'no-result');
assert.equal(rows.at(-1).reason, 'host-approval-required');
assert.equal(decide({kind:'read',path:path.resolve('tools/compiler')}).kind, 'approve-once');
assert.equal(decide({kind:'read',path:path.resolve('host/events.jsonl')}).kind, 'approve-once');
assert.equal(decide({kind:'read',path:path.resolve('host/other.jsonl')}).kind, 'reject');
assert.equal(decide({kind:'write',fileName:'.github/skills/harrtest/SKILL.md'}).kind, 'reject');
assert.equal(decide({kind:'write',fileName:'.github/copilot/settings.local.json'}).kind, 'reject');
assert.equal(decide({kind:'write',fileName:'rules.py'}).kind, 'approve-once');
assert.ok(rows.every(row=>Object.keys(row).length===5 && row.toolCallId==='test'));
assert.ok(!JSON.stringify(rows).includes('credential'));
'''
        runner = self.root / 'sdk-permission-test.mjs'
        runner.write_text("import assert from 'node:assert/strict';\nimport path from 'node:path';\n"
                          + bench.SDK_PERMISSION + test, encoding='utf-8')
        result = bench.command([shutil.which('node'), str(runner)], self.root, 15)
        self.assertEqual(result['exit_code'], 0, result['stderr'])

    def test_frozen_execution_order_is_complete_reproducible_and_rotated(self):
        plan=self.freeze('acceptance');order=plan['execution_order']
        self.assertIn('All arms', plan['native_task_pin_policy'])
        self.assertEqual(len(order),96)
        self.assertEqual(order,bench.balanced_execution_order(plan['cases'],plan['models'],plan['execution_seed']))
        self.assertEqual(len({(x['case'],x['model'],x['repetition'],x['arm']) for x in order}),96)
        first_counts={arm:sum(x['arm']==arm for x in order[::3]) for arm in bench.ARMS}
        self.assertLessEqual(max(first_counts.values())-min(first_counts.values()),1)
        for i in range(0,96,3):self.assertEqual({x['arm'] for x in order[i:i+3]},set(bench.ARMS))

    def test_acceptance_cannot_run_an_out_of_order_arm(self):
        plan=self.freeze('acceptance');second=plan['execution_order'][1]
        attempt=bench.prepare(self.experiment,second['case'],second['arm'],second['model'],second['repetition'])
        with self.assertRaisesRegex(ValueError,'frozen interleaved execution order'):
            bench.run_attempt(attempt,permit_generation=True)

    def test_acceptance_evaluation_requires_current_retained_generation(self):
        plan = self.freeze('acceptance')
        attempts = [bench.prepare(self.experiment, item['case'], item['arm'], item['model'], item['repetition'])
                    for item in plan['execution_order'][:2]]
        with patch.object(bench, '_evaluate_attempt', return_value={'passed': False}) as evaluator:
            for attempt in attempts:
                with self.assertRaisesRegex(ValueError, 'frozen interleaved execution order'):
                    bench.evaluate_attempt(attempt)
            bench.save(attempts[0] / 'generation.json', {'status': 'RUNNING'})
            with self.assertRaisesRegex(ValueError, 'Retained generation outcome'):
                bench.evaluate_attempt(attempts[0])
            bench.save(attempts[0] / 'generation.json', {'status': 'TIMEOUT'})
            bench.save(attempts[1] / 'generation.json', {'status': 'COMPLETED'})
            with self.assertRaisesRegex(ValueError, 'frozen interleaved execution order'):
                bench.evaluate_attempt(attempts[1])
            evaluator.assert_not_called()
            self.assertEqual(bench.evaluate_attempt(attempts[0]), {'passed': False})
            evaluator.assert_called_once_with(attempts[0])
            bench.save(attempts[0] / 'latest-evaluation.json', {'path': 'fixture-result.json'})
            with self.assertRaisesRegex(ValueError, 'frozen interleaved execution order'):
                bench.evaluate_attempt(attempts[0])
            self.assertEqual(evaluator.call_count, 1)

    def test_runtime_lock_prevents_concurrent_evaluation_and_releases_normally(self):
        self.freeze()
        with bench.exclusive_runtime(self.experiment):
            with self.assertRaisesRegex(ValueError,'owns the experiment runtime'):
                with bench.exclusive_runtime(self.experiment):pass
        with bench.exclusive_runtime(self.experiment):pass

    @unittest.skipUnless(shutil.which('node'),'Node required for actual TypeScript runtime')
    def test_typescript_oracle_accepts_positive_control(self):
        p=self.attempt('ts-record-framing');core=p/'work/rules.ts'
        original = core.read_text()
        old = next(line for line in original.splitlines() if "x.op === 'framing'" in line)
        core.write_text(original.replace(old, "  if (x.op === 'framing') return JSON.stringify({message: x.message}) + '\\n';"))
        result=bench.evaluate_attempt(p)
        self.assertTrue(result['functional_passed'])

    def test_csharp_actual_compiler_negative_and_positive_controls(self):
        dotnet=Path(os.environ.get('HARRTEST_BENCH_DOTNET') or ROOT/'output/v5-corporate/toolchains/dotnet/dotnet.exe')
        if not dotnet.is_file():self.skipTest('Pinned local .NET10SDK unavailable')
        self.fake_probe['tools']['dotnet']=str(dotnet)
        p=self.attempt('cs-credit-validation')
        probe = bench.command([sys.executable, '-B', 'check_existing.py'], p/'work')
        self.assertEqual(probe['exit_code'], 0, probe['stderr'])
        bad=bench.evaluate_attempt(p)
        self.assertTrue(all(x['exit_code']==0 for x in bad['builds']))
        self.assertFalse(bad['functional_passed'])
        core=p/'work/Rules.cs';text=core.read_text()
        text=text.replace('new {balance=left+amount,accepted=true}',
                          'new {balance=amount>0 ? left+amount : left,accepted=amount>0}')
        core.write_text(text)
        good=bench.evaluate_attempt(p)
        self.assertTrue(good['functional_passed'],str(good['builds']))

    def test_csharp_build_plan_preserves_existing_behavior_and_rejects_partial_errors(self):
        dotnet = Path(os.environ.get('HARRTEST_BENCH_DOTNET') or ROOT/'output/v5-corporate/toolchains/dotnet/dotnet.exe')
        if not dotnet.is_file():
            self.skipTest('Pinned local .NET10 SDK unavailable')
        self.fake_probe['tools']['dotnet'] = str(dotnet)
        attempt = self.attempt('cs-build-dependency-plan')
        baseline = bench.evaluate_attempt(attempt)
        self.assertTrue(all(row['passed'] for row in baseline['checks'] if row['check'].startswith('preservation')))
        self.assertFalse(baseline['functional_passed'])
        self.assertEqual(baseline['automated_artifact_layers']['resilience']['status'], 'FAIL')
        # Disposable oracle control, outside the frozen generator's project and skill.
        core = attempt / 'work/Rules.cs'
        old = core.read_text(encoding='utf-8')
        implementation = '''        var items = jobs.EnumerateArray().Select(job => (
            Id: job.GetProperty("id").GetString()!,
            Dependencies: job.GetProperty("depends_on").EnumerateArray().Select(value => value.GetString()!).ToArray()
        )).ToList();
        var known = items.Select(item => item.Id).ToHashSet(StringComparer.Ordinal);
        static string Failure(string error) => JsonSerializer.Serialize(new { order = Array.Empty<string>(), error });
        if (known.Count != items.Count)
            return Failure("duplicate-id");
        if (items.Any(item => item.Dependencies.Any(dep => !known.Contains(dep))))
            return Failure("missing-dependency");
        var order = new System.Collections.Generic.List<string>();
        var completed = new System.Collections.Generic.HashSet<string>(StringComparer.Ordinal);
        while (order.Count < items.Count)
        {
            var next = items.FindIndex(item => !completed.Contains(item.Id) && item.Dependencies.All(completed.Contains));
            if (next < 0)
                return Failure("cycle");
            order.Add(items[next].Id);
            completed.Add(items[next].Id);
        }
'''
        fixed = old[:old.index('        var order =')] + implementation + old[old.index('        return JsonSerializer.Serialize(new { order,'):]
        core.write_text(fixed, encoding='utf-8')
        correct = bench.evaluate_attempt(attempt)
        self.assertTrue(correct['automated_artifact_passed'], str([row['check'] for row in correct['checks'] if not row['passed']]))
        self.assertTrue(correct['unchanged_by_evaluator'])
        partial = fixed.replace('return Failure("cycle");', 'return JsonSerializer.Serialize(new { order, error = "cycle" });')
        core.write_text(partial, encoding='utf-8')
        partial_result = bench.evaluate_attempt(attempt)
        failures = [row for row in partial_result['checks'] if not row['passed']]
        self.assertEqual(len(failures), 2)
        self.assertTrue(all(row['observed'] == {'order': ['first'], 'error': 'cycle'} for row in failures))
        self.assertEqual(partial_result['automated_artifact_layers']['resilience']['status'], 'FAIL')

    def test_stock_components_have_independent_dotnet_oracles_and_real_cli_composition(self):
        dotnet = Path(os.environ.get('HARRTEST_BENCH_DOTNET') or ROOT/'output/v5-corporate/toolchains/dotnet/dotnet.exe')
        if not dotnet.is_file():
            self.skipTest('Pinned local .NET10 SDK unavailable')
        self.fake_probe['tools']['dotnet'] = str(dotnet)
        attempt = self.attempt('cs-stock-snapshot')
        workspace = attempt / 'work'
        baseline = bench.evaluate_attempt(attempt)
        checks = {row['check']: row['passed'] for row in baseline['checks']}
        self.assertTrue(all(passed for name, passed in checks.items() if name.startswith('preservation')))
        self.assertFalse(checks['stock-csv-quoted-fields'])
        self.assertFalse(checks['stock-projection-latest-case-sensitive-wide-total'])
        self.assertFalse(checks['public-composed-report'])
        # Disposable evaluator controls, never copied into the model workspace templates.
        (workspace/'StockCsv.cs').write_text('''using Microsoft.VisualBasic.FileIO;

public static class StockCsv
{
    public static StockRow[] Parse(string csv)
    {
        using var parser = new TextFieldParser(new System.IO.StringReader(csv));
        parser.SetDelimiters(",");
        parser.TrimWhiteSpace = false;
        var rows = new System.Collections.Generic.List<StockRow>();
        while (!parser.EndOfData)
        {
            var fields = parser.ReadFields()!;
            rows.Add(new StockRow(fields[0], fields[1], int.Parse(fields[2])));
        }
        return rows.ToArray();
    }
}
''', encoding='utf-8')
        isolated = bench.evaluate_attempt(attempt)
        checks = {row['check']: row['passed'] for row in isolated['checks']}
        self.assertTrue(checks['stock-csv-quoted-fields'])
        self.assertTrue(checks['stock-csv-retains-field-values'])
        self.assertFalse(checks['stock-projection-latest-case-sensitive-wide-total'])
        self.assertFalse(checks['public-composed-report'])
        projection = workspace/'StockProjection.cs'
        old = projection.read_text(encoding='utf-8')
        projection.write_text(old.replace('.Sum(row => (long)row.Units)',
            '.GroupBy(row => row.Sku, StringComparer.Ordinal).Sum(group => (long)group.Last().Units)'), encoding='utf-8')
        passed = bench.evaluate_attempt(attempt)
        self.assertTrue(passed['automated_artifact_passed'], str([row['check'] for row in passed['checks'] if not row['passed']]))
        self.assertTrue(passed['unchanged_by_evaluator'])

    @unittest.skipUnless(shutil.which('node'), 'Node required for TypeScript runtime')
    def test_triage_components_have_independent_typed_oracles_and_real_cli_composition(self):
        if not self.fake_probe['tools'].get('tsc'):
            self.skipTest('Pinned TypeScript compiler unavailable')
        attempt = self.attempt('ts-triage-queue')
        workspace = attempt / 'work'
        baseline = bench.evaluate_attempt(attempt)
        checks = {row['check']: row['passed'] for row in baseline['checks']}
        self.assertTrue(all(passed for name, passed in checks.items() if name.startswith('preservation')))
        self.assertEqual(baseline['type_correctness'], 'PASS', str(baseline['builds']))
        self.assertFalse(checks['triage-rank-stable-and-nonmutating'])
        self.assertFalse(checks['triage-group-owner-normalization'])
        self.assertFalse(checks['public-composed-report'])
        group = workspace/'group.ts'
        group_control = group.read_text(encoding='utf-8').replace('    if (ticket.owner === null) {',
            "    const name = ticket.owner?.trim() ?? '';\n    if (!name) {")
        group_control = group_control.replace('      const group = owners.get(ticket.owner)',
            '      const key = name.toLowerCase();\n      const group = owners.get(key)')
        group_control = group_control.replace('{name: ticket.owner,', '{name,').replace('owners.set(ticket.owner, group)', 'owners.set(key, group)')
        group.write_text(group_control, encoding='utf-8')
        isolated = bench.evaluate_attempt(attempt)
        checks = {row['check']: row['passed'] for row in isolated['checks']}
        self.assertTrue(checks['triage-group-owner-normalization'])
        self.assertFalse(checks['triage-rank-stable-and-nonmutating'])
        self.assertFalse(checks['public-composed-report'])
        rank = workspace/'rank.ts'
        original = rank.read_text(encoding='utf-8')
        rank.write_text(original.replace('  return tickets.sort((left, right) => left.severity.localeCompare(right.severity));',
            "  const names = ['critical', 'high', 'normal', 'low'];\n"
            '  const rank = (ticket: Ticket) => {\n'
            '    const position = names.indexOf(ticket.severity.trim().toLowerCase());\n'
            '    return position < 0 ? names.length : position;\n'
            '  };\n'
            '  return [...tickets].sort((left, right) => rank(left) - rank(right));'), encoding='utf-8')
        passed = bench.evaluate_attempt(attempt)
        self.assertTrue(passed['automated_artifact_passed'], str([row['check'] for row in passed['checks'] if not row['passed']]))
        self.assertEqual(passed['type_correctness'], 'PASS')
        types = workspace/'tickets.ts'
        types.write_text(types.read_text(encoding='utf-8') + '\n// Candidate edited the frozen interface file.\n', encoding='utf-8')
        changed = bench.evaluate_attempt(attempt)
        self.assertTrue(changed['functional_passed'])
        self.assertFalse(changed['documented_contract_and_adapter_preserved'])

    def test_cpp_actual_compiler_negative_and_positive_controls(self):
        if sys.platform!='win32':
            compiler=shutil.which('clang++') or shutil.which('g++')
            if not compiler:self.skipTest('C++ compiler unavailable')
            self.fake_probe['tools']['cxx']=[compiler]
        else:
            compiler=Path('C:/Program Files (x86)/Microsoft Visual Studio/2022/BuildTools/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/cl.exe')
            setup=Path('C:/Program Files (x86)/Microsoft Visual Studio/2022/BuildTools/VC/Auxiliary/Build/vcvars64.bat')
            if not compiler.is_file() or not setup.is_file():self.skipTest('MSVC toolchain unavailable')
            self.fake_probe['tools']['cxx']=[str(compiler)];self.fake_probe['tools']['msvc_env']=str(setup)
        p=self.attempt('cpp-index-validation')
        bad=bench.evaluate_attempt(p)
        self.assertTrue(all(x['exit_code']==0 for x in bad['builds']),str(bad['builds']))
        self.assertFalse(bad['functional_passed'])
        core=p/'work/rules.hpp';text=core.read_text().replace('std::vector<int> v{10,20,30}; return', 'std::vector<int> v{10,20,30}; if(index<0 || index>=static_cast<long long>(v.size())) throw std::out_of_range("index"); return')
        core.write_text(text)
        good=bench.evaluate_attempt(p)
        self.assertTrue(good['functional_passed'],str(good['builds']))

    def timeout_review(self, attempt, status='TIMEOUT'):
        result=bench.evaluate_attempt(attempt)
        bench.save(attempt/'generation.json',{'status':status,'source':result['source_before']})
        ref=bench.load(attempt/'latest-evaluation.json');evidence=attempt/ref['path']
        report={'schema':1,'evaluation_sha256':ref['sha256'],'source_sha256':bench.digest(result['source_before']),
                'reviewer':{'method':'human','id':'independent-unit-reviewer'},'limitations_reviewed':True,
                'completion_claim':'INCOMPLETE','layers':[{'id':name,'status':'UNVERIFIED',
                'rationale':'The retained timed-out generation did not establish this required quality layer.',
                'evidence':[{'path':str(evidence),'sha256':bench.sha(evidence)}]} for name in bench.LAYER_NAMES]}
        path=attempt/'independent-review.json';bench.save(path,report)
        return path

    def test_reviewed_timeout_is_a_failed_retained_denominator_not_a_dead_end(self):
        p=self.attempt('py-monthly-report-utc');review=self.timeout_review(p)
        assessment=bench.record_assessment(p,review)
        self.assertFalse(assessment['complete_quality_passed'])
        self.assertFalse(assessment['false_accept'])
        counts=bench.summarize(self.experiment)['counts']['plain']
        self.assertEqual(counts['denominator'],32)
        self.assertEqual(counts['unreviewed'],31)
        self.assertEqual(counts['false_accepts'],0)

    def test_monthly_report_review_requires_applicable_security_with_passing_controls(self):
        attempt = self.attempt('py-monthly-report-utc')
        report = self.timeout_review(attempt)
        review = bench.load(report)
        security = next(row for row in review['layers'] if row['id'] == 'security')
        for verdict, error in [('NOT_APPLICABLE', 'layers are required'),
                               ('PASS', 'scoped security controls cannot become PASS')]:
            with self.subTest(verdict=verdict):
                security['status'] = verdict
                bench.save(report, review)
                with self.assertRaisesRegex(ValueError, error):
                    bench.record_assessment(attempt, report)

    def test_failed_generation_cannot_be_upgraded_by_positive_layer_assertions(self):
        p=self.attempt('py-retry-recovery');core=p/'work/rules.py'
        core.write_text(core.read_text().replace("    for event in x['events']:\n", "    for event in x['events']:\n        if event['id'] in state['seen']:\n            continue\n"))
        review=self.timeout_review(p,'FAILED');data=bench.load(review)
        for layer in data['layers']:layer['status']='PASS'
        bench.save(review,data)
        self.assertFalse(bench.record_assessment(p,review)['complete_quality_passed'])

    def test_post_review_generation_changes_invalidate_summary(self):
        p=self.attempt('py-monthly-report-utc');review=self.timeout_review(p)
        bench.record_assessment(p,review)
        bench.save(p/'generation.json',{'status':'COMPLETED'})
        with self.assertRaisesRegex(ValueError,'generation record changed'):
            bench.summarize(self.experiment)

    def test_original_check_replay_detects_regression_after_generated_test_weakening(self):
        attempt = self.attempt('py-retry-recovery')
        workspace = attempt / 'work'
        core = workspace / 'rules.py'
        core.write_text(core.read_text().replace("state['balance'] += event['amount']", "state['balance'] += event['amount'] + 1"))
        edited_oracle = workspace / 'check_existing.py'
        edited_oracle.write_text(edited_oracle.read_text().replace("'balance':3", "'balance':4"))
        before = bench.tree(workspace)
        result = bench.evaluate_attempt(attempt)
        replay = next(check for check in result['checks'] if check['check'] == 'preservation-existing-test-replay')
        self.assertEqual(replay['execution']['baseline']['exit_code'], 0)
        self.assertNotEqual(replay['execution']['candidate']['exit_code'], 0)
        self.assertEqual(replay['oracle_sha256'], bench.load(attempt / 'attempt.json')['baseline']['check_existing.py'])
        self.assertEqual(result['automated_artifact_layers']['preservation']['status'], 'FAIL')
        self.assertEqual(bench.tree(workspace), before)

    def test_summary_reports_reviewed_layer_failures_and_bound_credit_receipts(self):
        attempt = self.attempt('py-monthly-report-utc')
        report = self.timeout_review(attempt)
        review = bench.load(report)
        for row in review['layers']:
            if row['id'] in ('preservation', 'architecture', 'security'):
                row['status'] = 'FAIL'
        bench.save(report, review)
        usage_path = attempt / 'usage.json'
        usage = {'aiCreditsStatus': 'complete', 'totalNanoAiu': 1_500_000_000,
                 'agentMetrics': {'main': {'totalNanoAiu': 1_000_000_000}, 'child': {'totalNanoAiu': 500_000_000}},
                 'modelMetrics': {'weak-observed': {'totalNanoAiu': 1_500_000_000}}}
        bench.save(usage_path, usage)
        generation_path = attempt / 'generation.json'
        generation = bench.load(generation_path)
        generation.update(seconds=3.5, native_observations={'usage_file_sha256': bench.sha(usage_path),
                          'completed_subagents': 1, 'subagents': [{'agentId': 'child'}]})
        bench.save(generation_path, generation)
        bench.record_assessment(attempt, report)
        summary = bench.summarize(self.experiment)
        counts = summary['counts']['plain']
        self.assertEqual((counts['regressions'], counts['security_defects'], counts['architecture_violations']), (1, 1, 1))
        self.assertEqual(counts['reviewed_layer_counts']['security']['UNREVIEWED'], 31)
        self.assertEqual(counts['generation_seconds']['median_observed'], 3.5)
        self.assertEqual(counts['evaluation_seconds']['observed_attempts'], 1)
        self.assertEqual(counts['copilot_usage']['reported_ai_credits_subtotal'], 1.5)
        self.assertEqual(counts['copilot_usage']['child_totals_reconciled'], 1)
        usage['totalNanoAiu'] = 0
        bench.save(usage_path, usage)
        invalidated = bench.summarize(self.experiment)['counts']['plain']['copilot_usage']
        self.assertEqual(invalidated['status_counts']['UNVERIFIED'], 1)
        self.assertIsNone(invalidated['reported_ai_credits_subtotal'])

    def test_usage_partial_and_unavailable_are_distinct_from_zero(self):
        usage_path = self.root / 'usage.json'
        for status, reported in [('complete', 0.0), ('partial', 0.0), ('unavailable', None)]:
            with self.subTest(status=status):
                bench.save(usage_path, {'aiCreditsStatus': status, 'totalNanoAiu': 0})
                result = bench.credit_metrics(self.root, {'native_observations': {'usage_file_sha256': bench.sha(usage_path)}})
                self.assertEqual(result['status'], status.upper())
                self.assertEqual(result['reported_ai_credits'], reported)

    def test_performance_metrics_keep_recorded_samples_and_reject_missing_samples(self):
        metric = bench.performance_metrics({'performance': {'status': 'PASS', 'median_ratio': 0.5,
                            'baseline': [{'exit_code': 0, 'seconds': 2.0}],
                            'candidate': [{'exit_code': 0, 'seconds': 1.0}, {'exit_code': None, 'timed_out': True, 'seconds': 120}]}})
        self.assertEqual(metric['median_ratio'], 0.5)
        self.assertEqual(metric['baseline_seconds'], [2.0])
        self.assertEqual(metric['candidate_seconds'], [1.0])
        self.assertIsNone(bench.performance_metrics({})['candidate_median_seconds'])

    @unittest.skipUnless(shutil.which('node'),'Node required')
    def test_multicomponent_typescript_consumer_and_safe_diagnostics(self):
        p=self.attempt('ts-explicit-config')
        bad=bench.evaluate_attempt(p)
        self.assertFalse(bad['functional_passed'])
        self.assertFalse(next(x for x in bad['checks'] if x['check']=='public-file-adapter')['passed'])
        core=p/'work/rules.ts';core.write_text(core.read_text().replace(' || ',' ?? '))
        (p/'work/cli.ts').write_text("import fs from 'node:fs';\nimport {evaluate} from './rules.ts';\ntry { const text=process.argv[2]==='--config'?fs.readFileSync(process.argv[3],'utf8'):process.argv[2]; console.log(evaluate(text)); } catch { console.error('Invalid configuration'); process.exitCode=1; }\n")
        good=bench.evaluate_attempt(p)
        self.assertTrue(good['functional_passed'])
        if self.fake_probe['tools'].get('tsc'):
            self.assertTrue(good['automated_artifact_passed'])
            self.assertTrue(good['documented_contract_and_adapter_preserved'])
        else:self.assertEqual(good['type_correctness'],'UNVERIFIED')
        self.assertFalse(good['complete_quality_passed'])

    @unittest.skipUnless(shutil.which('node'),'Node required')
    def test_runtime_success_does_not_hide_typescript_type_error(self):
        if not self.fake_probe['tools'].get('tsc'):self.skipTest('Pinned TypeScript compiler unavailable')
        p=self.attempt('ts-record-framing');core=p/'work/rules.ts'
        original = core.read_text()
        old = next(line for line in original.splitlines() if "x.op === 'framing'" in line)
        core.write_text(original.replace(old, "  if (x.op === 'framing') return JSON.stringify({message: x.message}) + '\\n';")
                        + '\nconst typeOnlyDefect: number = "wrong type";\n')
        result=bench.evaluate_attempt(p)
        self.assertTrue(result['functional_passed'])
        self.assertEqual(result['type_correctness'],'FAIL')
        self.assertFalse(result['automated_artifact_passed'])

    def test_multicomponent_csharp_api_and_public_adapter_positive_control(self):
        dotnet=ROOT/'output/v5-corporate/toolchains/dotnet/dotnet.exe'
        if not dotnet.is_file():self.skipTest('Pinned local .NET10SDK unavailable')
        self.fake_probe['tools']['dotnet']=str(dotnet)
        p=self.attempt('cs-atomic-transfer');core=p/'work/Rules.cs';text=core.read_text()
        text=text.replace('long left=x.GetProperty("left").GetInt64(), amount=x.GetProperty("amount").GetInt64();', '''if(op=="transfer_many") { long original=x.GetProperty("left").GetInt64(), l=original, r=x.GetProperty("right").GetInt64(), oldRight=r; foreach(var value in x.GetProperty("amounts").EnumerateArray()) { long n=value.GetInt64(); if(n<=0 || n>l) return JsonSerializer.Serialize(new {left=original,right=oldRight,accepted=false}); l-=n; r+=n; } return JsonSerializer.Serialize(new {left=l,right=r,accepted=true}); }\n  long left=x.GetProperty("left").GetInt64(), amount=x.GetProperty("amount").GetInt64();''')
        text=text.replace('long right=x.GetProperty("right").GetInt64(); left-=amount;', 'long right=x.GetProperty("right").GetInt64(); if(amount<=0 || amount>left) return JsonSerializer.Serialize(new {left,right,accepted=false}); left-=amount;')
        core.write_text(text)
        (p/'work/Program.cs').write_text('try { var text=args[0]=="--input-file"?System.IO.File.ReadAllText(args[1]):args[0]; Console.WriteLine(Rules.Evaluate(text)); } catch { Console.Error.WriteLine("Invalid input"); Environment.ExitCode=1; }\n')
        good=bench.evaluate_attempt(p)
        self.assertTrue(good['functional_passed'],str([x for x in good['checks'] if not x['passed']]))
        self.assertTrue(good['automated_artifact_passed'])


if __name__=='__main__':
    unittest.main()
