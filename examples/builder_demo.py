#!/usr/bin/env python3
"""Scripted greenfield acceptance of the generic builder on a real local HTTP API.

The author supplies the architecture/patches; no autonomous model performance is
claimed. Fresh subprocesses drive the same host-facing coordinator CLI as an agent.
"""
from __future__ import annotations
import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import proof
import builder
import root_gate


def run_demo(project):
    start = time.monotonic()
    project = Path(project).resolve(); project.mkdir(parents=True, exist_ok=False)
    request = 'Create and list tasks through a real HTTP API. Preserve valid tasks across process restarts and reject invalid input. Deliver a runnable package tested from a clean directory.'
    input_file = project.parent / (project.name + '-original-request.txt')
    with input_file.open('x', encoding='utf-8') as handle: handle.write(request)
    intake = builder.bootstrap(project, 'mission', input_file)
    assert intake['created'] and list(p.name for p in project.iterdir()) == ['.runtime-proof']
    # Minimal scaffold is setup, not acceptance. The host normally authors these files.
    (project / 'server.py').write_text('raise SystemExit("Unimplemented scaffold")\n', encoding='utf-8')
    (project / 'probe.py').write_bytes((ROOT / 'examples/builder_probe.py').read_bytes())
    (project / 'API.md').write_text('POST /items {title:string} -> 201 {id:int,title:string}; GET /items -> {items:list}; invalid title -> 400. Saved items must survive restart.\n', encoding='utf-8')
    goal = project / intake['goal']
    phases = [('slice', 'Create and list tasks through a real HTTP API'),
              ('persistence', 'Preserve valid tasks across process restarts and reject invalid input'),
              ('delivery', 'Deliver a runnable package tested from a clean directory')]
    contract = {'schema': 2, 'goal_id': 'mission', 'request_sha256': intake['request_sha256'],
                'scope_statement': 'All three parts of the fixed HTTP service request, including persistence and packaged execution.',
                'coverage_review': {'method': 'same-agent', 'rationale': 'This is a deterministic authored example, not a pretend independent LLM review. Each request sentence maps to its actual HTTP check.', 'unmapped_segments': []},
                'requirements': [{'id': 'ROOT_' + name.upper(), 'claim': phrase, 'oracle': 'Independent literal JSON and HTTP status assertions on separate server processes.',
                                  'source': 'user_request', 'source_excerpt': phrase, 'evidence_mode': 'live',
                                  'satisfiers': [{'task_id': name, 'requirement_id': 'R01'}]} for name, phrase in phases],
                'integration': {'task_id': 'delivery', 'requirement_id': 'R01', 'scope': 'Real clean-install package API, invalid input and restart persistence.'}}
    root_gate.validate(project, goal, contract)
    proof.save(goal / 'root-contract.json', contract)
    proof.save(goal / 'root-seal.json', {'root_hash': proof.digest(contract), 'request_sha256': contract['request_sha256'], 'sealed_at': proof.now()})
    for name, phrase in phases:
        child = project / '.runtime-proof' / name; child.mkdir()
        c = proof.load(ROOT / 'examples/cli-contract.json')
        c.update(task_id=name, kind='api', goal=phrase, source_paths=['server.py', 'probe.py', 'API.md'])
        c['requirements'][0].update(claim=phrase, oracle='Literal expected task and status assertions from the HTTP probe, not a server success flag.',
                                   failure_example='POST succeeds but GET after process restart loses the saved task.',
                                   checks=['http'], negative_control_exception='The demonstration retains a failed real restart attempt before implementing persistence; this is fixture acceptance, not a product certificate.')
        c['checks'] = [{'id': 'http', 'description': phrase, 'mode': 'live', 'role': 'acceptance',
                        'command': ['{python}', '-S', 'probe.py', name], 'timeout_seconds': 60, 'expected_exit_codes': [0],
                        'assertions': [{'type': 'json', 'file': 'observed.json', 'pointer': '/passed', 'op': 'eq', 'value': True},
                                       {'type': 'json', 'file': 'observed.json', 'pointer': '/phase', 'op': 'eq', 'value': name}],
                        'artifacts': [{'glob': 'observed.json', 'min_count': 1, 'min_bytes': 100},
                                      {'glob': 'server-*.log', 'min_count': 1, 'min_bytes': 10}]}]
        c['plan']['tasks'][0]['checks'] = ['http']
        proof.validate_contract(c); proof.save(child / 'contract.json', c); proof.save(child / 'context.json', {'project': str(project), 'root_goal': 'mission'})
        proof.save(child / 'seal.json', {'contract_hash': proof.digest(c), 'engine_hash': proof.engine_hash(c)})
    spec = {'schema': 1, 'goal_id': 'mission', 'root_goal': intake['goal'], 'tasks': [
                {'id': name, 'role': 'integrate', 'outcome': phrase, 'proof_task': '.runtime-proof/' + name,
                 'depends_on': [] if i == 0 else [phases[i-1][0]], 'write_scope': ['server.py'] if i < 2 else [],
                 'read_scope': ['probe.py', 'API.md'], 'resources': ['demo-server'], 'context_files': ['API.md']}
                for i, (name, phrase) in enumerate(phases)],
            'build': {'mode': 'greenfield', 'architecture': {'runtime': 'Local Python HTTP processes', 'selected_stack': 'Python standard library and JSON file persistence',
                        'rationale': 'Bounded local demonstration needs no additional dependency or paid service.',
                        'deliverable': 'ZIP with service executable and API contract', 'constraints': ['Loopback only; no paid models or production data'],
                        'alternatives': [{'option': 'Web framework and remote database', 'tradeoff': 'Unnecessary setup and external credentials for this fixture'}]},
                'host': {'delegation_available': False, 'stronger_model_available': False, 'max_parallel_workers': 1,
                         'evidence': 'Actual local Python subprocesses; no LLM or native host subagents in this demonstration'},
                'interfaces': [{'id': 'TASK_API', 'producer': 'slice', 'consumers': ['persistence', 'delivery'], 'contract_file': 'API.md'}],
                'risks': [{'failure': 'App acknowledges writes without persistence', 'probe': 'Stop and restart an actual HTTP process and read back data', 'milestone': 'M2'}],
                'milestones': [{'id': 'M' + str(i+1), 'kind': ['vertical_slice', 'increment', 'delivery'][i], 'outcome': phrase,
                                'tasks': [name], 'requirements': ['ROOT_' + name.upper()], 'depends_on': [] if i == 0 else ['M' + str(i)],
                                'integration_task': name} for i, (name, phrase) in enumerate(phases)]}}
    plan_path = project / '.runtime-proof/build-plan.json'; proof.save(plan_path, spec)
    env = os.environ.copy(); env['HARRTEST_STATE_HOME'] = str(project.parent / (project.name + '-private-memory'))
    command_count = 0
    def cmd(command, *args, expected=0):
        nonlocal command_count
        argv = [sys.executable, '-S', '-B', str(ROOT / 'scripts/builder.py'), '--project', str(project), command, *args]
        run = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=30); command_count += 1
        with (project / '.runtime-proof/builder-transcript.log').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(argv) + '\n' + ('[private claim packet omitted]\n' if command == 'claim' else run.stdout) + run.stderr)
        if run.returncode != expected: raise AssertionError(f'{command}: {run.returncode} {run.stdout} {run.stderr}')
        return json.loads(run.stdout)
    def check(tid, passed=True):
        with contextlib.redirect_stdout(io.StringIO()): actual = proof.run_check(project / '.runtime-proof' / tid, 'http')
        assert actual['passed'] is passed, actual
        if passed: proof.update_step(project / '.runtime-proof' / tid, 'T01', 'VERIFIED', 'Actual HTTP statuses and returned tasks inspected through independent requests.')
        return actual
    def finish(tid, token):
        store, saved, shape = builder.open_build(project, 'mission')
        path = project / '.runtime-proof' / tid / 'handoff.txt'
        path.write_text('Actual HTTP child observed and independently asserted; raw server and request receipts retained.', encoding='utf-8')
        store.handoff('mission', tid, token, builder.workflow.artifact(project, path.relative_to(project).as_posix()))
        assert store.verify('mission', tid, lambda n: proof.verify(project / n['proof_task']))['passed']
    cmd('init', '--plan', str(plan_path))
    first = cmd('claim', '--goal', 'mission', '--task', 'slice', '--worker', 'real-local-fixture-process', '--lease-seconds', '180')
    (project / 'server.py').write_text((ROOT / 'examples/builder_service.py').read_text().replace('PERSIST = True', 'PERSIST = False'), encoding='utf-8')
    check('slice'); finish('slice', first['token'])
    m1 = cmd('gate', '--goal', 'mission', '--milestone', 'M1')
    assert m1['passed'] and not m1['root_goal_achieved']
    resumed = cmd('next', '--goal', 'mission'); assert resumed['milestone'] == 'M2'
    second = cmd('claim', '--goal', 'mission', '--task', 'persistence', '--worker', 'real-local-fixture-process', '--lease-seconds', '180')
    bad = check('persistence', passed=False)
    bad_run = project / '.runtime-proof/persistence' / proof.load(project / '.runtime-proof/persistence/latest/http.json')['run']
    assert 'Restart lost persisted data' in (bad_run / 'stderr.log').read_text(encoding='utf-8')
    (project / 'server.py').write_bytes((ROOT / 'examples/builder_service.py').read_bytes())
    check('persistence'); finish('persistence', second['token'])
    # New implementation passed, but its change invalidates earlier current-source proof.
    rejected = cmd('gate', '--goal', 'mission', '--milestone', 'M2', expected=1)
    assert not rejected['passed']
    queue = cmd('checks', '--goal', 'mission', '--milestone', 'M2')
    assert [r['task'] for r in queue['run_only_missing_failed_or_stale']] == ['slice']
    check('slice')
    assert cmd('gate', '--goal', 'mission', '--milestone', 'M2')['passed']
    third = cmd('claim', '--goal', 'mission', '--task', 'delivery', '--worker', 'real-local-fixture-process', '--lease-seconds', '180')
    check('delivery'); finish('delivery', third['token'])
    root = cmd('gate', '--goal', 'mission', '--milestone', 'M3'); assert root['root_goal_achieved']
    fresh = cmd('checks', '--goal', 'mission', '--milestone', 'M3')
    assert not fresh['run_only_missing_failed_or_stale'] and len(fresh['reuse_current_checks']) == 3
    assert cmd('next', '--goal', 'mission')['action'] == 'DELIVER'
    original = (project / 'server.py').read_bytes(); (project / 'server.py').write_bytes(original + b'\n# relevant change after acceptance\n')
    assert not cmd('gate', '--goal', 'mission', '--milestone', 'M3', expected=1)['root_goal_achieved']
    (project / 'server.py').write_bytes(original)
    report = {'status': 'REAL_HTTP_FIXTURE_PASSED', 'greenfield_intake_preserved': True,
              'three_running_milestones': True, 'persistence_failure_reproduced': True,
              'earlier_regression_gate_enforced': True, 'clean_package_executed': True,
              'resume_selected_next_milestone': True, 'fresh_checks_reused': 3,
              'stale_final_source_rejected': True, 'root_goal_verified': True,
              'coordinator_process_invocations': command_count, 'paid_model_calls': 0,
              'elapsed_seconds': round(time.monotonic() - start, 3),
              'scope': 'Scripted actual local HTTP/process/packaging test; architecture and patches authored in fixture. Not autonomous LLM/Copilot/CARLA acceptance.'}
    proof.save(project / 'demo-result.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); print(json.dumps(run_demo(args.output), indent=2))
