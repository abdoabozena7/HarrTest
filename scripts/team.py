#!/usr/bin/env python3
"""Seal production scopes and verify native Codex implementation handoffs."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from uuid import UUID, uuid4

import proof
import strict_io

WORKER_NAME = re.compile(r'[a-z][a-z0-9_]{0,47}')
PATCH_PATH = re.compile(r'^\*\*\* (?:Add|Update|Delete|Move to) (?:File: )?([^\r\n]+)', re.M)
EXEC_PATCH = re.compile(r'\A\s*(?:const\s+([A-Za-z_$][\w$]*)\s*=\s*|text\s*\(\s*)'
                        r'await\s+tools\.apply_patch\s*\(\s*')
RECEIPT = 'HARRTEST_TEAM_RECEIPT '
MAX_ROLLOUT_BYTES = 32 * 1024 * 1024


def require(test, message):
    if not test:
        raise ValueError(message)


def product_key(path):
    value = path.replace('\\', '/')
    return value.casefold() if os.name == 'nt' else value


def name(value):
    require(isinstance(value, str) and WORKER_NAME.fullmatch(value),
            'Use a native worker name such as data_model')
    return value


def team_path(project, team_id, suffix='state.json', *, must_exist=True):
    proof.identifier(team_id, 'production team ID')
    return strict_io.scoped_path(project, f'{proof.STATE}/teams/{team_id}/{suffix}',
                                 must_exist=must_exist)


def concrete(value, label):
    proof.meaningful(value, label)
    require(len(value) <= 8000, f'{label} is too long for a focused packet')


def file_list(project, values, label):
    require(isinstance(values, list) and values, f'{label} needs explicit product files')
    for rel in values:
        path = strict_io.scoped_path(project, rel, must_exist=False)
        key = strict_io.scope_key(rel)
        require(not path.is_dir() and key.split('/')[0] not in {'.git', proof.STATE},
                f'{label}: {rel} is not a product file')
    return values


def ancestors(tasks):
    visited = {}

    def visit(task, trail):
        require(task in tasks, f'Unknown worker dependency: {task}')
        require(task not in trail, f'Worker dependency cycle: {task}')
        if task not in visited:
            direct = set(tasks[task]['depends_on'])
            visited[task] = direct | set().union(*(visit(dep, trail | {task}) for dep in direct))
        return visited[task]

    for task in tasks:
        visit(task, set())
    return visited


def validate_plan(project, plan):
    require(isinstance(plan, dict) and type(plan.get('schema')) is int and plan['schema'] == 1,
            'Expected a schema-1 production team plan')
    proof.identifier(plan.get('id'), 'production team ID')
    require(plan.get('kind') in ('greenfield', 'change'), 'Choose greenfield or change')
    concrete(plan.get('request'), 'Original request')
    concrete(plan.get('contract'), 'Shared interface and integration contract')
    outcomes = plan.get('outcomes')
    require(isinstance(outcomes, dict) and outcomes, 'Preserve observable original outcomes')
    for rid, acceptance in outcomes.items():
        proof.identifier(rid, 'outcome ID')
        concrete(acceptance, f'{rid} acceptance')
    rows = plan.get('tasks')
    require(isinstance(rows, list) and len(rows) >= 2,
            'A production team needs at least two implementation scopes')
    tasks, covered, owned = {}, set(), []
    for row in rows:
        require(isinstance(row, dict), 'Invalid production task')
        tid = name(row.get('id'))
        require(tid not in tasks and tid not in {'qa', 'check', 'integration'}, f'Reserved or duplicate worker: {tid}')
        require(row.get('role', 'implement') == 'implement', 'Team tasks must own implementation')
        concrete(row.get('brief'), f'{tid} brief')
        output = file_list(project, row.get('outputs'), tid)
        deps = row.get('depends_on')
        require(isinstance(deps, list) and all(isinstance(x, str) for x in deps)
                and len(set(deps)) == len(deps), f'{tid}: invalid dependencies')
        refs = row.get('outcomes')
        require(isinstance(refs, list) and refs and all(isinstance(x, str) and x in outcomes for x in refs),
                f'{tid}: link original outcome IDs')
        tasks[tid] = row
        covered.update(refs)
        owned.extend(output)
    require(covered == set(outcomes), 'Every original outcome needs a contributing implementation task')
    integration = plan.get('integration')
    require(isinstance(integration, dict), 'Specify the coordinator integration output and test')
    concrete(integration.get('check'), 'Integrated acceptance check')
    owned.extend(file_list(project, integration.get('outputs'), 'integration'))
    require(not any(strict_io.overlaps(a, b) for i, a in enumerate(owned) for b in owned[i+1:]),
            'Each product file needs one owner; scopes overlap')
    parents = ancestors(tasks)
    require(any(a not in parents[b] and b not in parents[a]
                for i, a in enumerate(tasks) for b in list(tasks)[i+1:]),
            'The team has no independently schedulable implementation pair')
    return tasks, owned


def snapshot(project, paths):
    result = {}
    for rel in paths:
        path = strict_io.scoped_path(project, rel, must_exist=False)
        require(not path.exists() or path.is_file(), f'{rel} is not a regular file')
        result[rel] = proof.file_hash(path) if path.is_file() else None
    return result


def init(project, plan):
    tasks, owned = validate_plan(project, plan)
    baseline = snapshot(project, owned)
    if plan['kind'] == 'greenfield':
        require(not any(baseline.values()), 'Seal a greenfield plan before creating its product files')
    state = {'plan': plan, 'plan_sha256': strict_io.digest(plan), 'baseline': baseline, 'created': proof.now()}
    proof.save(team_path(project, plan['id'], must_exist=False), state, exclusive=True)
    return {'team': plan['id'], 'plan_sha256': state['plan_sha256'],
            'ready': [packet(project, state, row) for row in tasks.values() if not row['depends_on']]}


def load_state(project, team_id):
    state = proof.load(team_path(project, team_id))
    plan = state['plan']
    _, owned = validate_plan(project, plan)
    require(plan['id'] == team_id and strict_io.digest(plan) == state['plan_sha256'],
            'Sealed production plan changed')
    require(set(owned) == set(state['baseline']), 'Production baseline does not cover all owners')
    return state


def binding(project, team_id, request_sha256):
    state = load_state(project, team_id)
    plan = state['plan']
    # Root request snapshots may use native Windows line endings.
    request = plan['request'].replace('\r\n', '\n')
    digests = {hashlib.sha256(text.encode('utf-8')).hexdigest()
               for text in (request, request.replace('\n', '\r\n'))}
    require(request_sha256 in digests, 'Production team is for a different original request')
    tasks = {row['id']: {key: row[key] for key in ('outputs', 'depends_on')} for row in plan['tasks']}
    return {'plan_sha256': state['plan_sha256'], 'tasks': tasks,
            'integration_outputs': [*plan['integration']['outputs'],
                                    *(rel for row in plan['tasks'] for rel in row['outputs'])]}


def worker_command(project, team_id, command):
    return f'python -B "{Path(__file__).resolve().as_posix()}" --project "{Path(project).resolve().as_posix()}" {command} --team {team_id}'


def packet(project, state, task):
    plan = state['plan']
    tid = task['id']
    outcomes = '\n'.join(f'- {rid}: {plan["outcomes"][rid]}' for rid in task['outcomes'])
    command = worker_command(project, plan['id'], 'handoff') + ' --task ' + tid
    message = (
        f'You are the implementation worker {tid}. Build your assigned component in this workspace.\n'
        f'Pinned HarrTest package: {Path(__file__).resolve().parents[1].as_posix()}. '
        'Use this packet and the pinned package; do not substitute another installed HarrTest version.\n'
        f'Project directory: {Path(project).resolve().as_posix()}. Use this directory for commands and '
        'use absolute product paths if the native patch tool has a different working directory.\n'
        f'Original request: {plan["request"]}\n'
        f'Shared interface: {plan["contract"]}\n'
        f'Assignment: {task["brief"]}\n'
        f'Acceptance:\n{outcomes}\n'
        f'Exclusive product files: {", ".join(task["outputs"])}. '
        'Use the host apply_patch tool for each product file so the native trace records the write. '
        'When using functions.exec, use text(await tools.apply_patch(<literal JSON string>)) '
        'as the only statement in that call. '
        'Read shared interfaces as needed and leave other product files to their owners. '
        'Run a focused check on your component and then record the current output by running:\n'
        f'{command}'
    )
    return {'task_name': tid, 'fork_turns': 'none', 'message': message}


def receipt_path(project, state, tid):
    return team_path(project, state['plan']['id'], f'receipts/{tid}.json', must_exist=False)


def current_receipt(project, state, tid):
    data = proof.load(receipt_path(project, state, tid))
    digest = data.pop('sha256')
    require(data['id'] == tid and data['plan'] == state['plan_sha256']
            and strict_io.digest(data) == digest, f'{tid}: invalid handoff receipt')
    require(snapshot(project, data['files']) == data['files'], f'{tid}: handoff is stale')
    return {**data, 'sha256': digest}


def record(project, state, tid, files, **extra):
    path = receipt_path(project, state, tid)
    previous = proof.load(path) if path.is_file() else None
    data = {'id': tid, 'plan': state['plan_sha256'], 'files': files, **extra}
    if previous and all(previous.get(k) == v for k, v in data.items()):
        return current_receipt(project, state, tid)
    if previous:
        archive = team_path(project, state['plan']['id'],
                            f'history/{tid}-{strict_io.digest(previous)}.json', must_exist=False)
        if not archive.exists():
            proof.save(archive, previous, exclusive=True)
    data['at'] = proof.now()
    data['sha256'] = strict_io.digest(data)
    proof.save(path, data)
    return data


def handoff(project, state, task):
    inputs = {dep: current_receipt(project, state, dep)['sha256'] for dep in task['depends_on']}
    files = snapshot(project, task['outputs'])
    require(all(digest and digest != state['baseline'][rel] for rel, digest in files.items()),
            f'{task["id"]}: deliver a changed file for every assigned output')
    return record(project, state, task['id'], files, inputs=inputs)


def integrate(project, state):
    plan = state['plan']
    children = {task['id']: current_receipt(project, state, task['id']) for task in plan['tasks']}
    files = snapshot(project, plan['integration']['outputs'])
    require(all(digest and digest != state['baseline'][rel] for rel, digest in files.items()),
            'Integration needs the changed shared entrypoint or glue files')
    receipt = record(project, state, 'integration', files,
                     inputs={tid: row['sha256'] for tid, row in children.items()})
    team_id = plan['id']
    evidence = f'{proof.STATE}/teams/{team_id}/qa-evidence.txt'
    command = worker_command(project, team_id, 'review')
    check = worker_command(project, team_id, 'check')
    message = (
        f'You are the independent QA worker for this integrated product. Project directory: '
        f'{Path(project).resolve().as_posix()}. Use that workdir for every relative command and absolute paths '
        f'for private evidence files. Pinned HarrTest package: {Path(__file__).resolve().parents[1].as_posix()}; '
        'do not substitute another installed HarrTest version. '
        f'Original request: {plan["request"]}\n'
        f'Check the public entrypoint on current source: {plan["integration"]["check"]}\n'
        f'Run the actual product check using {check} -- COMMAND ARGUMENTS. '
        'Use a finite acceptance command that exercises behavior and exits. Start any long-running '
        'server separately; server startup and syntax alone do not verify the user journey. '
        'For browser work, use an available real browser adapter. If app/browser access is '
        'unavailable, check terminal Playwright availability before declaring browser testing blocked. '
        'Python Playwright and the Node Playwright CLI are separate installations. Check an existing '
        'Node CLI with `npx.cmd --offline --package @playwright/cli playwright-cli --help` on Windows '
        '(use `npx` on other systems); an absent Python import or global executable alone is insufficient. '
        'Retain the actual capability errors if neither path works. '
        'Coordinate exclusive ownership of shared browser/runtime resources with the coordinator; '
        'close your owned browsers and servers after the last check and report their release. '
        'You may create a scoped test script under the private team directory. '
        f'Preserve observed results in {evidence}. Read product files without editing them. '
        'For a visual product, inspect real frames after the main interaction and name specific '
        'issues with the primary subject, surroundings, useful detail, legibility or state feedback. '
        'Record screenshot paths and what you actually observed in them. '
        'For timed or interactive work, retain a measured wall-time sample alongside visible '
        'product-clock/progress and frame/response timing when applicable. Identify the runtime '
        'and viewport; compare against declared acceptance and report unusably slow interaction as failure. '
        'State injection, accelerated controller stepping and component simulation are separate '
        'tests; they cannot establish that a user completed the public journey or reached its end state. '
        'Leave those journey outcomes unverified until real public actions reach them. '
        'Read any supplied project validation target/browser configuration before choosing the '
        'runtime. '
        'Verify the effective runtime configuration, including the actual renderer/backend when '
        'relevant; matching only viewport or browser name is not enough if launch options differ. '
        'Give separate functional, visual and responsiveness verdicts. An indistinct '
        'primary subject, unreadable content or an obstructed interaction view is a visual failure, '
        'not a caveat under PASS. Return it to the owner and recheck the integrated frames. '
        f'Run {command} --evidence {evidence} --verdict pass only when the checks pass. '
        'Use --verdict fail if the result fails or you cannot verify it, with concrete evidence.'
    )
    return receipt, {'task_name': 'qa', 'fork_turns': 'none', 'message': message}


def runtime_check(project, state, argv):
    integrated = current_receipt(project, state, 'integration')
    require(argv and all(isinstance(arg, str) for arg in argv), 'Supply actual test argv after --')
    team_id = state['plan']['id']
    private = team_path(project, team_id).parent
    with tempfile.TemporaryFile(dir=private) as stdout, tempfile.TemporaryFile(dir=private) as stderr:
        try:
            result = subprocess.run(argv, cwd=project, stdin=subprocess.DEVNULL, stdout=stdout,
                                    stderr=stderr, timeout=120, check=False)
            code = result.returncode
        except subprocess.TimeoutExpired:
            code = None
        stdout.seek(0)
        stderr.seek(0)
        out = stdout.read(proof.MAX_LOG_BYTES + 1)
        err = stderr.read(proof.MAX_LOG_BYTES + 1)
    require(max(len(out), len(err)) <= proof.MAX_LOG_BYTES, 'QA process output exceeded the retained limit')
    filename = f'check-{uuid4().hex}.json'
    path = team_path(project, team_id, filename, must_exist=False)
    proof.save(path, {'argv': argv, 'exit_code': code, 'stdout': out.decode('utf-8', errors='replace'),
                      'stderr': err.decode('utf-8', errors='replace')}, exclusive=True)
    files = {f'{proof.STATE}/teams/{team_id}/{filename}': proof.file_hash(path)}
    return record(project, state, 'check', files, integration=integrated['sha256'], exit_code=code)


def review(project, state, evidence, verdict):
    integrated = current_receipt(project, state, 'integration')
    team_id = state['plan']['id']
    prefix = f'{proof.STATE}/teams/{team_id}/'
    require(evidence.startswith(prefix), 'Keep QA observations in the private team directory')
    path = strict_io.scoped_path(project, evidence)
    require(path.is_file() and 0 < path.stat().st_size <= MAX_ROLLOUT_BYTES, 'Missing retained QA observations')
    check = current_receipt(project, state, 'check') if verdict == 'pass' else {}
    require(verdict != 'pass' or (check['exit_code'] == 0 and check['integration'] == integrated['sha256']),
            'Independent QA needs a successful current subprocess check')
    return record(project, state, 'qa', {evidence: proof.file_hash(path)},
                  integration=integrated['sha256'], check=check.get('sha256'), verdict=verdict)


def instant(value):
    timestamp = datetime.fromisoformat(value[:-1] + '+00:00' if value.endswith('Z') else value)
    require(timestamp.tzinfo is not None, 'Native trace timestamp lacks a timezone')
    return timestamp


def session_id(value):
    require(isinstance(value, str) and str(UUID(value)) == value, 'Use the actual Codex parent thread UUID')
    return value


def log_meta(path):
    with path.open(encoding='utf-8-sig') as log:
        row = strict_io.loads(log.readline(2_000_000))
    if row.get('type') == 'session_meta' and isinstance(row.get('payload'), dict):
        return row['payload']
    return {}


def locate_sessions(project, parent, sessions, created):
    """Read only relevant rollouts; keep full transcripts in the native store."""
    session_id(parent)
    logs = {}
    lower_bound = instant(created) - timedelta(hours=24)
    for path in sessions.glob('*/*/*/rollout-*.jsonl'):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            if path.stat().st_mtime < lower_bound.timestamp():
                continue
            meta = log_meta(path)
            source = meta.get('source')
            spawn = source.get('subagent', {}).get('thread_spawn', {}) if isinstance(source, dict) else {}
            if meta.get('id') == parent or spawn.get('parent_thread_id') == parent:
                workspace = Path(meta['cwd']).resolve()
                require(project == workspace or project.is_relative_to(workspace),
                        'Native worker used a different workspace')
                if spawn:
                    require(spawn['agent_path'].startswith('/root/'), 'Native child path is missing')
                task = 'integration' if meta.get('id') == parent else spawn['agent_path'].rsplit('/', 1)[1]
                require(task not in logs, f'Duplicate native session for {task}')
                logs[task] = (meta, path)
        except (OSError, json.JSONDecodeError):
            # Other sessions may still be opening. Required sessions are checked below.
            continue
    require('integration' in logs, 'No durable parent rollout found for this workspace')
    return logs


def result_text(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return '\n'.join(row.get('text', '') for row in value if isinstance(row, dict))
    return ''


def patch_paths(project, call, output):
    tool = call.get('name')
    source = call.get('input')
    if tool == 'exec' and isinstance(source, str):
        # A successful wrapper invocation alone does not establish a patch.
        if not (output.startswith('Script completed') and output.rstrip().endswith('\n{}')):
            return set()
        match = EXEC_PATCH.match(source)
        if not match:
            literal = re.match(r'\A\s*const\s+([A-Za-z_$][\w$]*)\s*=\s*', source)
            if not literal:
                return set()
            try:
                patch, end = json.JSONDecoder().raw_decode(source[literal.end():])
            except ValueError:
                return set()
            tail = r'\s*;\s*text\s*\(\s*await\s+tools\.apply_patch\s*\(\s*' + re.escape(literal.group(1)) + r'\s*\)\s*\)\s*;?\s*'
            remainder = source[literal.end() + end:]
            bound = (r'\s*;\s*const\s+([A-Za-z_$][\w$]*)\s*=\s*await\s+tools\.apply_patch\s*\(\s*'
                     + re.escape(literal.group(1))
                     + r'\s*\)\s*;\s*text\s*\(\s*\1\s*\)\s*;?\s*')
            if not (re.fullmatch(tail, remainder) or re.fullmatch(bound, remainder)):
                return set()
        else:
            try:
                patch, end = json.JSONDecoder().raw_decode(source[match.end():])
            except ValueError:
                return set()
            variable = match.group(1)
            suffix = (r'\s*\)\s*;?\s*text\s*\(\s*' + re.escape(variable) + r'\s*\)\s*;?\s*'
                      if variable else r'\s*\)\s*\)\s*;?\s*')
            if not re.fullmatch(suffix, source[match.end() + end:]):
                return set()
    elif tool == 'apply_patch' and re.search(r'Success\. Updated|Patch applied', output, re.I):
        args = call.get('arguments', '{}')
        patch = source if isinstance(source, str) else strict_io.loads(args).get('patch', '')
    else:
        return set()
    if not isinstance(patch, str) or not patch.startswith('*** Begin Patch') or not patch.rstrip().endswith('*** End Patch'):
        return set()
    paths = set()
    for raw in PATCH_PATH.findall(patch):
        value = raw.strip().replace('\\\\', '\\').replace('\\', '/')
        path = Path(value)
        if path.is_absolute():
            try:
                value = path.resolve().relative_to(project).as_posix()
            except ValueError:
                value = path.as_posix()
        paths.add(product_key(value))
    return paths


def read_trace(project, meta, path, since):
    require(path.stat().st_size <= MAX_ROLLOUT_BYTES, 'Native rollout exceeds the supported size')
    writes, markers, calls = [], {}, {}
    finished, context = None, {}
    turn_starts = []
    intervals, active = [], None
    with path.open(encoding='utf-8-sig') as log:
        for line in log:
            if not line.endswith('\n'):
                break  # The active parent may still be appending its final record.
            event = strict_io.loads(line)
            payload = event.get('payload', {})
            kind = payload.get('type')
            when = instant(event['timestamp'])
            if event['type'] == 'turn_context':
                context = payload
            if when < since:
                continue
            if event['type'] == 'event_msg' and kind == 'task_started':
                turn_starts.append(when)
                active = when
            if event['type'] == 'event_msg' and kind == 'task_complete':
                finished = when
                if active is not None:
                    intervals.append((active, when))
                    active = None
            if event['type'] == 'event_msg' and kind == 'patch_apply_end' and payload.get('success'):
                for value in payload.get('changes', {}):
                    path_value = Path(value)
                    if path_value.is_absolute() and path_value.resolve().is_relative_to(project):
                        value = path_value.resolve().relative_to(project).as_posix()
                    writes.append((when, product_key(value)))
            if event['type'] != 'response_item':
                continue
            if kind in ('function_call', 'custom_tool_call') and payload.get('call_id'):
                calls[payload['call_id']] = payload
            if kind in ('function_call_output', 'custom_tool_call_output'):
                output = result_text(payload.get('output'))
                call = calls.pop(payload.get('call_id'), {})
                writes.extend((when, rel) for rel in patch_paths(project, call, output))
                if 'team.py' in (call.get('input') or call.get('arguments') or ''):
                    for digest in re.findall(r'^' + RECEIPT + r'([0-9a-f]{64})\s*$', output, re.M):
                        markers[digest] = when
    return {'id': meta['id'], 'start': instant(meta['timestamp']), 'end': finished,
            'writes': writes, 'markers': markers, 'turn_starts': turn_starts,
            'intervals': intervals, 'active': active, 'model': context.get('model'),
            'effort': context.get('effort')}


def receipt_event(row, receipt, label):
    time = row['markers'].get(receipt['sha256'])
    require(time and time >= instant(receipt['at']), f'{label}: missing native tool receipt')
    return time


def turn_start(row, at):
    return max((t for t in row['turn_starts'] if t <= at), default=row['start'])


def completed_overlap(left, right):
    return any(max(a, c) < min(b, d) for a, b in left['intervals'] for c, d in right['intervals'])


def completed_receipt(row, at):
    return any(start <= at <= end for start, end in row['intervals'])


def verify_native(project, state, parent, sessions, require_qa):
    plan = state['plan']
    tasks = {row['id']: row for row in plan['tasks']}
    created = instant(state['created'])
    logs = locate_sessions(project, parent, sessions, state['created'])
    coordinator = read_trace(project, *logs['integration'], created)
    owned = {product_key(rel) for task in tasks.values() for rel in task['outputs']}
    glue = {product_key(rel) for rel in plan['integration']['outputs']}
    require(not any(rel in owned for _, rel in coordinator['writes']),
            'Coordinator wrote a worker-owned production file')
    require(not any(rel not in glue and not rel.startswith(proof.STATE + '/')
                    for _, rel in coordinator['writes']), 'Coordinator wrote outside integration scope')
    builds, handoffs = {}, {}
    for tid, task in tasks.items():
        receipt = current_receipt(project, state, tid)
        require(set(receipt['files']) == set(task['outputs']), f'{tid}: handoff scope changed')
        require(tid in logs, f'{tid}: missing direct native implementation worker')
        row = read_trace(project, *logs[tid], created)
        require(row['id'] != parent and row['start'] >= created and row['end'],
                f'{tid}: missing completed worker after the plan was sealed')
        at = receipt_event(row, receipt, tid)
        require(completed_receipt(row, at), f'{tid}: handoff is from a turn that has not completed')
        allowed = {product_key(rel) for rel in task['outputs']}
        product = {rel for when, rel in row['writes']
                   if not rel.startswith(proof.STATE + '/') and when <= at}
        require(product == allowed, f'{tid}: native writes must match its owned product files')
        require(not any(rel in allowed and when > at for when, rel in row['writes']),
                f'{tid}: product edited after its handoff')
        builds[tid] = {key: row[key] for key in ('id', 'model', 'effort')}
        builds[tid].update(files=task['outputs'], started=row['start'].isoformat(),
                           finished=row['end'].isoformat(), receipt=receipt['sha256'])
        handoffs[tid] = (row, at, receipt)
    require(len({row['id'] for row, _, _ in handoffs.values()}) == len(tasks),
            'Production tasks reused one worker session')
    parents = ancestors(tasks)
    pairs = []
    for i, (a, (left, left_at, receipt)) in enumerate(handoffs.items()):
        require(receipt['inputs'] == {dep: handoffs[dep][2]['sha256'] for dep in tasks[a]['depends_on']},
                f'{a}: worker did not use current prerequisites')
        for dep in tasks[a]['depends_on']:
            require(turn_start(left, left_at) >= handoffs[dep][1], f'{a} began before prerequisite handoff {dep}')
        for b, (right, _, _) in list(handoffs.items())[i+1:]:
            if a not in parents[b] and b not in parents[a] and completed_overlap(left, right):
                pairs.append([a, b])
    require(pairs, 'No overlap between independent native implementation workers')
    if require_qa:
        integrated = current_receipt(project, state, 'integration')
        require(set(integrated['files']) == set(plan['integration']['outputs']), 'Integration file scope changed')
        require(integrated['inputs'] == {tid: row['receipt'] for tid, row in builds.items()},
                'Integration did not use current worker handoffs')
        when = receipt_event(coordinator, integrated, 'integration')
        latest = max(at for _, at, _ in handoffs.values())
        first_wave = max(min(row['markers'].values()) for row, _, _ in handoffs.values())
        require(when >= latest and any(rel in glue and first_wave <= at <= when
                                       for at, rel in coordinator['writes']),
                'Integration glue must be written after worker handoffs')
        qa = current_receipt(project, state, 'qa')
        check = current_receipt(project, state, 'check')
        require(qa['integration'] == integrated['sha256'] and qa['verdict'] == 'pass',
                'Independent QA is incomplete or stale for the integrated output')
        require(qa['check'] == check['sha256'] and check['integration'] == integrated['sha256']
                and check['exit_code'] == 0, 'Independent runtime check is incomplete or stale')
        require('qa' in logs, 'No native independent QA session')
        reviewer = read_trace(project, *logs['qa'], created)
        qa_at = receipt_event(reviewer, qa, 'QA')
        check_at = receipt_event(reviewer, check, 'QA check')
        require(reviewer['id'] not in {parent, *(v['id'] for v in builds.values())}
                and turn_start(reviewer, check_at) >= when and reviewer['end']
                and check_at <= qa_at and completed_receipt(reviewer, qa_at),
                'QA must be a distinct completed worker started after integration')
        require(not any(not rel.startswith(proof.STATE + '/') for _, rel in reviewer['writes']),
                'QA edited product source')
    return {'passed': True, 'errors': [], 'team': plan['id'], 'coordinator': parent,
            'workers': builds, 'overlap': pairs, 'independent_qa': require_qa}


def codex_sessions():
    return Path(os.environ.get('CODEX_HOME') or (Path.home() / '.codex')) / 'sessions'


def verify_registered(project, team_id, *, require_qa=True, parent=None, sessions=None):
    try:
        project = Path(project).resolve()
        state = load_state(project, team_id)
        if parent is None:
            location = team_path(project, team_id, 'host.json', must_exist=False)
            parent = proof.load(location)['parent'] if location.is_file() else os.environ.get('CODEX_THREAD_ID')
        return verify_native(project, state, parent, Path(sessions or codex_sessions()), require_qa)
    except (ValueError, TypeError, KeyError, AttributeError, OSError, proof.ProofError) as exc:
        return {'passed': False, 'errors': [str(exc)], 'team': team_id}


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=Path('.'))
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('init').add_argument('--plan', required=True)
    for action in ('packets', 'handoff', 'integrate', 'check', 'review', 'verify'):
        command = commands.add_parser(action)
        command.add_argument('--team', required=True)
        if action == 'handoff':
            command.add_argument('--task', required=True)
        if action == 'review':
            command.add_argument('--evidence', required=True)
            command.add_argument('--verdict', choices=('pass', 'fail'), required=True)
        if action == 'check':
            command.add_argument('argv', nargs=argparse.REMAINDER)
        if action == 'verify':
            command.add_argument('--parent')
            command.add_argument('--production-only', action='store_true')
    args = parser.parse_args(argv)
    project = args.project.resolve()
    try:
        if args.command == 'init':
            result = init(project, proof.load(strict_io.scoped_path(project, args.plan)))
        elif args.command == 'verify':
            result = verify_registered(project, args.team, require_qa=not args.production_only, parent=args.parent)
            if result['passed'] and args.parent:
                path = team_path(project, args.team, 'host.json', must_exist=False)
                if not path.exists():
                    proof.save(path, {'parent': args.parent}, exclusive=True)
        else:
            state = load_state(project, args.team)
            tasks = {row['id']: row for row in state['plan']['tasks']}
            if args.command == 'packets':
                def ready(task):
                    if receipt_path(project, state, task['id']).exists():
                        return False
                    try:
                        for dep in task['depends_on']:
                            current_receipt(project, state, dep)
                    except (ValueError, proof.ProofError):
                        return False
                    return True
                result = {'ready': [packet(project, state, task) for task in tasks.values() if ready(task)]}
            elif args.command == 'handoff':
                result = handoff(project, state, tasks[args.task])
            elif args.command == 'integrate':
                result, qa = integrate(project, state)
                result = {**result, 'qa': qa}
            elif args.command == 'check':
                result = runtime_check(project, state, args.argv[1:] if args.argv[:1] == ['--'] else args.argv)
                result['passed'] = result['exit_code'] == 0
            else:
                result = review(project, state, args.evidence, args.verdict)
            if 'sha256' in result:
                print(RECEIPT + result['sha256'])
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result.get('passed') is False else 0
    except (ValueError, TypeError, KeyError, OSError, proof.ProofError) as exc:
        print(json.dumps({'passed': False, 'errors': [str(exc)]}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
