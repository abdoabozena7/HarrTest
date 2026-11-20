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
MAX_DETAIL_ARTIFACTS = 64
MAX_DETAIL_ARTIFACT_BYTES = 64 * 1024 * 1024
COPILOT_COVERAGE_REVIEW = 'coverage_review'
COPILOT_QA_RECOVERY = 'qa-recovery'


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
    reviewed = plan.get('decomposition') == 'reviewed-v1'
    t.require('decomposition' not in plan or reviewed, 'Unknown Team decomposition policy')
    if 'root_protocol' in plan:
        t.require(plan['root_protocol'] == 'corporate-v1' and reviewed,
                  'Team root_protocol corporate-v1 requires reviewed-v1 decomposition')
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
        reserved = {'qa', 'check', 'integration'} | ({'plan_review'} if reviewed else set())
        t.require(tid not in tasks and tid not in reserved, 'Duplicate/reserved owner')
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
    if 'detail_review' in integration:
        details = integration['detail_review']
        t.require(isinstance(details, dict) and 0 < len(details) <= MAX_DETAIL_ARTIFACTS,
                  'Declare a bounded set of required detail review criteria')
        for rid, criterion in details.items():
            proof.identifier(rid, 'Detail review ID')
            t.concrete(criterion, rid + ' observable detail criterion')
    glue = integration.get('outputs')
    t.require(isinstance(glue, list), 'Integration outputs must be an explicit list; [] is valid')
    if glue:
        owned.extend(t.file_list(project, glue, 'integration'))
    t.require(not any(strict_io.overlaps(a, b) for i, a in enumerate(owned) for b in owned[i + 1:]),
              'Each product path needs exactly one owner')
    t.ancestors(tasks)
    capacity = plan.get('max_parallel_workers', 1)
    t.require(type(capacity) is int and 1 <= capacity <= 128,
              'Invalid planned worker capacity' if reviewed else 'Invalid observed worker capacity')
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
    if reviewed:
        validate_decomposition(plan, tasks, owned)
    return tasks, owned


def validate_decomposition(plan, tasks, owned):
    t = common()
    sources = set(owned) | set(plan.get('validation_context', []))
    if len(tasks) == 1:
        t.concrete(plan.get('scope_rationale'), 'Explain why one implementation responsibility is sufficient')
    for tid, task in tasks.items():
        for field in ('responsibility', 'interface', 'check'):
            t.concrete(task.get(field), f'{tid}: define {field}')
        refs = task.get('scope_evidence')
        t.require(isinstance(refs, list) and refs and all(isinstance(ref, str) and ref in sources for ref in refs)
                  and len(refs) == len(set(refs)) <= t.MAX_VALIDATION_FILES,
                  tid + ': cite distinct paths bound by the old owned files or validation context')
        reasons = task.get('dependency_rationale', {})
        t.require(isinstance(reasons, dict) and set(reasons) == set(task['depends_on']),
                  tid + ': explain why each declared predecessor needs to finish first')
        for dep, reason in reasons.items():
            t.concrete(reason, f'{tid}: dependency on {dep}')


def independent_pairs(tasks):
    parents = common().ancestors(tasks)
    return [(a, b) for i, a in enumerate(tasks) for b in list(tasks)[i + 1:]
            if a not in parents[b] and b not in parents[a]]


def copilot_corporate_plan(plan):
    return (plan.get('root_protocol') == 'corporate-v1' and plan.get('host', {}).get('kind') == 'copilot')


def draft_state(project, plan, **revision):
    t = common()
    tasks, owned = validate_plan(project, plan)
    if copilot_corporate_plan(plan):
        t.require(COPILOT_COVERAGE_REVIEW not in tasks, 'Reserved Corporate coverage reviewer name')
    validation_inputs = t.validation_snapshot(project, plan)
    root = Path(project).resolve()
    outputs = {rel: (root / rel).resolve() for rel in owned}
    for context in validation_inputs:
        path = (root / context).resolve()
        for rel, output in outputs.items():
            t.require(not (path.is_relative_to(output) or output.is_relative_to(path)),
                      f'validation_context file {context} overlaps owned output {rel}. '
                      'Keep validation context unchanged. If the output needs editing, keep its '
                      'original baseline and checks as separate evidence.')
    baseline = t.snapshot(project, owned)
    if plan.get('decomposition') == 'reviewed-v1':
        for tid, task in tasks.items():
            t.require(all(validation_inputs.get(ref) or baseline.get(ref) for ref in task['scope_evidence']),
                      tid + ': scope evidence needs an existing source file before implementation')
    if plan['kind'] == 'greenfield':
        t.require(not any(baseline.values()), 'Seal greenfield scopes before product creation')
    for task in tasks.values():
        for rel in deleted_paths(task):
            t.require(baseline[rel] is not None, 'Deleted/renamed source must exist at baseline: ' + rel)
        for move in task.get('renames', []):
            t.require(baseline[move['to']] is None, 'Rename destination must be absent at baseline')
    state = {'plan': plan, 'plan_sha256': strict_io.digest(plan), 'baseline': baseline,
             'created': proof.now(), 'validation_inputs': validation_inputs, **revision}
    state['state_sha256'] = strict_io.digest(state)
    return state


def initial_packets(project, state):
    plan = state['plan']
    if plan.get('decomposition') == 'reviewed-v1':
        return {'team': plan['id'], 'schema': 2, 'plan_sha256': state['plan_sha256'],
                'plan_review': plan_review_packet(project, state), 'ready': []}
    return {'team': plan['id'], 'schema': 2, 'plan_sha256': state['plan_sha256'],
            'ready': [packet(project, state, row) for row in plan['tasks'] if not row['depends_on']]}


def init(project, plan):
    state = draft_state(project, plan)
    proof.save(common().team_path(project, plan['id'], must_exist=False), state, exclusive=True)
    return initial_packets(project, state)


def revise_plan(project, draft):
    """Keep the original request and rejected revision; reopen pre-edit planning only."""
    t = common()
    plan = t.request_from_root(project, draft, revising=True)
    team_id = plan['id']
    enrolled = os.environ.get('HARRTEST_CORPORATE_GOAL')
    t.require(not enrolled or enrolled == team_id, 'Keep the enrolled Corporate goal ID')
    path = t.team_path(project, team_id)
    with proof.latest_guard(path.parent):
        state = load_state(project, team_id)
        original = state['plan']
        t.require(copilot_corporate_plan(original) and copilot_corporate_plan(plan)
                  and all(plan.get(k) == original.get(k) for k in ('kind', 'request', 'host', 'model', 'reasoning_effort')),
                  'A revision must keep the original Copilot Corporate request, kind and host pins')
        goal = strict_io.scoped_path(project, f'{proof.STATE}/root-goals/{team_id}')
        t.require(not t.team_path(project, team_id, 'corporate-dispatch.json', must_exist=False).exists()
                  and not any((goal / name).exists() for name in ('root-seal.json', 'corporate-report.json')),
                  'An admitted or sealed Corporate plan cannot be revised')
        t.require(not any((goal / name).exists() for name in (
            'root-contract.json', 'corporate-plan.json', 'coverage-review.json')),
            'Retain the unsealed Corporate drafts separately before revising the Team')
        t.require(t.receipt_path(project, state, 'plan_review').is_file(),
                  'Record the rejected review before revising the Team')
        rejected = current_receipt(project, state, 'plan_review')
        t.require(rejected['verdict'] == 'fail' and rejected['state'] == state['state_sha256'],
                  'Only the current rejected plan can be revised')
        t.require(t.snapshot(project, state['baseline']) == state['baseline'],
                  'Keep the original implementation baseline when revising the Team')
        t.require(strict_io.digest(plan) != state['plan_sha256'], 'Correct the rejected plan before revising it')
        updated = draft_state(project, plan, revision=state.get('revision', 1) + 1,
                              previous_state_sha256=state['state_sha256'])
        archive = t.team_path(project, team_id, f'revisions/{state["state_sha256"]}.json', must_exist=False)
        history = {'state': state, 'review': rejected}
        if archive.exists():
            t.require(proof.load(archive) == history, 'Retained Team revision differs from the rejected plan')
        else:
            proof.save(archive, history, exclusive=True)
        proof.save(path, updated)
    return {**initial_packets(project, updated), 'revision': updated['revision'],
            'rejected_review_sha256': rejected['sha256']}


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


