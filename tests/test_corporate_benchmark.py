"""Executable evaluator controls; these are not live-model quality results."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
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
            (directory / "assets/corporate/retired-development.json").write_text("DO NOT EXPOSE ARCHIVE\n")
            (directory / "references").mkdir()
            for guide in ['cli-agent-validation.md','web-validation.md','simulation-validation.md']:
                (directory/'references'/guide).write_text('Production workflow guide\n')
        self.experiment = self.root / "experiment"
        self.fake_probe = {"tools": {"python":sys.executable,"node":shutil.which("node"),"copilot":"fixture-only"},
                           "blocked":[], "assurance":"unit-test substitution, not a capability observation"}
        tools_path=Path(os.environ.get('HARRTEST_BENCH_TOOLS') or ROOT/'output/v5-corporate/evaluation-tools.json')
        self.configured_tools = bench.load(tools_path) if tools_path.is_file() else {}
        for key in ['tsc','node_types']:
            if self.configured_tools.get(key):self.fake_probe['tools'][key]=self.configured_tools[key]

    def freeze(self,kind='development',corpus=bench.CORPUS):
        with patch.object(bench, "preflight", return_value=self.fake_probe):
            return bench.freeze(self.experiment,self.old,self.new,["weak-observed","normal-observed"],kind=kind,corpus=corpus)

    def attempt(self, case):
        active = bench.cases()
        if any(row['id'] == case for row in active):
            self.freeze()
        else:
            # Exercise historical evaluator behavior without admitting a retired
            # case to the current active corpus or a new acceptance experiment.
            retired = bench.load(bench.CORPUS.with_name('retired-development.json'))['cases']
            original = next(row for row in retired if row['id'] == case)
            replaced = next(row for row in active if row['language'] == original['language']
                            and row['split'] == 'development')
            path = self.root / 'historical-control-corpus.json'
            bench.save(path, {'schema': 1, 'cases': [original if row == replaced else row for row in active]})
            self.freeze(corpus=path)
        return bench.prepare(self.experiment,case,"plain","weak-observed",1)

    def summary_attempt(self):
        # Summaries enumerate the frozen held matrix, so the synthetic receipt
        # must be attached to an actual held slot regardless of corpus rotation.
        plan = self.freeze()
        held_python = {row['id'] for row in plan['cases']
                       if row['split'] == 'acceptance' and row['language'] == 'python'}
        slot = next(row for row in plan['execution_order'] if row['case'] in held_python and row['arm'] == 'plain')
        return bench.prepare(self.experiment, slot['case'], slot['arm'], slot['model'], slot['repetition'])

    def test_corporate_editor_guard_profile_for_v5_development(self):
        shutil.copy2(ROOT / 'scripts/copilot_guard.py', self.new / 'scripts/copilot_guard.py')
        with patch.object(bench, 'preflight', return_value=self.fake_probe):
            plan = bench.freeze(self.experiment, self.old, self.new, ['weak-observed', 'normal-observed'],
                                corporate_guard_goal='mission')
        self.assertEqual(plan['corporate_guard_goal'], 'mission')
        self.assertTrue((self.experiment / 'packages/v5/scripts/copilot_guard.py').is_file())
        case = next(row['id'] for row in plan['cases']
                    if row['split'] == 'development' and row['language'] == 'python')
        with self.assertRaisesRegex(ValueError, 'requires the V5 package'):
            bench.prepare(self.experiment, case, 'plain', 'weak-observed', 1)
        slot = bench.prepare(self.experiment, case, 'v5', 'weak-observed', 1)
        meta = bench.load(slot / 'attempt.json')
        self.assertTrue(meta['prompt'].startswith('$harrtest\n' + meta['case']['request']))

    def test_acceptance_guard_profiles_v5_on_the_frozen_substantial_cases(self):
        shutil.copy2(ROOT / 'scripts/copilot_guard.py', self.new / 'scripts/copilot_guard.py')
        with patch.object(bench, 'preflight', return_value=self.fake_probe):
            plan = bench.freeze(self.experiment, self.old, self.new, ['weak-observed', 'normal-observed'],
                                kind='acceptance', corporate_guard_goal='mission')
        cases = [case for case in plan['cases'] if case['split'] == 'acceptance']
        guarded = sorted(case['id'] for case in cases if case.get('complexity'))
        self.assertEqual(guarded, ['cs-studio-cue-report', 'ts-pick-list'])
        self.assertEqual(plan['corporate_guard_cases'], guarded)
        self.assertEqual(len(plan['execution_order']), 96)
        for arm in bench.ARMS:
            slot = bench.prepare(self.experiment, guarded[0], arm, 'weak-observed', 1)
            metadata = bench.load(slot / 'attempt.json')
            self.assertEqual(metadata['arm'], arm)
            self.assertEqual(bench.attempt_guard_goal(plan, metadata), 'mission' if arm == 'v5' else None)
            self.assertFalse((slot / 'work/.github/hooks/harrtest-corporate-guard.json').exists())
        bounded = next(case['id'] for case in cases if case['id'] not in guarded)
        narrow = bench.prepare(self.experiment, bounded, 'v5', 'normal-observed', 2)
        self.assertIsNone(bench.attempt_guard_goal(plan, bench.load(narrow / 'attempt.json')))
        summary = bench.summarize(self.experiment)
        self.assertEqual(summary['candidate_profile'], {'corporate_guard_cases': guarded,
                                                         'enrollment_arm': 'v5', 'goal': 'mission'})
        self.assertFalse(summary['release_qualified'])

    def test_corpus_has_distinct_development_and_held_cases(self):
        rows=bench.cases()
        self.assertEqual(len(rows),16)
        self.assertEqual(len({row['id'] for row in rows}),16)
        for split in ['development','acceptance']:
            self.assertEqual(sum(x['split']==split for x in rows),8)
            for language in bench.LANGUAGES:
                self.assertEqual(sum(x['split']==split and x['language']==language for x in rows),2)
        splits = {row['id']: row['split'] for row in rows}
        promoted = {'cs-build-dependency-plan', 'py-retry-recovery', 'cpp-lookup-scaling'}
        consumed = promoted | {'cs-stock-snapshot', 'ts-triage-queue', 'py-monthly-report-utc'}
        self.assertTrue(all(splits[case] == 'development' for case in consumed))
        retained = {'cs-studio-cue-report', 'ts-pick-list', 'ts-tile-window', 'py-museum-route', 'cpp-capacity-contract'}
        replacements = {'cs-room-schedule-recovery', 'py-checkpoint-publish-recovery', 'cpp-range-count-scaling'}
        self.assertEqual({case for case, split in splits.items() if split == 'acceptance'}, retained | replacements)
        self.assertEqual({row['id']: row['performance_max_ratio'] for row in rows if 'performance_max_ratio' in row},
                         {'cpp-lookup-scaling': 0.70, 'cpp-range-count-scaling': 0.70})
        archive = bench.load(bench.CORPUS.with_name('retired-development.json'))
        retired = archive['cases']
        retired_ids = {'cs-credit-validation', 'ts-path-boundary', 'py-log-redaction', 'py-batch-atomicity',
                       'ts-record-framing', 'cs-atomic-transfer', 'py-recipe-batch-scale', 'cpp-wide-total'}
        self.assertEqual(set(archive['rotations'][-1]['promoted_to_development']), promoted)
        self.assertEqual(len(retired), len(retired_ids))
        self.assertEqual({row['id'] for row in retired}, retired_ids)
        self.assertCountEqual([case for rotation in archive['rotations'] for case in rotation['retired']], retired_ids)
        self.assertTrue(all(row['split'] == 'development' and row['id'] not in splits for row in retired))
        for previously_retired in ['py-event-idempotency', 'cs-refund-boundary', 'cs-tenant-lookup', 'ts-explicit-limit']:
            self.assertNotIn(previously_retired, splits)

    def test_pin_does_not_expose_evaluator_or_corpus(self):
        self.freeze()
        pinned=self.experiment/'packages/v5'
        self.assertTrue((pinned/'scripts/tool.py').is_file())
        self.assertFalse((pinned/'scripts/corporate_benchmark.py').exists())
        self.assertFalse((pinned/'assets/corporate').exists())
        self.assertEqual(bench.sha(self.experiment/'evaluator/cases.json'), bench.sha(bench.CORPUS))
        self.assertEqual(bench.sha(self.experiment/'evaluator/corporate_benchmark.py'), bench.sha(bench.__file__))
        for guide in ['cli-agent-validation.md','web-validation.md','simulation-validation.md']:
            self.assertTrue((pinned/'references'/guide).is_file())

    def test_prepared_git_baseline_preserves_raw_source_with_autocrlf(self):
        create = bench.fixture

        def crlf_fixture(case, tools):
            files = create(case, tools)
            if os.linesep == '\n':
                files['rules.py'] = files['rules.py'].replace('\n', '\r\n')
            return files

        with patch.object(bench, 'fixture', side_effect=crlf_fixture), patch.dict(os.environ, {
                'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': 'core.autocrlf', 'GIT_CONFIG_VALUE_0': 'true'}):
            attempt = self.attempt('py-retry-recovery')
        source = attempt / 'work' / 'rules.py'
        original = subprocess.check_output(['git', 'cat-file', 'blob', 'HEAD:rules.py'], cwd=source.parent)
        self.assertIn(b'\r\n', original)
        self.assertEqual(original, source.read_bytes())

    def test_public_edit_scope_matches_artifact_protection_in_every_arm(self):
        def declared_paths(contract):
            scope = contract.split('Keep these existing paths byte-identical:\n', 1)[1]
            protected, editable = scope.split('\nExisting paths you may edit:\n', 1)
            return tuple([line[3:-1] for line in section.splitlines() if line.startswith('- `')]
                         for section in (protected, editable))

        plan = self.freeze()
        for case in plan['cases']:
            with self.subTest(case=case['id']):
                fixture = bench.fixture(case)
                protected, editable = declared_paths(fixture['CONTRACT.md'])
                self.assertCountEqual(protected + editable, fixture.keys())
                self.assertTrue({'.gitignore', 'CONTRACT.md', 'ARCHITECTURE.md', 'RUNTIME.md'} <= set(protected))
                self.assertIn('check_existing.py', editable)
                if 'Existing.csproj' in fixture:
                    self.assertIn('Existing.csproj', protected)
                    self.assertIn('Program.cs', protected)
                if 'package.json' in fixture:
                    self.assertIn('package.json', protected)
                    self.assertIn('cli.ts', editable if case['scenario'] == 'config' else protected)
                if 'PERFORMANCE.md' in fixture:
                    self.assertIn('PERFORMANCE.md', protected)
                    self.assertIn('main.cpp', protected)
                if case['scenario'] == 'cue-report':
                    self.assertEqual(editable, ['CueCoverage.cs', 'CueOrder.cs', 'check_existing.py'])
                    self.assertIn('StudioCue.cs', protected)
                    self.assertIn('Rules.cs', protected)

        for arm, mutation in zip(bench.ARMS, ('.gitignore', 'cli.py', 'CONTRACT.md')):
            with self.subTest(arm=arm):
                attempt = bench.prepare(self.experiment, 'py-retry-recovery', arm, 'weak-observed', 1)
                work = attempt / 'work'
                contract = (work / 'CONTRACT.md').read_text(encoding='utf-8')
                self.assertIn('original oracles are retained', contract)
                self.assertIn('You may add relevant tests', contract)
                self.assertIn('byte-identical paths listed in CONTRACT.md', bench.load(attempt/'attempt.json')['prompt'])
                public_protected, _ = declared_paths(contract)
                checker = work / 'check_existing.py'
                checker.write_text(checker.read_text() + '\nassert isinstance(actual["seen"], list)\n')
                (work / 'test_existing.py').write_text(
                    'from rules import evaluate\nassert evaluate(\'{"op":"redact","data":{"safe":1}}\') == \'{"safe": 1}\'\n')
                allowed = bench.evaluate_attempt(attempt)
                evidence = allowed['automated_artifact_layers']['architecture']
                self.assertEqual(evidence['status'], 'PASS')
                self.assertEqual(evidence['protected_paths'], public_protected)
                self.assertTrue(allowed['existing_tests_changed'])
                replay = next(row for row in allowed['checks'] if row['check'] == 'preservation-existing-test-replay')
                self.assertTrue(replay['passed'])

                target = work / mutation
                target.write_bytes(target.read_bytes() + b'\n')
                blocked = bench.evaluate_attempt(attempt)['automated_artifact_layers']['architecture']
                self.assertEqual(blocked['status'], 'FAIL')
                self.assertEqual(blocked['changed_protected_paths'], [mutation])

    def test_rotated_csharp_components_have_separate_runtime_oracles_and_cli(self):
        dotnet = Path(os.environ.get('HARRTEST_BENCH_DOTNET') or ROOT/'output/v5-corporate/toolchains/dotnet/dotnet.exe')
        if not dotnet.is_file():
            self.skipTest('Pinned local .NET10 SDK unavailable')
        self.fake_probe['tools']['dotnet'] = str(dotnet)
        attempt = self.attempt('cs-studio-cue-report')
        work = attempt/'work'

        def checks(result):
            return {row['check']: row['passed'] for row in result['checks']}

        baseline = bench.evaluate_attempt(attempt)
        bad = checks(baseline)
        self.assertTrue(all(value for key, value in bad.items() if key.startswith('preservation')))
        for key in ('cue-order-stable', 'cue-coverage-union', 'public-composed-report'):
            self.assertFalse(bad[key])

        # Disposable positive controls are never copied into generated fixtures.
        order = work/'CueOrder.cs'
        order.write_text(order.read_text(encoding='utf-8').replace(
            '.ThenBy(cue => cue.Id, StringComparer.Ordinal)', ''), encoding='utf-8')
        isolated = checks(bench.evaluate_attempt(attempt))
        self.assertTrue(isolated['cue-order-stable'])
        self.assertFalse(isolated['cue-coverage-union'])
        self.assertFalse(isolated['public-composed-report'])
        (work/'CueCoverage.cs').write_text('''public static class CueCoverage
{
    public static long TotalMilliseconds(IReadOnlyList<StudioCue> cues)
    {
        long total = 0, end = 0;
        foreach (var cue in cues.OrderBy(cue => cue.StartMs))
        {
            if (cue.EndMs <= end) continue;
            total += cue.EndMs - Math.Max(end, cue.StartMs);
            end = cue.EndMs;
        }
        return total;
    }
}
''', encoding='utf-8')
        fixed = bench.evaluate_attempt(attempt)
        self.assertTrue(fixed['automated_artifact_passed'])
        self.assertTrue(all(checks(fixed).values()))
        self.assertTrue(fixed['unchanged_by_evaluator'])

    @unittest.skipUnless(shutil.which('node'), 'Node required for TypeScript runtime')
    def test_rotated_typescript_runtime_preserves_positional_and_sdk_results(self):
        if not self.fake_probe['tools'].get('tsc'):
            self.skipTest('Pinned TypeScript compiler unavailable')
        attempt = self.attempt('ts-tile-window')
        baseline = bench.evaluate_attempt(attempt)
        checks = {row['check']: row['passed'] for row in baseline['checks']}
        self.assertEqual(baseline['type_correctness'], 'PASS')
        self.assertTrue(all(value for key, value in checks.items() if key.startswith('preservation')))
        self.assertFalse(checks['target-sdk-0'])
        self.assertFalse(checks['target-cli-0'])
        core = attempt/'work'/'rules.ts'
        old = core.read_text(encoding='utf-8')
        core.write_text(old.replace(
            'rows.slice(top, top + height).flatMap(row => row.slice(left, left + width))',
            'rows.slice(top, Math.max(top, y + height)).flatMap(row => row.slice(left, Math.max(left, x + width)))'),
            encoding='utf-8')
        fixed = bench.evaluate_attempt(attempt)
        self.assertTrue(fixed['automated_artifact_passed'])
        self.assertTrue(fixed['unchanged_by_evaluator'])

    def test_rotated_python_runtime_checks_exact_output_and_preserves_original_oracle(self):
        attempt = self.attempt('py-recipe-batch-scale')
        baseline = bench.evaluate_attempt(attempt)
        checks = {row['check']: row['passed'] for row in baseline['checks']}
        self.assertTrue(all(value for key, value in checks.items() if key.startswith('preservation')))
        self.assertFalse(checks['target-sdk-0'])
        self.assertFalse(checks['target-cli-0'])
        core = attempt/'work'/'rules.py'
        old = core.read_text(encoding='utf-8')
        core.write_text(old.replace("row['units'] * target // source",
            "((row['units'] * target + source * row['step'] - 1) // (source * row['step'])) * row['step']"),
            encoding='utf-8')
        fixed = bench.evaluate_attempt(attempt)
        self.assertTrue(fixed['automated_artifact_passed'])
        self.assertTrue(fixed['unchanged_by_evaluator'])
        self.assertFalse(fixed['existing_tests_changed'])

    def test_rotated_python_shortest_path_oracle_preserves_neighbor_order(self):
        attempt = self.attempt('py-museum-route')
        baseline = bench.evaluate_attempt(attempt)
        checks = {row['check']: row['passed'] for row in baseline['checks']}
        self.assertTrue(all(passed for name, passed in checks.items() if name.startswith('preservation')))
        self.assertFalse(checks['target-sdk-0'])
        self.assertFalse(checks['target-cli-2'])
        core = attempt/'work'/'rules.py'
        source = core.read_text(encoding='utf-8')
        implementation = '''def find_route(galleries, current, goal, path):
    frontier = [path]
    visited = {current}
    while frontier:
        route = frontier.pop(0)
        if route[-1] == goal:
            return route
        for neighbor in galleries[route[-1]]:
            if neighbor not in visited:
                visited.add(neighbor)
                frontier.append([*route, neighbor])
    return []


'''
        fixed_source = source[:source.index('def find_route')] + implementation + source[source.index('def evaluate'):]
        core.write_text(fixed_source.replace('in galleries[route[-1]]:', 'in sorted(galleries[route[-1]]):'),
                        encoding='utf-8')
        partial = bench.evaluate_attempt(attempt)
        self.assertFalse(partial['functional_passed'])
        self.assertEqual({row['check'] for row in partial['checks'] if not row['passed']},
                         {'target-sdk-1', 'target-cli-1'})
        core.write_text(fixed_source, encoding='utf-8')
        fixed = bench.evaluate_attempt(attempt)
        self.assertTrue(fixed['automated_artifact_passed'])
        self.assertTrue(fixed['unchanged_by_evaluator'])
        self.assertFalse(fixed['existing_tests_changed'])

    def test_room_schedule_rejections_and_recovery_use_real_sdk_and_cli(self):
        dotnet = Path(os.environ.get('HARRTEST_BENCH_DOTNET') or ROOT/'output/v5-corporate/toolchains/dotnet/dotnet.exe')
        if not dotnet.is_file():
            self.skipTest('Pinned .NET 10 SDK unavailable')
        self.fake_probe['tools']['dotnet'] = str(dotnet)
        attempt = self.attempt('cs-room-schedule-recovery')
        baseline = bench.evaluate_attempt(attempt)
        checks = {row['check']: row for row in baseline['checks']}
        self.assertTrue(all(row['passed'] for label, row in checks.items() if label.startswith('preservation')))
        for boundary, binary in [('sdk', 'Evaluator.dll'), ('cli', 'Existing.dll')]:
            control = checks[f'target-{boundary}-0']
            self.assertEqual(control['execution']['exit_code'], 0)
            self.assertEqual(Path(control['execution']['argv'][1]).name, binary)
            self.assertFalse(control['passed'])
        self.assertEqual(baseline['automated_artifact_layers']['resilience']['status'], 'FAIL')

        # A synthetic minute-occupancy implementation, not a held generation.
        core = attempt / 'work/Rules.cs'
        source = core.read_text(encoding='utf-8')
        fixed = source[:source.index('        var accepted')] + '''        var accepted = new List<string>();
        var rejected = new List<object>();
        var occupied = new HashSet<int>();
        foreach (var request in requests.EnumerateArray())
        {
            string id = request.GetProperty("id").GetString()!;
            int start = request.GetProperty("start_min").GetInt32();
            int end = request.GetProperty("end_min").GetInt32();
            if (start < 0 || end > 1440 || start >= end)
            {
                rejected.Add(new { id, error = "invalid_window" });
                continue;
            }
            var minutes = Enumerable.Range(start, end - start);
            if (minutes.Any(occupied.Contains))
            {
                rejected.Add(new { id, error = "overlap" });
                continue;
            }
            occupied.UnionWith(minutes);
            accepted.Add(id);
        }
        return JsonSerializer.Serialize(new { accepted, rejected });
    }
}
'''
        core.write_text(fixed, encoding='utf-8')
        passing = bench.evaluate_attempt(attempt)
        self.assertTrue(passing['automated_artifact_passed'])
        self.assertEqual(passing['automated_artifact_layers']['resilience']['status'], 'PASS')
        self.assertFalse(passing['complete_quality_passed'])

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

    def test_checkpoint_publish_checks_typed_failure_and_disk_across_processes(self):
        attempt = self.attempt('py-checkpoint-publish-recovery')
        baseline = bench.evaluate_attempt(attempt)
        checks = {row['check']: row for row in baseline['checks']}
        self.assertTrue(all(row['passed'] for label, row in checks.items() if label.startswith('preservation')))
        fault = checks['publish-interrupted']
        self.assertEqual(fault['observed'], 'RUNTIME_ERROR')
        self.assertNotEqual(fault['input_file_sha256_before'], fault['input_file_sha256_after'])
        self.assertNotEqual(fault['persisted_expected'], fault['persisted_observed'])
        self.assertFalse(fault['passed'])
        self.assertFalse(checks['publish-interrupted-empty']['passed'])
        self.assertFalse(checks['publish-empty']['passed'])
        self.assertEqual(baseline['automated_artifact_layers']['resilience']['status'], 'FAIL')

        report = self.timeout_review(attempt, result=baseline)
        review = bench.load(report)
        resilience = next(row for row in review['layers'] if row['id'] == 'resilience')
        for verdict, error in [('NOT_APPLICABLE', 'layers are required'), ('PASS', 'recovery controls cannot become PASS')]:
            with self.subTest(verdict=verdict):
                resilience['status'] = verdict
                bench.save(report, review)
                with self.assertRaisesRegex(ValueError, error):
                    bench.record_assessment(attempt, report)

        core = attempt / 'work/rules.py'
        original = core.read_text(encoding='utf-8')
        trigger = ("        if request.get('fail_before_publish', False):\n"
                   "            raise RuntimeError('injected interruption')\n")
        promotion = "        state['published'] = state['pending']\n"
        fixed = original.replace("if not state['pending']:", "if state['pending'] is None:")
        fixed = fixed.replace(trigger, '').replace(promotion, trigger + promotion)

        # Correct exception and semantic state alone must not excuse rewriting the store.
        rewriting = fixed.replace("            raise RuntimeError",
            "            store.write_text(json.dumps(state, sort_keys=True), encoding='utf-8')\n"
            "            raise RuntimeError")
        core.write_text(rewriting, encoding='utf-8')
        partial = {row['check']: row for row in bench.evaluate_attempt(attempt)['checks']}
        self.assertEqual(partial['publish-interrupted']['persisted_observed'], fault['persisted_expected'])
        self.assertFalse(partial['publish-interrupted']['passed'])
        self.assertTrue(partial['publish-recovery']['passed'])

        core.write_text(fixed, encoding='utf-8')
        passing = bench.evaluate_attempt(attempt)
        checks = {row['check']: row for row in passing['checks']}
        self.assertTrue(passing['automated_artifact_passed'])
        self.assertFalse(passing['complete_quality_passed'])
        self.assertEqual(checks['publish-recovery']['input_file_sha256_before'],
                         checks['publish-interrupted']['input_file_sha256_after'])
        self.assertEqual(checks['publish-replay-no-pending']['input_file_sha256_before'],
                         checks['publish-recovery']['persisted_sha256'])

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

    @unittest.skipUnless(shutil.which('node'), 'Node required for TypeScript runtime')
    def test_pick_list_separates_merge_package_arithmetic_and_public_composition(self):
        if not self.fake_probe['tools'].get('tsc'):
            self.skipTest('Pinned TypeScript compiler unavailable')
        attempt = self.attempt('ts-pick-list')
        work = attempt / 'work'
        merge_check, pack_check = 'pick-merge-exact-keys-and-order', 'pick-packages-round-up-with-unused-units'
        public = 'public-composed-report'

        def verify(expected):
            result = bench.evaluate_attempt(attempt)
            checks = {row['check']: row['passed'] for row in result['checks']}
            self.assertEqual(result['type_correctness'], 'PASS', str(result['builds']))
            self.assertTrue(all(passed for label, passed in checks.items() if label.startswith('preservation')))
            self.assertEqual(tuple(checks[label] for label in (merge_check, pack_check, public)), expected)
            return result

        verify((False, False, False))
        merge = work / 'merge.ts'
        original_merge = merge.read_text(encoding='utf-8')
        merge_control = original_merge.replace('  return lines.map(line => ({...line}));',
            '  const merged: PickLine[] = [];\n'
            '  for (const line of lines) {\n'
            '    if (!line.units) continue;\n'
            '    const previous = merged.find(row => row.zone === line.zone && row.sku === line.sku'
            ' && row.packSize === line.packSize);\n'
            '    if (previous) previous.units += line.units;\n'
            '    else merged.push({...line});\n'
            '  }\n  return merged;')
        merge.write_text(merge_control, encoding='utf-8')
        verify((True, False, False))
        merge.write_text(original_merge, encoding='utf-8')
        packs = work / 'packages.ts'
        packs.write_text(packs.read_text(encoding='utf-8').replace('Math.floor', 'Math.ceil'), encoding='utf-8')
        verify((False, True, False))
        merge.write_text(merge_control, encoding='utf-8')
        self.assertTrue(verify((True, True, True))['automated_artifact_passed'])

    def use_cpp_toolchain(self):
        configured = self.configured_tools.get('cxx')
        setup = self.configured_tools.get('msvc_env')
        if configured and Path(configured[0]).is_file() and (not setup or Path(setup).is_file()):
            self.fake_probe['tools']['cxx'] = configured
            if setup:
                self.fake_probe['tools']['msvc_env'] = setup
            return
        if sys.platform!='win32':
            compiler=shutil.which('clang++') or shutil.which('g++')
            if not compiler:self.skipTest('C++ compiler unavailable')
            self.fake_probe['tools']['cxx']=[compiler]
        else:
            compiler=Path('C:/Program Files (x86)/Microsoft Visual Studio/2022/BuildTools/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/cl.exe')
            setup=Path('C:/Program Files (x86)/Microsoft Visual Studio/2022/BuildTools/VC/Auxiliary/Build/vcvars64.bat')
            if not compiler.is_file() or not setup.is_file():self.skipTest('MSVC toolchain unavailable')
            self.fake_probe['tools']['cxx']=[str(compiler)];self.fake_probe['tools']['msvc_env']=str(setup)

    def test_cpp_actual_compiler_negative_and_positive_controls(self):
        self.use_cpp_toolchain()
        p=self.attempt('cpp-index-validation')
        bad=bench.evaluate_attempt(p)
        self.assertTrue(all(x['exit_code']==0 for x in bad['builds']),str(bad['builds']))
        self.assertFalse(bad['functional_passed'])
        core=p/'work/rules.hpp';text=core.read_text().replace('std::vector<int> v{10,20,30}; return', 'std::vector<int> v{10,20,30}; if(index<0 || index>=static_cast<long long>(v.size())) throw std::out_of_range("index"); return')
        core.write_text(text)
        good=bench.evaluate_attempt(p)
        self.assertTrue(good['functional_passed'],str(good['builds']))

    def test_cpp_range_count_compiles_and_pairs_the_same_executable_and_workload(self):
        self.use_cpp_toolchain()
        attempt = self.attempt('cpp-range-count-scaling')
        core = attempt / 'work/rules.hpp'
        original = core.read_text(encoding='utf-8')
        scan = '''        auto matches = std::count_if(keys.begin(), keys.end(), [&](int key) {
            return low <= key && key <= high;
        });'''
        self.assertIn(scan, original)
        core.write_text(original.replace(scan,
            '''        auto first = std::lower_bound(keys.begin(), keys.end(), low);
        auto matches = std::upper_bound(first, keys.end(), high) - first;'''), encoding='utf-8')

        # Compile and run ordinary/small controls for real; no large workload is executed here.
        workload = 'range_count 30000 20000 20731'
        public_target = (attempt / 'work/PERFORMANCE.md').read_text(encoding='utf-8')
        self.assertIn('`range_count 30000 20000 SEED`', public_target)
        self.assertNotIn(workload, public_target)
        expected = dict(bench.range_count_vectors()[1])[workload]
        real_command = bench.command
        workload_commands = []

        def synthetic_large_workload(argv, cwd, timeout=120, *, env=None):
            operation = str(argv[-1])
            if operation.startswith('range_count '):
                _, count, queries, _ = operation.split()
                if max(int(count), int(queries)) > 100:
                    self.assertEqual(operation, workload)
                    role = Path(argv[0]).parent.name
                    self.assertIn(role, {'baseline-build', 'build'})
                    workload_commands.append((role, list(map(str, argv)), cwd))
                    return {'argv': list(map(str, argv)), 'stdout': expected + '\n', 'stderr': '',
                            'exit_code': 0, 'timed_out': False, 'seconds': 2.0 if role == 'baseline-build' else 1.4}
            return real_command(argv, cwd, timeout, env=env)

        with patch.object(bench, 'command', side_effect=synthetic_large_workload):
            result = bench.evaluate_attempt(attempt)
        self.assertTrue(result['automated_artifact_passed'], str(result['builds']))
        self.assertFalse(result['complete_quality_passed'])
        checks = {row.get('input'): row for row in result['checks']}
        self.assertEqual(checks['range_count 7 11 0']['execution']['stdout'], '32,208\n')
        self.assertEqual(checks['range_count 37 23 4294967295']['execution']['stdout'], '376,4681\n')
        self.assertEqual(len(workload_commands), 13)  # one correctness probe plus 2 * (warmup + 5)
        for role, argv, cwd in workload_commands:
            argv0 = (checks[workload]['execution']['argv'][0] if role == 'build'
                     else result['performance']['baseline'][0]['argv'][0])
            self.assertEqual(argv, [argv0, workload])
            self.assertEqual(str(cwd), result['evidence_directory'])
        self.assertEqual(result['performance']['maximum_ratio'], 0.70)
        self.assertEqual(result['performance']['median_ratio'], 0.70)

        path = self.timeout_review(attempt, result=result)
        review = bench.load(path)
        next(row for row in review['layers'] if row['id'] == 'performance')['status'] = 'NOT_APPLICABLE'
        bench.save(path, review)
        with self.assertRaisesRegex(ValueError, 'layers are required'):
            bench.record_assessment(attempt, path)

    def test_paired_cpp_controls_reject_fast_wrong_output_and_failed_warmups(self):
        # Cover both the current held case and the consumed scaling case with synthetic receipts.
        for workload in ['lookup 30000 20000', 'range_count 30000 20000 20731']:
            for defect in [None, 'slow', 'wrong-candidate', 'wrong-baseline', 'timeout-warmup']:
                with self.subTest(workload=workload, defect=defect):
                    times = {'baseline': [0.01, 2, 2, 2, 2, 2],
                             'candidate': [10, 1, 1.3, 1.41 if defect == 'slow' else 1.4, 1.5, 1.6]}
                    seen = []

                    def run(argv, cwd, timeout):
                        role = argv[0]
                        self.assertEqual(argv, [role, workload])
                        self.assertEqual(cwd, self.root)
                        ordinal = seen.count(role)
                        seen.append(role)
                        output = {('wrong-candidate', 'candidate', 2): 'incorrect\n',
                                  ('wrong-baseline', 'baseline', 3): 'expected\n\n'}.get((defect, role, ordinal), 'expected\n')
                        timed_out = defect == 'timeout-warmup' and role == 'candidate' and ordinal == 0
                        return {'argv': argv, 'stdout': output,
                                'exit_code': None if timed_out else 0, 'timed_out': timed_out,
                                'seconds': times[role][ordinal]}

                    with patch.object(bench, 'command', side_effect=run):
                        measured = bench.measure_paired(['baseline'], ['candidate'], workload, 'expected', 0.70, self.root)
                    self.assertEqual(seen, ['baseline', 'candidate']
                                     + ['baseline', 'candidate', 'candidate', 'baseline'] * 2
                                     + ['baseline', 'candidate'])
                    self.assertEqual([len(measured[role]) for role in ('baseline', 'candidate')], [5, 5])
                    self.assertEqual(measured['warmups']['candidate']['seconds'], 10)
                    self.assertEqual(measured['status'], 'PASS' if defect is None else 'FAIL')
                    self.assertEqual(measured['median_ratio'],
                                     {None: 0.70, 'slow': 1.41 / 2}.get(defect))

    def timeout_review(self, attempt, status='TIMEOUT', *, result=None):
        if result is None:
            result = bench.evaluate_attempt(attempt)
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
        p=self.summary_attempt();review=self.timeout_review(p)
        assessment=bench.record_assessment(p,review)
        self.assertFalse(assessment['complete_quality_passed'])
        self.assertFalse(assessment['false_accept'])
        summary=bench.summarize(self.experiment)
        observed=next(row for row in summary['attempts'] if row['status']=='TIMEOUT')
        self.assertEqual(observed['case'],bench.load(p/'attempt.json')['case']['id'])
        self.assertEqual(observed['completion_claim'],'INCOMPLETE')
        counts=summary['counts']['plain']
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
        p=self.summary_attempt();review=self.timeout_review(p)
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
        attempt = self.summary_attempt()
        report = self.timeout_review(attempt)
        review = bench.load(report)
        for row in review['layers']:
            if row['id'] in ('preservation', 'architecture', 'security'):
                row['status'] = 'FAIL'
        bench.save(report, review)
        usage_path = attempt / 'usage.json'
        model = bench.load(attempt / 'attempt.json')['model']
        usage = {'aiCreditsStatus': 'complete', 'totalNanoAiu': 1_500_000_000,
                 'agentMetrics': {'main': {'totalNanoAiu': 1_000_000_000}, 'child': {'totalNanoAiu': 500_000_000}},
                 'modelMetrics': {model: {'totalNanoAiu': 1_500_000_000}}}
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
