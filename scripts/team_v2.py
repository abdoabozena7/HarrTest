"""Host-neutral production receipts for existing-code changes.

Local receipts establish current scopes and subprocess outcomes, not native
worker identity. Host adapters must establish that separate claim explicitly.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import time
from uuid import uuid4

import proof
import strict_io

MAX_NATIVE_EVENT_BYTES = 2 * 1024 * 1024
MAX_NATIVE_WINDOW_BYTES = 32 * 1024 * 1024
MAX_NATIVE_WINDOW_EVENTS = 100_000
MAX_NATIVE_PENDING_CALLS = 4096
MAX_NATIVE_SCAN_BYTES = 1024 * 1024 * 1024


class HostEvidenceUnavailable(ValueError):
    """The native format/capture needed for an identity claim is unavailable."""


class NativeWindow:
    """Stream a fixed file snapshot, retaining only bounded plan-time events.

    Every complete record is strictly decoded, including prehistory. An
    oversized or malformed record is never skipped by guessing its timestamp.
    The final unfinished record cannot establish a completion or a receipt.
    """
    def __init__(self, path, since, host):
        self.path, self.since, self.host = Path(path), since, host
        self.contexts, self.tail_incomplete = [], False
        self.snapshot_bytes = self.scanned_bytes = self.window_bytes = self.window_events = 0

    def __iter__(self):
        t = common()
        if self.path.is_symlink() or not self.path.is_file():
            raise HostEvidenceUnavailable('Missing regular native session file')
        with self.path.open('rb') as source:
            self.snapshot_bytes = os.fstat(source.fileno()).st_size
            if self.snapshot_bytes > MAX_NATIVE_SCAN_BYTES:
                raise HostEvidenceUnavailable('Native scan byte budget exceeded')
            carry, emitted_context, headers = {}, False, 0
            model_transition_time = None
            pending_tool_bytes = 0
            pending_tools = {}
            while source.tell() < self.snapshot_bytes:
                remaining = self.snapshot_bytes - source.tell()
                raw = source.readline(min(MAX_NATIVE_EVENT_BYTES + 1, remaining))
                self.scanned_bytes += len(raw)
                if len(raw) > MAX_NATIVE_EVENT_BYTES:
                    raise HostEvidenceUnavailable('Native event exceeds bounded record size')
                if not raw.endswith(b'\n'):
                    self.tail_incomplete = True
                    break
                try:
                    event = strict_io.loads(raw.decode('utf-8-sig'))
                    if not isinstance(event, dict):
                        raise ValueError('Event is not an object')
                    when = t.instant(event['timestamp'])
                except (ValueError, TypeError, KeyError, AttributeError, OverflowError, UnicodeError) as exc:
                    raise HostEvidenceUnavailable('Malformed native event before snapshot boundary') from exc
                if event.get('checkpoint') is True:
                    continue
                header_kind = 'session_meta' if self.host == 'codex' else 'session.start'
                kind = event.get('type')
                if self.host == 'copilot' and kind == 'session.model_change' and not event.get('agentId'):
                    if model_transition_time is not None and when < model_transition_time:
                        raise HostEvidenceUnavailable('Native model transitions are out of chronological order')
                    model_transition_time = when
                    if emitted_context and when < self.since:
                        raise HostEvidenceUnavailable('Pre-plan model transition follows plan-time execution')
                if kind == header_kind:
                    headers += 1
                    if headers != 1:
                        raise HostEvidenceUnavailable('Duplicate native session header')
                    self.charge(raw)
                    yield event
                    continue
                if when < self.since:
                    if (self.host == 'copilot' and not event.get('agentId')
                            and kind in {'tool.execution_start', 'tool.execution_complete'}):
                        # A coordinator tool can seal the plan before its own
                        # completion arrives. Carry only unmatched starts.
                        data = event.get('data', {})
                        call_id = data.get('toolCallId') if isinstance(data, dict) else None
                        if not isinstance(call_id, str) or not call_id or emitted_context:
                            raise HostEvidenceUnavailable('Invalid pre-plan Copilot tool lifecycle')
                        if kind == 'tool.execution_start':
                            if call_id in pending_tools:
                                raise HostEvidenceUnavailable('Duplicate pre-plan Copilot tool call')
                            pending_tools[call_id] = (event, raw, source.tell())
                            pending_tool_bytes += len(raw)
                            if (len(pending_tools) > MAX_NATIVE_PENDING_CALLS
                                    or pending_tool_bytes > MAX_NATIVE_WINDOW_BYTES):
                                raise HostEvidenceUnavailable('Native pre-plan pending tool budget exceeded')
                        else:
                            previous = pending_tools.pop(call_id, None)
                            if previous is not None:
                                pending_tool_bytes -= len(previous[1])
                    if self.host == 'codex' and kind == 'turn_context':
                        carry[kind] = (event, raw, source.tell())
                    if self.host == 'copilot' and kind == 'session.context_changed':
                        carry[kind] = (event, raw, source.tell())
                    if self.host == 'copilot' and kind == 'session.model_change' and not event.get('agentId'):
                        data = event.get('data', {})
                        if not isinstance(data, dict):
                            raise HostEvidenceUnavailable('Malformed native model transition')
                        # Keep actual records that last supplied each field. A
                        # later sparse transition must not erase the other field.
                        for field in ('newModel', 'reasoningEffort'):
                            if field in data:
                                carry[(kind, field)] = (event, raw, source.tell())
                    continue
                if not emitted_context:
                    carry.update({('tool', call_id): value for call_id, value in pending_tools.items()})
                    pending_tools.clear()
                    for previous, encoded in self.carry_records(carry):
                        self.charge(encoded)
                        if previous.get('type') == 'turn_context':
                            self.contexts.append(previous.get('payload', {}))
                        yield previous
                    carry.clear()
                    emitted_context = True
                self.charge(raw)
                if kind == 'turn_context':
                    self.contexts.append(event.get('payload', {}))
                yield event
            if not emitted_context:
                for previous, encoded in self.carry_records(carry):
                    self.charge(encoded)
                    if previous.get('type') == 'turn_context':
                        self.contexts.append(previous.get('payload', {}))
                    yield previous
            if headers != 1:
                raise HostEvidenceUnavailable('Missing native session header')

    @staticmethod
    def carry_records(carry):
        # One record may supply both model and effort. Re-emit it only once,
        # in its native journal order (including timestamp ties); never
        # synthesize a context event.
        rows = {id(event): (event, raw, offset) for event, raw, offset in carry.values()}
        return [(event, raw) for event, raw, _ in sorted(rows.values(), key=lambda item: item[2])]

    def charge(self, raw):
        self.window_bytes += len(raw)
        self.window_events += 1
        if self.window_bytes > MAX_NATIVE_WINDOW_BYTES or self.window_events > MAX_NATIVE_WINDOW_EVENTS:
            raise HostEvidenceUnavailable('Native plan-time evidence window budget exceeded')


def common():
    # Imported on demand: team dispatches schema 2 here after its legacy API loads.
    import team
    return team


def validate_plan(project, plan):
    t = common()
    t.require(isinstance(plan, dict) and type(plan.get('schema')) is int
              and plan['schema'] == 2, 'Expected a schema-2 production team plan')
    proof.identifier(plan.get('id'), 'production team ID')
    t.require(plan.get('kind') in ('change', 'greenfield'), 'Choose change or greenfield')
    t.concrete(plan.get('request'), 'Original request')
    t.concrete(plan.get('contract'), 'Shared contract')
    t.validation_files(project, plan)
    outcomes = plan.get('outcomes')
    t.require(isinstance(outcomes, dict) and outcomes, 'Declare original outcomes')
    for rid, value in outcomes.items():
        proof.identifier(rid, 'outcome ID')
        t.concrete(value, rid + ' acceptance')
    rows = plan.get('tasks')
    t.require(isinstance(rows, list) and rows, 'Declare at least one implementation owner')
    tasks, owned, covered = {}, [], set()
    for row in rows:
        t.require(isinstance(row, dict), 'Invalid implementation scope')
        tid = t.name(row.get('id'))
        t.require(tid not in tasks and tid not in {'qa', 'check', 'integration'}, 'Duplicate/reserved owner')
        t.require(row.get('role', 'implement') == 'implement', 'An owner must implement product files')
        t.concrete(row.get('brief'), tid + ' brief')
        outputs = t.file_list(project, row.get('outputs'), tid)
        deps = row.get('depends_on')
        t.require(isinstance(deps, list) and all(isinstance(d, str) for d in deps)
                  and len(deps) == len(set(deps)), tid + ': invalid dependencies')
        refs = row.get('outcomes')
        t.require(isinstance(refs, list) and refs and all(x in outcomes for x in refs),
                  tid + ': link known original outcomes')
        deleted = row.get('deletions', [])
        t.require(isinstance(deleted, list) and all(isinstance(x, str) for x in deleted)
                  and len(deleted) == len(set(deleted)) and set(deleted) <= set(outputs),
                  tid + ': deletions must be distinct owned paths')
        renames = row.get('renames', [])
        t.require(isinstance(renames, list), tid + ': invalid renames')
        seen = set()
        for move in renames:
            t.require(isinstance(move, dict) and set(move) == {'from', 'to'}, 'Rename needs from/to paths')
            a, b = move['from'], move['to']
            t.require(isinstance(a, str) and isinstance(b, str) and a != b
                      and a in outputs and b in outputs and a not in seen and b not in seen,
                      tid + ': rename paths must be distinct and owned')
            seen.update((a, b))
        tasks[tid] = row
        owned.extend(outputs)
        covered.update(refs)
    t.require(covered == set(outcomes), 'Map every original outcome to implementation')
    integration = plan.get('integration')
    t.require(isinstance(integration, dict), 'Declare integrated acceptance')
    t.concrete(integration.get('check'), 'Integrated acceptance check')
    glue = integration.get('outputs')
    t.require(isinstance(glue, list), 'Integration outputs must be an explicit list; [] is valid')
    if glue:
        owned.extend(t.file_list(project, glue, 'integration'))
    t.require(not any(strict_io.overlaps(a, b) for i, a in enumerate(owned) for b in owned[i + 1:]),
              'Each product path needs exactly one owner')
    t.ancestors(tasks)
    capacity = plan.get('max_parallel_workers', 1)
    t.require(type(capacity) is int and 1 <= capacity <= 128, 'Invalid observed worker capacity')
    if capacity == 1 and independent_pairs(tasks):
        t.concrete(plan.get('execution_rationale'), 'Explain serial execution of independent scopes')
    timeout = integration.get('timeout_seconds', 120)
    t.require(type(timeout) is int and 1 <= timeout <= 3600, 'Integrated check timeout must be 1..3600 seconds')
    host = plan.get('host', {'kind': 'unverified'})
    t.require(isinstance(host, dict) and host.get('kind') in {'codex', 'copilot', 'unverified'},
              'Declare codex, copilot or unverified host evidence')
    for field in ('model', 'reasoning_effort'):
        if field in plan:
            t.require(isinstance(plan[field], str) and bool(plan[field].strip()), 'Invalid pinned ' + field)
    return tasks, owned


def independent_pairs(tasks):
    parents = common().ancestors(tasks)
    return [(a, b) for i, a in enumerate(tasks) for b in list(tasks)[i + 1:]
            if a not in parents[b] and b not in parents[a]]


def init(project, plan):
    t = common()
    tasks, owned = validate_plan(project, plan)
    baseline = t.snapshot(project, owned)
    if plan['kind'] == 'greenfield':
        t.require(not any(baseline.values()), 'Seal greenfield scopes before product creation')
    for task in tasks.values():
        for rel in deleted_paths(task):
            t.require(baseline[rel] is not None, 'Deleted/renamed source must exist at baseline: ' + rel)
        for move in task.get('renames', []):
            t.require(baseline[move['to']] is None, 'Rename destination must be absent at baseline')
    state = {'plan': plan, 'plan_sha256': strict_io.digest(plan), 'baseline': baseline,
             'created': proof.now(), 'validation_inputs': t.validation_snapshot(project, plan)}
    state['state_sha256'] = strict_io.digest(state)
    proof.save(t.team_path(project, plan['id'], must_exist=False), state, exclusive=True)
    return {'team': plan['id'], 'schema': 2, 'plan_sha256': state['plan_sha256'],
            'ready': [packet(project, state, row) for row in tasks.values() if not row['depends_on']]}


def load_state(project, team_id):
    t = common()
    state = proof.load(t.team_path(project, team_id))
    t.require(state.get('state_sha256') == strict_io.digest({k: v for k, v in state.items() if k != 'state_sha256'}),
              'Sealed production baseline/state changed')
    _, owned = validate_plan(project, state['plan'])
    t.require(state['plan']['id'] == team_id and strict_io.digest(state['plan']) == state['plan_sha256'],
              'Sealed production plan changed')
    t.require(set(owned) == set(state['baseline']), 'Production baseline scope changed')
    t.validation_message(project, state)
    return state


def binding(project, team_id, request_sha256):
    state = load_state(project, team_id)
    plan = state['plan']
    request = plan['request'].replace('\r\n', '\n')
    hashes = {hashlib.sha256(s.encode('utf-8')).hexdigest() for s in (request, request.replace('\n', '\r\n'))}
    common().require(request_sha256 in hashes, 'Production team belongs to another request')
    return {'plan_sha256': state['plan_sha256'],
            'tasks': {r['id']: {k: r[k] for k in ('outputs', 'depends_on')} for r in plan['tasks']},
            'integration_outputs': list(state['baseline'])}


def deleted_paths(task):
    return set(task.get('deletions', [])) | {r['from'] for r in task.get('renames', [])}


def packet(project, state, task):
    t = common()
    plan, tid = state['plan'], task['id']
    text = (f'You own implementation scope {tid}. Project: {Path(project).resolve().as_posix()}.\n'
            f'Pinned HarrTest: {Path(__file__).resolve().parents[1].as_posix()}.\n'
            f'Original request: {plan["request"]}\nExisting architecture/interfaces: {plan["contract"]}\n'
            f'{t.validation_message(project, state)}Assignment: {task["brief"]}\n'
            f'Exclusive product paths: {", ".join(task["outputs"])}.\n'
            f'Declared removals: {sorted(deleted_paths(task))}; renames: {task.get("renames", [])}.\n'
            'Preserve existing contracts and unrelated behavior. Use the actual host editing tools; '
            'do not invent native identity or verification. Read prerequisite handoffs and supplied '
            'acceptance/risk criteria. Implement and test only your scope; return boundary conflicts '
            'to the coordinator. Record meaningful focused behavior checks and unresolved findings.\n'
            'Acceptance:\n' + '\n'.join(f'- {x}: {plan["outcomes"][x]}' for x in task['outcomes']) + '\n'
            'Handoff command:\n' + t.worker_command(project, plan['id'], 'handoff') + ' --task ' + tid)
    repair = pending_repair(project, state, tid)
    if repair:
        text += (f'\nRepair current finding: {repair["observation"]}. '
                 f'Read immutable evidence {next(iter(repair["files"]))}; retain the failed attempt. '
                 'Diagnose in your owned scope, rerun affected checks, then hand off again.')
    return {'task_name': tid, 'fork_turns': 'none', 'message': text}


def current_receipt(project, state, tid):
    t = common()
    data = proof.load(t.receipt_path(project, state, tid))
    digest = data.pop('sha256')
    t.require(data['id'] == tid and data['plan'] == state['plan_sha256']
              and strict_io.digest(data) == digest, tid + ': invalid receipt')
    t.require(t.snapshot(project, data['files']) == data['files'], tid + ': current files differ from receipt')
    return {**data, 'sha256': digest}


def record(project, state, tid, files, **extra):
    # Legacy receipt serialization is schema-neutral and preserves immutable history.
    return common().record(project, state, tid, files, **extra)


def handoff(project, state, task):
    t = common()
    t.validation_message(project, state)
    files = t.snapshot(project, task['outputs'])
    deleted = deleted_paths(task)
    for rel, digest in files.items():
        t.require((digest is None) == (rel in deleted), 'Only declared deletions may be absent: ' + rel)
    t.require(any(value != state['baseline'][rel] for rel, value in files.items()),
              task['id'] + ': handoff must contain an actual change')
    inputs = {dep: usable_handoff(project, state, dep)['sha256'] for dep in task['depends_on']}
    extra = {}
    path = t.receipt_path(project, state, 'repair-' + task['id'])
    if path.is_file():
        extra['repair'] = current_receipt(project, state, 'repair-' + task['id'])['sha256']
    return record(project, state, task['id'], files, inputs=inputs, **extra)


def pending_repair(project, state, tid):
    t = common()
    if not t.receipt_path(project, state, 'repair-' + tid).is_file():
        return None
    repair = current_receipt(project, state, 'repair-' + tid)
    try:
        owner = current_receipt(project, state, tid)
    except (ValueError, proof.ProofError):
        return repair
    return repair if owner.get('repair') != repair['sha256'] else None


def usable_handoff(project, state, tid):
    t = common()
    t.validation_message(project, state)
    t.require(not pending_repair(project, state, tid), tid + ': owner repair remains open')
    task = next(r for r in state['plan']['tasks'] if r['id'] == tid)
    receipt = current_receipt(project, state, tid)
    t.require(set(receipt['files']) == set(task['outputs']), tid + ': receipt scope differs from sealed owner')
    deps = {d: usable_handoff(project, state, d)['sha256'] for d in task['depends_on']}
    t.require(receipt.get('inputs') == deps, tid + ': stale prerequisite handoff')
    return receipt


def ready_packets(project, state):
    common().validation_message(project, state)
    ready = []
    for row in state['plan']['tasks']:
        try:
            for dep in row['depends_on']:
                usable_handoff(project, state, dep)
        except (ValueError, proof.ProofError):
            continue
        try:
            usable_handoff(project, state, row['id'])
        except (ValueError, proof.ProofError):
            ready.append(packet(project, state, row))
    return ready


def integrate(project, state):
    t = common()
    t.validation_message(project, state)
    plan = state['plan']
    children = {r['id']: usable_handoff(project, state, r['id']) for r in plan['tasks']}
    receipt = record(project, state, 'integration', t.snapshot(project, state['baseline']),
                     inputs={tid: row['sha256'] for tid, row in children.items()})
    evidence = f'{proof.STATE}/teams/{plan["id"]}/qa-evidence.txt'
    command = t.worker_command(project, plan['id'], 'check')
    review_command = t.worker_command(project, plan['id'], 'review')
    message = (f'You are independent QA. Project: {Path(project).resolve().as_posix()}.\n'
               f'Original request: {plan["request"]}\nShared contract: {plan["contract"]}\n'
               f'{t.validation_message(project, state)}Integrated receipt: {receipt["sha256"]}.\n'
               f'Acceptance check: {plan["integration"]["check"]}\n'
               'Read current-source inputs and test the actual behavior independently. Cover applicable '
               'functionality, preservation, architecture, security, performance and failure/data risks. '
               'Use independent expected results and retain failures. Missing checks are UNVERIFIED, '
               'not PASS. Record each quality layer as PASS, FAIL, UNVERIFIED or NOT_APPLICABLE; '
               'retain failed and unverified observations. NOT_APPLICABLE needs an impact rationale '
               'and supporting evidence reviewed independently. Do not omit required layers or '
               'turn a missing measurement into an applicability exclusion. Do not edit product '
               'files or weaken the contract. Run a finite real check with assertions through:\n'
               f'{command} -- ACTUAL_ARGV\nRecord observations privately in {evidence}. '
               f'Then run {review_command} --evidence {evidence} --verdict pass only if all required '
               'checks pass, otherwise --verdict fail. Release owned runtime resources afterward. '
               'A successful receipt proves the recorded process, not semantic correctness or native identity.')
    return receipt, {'task_name': 'qa', 'fork_turns': 'none', 'message': message}


def runtime_check(project, state, argv):
    t = common()
    t.validation_message(project, state)
    integrated = current_receipt(project, state, 'integration')
    t.require(isinstance(argv, list) and argv and all(isinstance(x, str) and x for x in argv),
              'Supply actual executable argv after --')
    private = t.team_path(project, state['plan']['id']).parent
    started = proof.now()
    timeout = state['plan']['integration'].get('timeout_seconds', 120)
    spawn_error, timed_out, overflow = None, False, False
    with tempfile.TemporaryFile(dir=private) as stdout, tempfile.TemporaryFile(dir=private) as stderr:
        process = None
        try:
            options = ({'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt'
                       else {'start_new_session': True})
            process = subprocess.Popen(argv, cwd=project, stdin=subprocess.DEVNULL, stdout=stdout,
                                       stderr=stderr, shell=False, **options)
            clock = time.monotonic()
            while process.poll() is None:
                timed_out = time.monotonic() - clock > timeout
                overflow = max(stdout.tell(), stderr.tell()) > proof.MAX_LOG_BYTES
                if timed_out or overflow:
                    proof.stop_owned_process(process)
                    break
                time.sleep(.05)
            code = process.wait()
        except OSError as exc:
            code, spawn_error = None, str(exc)
        except KeyboardInterrupt:
            if process is not None:
                proof.stop_owned_process(process)
            raise
        stdout.seek(0)
        stderr.seek(0)
        out, err = stdout.read(proof.MAX_LOG_BYTES + 1), stderr.read(proof.MAX_LOG_BYTES + 1)
    overflow = overflow or max(len(out), len(err)) > proof.MAX_LOG_BYTES
    source_unchanged = t.snapshot(project, integrated['files']) == integrated['files']
    filename = f'check-{uuid4().hex}.json'
    path = t.team_path(project, state['plan']['id'], filename, must_exist=False)
    proof.save(path, {'argv': argv, 'cwd': str(Path(project).resolve()), 'exit_code': code,
                     'started_at': started, 'finished_at': proof.now(), 'timed_out': timed_out,
                     'overflow': overflow, 'spawn_error': spawn_error, 'source_unchanged': source_unchanged,
                     'stdout': out[:proof.MAX_LOG_BYTES].decode('utf-8', errors='replace'),
                     'stderr': err[:proof.MAX_LOG_BYTES].decode('utf-8', errors='replace')}, exclusive=True)
    receipt = record(project, state, 'check', {path.relative_to(project).as_posix(): proof.file_hash(path)},
                     integration=integrated['sha256'],
                     exit_code=code if not (timed_out or overflow or spawn_error) else None)
    # Preserve failed observations before reporting a verifier/source problem.
    t.require(source_unchanged, 'QA command changed integrated source')
    t.validation_message(project, state)
    return receipt


def review(project, state, evidence, verdict):
    # Legacy review already binds immutable narrative, current finite check and owner inputs.
    common().require(verdict in {'pass', 'fail'}, 'Review verdict must be pass or fail')
    return common().review(project, state, evidence, verdict)


def repair(project, state, tid, evidence, observation):
    return common().repair(project, state, tid, evidence, observation)


def verify_structural(project, state, require_qa):
    t = common()
    t.validation_message(project, state)
    children = {r['id']: usable_handoff(project, state, r['id']) for r in state['plan']['tasks']}
    if require_qa:
        integrated = current_receipt(project, state, 'integration')
        t.require(set(integrated['files']) == set(state['baseline']), 'Integrated source scope differs from plan')
        t.require(integrated['inputs'] == {tid: row['sha256'] for tid, row in children.items()},
                  'Integration did not consume current owner handoffs')
        check = current_receipt(project, state, 'check')
        qa = current_receipt(project, state, 'qa')
        t.require(check.get('integration') == integrated['sha256'] and check.get('exit_code') == 0,
                  'Missing successful current integrated subprocess')
        t.require(qa.get('verdict') == 'pass' and qa.get('integration') == integrated['sha256']
                  and qa.get('check') == check['sha256'], 'QA is failed or stale')
    return children


def codex_adapter(project, state, parent, sessions, require_qa):
    """Use the established host parser; schema-2 acceptance is separate below."""
    t = common()
    created = t.instant(state['created'])
    logs = t.locate_sessions(project, parent, Path(sessions or t.codex_sessions()), state['created'])
    rows = {}
    for role, (meta, path) in logs.items():
        window = NativeWindow(path, created, 'codex')
        try:
            rows[role] = t.read_trace(project, meta, path, created, events=window,
                                      lifecycle_limit=MAX_NATIVE_PENDING_CALLS)
        except ValueError as exc:
            if 'pending lifecycle limit exceeded' in str(exc):
                raise HostEvidenceUnavailable(str(exc)) from exc
            raise
        rows[role]['tail_incomplete'] = window.tail_incomplete
        for context in window.contexts:
            for key, field in [('models', 'model'), ('efforts', 'effort')]:
                rows[role].setdefault(key, set()).update(filter(None, [context.get(field)]))
    return verify_native_rows(project, state, parent, rows, require_qa, 'codex-rollout')


def read_copilot_traces(project, parent, sessions, since):
    """Read Copilot's persisted session-events v1, not model-authored summaries.

    Format: CLI1.0.104 live native probe and the installed official SDK's
    generated/session-events.d.ts. Successful tool completions bind fileEdits
    and receipt stdout to their original calls and native subagent IDs.
    """
    t = common()
    t.session_id(parent)
    base = Path(sessions) if sessions else Path(os.environ.get('COPILOT_HOME') or Path.home() / '.copilot') / 'session-state'
    path = base / parent / 'events.jsonl'
    t.require(not path.is_symlink(), 'Copilot native session cannot be a symlink')
    if not path.is_file():
        raise HostEvidenceUnavailable('Missing selected Copilot native session')
    window = NativeWindow(path, since, 'copilot')
    events = iter(window)
    header = next(events, None)
    if header is None or header.get('type') != 'session.start':
        raise HostEvidenceUnavailable('Need one native Copilot session.start header')
    data = header.get('data', {})
    t.require(data.get('sessionId') == parent and data.get('producer') == 'copilot-agent',
              'Copilot native session identity mismatch')
    if data.get('version') != 1:
        raise HostEvidenceUnavailable('Unsupported Copilot session event format version')
    t.require(Path(data.get('context', {}).get('cwd', '')).resolve() == project,
              'Copilot native workspace differs from the project')
    def row(uid, start, model, effort=None):
        return {'id': uid, 'start': start, 'end': None, 'writes': [], 'markers': {},
                'intervals': [], 'turn_starts': [], 'active': None, 'model': model,
                'effort': effort, 'models': set(filter(None, [model])), 'efforts': set(filter(None, [effort]))}
    coordinator = row(parent, t.instant(data['startTime']), data.get('selectedModel'), data.get('reasoningEffort'))
    rows, by_agent, calls, dispatch = {'integration': coordinator}, {}, {}, {}
    seen_ids = {header.get('id')}
    boundary_initialized = False
    def apply_model_transition(current, payload, record):
        t.require(isinstance(payload, dict), 'Invalid native model transition')
        for field, target, history in [('newModel', 'model', 'models'),
                                       ('reasoningEffort', 'effort', 'efforts')]:
            if field not in payload:
                continue
            value = payload[field]
            t.require((value is None and field == 'reasoningEffort')
                      or isinstance(value, str) and bool(value.strip()), 'Invalid native ' + field)
            current[target] = value
            if record:
                current[history].add(value)
    for event in events:
        eid = event.get('id')
        t.require(isinstance(eid, str) and eid not in seen_ids, 'Duplicate/missing Copilot event ID')
        seen_ids.add(eid)
        kind, payload = event.get('type'), event.get('data', {})
        when = t.instant(event['timestamp'])
        agent = event.get('agentId')
        current = by_agent.get(agent) if agent else coordinator
        if kind == 'session.context_changed':
            t.require(Path(payload.get('cwd', '')).resolve() == project,
                      'Copilot session changed to a different workspace')
        if when < since:
            if kind == 'session.model_change' and not agent:
                apply_model_transition(coordinator, payload, False)
            elif kind == 'tool.execution_start' and not agent:
                call_id = payload['toolCallId']
                t.require(call_id not in calls, 'Duplicate Copilot tool call')
                calls[call_id] = (event, when)
            continue
        if not boundary_initialized:
            # The header may be hours old. Pins compare the actual effective
            # context at the seal and every later transition, not old choices.
            coordinator['models'] = {coordinator['model']}
            coordinator['efforts'] = {coordinator['effort']}
            boundary_initialized = True
        if kind == 'session.model_change':
            t.require(current is not None, 'Native model transition lacks its agent identity')
            if agent:
                t.require(when >= current['start'] and (current['end'] is None or when <= current['end']),
                          'Copilot model transition is outside its task lifecycle')
            apply_model_transition(current, payload, True)
        elif kind == 'session.context_changed':
            t.require(Path(payload.get('cwd', '')).resolve() == project,
                      'Copilot session changed to a different workspace')
        elif kind == 'tool.execution_start':
            if agent:
                t.require(current is not None and when >= current['start']
                          and (current['end'] is None or when <= current['end']),
                          'Copilot child tool is outside its actual task lifecycle')
            call_id = payload.get('toolCallId')
            t.require(isinstance(call_id, str) and call_id not in calls, 'Duplicate Copilot tool call')
            calls[call_id] = (event, when)
            if len(calls) > MAX_NATIVE_PENDING_CALLS or len(dispatch) > MAX_NATIVE_PENDING_CALLS:
                raise HostEvidenceUnavailable('Native trace pending lifecycle limit exceeded')
            if current and payload.get('model'):
                current['models'].add(payload['model'])
            if payload.get('toolName') == 'task' and not agent:
                dispatch[call_id] = payload
        elif kind == 'subagent.started':
            call_id = payload.get('toolCallId')
            args = dispatch.pop(call_id, {}).get('arguments', {})
            label = args.get('name') if isinstance(args, dict) else None
            t.require(label and label == payload.get('agentDisplayName') and label not in rows
                      and isinstance(agent, str) and agent not in by_agent and agent != parent,
                      'Copilot subagent lacks a unique originating named task')
            current = row(agent, when, payload.get('model'))
            current['dispatch_call'] = call_id
            current['turn_starts'].append(when)
            current['active'] = when
            by_agent[agent], rows[label] = current, current
        elif kind == 'subagent.configured':
            t.require(current is not None and agent, 'Copilot subagent configuration lacks identity')
            current['model'], current['effort'] = payload.get('model'), payload.get('reasoningEffort')
            current['models'].update(filter(None, [current['model']]))
            current['efforts'].update(filter(None, [current['effort']]))
        elif kind in ('subagent.completed', 'subagent.failed'):
            t.require(current is not None and agent and payload.get('toolCallId') == current['dispatch_call']
                      and current['end'] is None and when >= current['start'], 'Invalid Copilot subagent completion')
            current['end'] = when
            current['active'] = None
            current['intervals'].append((current['start'], when))
            current['failed'] = kind == 'subagent.failed'
        elif kind == 'assistant.turn_start' and not agent:
            coordinator['active'] = when
            coordinator['turn_starts'].append(when)
        elif kind == 'assistant.turn_end' and not agent:
            if coordinator['active'] is not None:
                coordinator['intervals'].append((coordinator['active'], when))
                coordinator['active'] = None
        elif kind == 'tool.execution_complete':
            original = calls.pop(payload.get('toolCallId'), None)
            t.require(original is not None, 'Copilot completion lacks its original tool call')
            request, started = original
            t.require(request.get('agentId') == agent and when >= started and current is not None,
                      'Copilot tool completion changed agent identity/order')
            if agent:
                t.require(payload.get('parentToolCallId') == current['dispatch_call']
                          and request['data'].get('parentToolCallId') == current['dispatch_call'],
                          'Copilot child tool belongs to a different task')
            if payload.get('success') is not True:
                continue
            edits = payload.get('fileEdits', [])
            t.require(isinstance(edits, list), 'Invalid Copilot committed file edits')
            for edit in edits:
                if not isinstance(edit, dict) or edit.get('kind') not in {'create', 'edit', 'delete'}:
                    raise HostEvidenceUnavailable('Unsupported Copilot file edit kind')
                target = Path(edit.get('path', ''))
                t.require(target.is_absolute() and target.resolve().is_relative_to(project),
                          'Copilot file edit escaped project')
                current['writes'].append((when, t.product_key(target.resolve().relative_to(project).as_posix())))
            call = request['data']
            args = call.get('arguments', {})
            command = args.get('command') if isinstance(args, dict) else None
            if (started >= since and call.get('toolName') in {'powershell', 'bash'} and isinstance(command, str)
                    and t.team_command(command) and payload.get('shellExecution', {}).get('exitCode') == 0):
                result = payload.get('result', {})
                # Never search assistant prose, call arguments, or partial stdout for receipts.
                content = result.get('content', '') if isinstance(result, dict) else ''
                if isinstance(content, str):
                    for digest in t.re.findall(r'^' + t.RECEIPT + r'([0-9a-f]{64})\s*$', content, t.re.M):
                        current['markers'].setdefault(digest, when)
    if not boundary_initialized:
        coordinator['models'], coordinator['efforts'] = {coordinator['model']}, {coordinator['effort']}
    return rows


def copilot_adapter(project, state, parent, sessions, require_qa):
    rows = read_copilot_traces(project, parent, sessions, common().instant(state['created']))
    return verify_native_rows(project, state, parent, rows, require_qa, 'copilot-session-events-v1')


def verify_native_rows(project, state, parent, rows, require_qa, adapter):
    t = common()
    created = t.instant(state['created'])
    plan = state['plan']
    tasks = {r['id']: r for r in plan['tasks']}
    coordinator = rows['integration']
    for role, source in rows.items():
        for declared, observed in [('model', 'model'), ('reasoning_effort', 'effort')]:
            if declared in plan:
                values = source.get('models' if observed == 'model' else 'efforts', {source[observed]})
                t.require(values == {plan[declared]}, role + ': native ' + declared + ' differs from plan')
    glue = {t.product_key(x) for x in plan['integration']['outputs']}
    t.require(not any(not rel.startswith(proof.STATE + '/') and rel not in glue
                      for _, rel in coordinator['writes']), 'Coordinator wrote outside its integration scope')
    for role, source in rows.items():
        if role not in {'integration', 'qa', *tasks}:
            t.require(not any(not rel.startswith(proof.STATE + '/') for _, rel in source['writes']),
                      role + ': unassigned agent wrote product files')
    builds, handoffs = {}, {}
    for tid, task in tasks.items():
        t.require(tid in rows, tid + ': missing native worker')
        row, receipt = rows[tid], usable_handoff(project, state, tid)
        t.require(row['id'] != parent and row['start'] >= created, tid + ': wrong native identity/start')
        t.require(not row.get('failed'), tid + ': native worker failed')
        t.require_receipt_turn_finished(row, [receipt], tid)
        at = t.receipt_event(row, receipt, tid)
        t.require(row['end'] and t.completed_receipt(row, at), tid + ': worker turn has not completed')
        allowed = {t.product_key(x) for x in task['outputs']}
        all_writes = {rel for _, rel in row['writes'] if not rel.startswith(proof.STATE + '/')}
        writes = {rel for when, rel in row['writes'] if when <= at and not rel.startswith(proof.STATE + '/')}
        changed = {t.product_key(rel) for rel, digest in receipt['files'].items()
                   if state['baseline'][rel] != digest}
        t.require(all_writes <= allowed and changed <= writes, tid + ': native writes do not establish owned changes')
        handoffs[tid] = (row, at, receipt)
        builds[tid] = {'id': row['id'], 'model': row['model'], 'effort': row['effort'],
                       'files': task['outputs'], 'receipt': receipt['sha256']}
    t.require(len({r['id'] for r, _, _ in handoffs.values()}) == len(tasks), 'Owners reused one native session')
    overlap = []
    for tid, (row, at, _) in handoffs.items():
        for dep in tasks[tid]['depends_on']:
            t.require(t.turn_start(row, at) >= handoffs[dep][1], tid + ': started before prerequisite handoff')
    for a, b in independent_pairs(tasks):
        if t.completed_overlap(handoffs[a][0], handoffs[b][0]):
            overlap.append([a, b])
    if plan.get('max_parallel_workers', 1) > 1 and independent_pairs(tasks):
        t.require(overlap, 'Declared available parallel workers were not used on independent scopes')
    if require_qa:
        integrated, check, qa = (current_receipt(project, state, x) for x in ('integration', 'check', 'qa'))
        when = t.receipt_event(coordinator, integrated, 'integration')
        t.require(when >= max(at for _, at, _ in handoffs.values()), 'Integration preceded owner handoffs')
        changed_glue = {t.product_key(x) for x in plan['integration']['outputs']
                        if state['baseline'][x] != integrated['files'][x]}
        glue_writes = {rel for at, rel in coordinator['writes'] if at <= when}
        t.require(changed_glue <= glue_writes, 'Integration changes lack native write evidence')
        t.require('qa' in rows, 'Missing native QA worker')
        reviewer = rows['qa']
        t.require(not reviewer.get('failed'), 'Native QA worker failed')
        t.require(reviewer['id'] not in {parent, *(v['id'] for v in builds.values())}, 'QA is not independent')
        t.require_receipt_turn_finished(reviewer, [check, qa], 'qa')
        check_at, qa_at = t.receipt_event(reviewer, check, 'QA check'), t.receipt_event(reviewer, qa, 'QA')
        t.require(reviewer['end'] and t.turn_start(reviewer, check_at) >= when
                  and check_at <= qa_at and t.completed_receipt(reviewer, qa_at), 'QA has wrong order or incomplete turn')
        t.require(not any(not rel.startswith(proof.STATE + '/') for _, rel in reviewer['writes']),
                  'QA edited product source')
    return {'status': 'PASS', 'adapter': adapter, 'workers': builds,
            'overlap': overlap, 'independent_qa': require_qa,
            'limitation': 'Cooperative local host records, not a hostile-writer security boundary.'}


def verify_registered(project, team_id, *, require_qa=True, parent=None, sessions=None, **unused):
    t = common()
    try:
        project = Path(project).resolve()
        state = load_state(project, team_id)
        verify_structural(project, state, require_qa)
        kind = state['plan'].get('host', {}).get('kind', 'unverified')
        path = t.team_path(project, team_id, 'host.json', must_exist=False)
        selected = proof.load(path) if path.is_file() else {}
        if parent is None:
            parent = (selected['parent'] if selected
                      else t.os.environ.get('CODEX_THREAD_ID') if kind == 'codex'
                      else os.environ.get('HARRTEST_PARENT_SESSION_ID') if kind == 'copilot' else None)
        if sessions is None and selected.get('parent') == parent:
            sessions = selected.get('sessions')
        if kind == 'unverified' or (kind == 'copilot' and parent is None):
            return {'passed': False, 'status': 'UNVERIFIED', 'structural_passed': True,
                    'team': team_id, 'errors': ['Native ' + kind + ' provenance is not established by a supported adapter'],
                    'host_assurance': {'status': 'UNVERIFIED', 'host': kind}, 'mission_complete': False}
        host = (copilot_adapter if kind == 'copilot' else codex_adapter)(project, state, parent, sessions, require_qa)
        return {'passed': True, 'status': 'PASS', 'team': team_id,
                'structural_passed': True, 'host_assurance': host, 'independent_qa': require_qa}
    except HostEvidenceUnavailable as exc:
        return {'passed': False, 'status': 'UNVERIFIED', 'team': team_id,
                'structural_passed': True, 'errors': [str(exc)], 'mission_complete': False,
                'host_assurance': {'status': 'UNVERIFIED'}}
    except t.NativeTurnPending as exc:
        return {'passed': False, 'status': 'pending-native-turn', 'team': team_id,
                'errors': [str(exc)], 'retryable': True, 'pending_workers': [exc.worker],
                'mission_complete': False}
    except (ValueError, TypeError, KeyError, AttributeError, OSError, proof.ProofError) as exc:
        return {'passed': False, 'status': 'FAIL', 'team': team_id, 'errors': [str(exc)]}