def revision_origin(project, state):
    t = common()
    team_id = state['plan']['id']
    start = t.instant(state['created'])
    while state.get('revision', 1) > 1:
        previous = state['previous_state_sha256']
        t.require(t.re.fullmatch('[0-9a-f]{64}', previous), 'Invalid previous Team state identity')
        history = proof.load(t.team_path(project, team_id, f'revisions/{previous}.json'))
        old = history['state']
        t.require(old['state_sha256'] == previous == strict_io.digest(
            {key: value for key, value in old.items() if key != 'state_sha256'})
            and old['plan']['id'] == team_id and old.get('revision', 1) == state['revision'] - 1,
            'Retained Team revision differs from the original state')
        review = current_receipt(project, old, 'plan_review')
        original_start = t.instant(old['created'])
        t.require(review == history['review'] and review['state'] == previous and review['verdict'] == 'fail'
                  and original_start <= t.instant(review['at']) <= start,
                  'Retained Team revision lacks its original rejection')
        state, start = old, original_start
    return start


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


def dispatch_packet(plan, task_name, message):
    result = {'task_name': task_name, 'fork_turns': 'none', 'message': message}
    if plan.get('host', {}).get('kind') == 'copilot':
        result['dispatch_note'] = (
            'For an initial Copilot dispatch when this actor may need follow-up, use task with '
            'mode: background. Retain the returned agent_id and use read_agent with wait: true. '
            'For repair or re-review, send the complete message with write_agent to the original '
            'agent_id, then wait for that ID with read_agent.')
    return result


def plan_review_packet(project, state):
    packet = plan_review_brief(project, state)
    if 'revision' in state:
        command = common().worker_command(project, state['plan']['id'], 'review-brief')
        packet['message'] = (f'Run {command} --revision {state["revision"]}\n'
                             'Follow the returned review instructions. Keep product files read-only.')
    return packet


def plan_review_brief(project, state):
    t = common()
    plan = state['plan']
    path = t.team_path(project, plan['id']).as_posix()
    evidence = t.plan_review_evidence(state)
    command = t.worker_command(project, plan['id'], 'review-plan')
    split_check = ''
    if plan.get('root_protocol') == 'corporate-v1' or plan['kind'] == 'greenfield':
        split_check = ('Compare the owner map against the nearest viable split within each major scope. '
                       'Ask which part could deliver a distinct artifact with disjoint writes, a stable interface and '
                       'its own check while another owner works. A final integration test does not block either part. '
                       'Reject a missing implementation scope when splitting gives a significant requested part its '
                       'own deliverable and improves ownership or independent validation. Explain what a handoff '
                       'would add beyond a focused check within the existing scope. Separately flag criteria missing '
                       'from otherwise coherent scopes; add a focused check or reviewer when another writer would '
                       'only split a file, shared write path or coupled invariant. '
                       'A reviewer is not an implementation owner. Keep product files read-only. ')
    if plan['kind'] == 'greenfield':
        split_check += ('In the same review, challenge the proposed finishing brief against the original request. '
                        'For each major component, name a plausible unfinished result and the observed criterion '
                        'that would reject it. Return fail for any unresolved gap. Record the intent judgments '
                        'alongside the ownership findings; do not treat a file list as a finishing criterion. ')
    if plan['integration'].get('detail_review'):
        split_check += ('Check the sealed detail_review IDs against the brief. Reject an omitted consequential '
                        'detail, missing view or state, or criterion that can pass without an actual observation. ')
    message = (f'Review the sealed decomposition independently before implementation. Read {path}.\n'
               f'Plan SHA-256 {state["plan_sha256"]}; baseline/state SHA-256 {state["state_sha256"]}.\n'
               'Inspect the actual project contracts, affected consumers and each scope_evidence path. '
               'For each owner verify the responsibility, preserved interface, exact owned files, '
               'outcomes and independent check against those sources. Find missing responsibilities '
               'or independent components grouped into one owner. A narrow responsibility may span '
               f'multiple files. Confirm any single-scope and dependency rationales. {split_check}'
               'The coordinator owns integration and only its declared output paths. Check the planned '
               'interfaces and handoffs into that scope; do not require a separate integration owner. '
               'Check the planned worker width against available native dispatch and known runtime limits. Use that '
               'capability evidence at plan review. The ready list can exceed the evidenced width; run bounded waves. '
               'Actual owner overlap is verified after dispatch. '
               'Serial independent work needs a documented host cap, rejected '
               'simultaneous dispatch or another observed constraint. Record each judgment with the '
               'source location and why it supports the scope. '
               f'Keep the evidence at most {t.MAX_PACKET_CHARS} characters: use short, source-backed findings '
               'instead of copying the plan, and combine a scope and its finishing counterexample where useful. '
               f'Write your observations to {evidence}. Use this literal project-relative evidence path. '
               'Record fail if a required scope, source or justification is missing. '
               'Run the following review command by itself after saving evidence. Replace VERDICT '
               'with pass or fail based on the observations:\n'
               f'{command} --evidence {evidence} --verdict VERDICT')
    packet = {'task_name': 'plan_review', 'fork_turns': 'none', 'message': message}
    if plan.get('host', {}).get('kind') == 'copilot':
        packet['dispatch_note'] = ('Select a Copilot reviewer that can run commands and write private evidence. '
                                   'Use an available general-purpose agent if the built-in task worker restricts writes. '
                                   'Where independent owner scopes are planned, available task background dispatch can '
                                   'support the planned width. Verify actual overlap after implementation.')
    return packet


