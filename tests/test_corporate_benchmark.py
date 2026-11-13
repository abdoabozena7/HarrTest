"""Executable evaluator controls; these are not live-model quality results."""
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
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

    def freeze(self):
        with patch.object(bench, "preflight", return_value=self.fake_probe):
            return bench.freeze(self.experiment,self.old,self.new,["weak-observed","normal-observed"])

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
        self.assertTrue(good['automated_artifact_passed'])
        self.assertTrue(good['documented_contract_and_adapter_preserved'])
        self.assertFalse(good['complete_quality_passed'])

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
