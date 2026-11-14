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
        tools_path=ROOT/'output/v5-corporate/evaluation-tools.json'
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

    def test_corpus_has_distinct_development_and_held_cases(self):
        rows=bench.cases()
        self.assertEqual(len(rows),16)
        self.assertEqual(len({row['id'] for row in rows}),16)
        for split in ['development','acceptance']:
            self.assertEqual(sum(x['split']==split for x in rows),8)

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
            bench.prepare(self.experiment,'py-event-idempotency','plain','other',1)

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
        p=self.attempt('py-event-idempotency')
        with self.assertRaises(FileExistsError):
            bench.prepare(self.experiment,'py-event-idempotency','plain','weak-observed',1)
        self.assertEqual(bench.load(p/'attempt.json')['arm'],'plain')

    def test_plain_settings_are_local_and_do_not_turn_off_hooks(self):
        p=self.attempt('py-event-idempotency')
        settings=bench.load(p/'work/.github/copilot/settings.local.json')
        self.assertEqual(settings['disabledSkills'],['harrtest'])
        self.assertNotIn('disableAllHooks',settings)

    def test_generation_needs_explicit_authorization(self):
        p=self.attempt('py-event-idempotency')
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
        p=self.attempt('py-event-idempotency')
        result=bench.evaluate_attempt(p)
        self.assertTrue(result['checks'][0]['passed'])
        self.assertFalse(result['checks'][1]['passed'])
        self.assertEqual(result['checks'][1]['observed']['balance'],6)
        self.assertTrue(result['unchanged_by_evaluator'])
        self.assertFalse(result['complete_quality_passed'])

    def test_independent_oracle_accepts_known_positive_control(self):
        # Disposable evaluator unit control only; never enters a live arm or claim.
        p=self.attempt('py-event-idempotency');core=p/'work/rules.py'
        text=core.read_text();text=text.replace("    for event in x['events']:\n", "    for event in x['events']:\n        if event['id'] in state['seen']:\n            continue\n")
        core.write_text(text)
        result=bench.evaluate_attempt(p)
        self.assertTrue(result['functional_passed'])
        self.assertTrue(result['documented_contract_and_adapter_preserved'])
        self.assertFalse(result['complete_quality_passed'])

    def test_contract_edit_is_detected_despite_correct_function(self):
        p=self.attempt('py-event-idempotency');(p/'work/ARCHITECTURE.md').write_text('relaxed contract')
        result=bench.evaluate_attempt(p)
        self.assertFalse(result['documented_contract_and_adapter_preserved'])

    def test_extended_existing_tests_do_not_fail_architecture_on_byte_changes(self):
        p=self.attempt('py-event-idempotency');test=p/'work/check_existing.py'
        test.write_text(test.read_text()+'\nassert len([1,2,3]) == 3\n')
        result=bench.evaluate_attempt(p)
        self.assertTrue(result['existing_tests_changed'])
        self.assertTrue(result['documented_contract_and_adapter_preserved'])
        self.assertIn('Independent',result['test_oracle_preservation'])

    def test_deleted_or_trivially_weakened_test_does_not_pass_architecture(self):
        p=self.attempt('py-event-idempotency');test=p/'work/check_existing.py'
        test.write_text('assert True\n')
        self.assertFalse(bench.evaluate_attempt(p)['documented_contract_and_adapter_preserved'])
        test.unlink()
        self.assertFalse(bench.evaluate_attempt(p)['documented_contract_and_adapter_preserved'])

    def test_actual_shell_policy_edit_is_invalid_even_with_exit_zero(self):
        p=self.attempt('py-event-idempotency');work=p/'work'
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
        attempt = bench.prepare(self.experiment, 'py-event-idempotency', 'v5', 'weak-observed', 1)
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
                attempt = bench.prepare(self.experiment, 'py-event-idempotency', arm, 'weak-observed', 1)
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

    def test_frozen_execution_order_is_complete_reproducible_and_rotated(self):
        plan=self.freeze('acceptance');order=plan['execution_order']
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
        p=self.attempt('ts-explicit-limit');core=p/'work/rules.ts'
        core.write_text(core.read_text().replace(' || ', ' ?? '))
        result=bench.evaluate_attempt(p)
        self.assertTrue(result['functional_passed'])

    def test_csharp_actual_compiler_negative_and_positive_controls(self):
        dotnet=ROOT/'output/v5-corporate/toolchains/dotnet/dotnet.exe'
        if not dotnet.is_file():self.skipTest('Pinned local .NET10SDK unavailable')
        self.fake_probe['tools']['dotnet']=str(dotnet)
        p=self.attempt('cs-refund-boundary')
        probe = bench.command([sys.executable, '-B', 'check_existing.py'], p/'work')
        self.assertEqual(probe['exit_code'], 0, probe['stderr'])
        bad=bench.evaluate_attempt(p)
        self.assertTrue(all(x['exit_code']==0 for x in bad['builds']))
        self.assertFalse(bad['functional_passed'])
        core=p/'work/Rules.cs';text=core.read_text()
        text=text.replace('<x.GetProperty("window")','<=x.GetProperty("window")')
        core.write_text(text)
        good=bench.evaluate_attempt(p)
        self.assertTrue(good['functional_passed'],str(good['builds']))

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
        p=self.attempt('py-batch-atomicity');review=self.timeout_review(p)
        assessment=bench.record_assessment(p,review)
        self.assertFalse(assessment['complete_quality_passed'])
        self.assertFalse(assessment['false_accept'])
        counts=bench.summarize(self.experiment)['counts']['plain']
        self.assertEqual(counts['denominator'],32)
        self.assertEqual(counts['unreviewed'],31)
        self.assertEqual(counts['false_accepts'],0)

    def test_failed_generation_cannot_be_upgraded_by_positive_layer_assertions(self):
        p=self.attempt('py-event-idempotency');core=p/'work/rules.py'
        core.write_text(core.read_text().replace("    for event in x['events']:\n", "    for event in x['events']:\n        if event['id'] in state['seen']:\n            continue\n"))
        review=self.timeout_review(p,'FAILED');data=bench.load(review)
        for layer in data['layers']:layer['status']='PASS'
        bench.save(review,data)
        self.assertFalse(bench.record_assessment(p,review)['complete_quality_passed'])

    def test_post_review_generation_changes_invalidate_summary(self):
        p=self.attempt('py-batch-atomicity');review=self.timeout_review(p)
        bench.record_assessment(p,review)
        bench.save(p/'generation.json',{'status':'COMPLETED'})
        with self.assertRaisesRegex(ValueError,'generation record changed'):
            bench.summarize(self.experiment)

    def test_original_check_replay_detects_regression_after_generated_test_weakening(self):
        attempt = self.attempt('py-event-idempotency')
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
        attempt = self.attempt('py-batch-atomicity')
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
        p=self.attempt('ts-explicit-limit');core=p/'work/rules.ts'
        core.write_text(core.read_text().replace(' || ',' ?? ')+'\nconst typeOnlyDefect: number = "wrong type";\n')
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