def packet(project, state, task, *, admission=None):
    t = common()
    plan, tid = state['plan'], task['id']
    if admission is None:
        admission = corporate_admission(project, state)
    text = (f'You own implementation scope {tid}. Project: {Path(project).resolve().as_posix()}.\n'
            f'Pinned HarrTest: {Path(__file__).resolve().parents[1].as_posix()}.\n'
            f'Original request: {plan["request"]}\nExisting architecture/interfaces: {plan["contract"]}\n'
            f'{t.validation_message(project, state)}Assignment: {task["brief"]}\n'
            f'Exclusive product paths: {", ".join(task["outputs"])}.\n'
            f'Declared removals: {sorted(deleted_paths(task))}; renames: {task.get("renames", [])}.\n'
            'Preserve existing contracts and unrelated behavior. Use the actual host editing tools; '
            'do not invent native identity or verification. Read prerequisite handoffs and supplied '
            'acceptance/risk criteria. Implement and test only your scope; return boundary conflicts '
            'to the coordinator. Use the project’s documented checks and runtime with its approved '
            'workspace scratch directory if needed. Report observed results or exact blockers.\n'
            'Acceptance:\n' + '\n'.join(f'- {x}: {plan["outcomes"][x]}' for x in task['outcomes']) + '\n'
            'Run this handoff command with its exact script path and flags:\n'
            + t.worker_command(project, plan['id'], 'handoff') + ' --task ' + tid)
    if plan.get('decomposition') == 'reviewed-v1':
        text += (f'\nReviewed responsibility: {task["responsibility"]}\n'
                 f'Interface: {task["interface"]}\nIndependent component check: {task["check"]}\n'
                 f'Reviewed sources: {", ".join(task["scope_evidence"])}')
    if admission:
        text += f'\nCorporate root seal SHA-256: {admission["binding"]["seal_sha256"]}.'
    repair = pending_repair(project, state, tid)
    if repair:
        text += (f'\nRepair current finding: {repair["observation"]}. '
                 f'Read immutable evidence {next(iter(repair["files"]))}; retain the failed attempt. '
                 'Diagnose in your owned scope, rerun affected checks, then hand off again.')
    return dispatch_packet(plan, tid, text)


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


def review_plan(project, state, evidence, verdict):
    t = common()
    plan = state['plan']
    t.require(plan.get('decomposition') == 'reviewed-v1', 'Plan review requires reviewed-v1 decomposition')
    t.require(verdict in {'pass', 'fail'}, 'Plan review verdict must be pass or fail')
    t.validation_message(project, state)
    t.require(t.snapshot(project, state['baseline']) == state['baseline'],
              'Review the sealed baseline before any product edit')
    prefix = f'{proof.STATE}/teams/{plan["id"]}/'
    t.require(evidence.startswith(prefix), 'Keep plan review evidence in the private team directory')
    if 'revision' in state:
        t.require(evidence == t.plan_review_evidence(state),
                  'Use the current revision-specific plan review evidence path')
    path = strict_io.scoped_path(project, evidence)
    t.require(path.is_file() and 0 < path.stat().st_size <= t.MAX_VALIDATION_FILE_BYTES,
              'Missing bounded plan review evidence')
    body = path.read_bytes()
    t.concrete(body.decode('utf-8-sig'), 'Independent plan review observations')
    digest = hashlib.sha256(body).hexdigest()
    retained = f'{prefix}plan-review-evidence/{digest}.txt'
    destination = strict_io.scoped_path(project, retained, must_exist=False)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open('xb') as saved:
            saved.write(body)
    except FileExistsError:
        pass
    t.require(proof.file_hash(destination) == digest, 'Retained plan review evidence changed')
    receipt = {'id': 'plan_review', 'plan': state['plan_sha256'], 'files': {retained: digest},
               'state': state['state_sha256'], 'verdict': verdict, 'at': proof.now()}
    receipt['sha256'] = strict_io.digest(receipt)
    proof.save(t.receipt_path(project, state, 'plan_review'), receipt, exclusive=True)
    return receipt


def approved_decomposition(project, state):
    if state['plan'].get('decomposition') != 'reviewed-v1':
        return None
    t = common()
    path = t.receipt_path(project, state, 'plan_review')
    t.require(path.is_file(), 'Independent plan review is required before dispatch')
    receipt = current_receipt(project, state, 'plan_review')
    t.require(receipt.get('verdict') == 'pass' and receipt.get('state') == state['state_sha256'],
              'Independent plan review failed or is stale; retain it and review a corrected plan')
    return receipt


def corporate_admission(project, state, *, issue=False):
    if state['plan'].get('root_protocol') != 'corporate-v1':
        return None
    import root_gate

    t = common()
    path = t.team_path(project, state['plan']['id'], 'corporate-dispatch.json', must_exist=False)
    exists = path.is_file()
    t.require(exists or issue, 'Use Team packets to admit the sealed Corporate root before dispatch')
    binding = root_gate.require_corporate_dispatch(project, state, baseline_current=not exists)
    if not exists:
        admission = {'binding': binding, 'admitted_at': proof.now()}
        admission['sha256'] = strict_io.digest(admission)
        try:
            proof.save(path, admission, exclusive=True)
        except FileExistsError:
            pass  # A concurrent caller may have admitted the same immutable root.
    admission = proof.load(path)
    digest = admission.pop('sha256')
    t.require(strict_io.digest(admission) == digest and admission['binding'] == binding,
              'Corporate dispatch admission differs from the current root seal')
    t.require(t.instant(admission['admitted_at']) >= t.instant(binding['sealed_at']),
              'Corporate dispatch admission predates the root seal')
    return {**admission, 'sha256': digest}


def handoff(project, state, task):
    t = common()
    t.validation_message(project, state)
    admission = corporate_admission(project, state)
    files = t.snapshot(project, task['outputs'])
    deleted = deleted_paths(task)
    for rel, digest in files.items():
        t.require((digest is None) == (rel in deleted), 'Only declared deletions may be absent: ' + rel)
    t.require(any(value != state['baseline'][rel] for rel, value in files.items()),
              task['id'] + ': handoff must contain an actual change')
    inputs = {dep: usable_handoff(project, state, dep, admission=admission)['sha256'] for dep in task['depends_on']}
    extra = {}
    review = approved_decomposition(project, state)
    if review:
        extra['plan_review'] = review['sha256']
    if admission:
        extra['root_seal_sha256'] = admission['binding']['seal_sha256']
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


def usable_handoff(project, state, tid, *, admission=None):
    t = common()
    t.validation_message(project, state)
    if admission is None:
        admission = corporate_admission(project, state)
    t.require(not pending_repair(project, state, tid), tid + ': owner repair remains open')
    task = next(r for r in state['plan']['tasks'] if r['id'] == tid)
    receipt = current_receipt(project, state, tid)
    review = approved_decomposition(project, state)
    if review:
        t.require(receipt.get('plan_review') == review['sha256'], tid + ': handoff lacks the current plan review')
    if admission:
        t.require(receipt.get('root_seal_sha256') == admission['binding']['seal_sha256'],
                  tid + ': handoff lacks the admitted Corporate root seal')
    t.require(set(receipt['files']) == set(task['outputs']), tid + ': receipt scope differs from sealed owner')
    deps = {d: usable_handoff(project, state, d, admission=admission)['sha256'] for d in task['depends_on']}
    t.require(receipt.get('inputs') == deps, tid + ': stale prerequisite handoff')
    return receipt


def ready_packets(project, state):
    t = common()
    t.validation_message(project, state)
    if state['plan'].get('decomposition') == 'reviewed-v1':
        path = t.receipt_path(project, state, 'plan_review')
        if not path.is_file() or current_receipt(project, state, 'plan_review').get('verdict') == 'fail':
            return []
        approved_decomposition(project, state)
    admission = corporate_admission(project, state, issue=True)
    ready = []
    for row in state['plan']['tasks']:
        try:
            for dep in row['depends_on']:
                usable_handoff(project, state, dep, admission=admission)
        except (ValueError, proof.ProofError):
            continue
        try:
            usable_handoff(project, state, row['id'], admission=admission)
        except (ValueError, proof.ProofError):
            ready.append(packet(project, state, row, admission=admission))
    return ready


def integrate(project, state):
    t = common()
    t.validation_message(project, state)
    plan = state['plan']
    admission = corporate_admission(project, state)
    children = {r['id']: usable_handoff(project, state, r['id'], admission=admission) for r in plan['tasks']}
    receipt = record(project, state, 'integration', t.snapshot(project, state['baseline']),
                     inputs={tid: row['sha256'] for tid, row in children.items()})
    return receipt, qa_packet(project, state, receipt)


def qa_packet(project, state, receipt):
    t = common()
    plan = state['plan']
    details = plan['integration'].get('detail_review')
    suffix = 'json' if details else 'txt'
    evidence = f'{proof.STATE}/teams/{plan["id"]}/qa-evidence.{suffix}'
    command = t.worker_command(project, plan['id'], 'check')
    review_command = t.worker_command(project, plan['id'], 'review')
    boundary = ', '.join(sorted(state['baseline']))
    message = (f'You are independent QA. Project: {Path(project).resolve().as_posix()}.\n'
               f'Original request: {plan["request"]}\nShared contract: {plan["contract"]}\n'
               f'{t.validation_message(project, state)}Integrated receipt: {receipt["sha256"]}.\n'
               f'Sealed implementation and integration paths: {boundary}.\n'
               f'Acceptance check: {plan["integration"]["check"]}\n'
               'Inspect the full diff from the recorded pre-edit baseline, including additions and removals. '
               'Check the applicable project write restrictions before a long runtime check. Do not ignore '
               'an unauthorized change merely because it does not affect output. Then test the actual behavior independently. Cover applicable '
               'functionality, preservation, architecture, security, performance and failure/data risks. '
               'Derive expected results from the agreed contract. Cover affected input controls, '
               'including optional ones, and assert relevant state for rejected operations. '
               'Compare execution order at changed boundaries: if work moved ahead of parsing, '
               'validation, a no-op, or an empty loop, replay those paths on baseline and candidate. '
               'Replay apparent inherited failures on the baseline before judging their impact on this request. '
               'Retain failures. Missing checks are UNVERIFIED, '
               'not PASS. Record each quality layer as PASS, FAIL, UNVERIFIED or NOT_APPLICABLE; '
               'retain failed and unverified observations. NOT_APPLICABLE needs an impact rationale '
               'and supporting evidence reviewed independently. Do not omit required layers or '
               'turn a missing measurement into an applicability exclusion. Leave product files and '
               'the contract intact. Run the documented project checks on this source. Use the '
               'approved runtime and workspace-local scratch path for temporary files. Run a finite '
               'check with assertions yourself and use this exact Team command prefix:\n'
               f'{command} -- ACTUAL_ARGV\nReplace ACTUAL_ARGV with the real executable and arguments '
               'for the check. The collector runs them directly from the project and manages its '
               'subprocess. If access or an executable is missing, record the exact blocker and '
               f'retain any results. Write observations to {evidence} if authorized. Use the exact '
               'project-relative forward-slash --evidence path below, including on Windows.\n'
               f'{review_command} --evidence {evidence} --verdict pass\nUse pass only if the required '
               'checks pass. Otherwise submit fail with the available evidence. Report and release '
               'any separate service or resource you actually started. '
               'A successful receipt proves the recorded process, not semantic correctness or native identity.')
    if details:
        message += (
            '\n\nRequired detail review (in addition to the user journey):\n'
            + '\n'.join(f'- {rid}: {criterion}' for rid, criterion in details.items())
            + '\nThe finite check must capture actual observations in its fresh PROVE_IT_OUTPUT_DIR. '
              'Use flat file names. Open and inspect the captured frames, motion samples or other artifacts '
              'on the current product. Do not reuse older captures. Review each ID independently, including '
              'any shorter-lived state or subtle defect the criterion names. Save the JSON observations '
              'with check_sha256 from the check receipt, observations for all quality layers, and details '
              'keyed by ID. Each row has verdict (pass, fail, or unverified), observation, and artifacts '
              '(a list of file names captured by that check). Find the captures next to the retained '
              'check-NAME.json in the check-NAME directory. A missing or unresolved row cannot pass.'
        )
    packet = dispatch_packet(plan, 'qa', message)
    if plan.get('host', {}).get('kind') == 'copilot':
        packet['dispatch_note'] += (
            ' After a Copilot reconnect, if write_agent reports that the original QA actor is not found, '
            f'dispatch one new read-only worker named {COPILOT_QA_RECOVERY} with this same current message. '
            'Retain the original evidence. The replacement must run the current checks and review itself.')
    return packet


def runtime_check(project, state, argv):
    t = common()
    t.validation_message(project, state)
    integrated = current_receipt(project, state, 'integration')
    t.require(isinstance(argv, list) and argv and all(isinstance(x, str) and x for x in argv),
              'Supply actual executable argv after --')
    private = t.team_path(project, state['plan']['id']).parent
    name = f'check-{uuid4().hex}'
    details = state['plan']['integration'].get('detail_review')
    env = None
    if details:
        captures = t.team_path(project, state['plan']['id'], name, must_exist=False)
        captures.mkdir()
        env = {**os.environ, 'PROVE_IT_OUTPUT_DIR': str(captures)}
    started = proof.now()
    timeout = state['plan']['integration'].get('timeout_seconds', 120)
    spawn_error, timed_out, overflow = None, False, False
    with tempfile.TemporaryFile(dir=private) as stdout, tempfile.TemporaryFile(dir=private) as stderr:
        process = None
        try:
            options = ({'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt'
                       else {'start_new_session': True})
            process = subprocess.Popen(argv, cwd=project, stdin=subprocess.DEVNULL, stdout=stdout,
                                       stderr=stderr, shell=False, env=env, **options)
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
    filename = name + '.json'
    path = t.team_path(project, state['plan']['id'], filename, must_exist=False)
    proof.save(path, {'argv': argv, 'cwd': str(Path(project).resolve()), 'exit_code': code,
                     'started_at': started, 'finished_at': proof.now(), 'timed_out': timed_out,
                     'overflow': overflow, 'spawn_error': spawn_error, 'source_unchanged': source_unchanged,
                     'stdout': out[:proof.MAX_LOG_BYTES].decode('utf-8', errors='replace'),
                     'stderr': err[:proof.MAX_LOG_BYTES].decode('utf-8', errors='replace')}, exclusive=True)
    files = {path.relative_to(project).as_posix(): proof.file_hash(path)}
    exit_code = code if not (timed_out or overflow or spawn_error) else None
    extra = {}
    if details and source_unchanged:
        try:
            extra['detail_artifacts'] = capture_manifest(project, captures)
        except (ValueError, OSError):
            record(project, state, 'check', files, integration=integrated['sha256'], exit_code=None)
            raise
    receipt = record(project, state, 'check', files, integration=integrated['sha256'],
                     exit_code=None if details and not source_unchanged else exit_code, **extra)
    # Preserve failed observations before reporting a verifier/source problem.
    t.require(source_unchanged, 'QA command changed integrated source')
    t.validation_message(project, state)
    return receipt


def capture_manifest(project, directory):
    t = common()
    files, total = {}, 0
    relative = directory.relative_to(project).as_posix()
    t.require(strict_io.scoped_path(project, relative).is_dir(), 'Missing private detail capture directory')
    for path in directory.iterdir():
        file = strict_io.scoped_path(project, f'{relative}/{path.name}')
        t.require(file.is_file(), 'Detail captures must be flat regular files')
        size = file.stat().st_size
        total += size
        t.require(0 < size and total <= MAX_DETAIL_ARTIFACT_BYTES and len(files) < MAX_DETAIL_ARTIFACTS,
                  'Detail captures are empty or exceed the evidence limit')
        files[path.name] = proof.file_hash(file)
    return files


def verify_detail_review(project, state, check, evidence):
    t = common()
    criteria = state['plan']['integration']['detail_review']
    report = proof.load(evidence)
    t.require(isinstance(report, dict) and report.get('check_sha256') == check['sha256'],
              'Detail review must name the current successful QA check')
    proof.meaningful(report.get('observations'), 'Independent QA observations')
    rows = report.get('details')
    t.require(isinstance(rows, dict), 'Detail review must report each sealed criterion')
    missing, extra = criteria.keys() - rows.keys(), rows.keys() - criteria.keys()
    t.require(not missing and not extra,
              'Detail review IDs differ from the sealed plan: missing ' + ', '.join(sorted(missing))
              + '; unexpected ' + ', '.join(sorted(extra)))
    captures = strict_io.scoped_path(project, next(iter(check['files']))).with_suffix('')
    artifacts = check.get('detail_artifacts', {})
    t.require(artifacts and capture_manifest(project, captures) == artifacts,
              'Current QA detail captures are absent or changed')
    for rid, row in rows.items():
        t.require(isinstance(row, dict) and row.get('verdict') == 'pass',
                  rid + ': detail review is not passed')
        proof.meaningful(row.get('observation'), rid + ' observed detail')
        names = row.get('artifacts')
        t.require(isinstance(names, list) and names and all(isinstance(name, str) and name in artifacts
                                                            for name in names),
                  rid + ': cite artifacts from the current QA check')


def review(project, state, evidence, verdict):
    # Legacy review already binds immutable narrative, current finite check and owner inputs.
    common().require(verdict in {'pass', 'fail'}, 'Review verdict must be pass or fail')
    return common().review(project, state, evidence, verdict)


def repair(project, state, tid, evidence, observation):
    return common().repair(project, state, tid, evidence, observation)


def verify_structural(project, state, require_qa):
    t = common()
    t.validation_message(project, state)
    admission = corporate_admission(project, state)
    children = {r['id']: usable_handoff(project, state, r['id'], admission=admission) for r in state['plan']['tasks']}
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
        if state['plan']['integration'].get('detail_review'):
            verify_detail_review(project, state, check, strict_io.scoped_path(project, next(iter(qa['files']))))
    return children


def codex_adapter(project, state, parent, sessions, require_qa):
    """Use the established host parser; schema-2 acceptance is separate below."""
    t = common()
    created = t.instant(state['created'])
    logs = t.locate_sessions(project, parent, Path(sessions or t.codex_sessions()), state['created'])
    rows = {}
    reviewed = state['plan'].get('decomposition') == 'reviewed-v1'
    for role, (meta, path) in logs.items():
        window = NativeWindow(path, created, 'codex')
        review_team = state['plan']['id'] if reviewed and role == 'plan_review' else None
        try:
            rows[role] = t.read_trace(project, meta, path, created, events=window,
                                      lifecycle_limit=MAX_NATIVE_PENDING_CALLS, review_team=review_team)
        except ValueError as exc:
            if 'pending lifecycle limit exceeded' in str(exc):
                raise HostEvidenceUnavailable(str(exc)) from exc
            raise
        rows[role]['tail_incomplete'] = window.tail_incomplete
        for context in window.contexts:
            for key, field in [('models', 'model'), ('efforts', 'effort')]:
                rows[role].setdefault(key, set()).update(filter(None, [context.get(field)]))
    return verify_native_rows(project, state, parent, rows, require_qa, 'codex-rollout')


def copilot_agent_message(worker, parent, payload, when):
    """Bind the follow-up delivered by the parent to its original worker."""
    t = common()
    resume = worker.get('resume')
    message = payload.get('content')
    interaction = payload.get('interactionId')
    initial_turn = payload.get('turnId')
    if payload.get('delivery') == 'steering':
        steering = (resume or {}).get('steering')
        # Steering is emitted just after the receiving turn starts, without
        # creating a new interaction or a completed worker interval.
        t.require(steering is not None and resume.get('turn') is not None and not resume['turn_used']
                  and interaction == resume['interaction'] and initial_turn == resume['turn']
                  and steering[0] <= resume['turn_start'] <= when
                  and payload.get('source') == 'agent-' + parent
                  and isinstance(message, str) and hashlib.sha256(message.encode()).digest() == steering[1],
                  'Copilot steering message lacks its original native delivery')
        del resume['steering']
        return
    t.require(resume is not None and 'interaction' not in resume and when >= resume['sent']
              and payload.get('source') == 'agent-' + parent and payload.get('delivery') == 'idle'
              and isinstance(interaction, str) and interaction and interaction not in worker['interactions']
              and isinstance(initial_turn, str) and initial_turn
              and isinstance(message, str) and hashlib.sha256(message.encode()).digest() == resume['message'],
              'Copilot follow-up message lacks its original native delivery')
    worker['interactions'].add(interaction)
    resume.update(interaction=interaction, delivered=when, initial_turn=initial_turn,
                  turns=set(), pending=set())


def copilot_followup_turn(worker, kind, payload, when):
    t = common()
    resume = worker.get('resume')
    turn = payload.get('turnId')
    t.require(resume is not None and 'interaction' in resume
              and payload.get('parentToolCallId') == worker['dispatch_call']
              and isinstance(turn, str) and turn, 'Copilot follow-up turn lacks its original task identity')
    if kind == 'assistant.turn_start':
        t.require(resume.get('turn') is None and turn not in resume['turns']
                  and payload.get('interactionId') == resume['interaction']
                  and (resume['turns'] or turn == resume['initial_turn'])
                  and when >= resume.get('turn_end', resume['delivered']),
                  'Copilot follow-up turn has wrong interaction or order')
        if worker['active'] is None:
            worker['active'] = when
            worker['turn_starts'].append(when)
        resume['turn'], resume['turn_start'] = turn, when
        resume['turn_used'] = False
        resume['turns'].add(turn)
    else:
        t.require(resume.get('turn') == turn and when >= resume['turn_start'] and not resume['pending'],
                  'Copilot follow-up turn ended without its own completed tools')
        resume['turn'], resume['turn_end'] = None, when


def copilot_followup_result(by_agent, tool, args, payload, started, when):
    """Accept delivery and final idle only from paired native parent tools."""
    if tool not in {'write_agent', 'read_agent'} or not isinstance(args, dict):
        return
    worker = by_agent.get(args.get('agent_id'))
    if worker is None or worker['end'] is None or 'auxiliary_parent' in worker:
        return
    telemetry = payload.get('toolTelemetry', {})
    properties, metrics = telemetry.get('properties', {}), telemetry.get('metrics', {})
    if properties.get('agent_id') != worker['id']:
        return
    resume = worker.get('resume')
    if tool == 'write_agent':
        message = args.get('message')
        if started < worker['end'] or not isinstance(message, str) or not message:
            return
        digest = hashlib.sha256(message.encode()).digest()
        if resume is None:
            worker['resume'] = {'sent': when, 'message': digest}
        elif worker['active'] is not None and started >= worker['active']:
            common().require('steering' not in resume, 'Copilot has multiple unpaired steering messages')
            resume['steering'] = (when, digest)
        return
    wait = args.get('wait', False)
    # Copilot also emits an automatic idle-status read with no wait argument.
    # A non-waiting read must start after the last observed turn has ended.
    if (not resume or 'turn_end' not in resume or resume.get('turn') is not None or 'steering' in resume
            or type(wait) is not bool or (not wait and started < resume['turn_end'])
            or properties.get('status') != 'idle'
            or type(metrics.get('queue_depth')) is not int or metrics['queue_depth'] != 0
            or type(metrics.get('total_turns')) is not int or metrics['total_turns'] != len(worker['intervals']) + 1
            or started < resume['delivered'] or when < resume['turn_end']):
        return
    worker['end'] = resume['turn_end']
    worker['intervals'].append((worker['active'], worker['end']))
    worker['active'] = None
    del worker['resume']


def copilot_missing_qa(reconnect, qa, tool, args, payload, started, when):
    if not (reconnect and qa and tool == 'write_agent' and isinstance(args, dict)
            and args.get('agent_id') == qa['id'] and isinstance(args.get('message'), str) and args['message']
            and qa['end'] is not None and qa['active'] is None and qa.get('resume') is None
            and qa['end'] <= reconnect[0] <= reconnect[1] <= started <= when
            and payload.get('success') is False):
        return False
    fields = payload.get('toolTelemetry', {}).get('properties', {})
    return (fields.get('agent_id') == qa['id'] and fields.get('error') == 'not_found'
            and payload.get('error', {}).get('code') == 'failure')


def is_copilot_coverage_review(project, review_team, request, args):
    """Recognize the exact historical packet, including superseded draft hashes."""
    import corporate
    from copilot_guard import TASK_FIELDS

    if (args.get('name') != COPILOT_COVERAGE_REVIEW or args.keys() - TASK_FIELDS
            or args.get('agent_type') not in ('general-purpose', 'task')
            or args.get('mode', 'sync') not in ('sync', 'background')
            or not all(isinstance(value, str) for value in args.values())):
        return False
    prompt = args.get('prompt', '')
    goal = project / proof.STATE / 'root-goals' / review_team
    start = (f'Independently review coverage of {(goal / "original-request.txt").as_posix()} '
             f'against {(goal / "root-contract.json").as_posix()}.\n'
             'Current request, span and acceptance bindings: ')
    details = prompt.removeprefix(start)
    if details == prompt:
        return False
    bindings_text, _, remaining = details.partition('.\n')
    _, marker, planner_text = remaining.partition('method fresh-context-agent, planner ')
    planner_json, delimiter, _ = planner_text.rpartition(', your actual reviewer identity, concrete observations, ')
    if not marker or not delimiter:
        return False
    try:
        bindings = strict_io.loads(bindings_text)
        planner = strict_io.loads(planner_json)
        corporate.text(planner, 'Actual planner identity')
    except (ValueError, TypeError, RecursionError, proof.ProofError):
        return False
    if (not isinstance(bindings, dict)
            or bindings.keys() != {'request_sha256', 'segments_sha256', 'acceptance_sha256'}
            or any(not isinstance(digest, str) or not common().re.fullmatch(r'[0-9a-f]{64}', digest)
                   for digest in bindings.values())):
        return False
    request = request.replace('\r\n', '\n')
    if bindings['request_sha256'] not in {hashlib.sha256(s.encode('utf-8')).hexdigest()
                                         for s in (request, request.replace('\n', '\r\n'))}:
        return False
    return prompt == corporate.coverage_review_message(goal, bindings, planner)


def read_copilot_traces(project, parent, sessions, since, *, review_team=None, review_evidence=None,
                        corporate_request=None, original_since=None):
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
    window = NativeWindow(path, original_since or since, 'copilot')
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
    auxiliary_calls = {}
    seen_ids = {header.get('id')}
    boundary_initialized = False
    shutdown = reconnect = None
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
            elif kind == 'tool.execution_complete':
                if not agent:
                    calls.pop(payload.get('toolCallId'), None)
                if original_since is not None and when >= original_since:
                    t.require(all(Path(edit['path']).is_absolute() and Path(edit['path']).resolve()
                                  .is_relative_to(project / proof.STATE)
                                  for edit in payload.get('fileEdits', [])),
                              'Native product write preceded the revised plan')
            continue
        if not boundary_initialized:
            # The header may be hours old. Pins compare the actual effective
            # context at the seal and every later transition, not old choices.
            coordinator['models'] = {coordinator['model']}
            coordinator['efforts'] = {coordinator['effort']}
            boundary_initialized = True
        if kind == 'session.shutdown' and not agent:
            shutdown, reconnect = when, None
        elif kind == 'session.resume' and not agent:
            reconnect = ((shutdown, when) if shutdown is not None and shutdown <= when
                         and payload.get('alreadyInUse') is False and payload.get('sessionWasActive') is False
                         else None)
        elif kind == 'session.model_change':
            t.require(current is not None, 'Native model transition lacks its agent identity')
            if agent:
                t.require(when >= current['start'] and (current['end'] is None or current['active'] is not None),
                          'Copilot model transition is outside its task lifecycle')
            apply_model_transition(current, payload, True)
        elif kind == 'user.message' and agent and current is not None:
            if current['end'] is not None:
                copilot_agent_message(current, parent, payload, when)
                context = payload.get('responsesReasoning', {})
                for field, observed in [('model', 'models'), ('effort', 'efforts'), ('initialEffort', 'efforts')]:
                    if field in context:
                        current[observed].add(context[field])
            elif isinstance(payload.get('interactionId'), str):
                current['interactions'].add(payload['interactionId'])
        elif kind == 'session.context_changed':
            t.require(Path(payload.get('cwd', '')).resolve() == project,
                      'Copilot session changed to a different workspace')
        elif kind == 'tool.execution_start':
            call_id = payload.get('toolCallId')
            t.require(isinstance(call_id, str) and call_id not in calls and call_id not in auxiliary_calls,
                      'Duplicate Copilot tool call')
            if agent:
                t.require(current is not None and when >= current['start'],
                          'Copilot child tool is outside its actual task lifecycle')
                if current['end'] is not None:
                    resume = current.get('resume', {})
                    t.require(resume.get('turn') is not None and payload.get('turnId') == resume['turn']
                              and payload.get('parentToolCallId') == current['dispatch_call']
                              and when >= resume['turn_start'], 'Copilot child tool is outside its actual task lifecycle')
                    resume['turn_used'] = True
                    resume['pending'].add(call_id)
            calls[call_id] = (event, when)
            if len(calls) > MAX_NATIVE_PENDING_CALLS or len(dispatch) > MAX_NATIVE_PENDING_CALLS:
                raise HostEvidenceUnavailable('Native trace pending lifecycle limit exceeded')
            if current and payload.get('model'):
                current['models'].add(payload['model'])
            if payload.get('toolName') == 'task' and not agent:
                dispatch[call_id] = (payload, when)
        elif kind == 'subagent.started':
            call_id = payload.get('toolCallId')
            task_dispatch, dispatched_at = dispatch.pop(call_id, (None, None))
            auxiliary_parent = None
            if task_dispatch is None and corporate_request is not None and call_id in calls:
                request, started = calls[call_id]
                dispatcher = request.get('agentId')
                candidate = request['data']
                if dispatcher and candidate.get('toolName') == 'task':
                    origin = by_agent[dispatcher]
                    arguments = candidate.get('arguments')
                    # The lifecycle payload identifies the dispatching agent.
                    # The outer event's parentId identifies another event.
                    t.require(call_id and call_id not in auxiliary_calls and origin['active'] is not None
                              and origin['active'] <= started <= when
                              and candidate.get('parentToolCallId') == origin['dispatch_call']
                              and payload.get('parentId') == dispatcher
                              and payload.get('executionMode') == 'sync'
                              and isinstance(arguments, dict) and arguments.get('mode', 'sync') == 'sync',
                              'Invalid nested Copilot task dispatch')
                    task_dispatch = candidate
                    auxiliary_parent = (dispatcher, origin['active'])
            args = (task_dispatch or {}).get('arguments', {})
            label = args.get('name') if isinstance(args, dict) else None
            t.require(isinstance(label, str) and label and label == payload.get('agentDisplayName')
                      and isinstance(agent, str) and agent and agent not in by_agent and agent != parent,
                      'Copilot subagent lacks a unique originating named task')
            role = label
            if auxiliary_parent is not None:
                role = f'auxiliary:{agent}'
            elif (label == COPILOT_COVERAGE_REVIEW and corporate_request is not None and review_team is not None
                  and is_copilot_coverage_review(project, review_team, corporate_request, args)):
                # Keep review activity observable without claiming an implementation role.
                role = f'{COPILOT_COVERAGE_REVIEW}:{agent}'
            t.require(role not in rows, 'Copilot subagent lacks a unique originating named task')
            current = row(agent, when, payload.get('model'))
            current['dispatch_call'] = call_id
            current['interactions'] = set()
            current['turn_starts'].append(when)
            current['active'] = when
            if label == COPILOT_QA_RECOVERY and auxiliary_parent is None:
                original_qa = rows.get('qa', {})
                missing = original_qa.get('unavailable')
                t.require(missing is not None and missing[0] == reconnect
                          and missing[1] <= dispatched_at <= when and original_qa.get('resume') is None
                          and isinstance(args.get('prompt'), str),
                          'Replacement QA needs an observed unavailable original worker after reconnect')
                current['replacement'] = {'previous_actor': original_qa['id'], 'unavailable_at': missing[1]}
                current['prompt'] = args['prompt']
            if auxiliary_parent is not None:
                current['auxiliary_parent'] = auxiliary_parent
                auxiliary_calls[call_id] = current
            by_agent[agent], rows[role] = current, current
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
        elif kind in ('assistant.turn_start', 'assistant.turn_end') and agent and current is not None and current['end'] is not None:
            copilot_followup_turn(current, kind, payload, when)
        elif kind in ('abort', 'session.error') and agent and current is not None and current.get('resume') is not None:
            t.require(False, 'Copilot follow-up reported a native failure or abort')
        elif kind == 'assistant.turn_start' and not agent:
            coordinator['active'] = when
            coordinator['turn_starts'].append(when)
        elif kind == 'assistant.turn_end' and not agent:
            if coordinator['active'] is not None:
                coordinator['intervals'].append((coordinator['active'], when))
                coordinator['active'] = None
        elif kind == 'tool.execution_complete':
            call_id = payload.get('toolCallId')
            original = calls.pop(call_id, None)
            t.require(original is not None, 'Copilot completion lacks its original tool call')
            request, started = original
            t.require(request.get('agentId') == agent and when >= started and current is not None,
                      'Copilot tool completion changed agent identity/order')
            if agent:
                t.require(payload.get('parentToolCallId') == current['dispatch_call']
                          and request['data'].get('parentToolCallId') == current['dispatch_call'],
                          'Copilot child tool belongs to a different task')
                if current['end'] is not None:
                    resume = current.get('resume', {})
                    t.require(payload.get('toolCallId') in resume.get('pending', ())
                              and payload.get('turnId') == resume.get('turn')
                              and payload.get('interactionId') == resume.get('interaction'),
                              'Copilot child completion lacks its follow-up turn identity')
                    resume['pending'].remove(payload['toolCallId'])
                    if payload.get('model'):
                        current['models'].add(payload['model'])
            auxiliary = auxiliary_calls.get(call_id)
            if auxiliary is not None:
                dispatcher, active = auxiliary['auxiliary_parent']
                t.require(agent == dispatcher and current['active'] == active
                          and auxiliary['end'] is not None and auxiliary['end'] <= when
                          and isinstance(payload.get('success'), bool),
                          'Copilot nested task lifecycle did not complete within its parent dispatch')
                auxiliary['dispatch_completed'] = when
            call = request['data']
            args = call.get('arguments', {})
            if not agent and started >= since:
                qa = rows.get('qa')
                tool = call.get('toolName')
                if copilot_missing_qa(reconnect, qa, tool, args, payload, started, when):
                    qa['unavailable'] = (reconnect, when)
                elif (qa and tool == 'write_agent' and isinstance(args, dict) and args.get('agent_id') == qa['id']
                      and payload.get('success') is True):
                    t.require(COPILOT_QA_RECOVERY not in rows, 'Original QA was resumed after replacement')
                    qa.pop('unavailable', None)
            if (payload.get('success') is not True and 'auxiliary_parent' not in current
                    and not current.get('replacement')):
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
            if 'auxiliary_parent' in current or payload.get('success') is not True:
                # Retain reported edits even for a failed tool. Only a direct
                # worker may produce a role's native receipt markers.
                continue
            if not agent and started >= since:
                copilot_followup_result(by_agent, call.get('toolName'), args, payload, started, when)
            command = args.get('command') if isinstance(args, dict) else None
            if (started >= since and call.get('toolName') in {'powershell', 'bash'} and isinstance(command, str)
                    and payload.get('shellExecution', {}).get('exitCode') == 0):
                if review_team is not None and current is rows.get('plan_review'):
                    matches = t.plan_review_command(command, project, review_team, evidence=review_evidence)
                else:
                    matches = t.team_command(command)
                if not matches:
                    continue
                result = payload.get('result', {})
                # Never search assistant prose, call arguments, or partial stdout for receipts.
                content = result.get('content', '') if isinstance(result, dict) else ''
                if isinstance(content, str):
                    for digest in t.re.findall(r'^' + t.RECEIPT + r'([0-9a-f]{64})\s*$', content, t.re.M):
                        current['markers'].setdefault(digest, when)
    if not boundary_initialized:
        coordinator['models'], coordinator['efforts'] = {coordinator['model']}, {coordinator['effort']}
    for auxiliary in auxiliary_calls.values():
        if 'dispatch_completed' not in auxiliary:
            dispatcher, active = auxiliary['auxiliary_parent']
            t.require(by_agent[dispatcher]['active'] == active,
                      'Copilot nested task lifecycle did not complete within its parent dispatch')
    return rows


def copilot_adapter(project, state, parent, sessions, require_qa):
    t = common()
    plan = state['plan']
    review_team = plan['id'] if plan.get('decomposition') == 'reviewed-v1' else None
    corporate_request = plan['request'] if plan.get('root_protocol') == 'corporate-v1' else None
    rows = read_copilot_traces(project, parent, sessions, t.instant(state['created']),
                               review_team=review_team, review_evidence=t.plan_review_evidence(state),
                               corporate_request=corporate_request,
                               original_since=revision_origin(project, state) if 'revision' in state else None)
    return verify_native_rows(project, state, parent, rows, require_qa, 'copilot-session-events-v1')


def verify_native_plan_review(project, state, parent, rows):
    t = common()
    receipt = approved_decomposition(project, state)
    reviewer = rows.get('plan_review')
    t.require(reviewer is not None, 'Missing native plan_review worker')
    t.require(reviewer['id'] != parent and all(row['id'] != reviewer['id'] for role, row in rows.items()
                                              if role != 'plan_review'), 'Plan review is not independent')
    t.require(reviewer['start'] >= t.instant(state['created']) and not reviewer.get('failed'),
              'Native plan review has wrong start or failed')
    if reviewer.get('resume') is not None:
        raise t.NativeTurnPending('plan_review')
    t.require_receipt_turn_finished(reviewer, [receipt], 'plan_review')
    at = t.receipt_event(reviewer, receipt, 'plan_review')
    finished = next((end for start, end in reviewer['intervals'] if start <= at <= end), None)
    t.require(finished is not None, 'Native plan review turn has not completed')
    for task in state['plan']['tasks']:
        row = rows.get(task['id'])
        t.require(row is not None and row['start'] >= finished, task['id'] + ': owner started before plan review completed')
    t.require(not any(when < finished and not path.startswith(proof.STATE + '/')
                      for row in rows.values() for when, path in row['writes']),
              'Native product write preceded completed plan review')
    return {'actor': reviewer['id'], 'receipt': receipt['sha256'], 'completed_at': finished.isoformat()}


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
    pending_auxiliary = next((role for role, source in rows.items()
                              if 'auxiliary_parent' in source and 'dispatch_completed' not in source), None)
    if pending_auxiliary is not None:
        raise t.NativeTurnPending(pending_auxiliary)
    plan_review = None
    if plan.get('decomposition') == 'reviewed-v1':
        plan_review = verify_native_plan_review(project, state, parent, rows)
    admission = corporate_admission(project, state)
    if admission:
        admitted = t.instant(admission['admitted_at'])
        sealed = t.instant(admission['binding']['sealed_at'])
        t.require(not any(source['start'] >= sealed for role, source in rows.items()
                          if role.startswith(COPILOT_COVERAGE_REVIEW + ':')),
                  'Native coverage reviewer started after Corporate root sealing')
        t.require(not any(when < admitted and not rel.startswith(proof.STATE + '/')
                          for row in rows.values() for when, rel in row['writes']),
                  'Native product write preceded Corporate root admission')
    builds, handoffs = {}, {}
    for tid, task in tasks.items():
        t.require(tid in rows, tid + ': missing native worker')
        row, receipt = rows[tid], usable_handoff(project, state, tid, admission=admission)
        t.require(row['id'] != parent and row['start'] >= created, tid + ': wrong native identity/start')
        if admission:
            t.require(row['start'] >= admitted, tid + ': owner started before Corporate root admission')
        t.require(not row.get('failed'), tid + ': native worker failed')
        if row.get('resume') is not None:
            raise t.NativeTurnPending(tid)
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
        left, right = handoffs[a][0], handoffs[b][0]
        if plan_review:
            left_start, left_end = left['intervals'][0]
            right_start, right_end = right['intervals'][0]
            overlaps = max(left_start, right_start) < min(left_end, right_end)
        else:
            overlaps = t.completed_overlap(left, right)
        if overlaps:
            overlap.append([a, b])
    if plan.get('max_parallel_workers', 1) > 1 and independent_pairs(tasks):
        t.require(overlap, 'Declared available parallel workers were not used on independent scopes')
    recovery = None
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
        t.require(not any(not rel.startswith(proof.STATE + '/') for _, rel in reviewer['writes']),
                  'QA edited product source')
        if COPILOT_QA_RECOVERY in rows:
            t.require(adapter == 'copilot-session-events-v1', 'Unsupported native QA replacement')
            reviewer = rows[COPILOT_QA_RECOVERY]
            expected = qa_packet(project, state, integrated)['message']
            t.require(reviewer['start'] >= when and (reviewer['prompt'] == expected
                      or reviewer['prompt'].startswith(expected + '\n\n')),
                      'Replacement QA must receive the current integrated QA packet')
            recovery = {'actor': reviewer['id'], 'previous_actor': reviewer['replacement']['previous_actor'],
                        'unavailable_at': reviewer['replacement']['unavailable_at'].isoformat()}
        t.require(not reviewer.get('failed'), 'Native QA worker failed')
        t.require(reviewer['id'] not in {parent, *(v['id'] for v in builds.values())}, 'QA is not independent')
        if admission:
            t.require(reviewer['start'] >= admitted, 'QA started before Corporate root admission')
        if reviewer.get('resume') is not None:
            raise t.NativeTurnPending('qa')
        t.require_receipt_turn_finished(reviewer, [check, qa], 'qa')
        check_at, qa_at = t.receipt_event(reviewer, check, 'QA check'), t.receipt_event(reviewer, qa, 'QA')
        t.require(reviewer['end'] and t.turn_start(reviewer, check_at) >= when
                  and check_at <= qa_at and t.completed_receipt(reviewer, qa_at), 'QA has wrong order or incomplete turn')
        t.require(not any(not rel.startswith(proof.STATE + '/') for _, rel in reviewer['writes']),
                  'QA edited product source')
    assurance = {'status': 'PASS', 'adapter': adapter, 'workers': builds,
                 'overlap': overlap, 'independent_qa': require_qa,
                 'limitation': 'Cooperative local host records, not a hostile-writer security boundary.'}
    if plan_review:
        assurance['plan_review'] = plan_review
    if admission:
        assurance['corporate_dispatch'] = admission
    if recovery:
        assurance['qa_recovery'] = recovery
    return assurance


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
