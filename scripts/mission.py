#!/usr/bin/env python3
"""Scoped preservation and completion gates for an explicitly managed goal."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3
import subprocess
import sys

import corporate
from project_memory import DENY, MAX_GOAL, Memory, sha, source_path, utc
import proof
import strict_io

PROTOCOL = 'preservation-v1'
PRESERVED = {'PRESERVE', 'EXTEND'}
EXPLICIT = {'MODIFY_EXPLICITLY_REQUESTED', 'REMOVE_EXPLICITLY_REQUESTED'}
COLLATERAL = 'POTENTIAL_COLLATERAL_CHANGE'
EFFECTS = PRESERVED | EXPLICIT | {COLLATERAL, 'UNVERIFIED'}
DELIVERED = {'IMPLEMENTED', 'VERIFYING', 'VERIFIED'}
TRANSITIONS = {
    'TODO': {'IN_PROGRESS', 'IMPLEMENTED', 'BLOCKED_ENVIRONMENT'},
    'IN_PROGRESS': {'IMPLEMENTED', 'BLOCKED_ENVIRONMENT', 'FAILED'},
    'IMPLEMENTED': {'FAILED', 'BLOCKED_ENVIRONMENT'},
    'VERIFYING': {'FAILED', 'BLOCKED_ENVIRONMENT'},
    'FAILED': {'BLOCKED_ENVIRONMENT'},
}
CHECK_ERRORS = (ValueError, OSError, TypeError, KeyError, proof.ProofError)
MAX_DOCUMENT = 2_000_000
MAX_ROWS = 1024
NEGATION = re.compile(r'\b(?:never|not|except|unless|nothing)\b|\b(?:don|doesn|won)[’\']t\b', re.I)
REMOVAL = re.compile(r'\b(?:remov\w*|delet\w*|drop\w*|retir\w*|eliminat\w*|disabl\w*|'
                     r'discontinu\w*|strip(?:ping)? out|no longer support|stop supporting)\b', re.I)
CLAUSE_BOUNDARY = re.compile(r'[\n;]|[.!?]\s+')
CONTRAST = re.compile(r'\b(?:but|rather than|instead of|without)\b', re.I)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def identifier(value, label):
    require(isinstance(value, str) and proof.ID_RE.fullmatch(value), f'Invalid {label}')
    return value


def text(value, label, minimum=1, maximum=4000):
    require(isinstance(value, str) and minimum <= len(value.strip()) and len(value) <= maximum,
            f'{label} needs concrete, bounded text')
    proof.meaningful(value, label, minimum)
    return value


def is_hash(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) is not None


def strings(value, label, *, empty=False):
    require(isinstance(value, list) and (empty or bool(value)) and len(value) <= MAX_ROWS and
            all(isinstance(item, str) for item in value) and len(set(value)) == len(value),
            f'{label} must list distinct values')
    return value


def rows(value, label, *, empty=False):
    require(isinstance(value, list) and (empty or bool(value)) and len(value) <= MAX_ROWS,
            f'{label} must be a bounded list')
    result = {}
    for row in value:
        require(isinstance(row, dict), f'{label} must contain objects')
        key = identifier(row.get('id'), label + ' ID')
        require(key not in result, f'Duplicate {label} ID: {key}')
        result[key] = row
    return result


def file_identity(project, name):
    require(strict_io.scope_key(name) and not name.endswith('/') and
            not any(ord(c) < 32 for c in name) and not Path(name).name.casefold().startswith('.env'),
            'Mission sources must be explicit, safe file paths')
    path = source_path(project, name, must_exist=False)
    require(not any(part in proof.SKIP_DIRS for part in Path(name).parts),
            f'Generated path excluded from mission scope: {name}')
    return proof.file_hash(path) if path.exists() else None


def snapshot(project, paths):
    project = Path(project).resolve()
    return {name: file_identity(project, name) for name in paths}


def ancestors(tasks):
    pending = dict(tasks)
    known = {}
    while pending:
        ready = [tid for tid, task in pending.items() if set(task['depends_on']) <= known.keys()]
        require(ready, 'Mission TODO dependency cycle')
        for tid in ready:
            deps = set(pending.pop(tid)['depends_on'])
            known[tid] = deps.union(*(known[dep] for dep in deps))
    return known


def feature_paths(row):
    return {row['path'], *row['related_paths'], *row['test_paths'], *row.get('oracle_paths', []),
            *([row['relocation']] if row.get('relocation') else [])}


def scope_anchor(message, feature):
    # Match the named feature, its literal source location, or a code token
    # such as a CLI flag or qualified symbol, not a broader file/owner scope.
    location = feature['location']
    anchors = [feature['id'], feature.get('label'), location, feature['behavior'],
               *(token.strip('`') for token in re.findall(r'--[\w-]+|\b\w+(?:\.\w+)+\b|`[^`]+`', location))]
    return any(anchor and re.search(r'(?<![\w-])' + re.escape(anchor) + r'(?![\w-])', message)
               for anchor in anchors)


def matching_reply(response, verdict, feature):
    if not isinstance(response, str) or not 0 < len(response) <= 8000:
        return False
    reply = response.strip()
    return bool(re.fullmatch(rf'(?i:{verdict})\s+{re.escape(feature["id"])}', reply)
                or reply == f'I {verdict}: ' + feature['planned_effect'].strip())


def request_quote(request, excerpt):
    """Keep semantic scope judgment with the reviewer; reject obvious negation."""
    if not isinstance(excerpt, str) or not excerpt.strip() or NEGATION.search(excerpt):
        return False
    for match in re.finditer(re.escape(excerpt), request):
        lead = CLAUSE_BOUNDARY.split(request[:match.start()])[-1]
        if not NEGATION.search(lead):
            return True
    return False


def removal_quote(excerpt, feature):
    for clause in CLAUSE_BOUNDARY.split(excerpt):
        primary = CONTRAST.split(clause, maxsplit=1)[0]
        action = REMOVAL.search(primary)
        if action and scope_anchor(primary[action.end():], feature):
            return True
    return False


def normalize(draft, request):
    require(isinstance(draft, dict) and type(draft.get('schema')) is int and draft['schema'] == 1,
            'Expected mission draft schema 1')
    require(len(proof.canonical(draft)) <= MAX_DOCUMENT, 'Mission draft is oversized')
    plan = deepcopy(draft)
    identifier(plan.get('goal_id'), 'goal ID')
    require(plan.get('kind') in {'change', 'greenfield'}, 'Mission kind must be change or greenfield')
    text(plan.get('author'), 'Mission author', maximum=256)
    sources = plan.get('sources')
    require(isinstance(sources, dict) and 0 < len(sources) <= MAX_ROWS,
            'Declare a bounded explicit file scope')
    keys = set()
    for name, value in sources.items():
        require(isinstance(name, str) and 0 < len(name) <= 512 and not any(ord(c) < 32 for c in name),
                'Invalid mission source path')
        key = strict_io.scope_key(name)
        require(key and not name.endswith('/') and (value is None or is_hash(value)),
                f'Expected an explicit file and baseline SHA-256 or absence: {name}')
        require(key not in keys, f'Ambiguous mission source path: {name}')
        keys.add(key)
    for key in keys:
        require(not any(parent.as_posix() in keys for parent in Path(key).parents),
                f'Mission file scope has overlapping paths: {key}')
    reqs = plan.get('requirements')
    require(isinstance(reqs, dict) and 0 < len(reqs) <= MAX_ROWS, 'Record the original requirements')
    for rid, row in reqs.items():
        identifier(rid, 'requirement ID')
        require(isinstance(row, dict), f'Invalid requirement {rid}')
        text(row.get('claim'), f'{rid} claim')
        excerpt = row.get('excerpt')
        require(isinstance(excerpt, str) and excerpt.strip() and excerpt in request,
                f'{rid} excerpt is not in the exact original request')
    tasks = rows(plan.get('tasks'), 'TODO')
    for tid, row in tasks.items():
        require(row.get('requirement_id') in reqs, f'{tid}: unknown original requirement')
        identifier(row.get('owner'), f'{tid} owner')
        text(row.get('description'), f'{tid} description')
        text(row.get('done'), f'{tid} Definition of Done')
        strings(row.get('checks'), f'{tid} checks')
        require(set(strings(row.get('depends_on'), f'{tid} dependencies', empty=True)) <= tasks.keys(),
                f'{tid}: unknown TODO dependency')
    require({row['requirement_id'] for row in tasks.values()} == reqs.keys(),
            'Mission TODOs omit original requirements')
    ancestors(tasks)
    features = rows(plan.get('features'), 'feature', empty=True)
    if not features:
        text(plan.get('no_existing_behavior'), 'Rationale for no existing scoped behavior', minimum=12)
    for fid, row in features.items():
        for name in ('behavior', 'location', 'reason', 'planned_effect'):
            text(row.get(name), f'{fid} {name}')
        if 'label' in row:
            text(row['label'], f'{fid} human-facing label', maximum=256)
        require(row.get('contract') in {'public', 'internal'} and
                row.get('basis') in {'documented', 'observed', 'implementation_detail', 'assumption'},
                f'{fid}: classify its contract and basis')
        effect = row.setdefault('effect', 'PRESERVE')
        require(effect in EFFECTS, f'{fid}: invalid preservation effect')
        require('uncertainty' in row, f'{fid}: make uncertainty explicit')
        if row['uncertainty'] is not None:
            text(row['uncertainty'], f'{fid} uncertainty')
        paths = {row.get('path')}
        for field in ('related_paths', 'test_paths', 'oracle_paths'):
            paths.update(strings(row.get(field, [] if field == 'oracle_paths' else None),
                                 f'{fid} {field}', empty=True))
        require(all(name in sources and sources[name] is not None for name in paths),
                f'{fid}: source, dependencies, tests and oracles must be in the actual baseline')
        linked = strings(row.get('tasks'), f'{fid} TODOs')
        checks = strings(row.get('checks'), f'{fid} checks', empty=effect == 'UNVERIFIED')
        require(all(tid in tasks and set(checks) <= set(tasks[tid]['checks']) for tid in linked),
                f'{fid}: affected TODOs must include the feature checks')
        if effect in EXPLICIT:
            excerpt = row.get('request_excerpt')
            require(request_quote(request, excerpt) and scope_anchor(excerpt, row) and (
                        effect != 'REMOVE_EXPLICITLY_REQUESTED' or removal_quote(excerpt, row)) and not re.match(
                        r'(?:please\s+)?(?:preserve|keep|retain|leave)\b', excerpt.strip(), re.I),
                    f'{fid}: explicit authorization must quote the original request for this exact behavior')
        if effect == COLLATERAL:
            alternatives = row.get('alternatives')
            if isinstance(alternatives, list):
                for alternative in strings(alternatives, f'{fid} preservation alternatives'):
                    text(alternative, f'{fid} alternative')
            else:
                text(alternatives, f'{fid} preservation alternatives')
            text(row.get('impact'), f'{fid} impact')
        if 'removes' in row:
            require(effect == COLLATERAL and type(row['removes']) is bool,
                    f'{fid}: primary source removal must be explicit')
        if 'relocation' in row:
            dest = row['relocation']
            require(effect in PRESERVED and dest in sources and dest != row['path'],
                    f'{fid}: compatible relocation needs a distinct scoped destination and preservation replay')
    return plan


def selector(value):
    pieces = value.split('/')
    require(len(pieces) == 2, f'Invalid proof selector: {value}')
    return tuple(identifier(item, 'proof selector component') for item in pieces)


def get_contract(project, task_id):
    try:
        directory = strict_io.scoped_path(project, f'{proof.STATE}/{task_id}')
        for name in ('contract.json', 'context.json', 'seal.json'):
            path = strict_io.scoped_path(directory, name)
            require(path.is_file() and 0 < path.stat().st_size <= MAX_DOCUMENT, f'Invalid sealed proof input: {name}')
        task, root, contract = proof.task_context(directory)
        require(root == project and task == directory and contract['task_id'] == task_id,
                f'{task_id}: sealed proof task identity differs')
        return task, contract
    except CHECK_ERRORS as exc:
        raise ValueError(f'{task_id}: cannot load sealed proof task: {exc}') from exc


def bind_checks(project, plan):
    requested = sorted({item for row in plan['tasks'] for item in row['checks']})
    contracts, checks = {}, {}
    for sel in requested:
        tid, cid = selector(sel)
        if tid not in contracts:
            task, contract = get_contract(project, tid)
            contracts[tid] = (task, contract)
            for name in strings(contract['source_paths'], f'{tid} proof source roots'):
                source_path(project, name, must_exist=False, allow_directory=True)
        contract = contracts[tid][1]
        check = proof.get_check(contract, cid)
        checks[sel] = check
        if check['role'] != 'negative_control':
            for req in contract['requirements']:
                if cid in req['checks']:
                    for negative in req.get('negative_checks', []) + req['checks']:
                        control = proof.get_check(contract, negative)
                        if control['role'] == 'negative_control':
                            checks[f'{tid}/{negative}'] = control
    for row in plan['tasks']:
        require(any(checks[sel]['role'] != 'negative_control' for sel in row['checks']),
                f'{row["id"]}: TODO needs a regular acceptance or regression check')
    scopes = {}
    for tid, (task, contract) in contracts.items():
        roots = contract['source_paths']
        scope = [name for name in plan['sources'] if any(
            name == root or name.startswith(root + '/') for root in roots)]
        require(scope, f'{tid}: sealed proof has no mission sources')
        scopes[tid] = {'sha256': proof.digest(contract), 'engine_sha256': proof.engine_hash(contract),
                       'sources': sorted(scope)}
    for row in plan['features']:
        if row['effect'] in PRESERVED:
            require(any(checks[sel]['role'] != 'negative_control' for sel in row['checks']),
                    f'{row["id"]}: preservation needs a regular baseline replay')
        inputs = set().union(*(scopes[selector(sel)[0]]['sources'] for sel in row['checks']))
        require(not row['checks'] or feature_paths(row) <= inputs,
                f'{row["id"]}: checks do not cover the feature and its dependencies')
    return scopes, {sel: proof.digest(check) for sel, check in sorted(checks.items())}


def revision(project):
    try:
        result = subprocess.run(['git', 'rev-parse', '--verify', 'HEAD'], cwd=project, check=True,
                                capture_output=True, timeout=5)
        value = result.stdout.decode('ascii').strip()
        return value if re.fullmatch(r'[0-9a-f]{40,64}', value) else None
    except (OSError, UnicodeError, subprocess.SubprocessError):
        return None


def enrolled(project, goal_id):
    return Memory(project, create=False).mission_record(identifier(goal_id, 'goal ID')) is not None


def open_mission(project, goal_id, binding=None):
    memory = Memory(project, create=False)
    row = memory.mission_record(identifier(goal_id, 'goal ID'))
    require(row is not None and (binding is None or binding == row[0]),
            'Missing managed mission or immutable mission binding differs')
    return Mission(memory, goal_id, row[0], row[1])


def initialize(project, draft, request: str, origin: str):
    require(isinstance(request, str) and request.strip() and len(request.encode('utf-8')) <= MAX_GOAL,
            'Original request is missing or exceeds the byte limit')
    text(origin, 'Original request provenance', maximum=512)
    project = Path(project).expanduser().resolve()
    plan = normalize(draft, request)
    goal_id = plan['goal_id']
    baseline = plan['sources']
    require(snapshot(project, baseline) == baseline, 'Mission baseline sources are stale or changed')
    memory = Memory(project)
    with memory.db() as db:
        prior = memory.mission_record(goal_id, db=db)
        if prior:
            binding, spec, _ = prior
            require(spec['draft'] == plan and spec['request'] == request and spec['origin'] == origin,
                    'Mission is already registered; do not rewrite its immutable plan or request')
            Mission(memory, goal_id, binding, spec)._baseline()
            return binding
        sealed = (f'{proof.STATE}/teams/{goal_id}/state.json',
                  f'{proof.STATE}/root-goals/{goal_id}/root-seal.json')
        require(not any(strict_io.scoped_path(project, path, must_exist=False).exists() for path in sealed),
                'Do not enroll an already sealed Team/root goal; use a new managed goal ID')
        old = db.execute('SELECT text FROM goals WHERE goal_id=? ORDER BY revision DESC LIMIT 1',
                         (goal_id,)).fetchone()
        require(not old or old[0] in {request, request.removeprefix('\ufeff').strip()},
                'Managed mission request conflicts with prior project memory')
        scopes, checks = bind_checks(project, plan)
        spec = {'protocol': PROTOCOL, 'draft': plan, 'request': request, 'origin': origin,
                'request_sha256': sha(request.encode('utf-8')), 'revision': revision(project),
                'proof_tasks': scopes, 'checks': checks, 'baseline_receipts': {}}
        mission = Mission(memory, goal_id, None, spec)
        contracts = mission._contracts()
        mission._proof_sources(baseline, contracts, allow_empty=True)
        for sel in sorted(mission._baseline_selectors()):
            ref, _ = mission._execution(sel, baseline, contracts)
            spec['baseline_receipts'][sel] = ref
        require(snapshot(project, baseline) == baseline, 'Mission source changed during baseline registration')
        binding = proof.digest(spec)
        state = {'admitted_at': None, 'authorized': {}, 'inspected': baseline, 'decisions': {}, 'review': None,
                 'progress': {row['id']: {'status': 'TODO'} for row in plan['tasks']}}
        db.execute('INSERT INTO missions VALUES (?,?,?,?)',
                   (goal_id, binding, strict_io.canonical(spec), strict_io.canonical(state)))
    return binding


class Mission:
    def __init__(self, memory, goal_id, binding, spec):
        self.memory, self.project, self.goal_id = memory, memory.project, goal_id
        self.binding, self.request = binding, spec['request']
        self._spec, self._plan = spec, spec['draft']
        self._tasks = {row['id']: row for row in self._plan['tasks']}
        self._features = {row['id']: row for row in self._plan['features']}
        self._ancestors = ancestors(self._tasks)

    @property
    def plan(self):
        return deepcopy({**self._plan, 'request_sha256': self._spec['request_sha256'],
                         'revision': self._spec['revision'], 'proof_tasks': self._spec['proof_tasks'],
                         'check_hashes': self._spec['checks'], 'baseline_receipts': self._spec['baseline_receipts']})

    @contextmanager
    def _state(self, *, write=False):
        with self.memory.db(read_only=not write) as db:
            row = self.memory.mission_record(self.goal_id, db=db)
            require(row is not None and row[0] == self.binding, 'Managed mission binding was lost or changed')
            state = row[2]
            require(self._tasks.keys() == state['progress'].keys(), 'Mission TODO ledger is incomplete')
            prior = deepcopy(state) if write else None
            yield state
            if write and state != prior:
                replaced = {tid: progress for tid, progress in prior['progress'].items()
                            if progress != state['progress'][tid] and progress != {'status': 'TODO'}}
                prior_review = prior['review'] if prior['review'] != state['review'] else None
                if replaced or prior_review:
                    db.execute('INSERT INTO mission_history VALUES (?,?,?)',
                               (self.goal_id, utc(), strict_io.canonical({'progress': replaced, 'review': prior_review})))
                db.execute('UPDATE missions SET state=? WHERE goal_id=?',
                           (strict_io.canonical(state), self.goal_id))

    def _contracts(self):
        contracts = {}
        for tid, frozen in self._spec['proof_tasks'].items():
            path, contract = get_contract(self.project, tid)
            require(proof.digest(contract) == frozen['sha256'] and
                    proof.engine_hash(contract) == frozen['engine_sha256'],
                    f'{tid}: immutable mission proof contract or engine changed')
            require(not (path / 'blocked.json').exists(), f'{tid}: proof task is blocked')
            contracts[tid] = (path, contract)
        return contracts

    def _latest(self, sel, contracts):
        tid, cid = selector(sel)
        task, _ = contracts[tid]
        pointer = corporate.document(strict_io.scoped_path(task, f'latest/{cid}.json'))
        run = pointer['run']
        require(isinstance(run, str) and len(run.split('/')) == 3 and run.startswith(f'runs/{cid}/') and
                is_hash(pointer.get('receipt_hash')), f'{sel}: latest execution is missing or unfinished')
        receipt = f'{proof.STATE}/{tid}/{run}/receipt.json'
        return {'receipt': receipt, 'sha256': pointer['receipt_hash']}

    def _proof_sources(self, sources, contracts, *, allow_empty=False):
        for tid, (_, contract) in contracts.items():
            optional = proof.absent_source_paths(contract)
            expected = {name: sources[name] for name in self._spec['proof_tasks'][tid]['sources']
                        if sources[name] is not None or name in optional}
            roots = {name: source_path(self.project, name, must_exist=name not in optional,
                                       allow_directory=True) for name in contract['source_paths']}
            # The ordinary collector intentionally cannot execute an empty
            # project. Enrollment can precede creation of explicit absent roots.
            if allow_empty and not any(expected.values()) and not any(path.exists() for path in roots.values()):
                continue
            # Inspect names before the collector reads any bytes. Unexpected or
            # unsafe directory contents are not silently ingested into scope.
            for root in roots.values():
                for path in root.rglob('*') if root.is_dir() else (root,):
                    rel = path.relative_to(self.project)
                    if any(part in proof.SKIP_DIRS for part in rel.parts):
                        continue
                    require(not path.is_symlink() and (not path.is_file() or rel.as_posix() in expected),
                            f'{tid}: proof input is outside the sealed mission source scope: {rel}')
            try:
                actual = proof.snapshot(self.project, contract)
            except proof.ProofError as exc:
                raise ValueError(f'{tid}: cannot snapshot the current proof scope: {exc}') from exc
            require(actual == {'files': expected, 'digest': proof.digest(expected)},
                    f'{tid}: actual proof input is outside the sealed mission source scope or changed')

    def _execution(self, sel, sources, contracts, *, ref=None, after=None):
        try:
            tid, cid = selector(sel)
            latest = ref is None
            ref = self._latest(sel, contracts) if latest else ref
            files = {path: sources[path] for path in self._spec['proof_tasks'][tid]['sources']}
            result = corporate.execution(self.project, ref, {'files': files, 'digest': proof.digest(files)},
                                         latest=latest)
            require(result['selector'] == (tid, cid) and
                    result['receipt']['contract_hash'] == self._spec['proof_tasks'][tid]['sha256'] and
                    proof.digest(result['check']) == self._spec['checks'][sel],
                    f'{sel}: sealed mission selector changed')
            require(result['passed'], f'{sel}: runtime check failed: {result["errors"]}')
            if after is not None:
                require(corporate.instant(result['receipt']['started_at']) >= corporate.instant(after),
                        f'{sel}: candidate execution must start after mission admission or the latest reopen')
            return ref, result
        except CHECK_ERRORS as exc:
            raise ValueError(f'{sel}: missing or invalid passing proof: {exc}') from exc

    def _baseline_selectors(self):
        return {sel for row in self._features.values() if row['effect'] in PRESERVED for sel in row['checks']}

    def _baseline_evidence(self, contracts):
        refs = self._spec['baseline_receipts']
        require(refs.keys() == self._baseline_selectors(), 'Missing immutable preservation baseline receipts')
        for sel, ref in refs.items():
            self._execution(sel, self._plan['sources'], contracts, ref=ref)

    def _baseline(self):
        original = self._plan['sources']
        require(snapshot(self.project, original) == original, 'Pre-edit mission source differs from original baseline')
        contracts = self._contracts()
        self._proof_sources(original, contracts, allow_empty=True)
        self._baseline_evidence(contracts)
        require(snapshot(self.project, original) == original, 'Source changed during pre-edit mission admission')

    def bind_baseline(self):
        self._baseline()
        return self.binding

    def _affected(self, tids):
        return set(tids) | {tid for tid, deps in self._ancestors.items() if deps.intersection(tids)}

    def _owner_tasks(self, owner):
        tids = {tid for tid, row in self._tasks.items() if row['owner'] == owner}
        require(tids, f'Unknown mission owner: {owner}')
        return tids

    def _bound_decision(self, row, state):
        decision = state['decisions'].get(row['id'])
        if not isinstance(decision, dict):
            return None
        try:
            response, origin = decision['response'], decision['origin']
            text(origin, 'User response provenance', maximum=512)
            if (decision['mission_sha256'] == self.binding and decision['feature_id'] == row['id']
                    and decision['scope_sha256'] == proof.digest(row) and decision['effect'] == row['effect']
                    and decision['verdict'] in {'approve', 'deny'}
                    and matching_reply(response, decision['verdict'], row)
                    and decision['response_sha256'] == sha(response.encode('utf-8'))
                    and corporate.instant(decision['at']) <= datetime.now(timezone.utc)):
                return decision
        except CHECK_ERRORS:
            pass
        return None

    def _pending(self, row, state):
        return row['effect'] == COLLATERAL and (self._bound_decision(row, state) or {}).get('verdict') != 'approve'

    def _unknown(self, row):
        return row['effect'] == 'UNVERIFIED' or row['basis'] == 'assumption'

    def _blocks(self, tids, state):
        return [row for row in self._features.values() if tids & self._affected(row['tasks'])
                and (self._pending(row, state) or self._unknown(row))]

    def _task_paths(self, tid):
        linked = [feature_paths(row) for row in self._features.values() if tid in row['tasks']]
        if not linked:
            linked = [self._spec['proof_tasks'][selector(sel)[0]]['sources'] for sel in self._tasks[tid]['checks']]
        return set().union(*linked)

    def _task_digest(self, tid, sources):
        return proof.digest({path: sources[path] for path in self._task_paths(tid)})

    def admit(self, owner=None, *, writes=None):
        with self._state(write=True) as state:
            tids = self._owner_tasks(owner) if owner is not None else set()
            if not state['admitted_at']:
                self._baseline()
                state['admitted_at'] = utc()
            if owner is None:
                return True
            if self._blocks(tids, state):
                return False
            progress = state['progress']
            if any(progress[tid]['status'] in {'BLOCKED_ENVIRONMENT', 'CANCELLED_BY_USER'} for tid in tids):
                return False
            prerequisites = set().union(*(self._ancestors[tid] for tid in tids))
            if any(progress[dep]['status'] not in DELIVERED for dep in prerequisites - tids):
                return False
            relevant = set().union(*(self._task_paths(tid) for tid in prerequisites | tids))
            writable = (set(writes) if writes is not None else
                        set().union(*(self._task_paths(tid) for tid in tids)))
            require(writable <= self._plan['sources'].keys(), 'Writable scope is outside the mission baseline')
            if any(writable & feature_paths(row) and (self._pending(row, state) or self._unknown(row))
                   for row in self._features.values()):
                return False
            relevant |= writable
            current = snapshot(self.project, relevant)
            if any(current[name] != state['inspected'][name] for name in relevant):
                return False
            self._contracts()
            self._guard(state, current, paths=relevant, pending=False)
            state['authorized'][owner] = utc()
            return True

    def refresh(self, note):
        text(note, 'Source reinspection observations', minimum=12)
        with self._state(write=True) as state:
            current = snapshot(self.project, self._plan['sources'])
            changed = sorted(name for name, value in current.items() if value != state['inspected'][name])
            state['inspected'] = current
            state['refresh'] = {'at': utc(), 'note': note, 'paths': changed}
            return deepcopy(state['refresh'])

    def decision(self, feature, verdict, response, origin):
        require(feature in self._features, f'Unknown feature: {feature}')
        row = self._features[feature]
        require(row['effect'] == COLLATERAL and verdict in {'approve', 'deny'},
                'A decision must address one pending collateral feature')
        text(origin, 'Actual user response provenance', maximum=512)
        require(matching_reply(response, verdict, row),
                f'Provide an exact scoped user reply, e.g. {verdict} {feature}')
        with self._state(write=True) as state:
            prior = state['decisions'].get(feature)
            decision = {'verdict': verdict, 'response': response, 'origin': origin,
                        'response_sha256': sha(response.encode('utf-8')), 'feature_id': feature,
                        'mission_sha256': self.binding, 'scope_sha256': proof.digest(row), 'effect': row['effect']}
            if prior is not None:
                require(self._bound_decision(row, state) and all(prior.get(k) == v for k, v in decision.items()),
                        'The recorded user decision is immutable or invalid')
                return deepcopy(prior)
            original = self._plan['sources']
            require(all(value == original[name] for name, value in
                        snapshot(self.project, feature_paths(row)).items()),
                    'User approval must precede edits to the affected feature scope')
            decision['at'] = utc()
            state['decisions'][feature] = decision
            return deepcopy(decision)

    def step(self, tid, status, note='', evidence=None):
        require(tid in self._tasks, f'Unknown mission TODO: {tid}')
        require(status not in {'VERIFIED', 'VERIFYING', 'BLOCKED_APPROVAL'},
                f'Direct {status} is not a valid progress transition')
        if note or status in {'FAILED', 'BLOCKED_ENVIRONMENT'}:
            text(note, 'Progress reason')
        row = self._tasks[tid]
        with self._state(write=True) as state:
            old = state['progress'][tid]['status']
            if status == 'CANCELLED_BY_USER':
                require(old != 'CANCELLED_BY_USER' and isinstance(evidence, dict),
                        'Cancellation requires exact scope and actual user provenance')
                response = text(evidence.get('response'), 'Exact user cancellation')
                origin = text(evidence.get('origin'), 'User cancellation provenance', maximum=512)
                require(re.fullmatch(r'(?i:cancel)\s+' + re.escape(tid), response.strip()),
                        f'Cancellation needs an exact user reply: cancel {tid}')
                evidence = {'response': response, 'origin': origin, 'response_sha256': sha(response.encode('utf-8'))}
            else:
                require(status in TRANSITIONS.get(old, set()), f'Invalid TODO transition {old} → {status}')
                if evidence is not None:
                    text(evidence, 'Progress evidence reference')
                if status != 'BLOCKED_ENVIRONMENT':
                    require(row['owner'] in state['authorized'] and not self._blocks({tid}, state),
                            f'{tid}: owner has no current admission or a feature is unresolved')
                if status in {'BLOCKED_ENVIRONMENT', 'FAILED'}:
                    state['authorized'].pop(row['owner'], None)
                if status in {'IN_PROGRESS', 'IMPLEMENTED'}:
                    for dep in row['depends_on']:
                        require(state['progress'][dep]['status'] in DELIVERED,
                                f'{tid}: dependency {dep} has no deliverable')
            progress = {'status': status, 'note': note, 'evidence': evidence, 'at': utc()}
            state['progress'][tid] = progress
            return deepcopy(progress)

    def handoff(self, owner, evidence_ref):
        require(is_hash(evidence_ref), 'Handoff requires the actual owner receipt SHA-256')
        tids = self._owner_tasks(owner)
        with self._state(write=True) as state:
            require(owner in state['authorized'] and not self._blocks(tids, state),
                    f'{owner}: owner handoff lacks prior admission or approval')
            paths = set().union(*(self._task_paths(tid) for tid in tids))
            self._guard(state, snapshot(self.project, paths), paths=paths, pending=False)
            rows = {tid: state['progress'][tid] for tid in tids}
            require(all(row['status'] in DELIVERED for row in rows.values()),
                    f'{owner}: every owner TODO must be explicitly IMPLEMENTED before handoff')
            for row in rows.values():
                if row['status'] == 'IMPLEMENTED':
                    row['handoff'] = evidence_ref
                else:
                    require(row.get('handoff') == evidence_ref, 'Reopen the TODO before replacing its receipt')
            return {'tasks': sorted(tids), 'evidence_ref': evidence_ref}

    def integrate(self):
        with self._state(write=True) as state:
            moved = []
            for tid, row in state['progress'].items():
                if row['status'] == 'IMPLEMENTED':
                    row.update(status='VERIFYING', at=utc())
                    moved.append(tid)
            return {'status': 'VERIFYING', 'tasks': moved}

    def reopen(self, owner, note):
        text(note, 'Repair finding')
        tids = self._affected(self._owner_tasks(owner)) if owner is not None else set(self._tasks)
        with self._state(write=True) as state:
            moved = []
            for tid in sorted(tids):
                if (state['progress'][tid]['status'] in DELIVERED | {'FAILED', 'BLOCKED_ENVIRONMENT'} and
                        not self._blocks({tid}, state)):
                    at = utc()
                    state['progress'][tid] = {'status': 'TODO', 'note': note, 'at': at}
                    state.setdefault('reopened', {})[tid] = at
                    state['authorized'].pop(self._tasks[tid]['owner'], None)
                    moved.append(tid)
            return {'status': 'REOPENED', 'tasks': moved}

    def _guard(self, state, current, *, paths=None, pending=True):
        original = self._plan['sources']
        selected = self._features.values() if paths is None else [
            row for row in self._features.values() if feature_paths(row).intersection(paths)]
        for row in selected:
            fid = row['id']
            if pending:
                require(not self._pending(row, state), f'{fid}: unresolved scoped user approval')
                require(not self._unknown(row), f'{fid}: behavior is UNVERIFIED')
            for name in set(row.get('oracle_paths', [])).intersection(current):
                require(current[name] == original[name], f'{fid}: frozen oracle changed: {name}')
        for name, value in current.items():
            if value is not None or original[name] is None:
                continue
            affected = [row for row in selected if name in feature_paths(row)]
            require(affected, f'Prohibited source deletion: {name}')
            for row in affected:
                # Non-pinned legacy test suites can be replaced; independent QA
                # must review deletion/moves just as it reviews edited test bytes.
                if name in row['test_paths'] and name != row['path'] and name not in row['related_paths']:
                    continue
                allowed = row['effect'] == 'REMOVE_EXPLICITLY_REQUESTED' or (
                    row['effect'] == COLLATERAL and row.get('removes') and not self._pending(row, state))
                require(name == row['path'] and (allowed or row.get('relocation')),
                        f'{row["id"]}: prohibited source deletion: {name}')
                if not allowed:
                    complete = snapshot(self.project, original)
                    require(complete[row['relocation']] is not None and state['admitted_at'],
                            f'{row["id"]}: compatible relocation needs a present destination and admitted replay')
                    contracts = self._contracts()
                    self._proof_sources(complete, {selector(sel)[0]: contracts[selector(sel)[0]]
                                                   for sel in row['checks']})
                    for sel in row['checks']:
                        self._execution(sel, complete, contracts, after=state['admitted_at'])

    def guard_candidate(self, paths=None):
        selected = self._select_paths(paths)
        with self._state() as state:
            self._guard(state, snapshot(self.project, selected), paths=selected)
        return True

    def _select_paths(self, paths):
        if paths is None:
            return set(self._plan['sources'])
        paths = tuple(paths)
        for scope in paths:
            strict_io.scope_key(scope)
        return {path for path in self._plan['sources'] if any(strict_io.overlaps(p, path) for p in paths)}

    def _changed_tests(self, sources):
        tests = {name for row in self._features.values() for name in row['test_paths']}
        return sorted(name for name in tests if sources[name] != self._plan['sources'][name])

    def _review_input(self, sources, contracts, state):
        def latest(sel):
            try:
                return self._latest(sel, contracts)['sha256']
            except CHECK_ERRORS:
                return None

        def placeholders(names):
            return {key: {'verdict': None, 'observations': ''} for key in sorted(names)}

        return {'schema': 1, 'mission_sha256': self.binding, 'source_digest': proof.digest(sources),
                'ledger_epoch': proof.digest(state.get('reopened', {})),
                'checks': {sel: latest(sel) for sel in self._spec['checks']},
                'tasks': placeholders(self._tasks), 'features': placeholders(self._features),
                'changed_tests': placeholders(self._changed_tests(sources)), 'method': None, 'reviewer': ''}

    def review_input(self):
        with self._state() as state:
            return self._review_input(snapshot(self.project, self._plan['sources']), self._contracts(), state)

    def _validate_review(self, body, state):
        require(isinstance(body, dict) and type(body.get('schema')) is int and body['schema'] == 1,
                'Expected structured mission review schema 1')
        require(state['admitted_at'], 'Mission review requires pre-edit admission')
        require(body.get('method') in {'human', 'fresh-context-agent', 'external-verifier'},
                'Record the actual independent review method')
        reviewer = text(body.get('reviewer'), 'Independent reviewer identity', maximum=256)
        require(reviewer.strip().casefold() != self._plan['author'].strip().casefold(),
                'Review identity must differ from the implementation author')
        current = snapshot(self.project, self._plan['sources'])
        self._guard(state, current)
        contracts = self._contracts()
        self._proof_sources(current, contracts)
        expected = self._review_input(current, contracts, state)
        for key in ('mission_sha256', 'source_digest', 'ledger_epoch', 'checks'):
            require(body.get(key) == expected[key], f'Mission review {key} is missing, stale or not exact')
        for section in ('tasks', 'features', 'changed_tests'):
            require(isinstance(body.get(section), dict) and body[section].keys() == expected[section].keys(),
                    f'Mission review needs exact {section} coverage')
            for key, row in body[section].items():
                require(isinstance(row, dict) and str(row.get('verdict')).casefold() == 'pass',
                        f'Mission review {section}/{key} must pass')
                text(row.get('observations'), f'{section}/{key} actual review observations', minimum=12)
        prior_review = state['review']
        prior_digest = proof.digest(prior_review['body']) if prior_review else None
        for tid, row in state['progress'].items():
            require(row['status'] in {'VERIFYING', 'VERIFIED'},
                    f'Mandatory mission TODO {tid} has not reached VERIFYING: {row["status"]}')
            if row['status'] == 'VERIFIED':
                require(prior_digest and row.get('review_sha256') == prior_digest and
                        row.get('verified_source_digest') == self._task_digest(tid, current),
                        f'Mission TODO {tid} has stale reviewed source; reopen and reimplement it before QA')
        self._baseline_evidence(contracts)
        fresh_after = {}
        for tid, at in state.get('reopened', {}).items():
            for sel in self._tasks[tid]['checks']:
                child = selector(sel)[0]
                fresh_after[child] = max(fresh_after.get(child, state['admitted_at']), at)
        for sel, receipt in expected['checks'].items():
            ref, _ = self._execution(sel, current, contracts,
                                     after=fresh_after.get(selector(sel)[0], state['admitted_at']))
            require(ref['sha256'] == receipt, f'{sel}: execution was superseded during review')
        require(snapshot(self.project, current) == current, 'Mission source changed during review')
        self._proof_sources(current, contracts)
        require(all(self._latest(sel, contracts)['sha256'] == value for sel, value in expected['checks'].items()),
                'Execution evidence was superseded during review')
        return {'status': 'MISSION_VERIFIED', 'passed': True, 'goal_id': self.goal_id,
                'mission_sha256': self.binding, 'request_sha256': self._spec['request_sha256'],
                'review_sha256': proof.digest(body), 'source_digest': expected['source_digest'],
                'checks': expected['checks']}

    def validate_review(self, body):
        with self._state() as state:
            return self._validate_review(body, state)

    def accept_review(self, body, evidence_ref=None):
        require(evidence_ref is None or is_hash(evidence_ref), 'Invalid Team QA receipt SHA-256')
        with self._state(write=True) as state:
            result = self._validate_review(body, state)
            reconciled = snapshot(self.project, self._plan['sources'])
            require(proof.digest(reconciled) == result['source_digest'], 'Mission source changed during review')
            state['inspected'] = reconciled
            state['review'] = {'body': body, 'evidence_ref': evidence_ref, 'at': utc()}
            for tid, row in state['progress'].items():
                row.update(status='VERIFIED', review_sha256=result['review_sha256'], at=utc(),
                           verified_source_digest=self._task_digest(tid, reconciled))
            return {**result, 'evidence_ref': evidence_ref}

    def verify(self, evidence_ref=None):
        with self._state() as state:
            review = state['review']
            require(review and (evidence_ref is None or evidence_ref == review['evidence_ref']),
                    'No current independently accepted mission review for this evidence reference')
            unfinished = [tid for tid, row in state['progress'].items() if row['status'] != 'VERIFIED']
            require(not unfinished, f'Mission TODO ledger has unfinished items: {unfinished}')
            result = self._validate_review(review['body'], state)
            require(all(row.get('review_sha256') == result['review_sha256']
                        for row in state['progress'].values()), 'Mission TODO ledger review evidence differs')
            return {**result, 'evidence_ref': review['evidence_ref']}

    def context(self, owner=None, scopes=()):
        paths = self._select_paths(scopes if scopes or owner is not None else None)
        tids = self._owner_tasks(owner) if owner is not None else {
            tid for tid in self._tasks if not scopes or self._task_paths(tid).intersection(paths)}
        tids |= set().union(*(self._ancestors[tid] for tid in tids))
        if owner is not None:
            paths |= set().union(*(self._task_paths(tid) for tid in tids))
        features = [row for row in self._features.values()
                    if tids.intersection(self._affected(row['tasks'])) or (scopes and paths & feature_paths(row))]
        paths |= set().union(*(feature_paths(row) for row in features))
        original = self._plan['sources']
        with self._state() as state:
            sources = {}
            for name in sorted(paths):
                error = None
                try:
                    value = file_identity(self.project, name)
                except (ValueError, OSError) as exc:
                    value, error = None, str(exc)
                stale = error is not None or value != state['inspected'][name]
                sources[name] = {'baseline_sha256': original[name], 'inspected_sha256': state['inspected'][name],
                                 'current_sha256': value,
                                 'status': 'STALE_REINSPECT' if stale else 'CURRENT_SOURCE'}
                if error:
                    sources[name]['error'] = error
            stale_paths = {name for name, value in sources.items() if value['status'] == 'STALE_REINSPECT'}
            different = {name for name, value in sources.items() if value['current_sha256'] != original[name]}
            reviewed = False
            if state['review'] and any(state['progress'][tid]['status'] == 'VERIFIED' for tid in tids):
                try:
                    self._validate_review(state['review']['body'], state)
                    reviewed = True
                except CHECK_ERRORS:
                    pass
            features = [{**row, 'baseline_sha256': original[row['path']],
                         'current_sha256': sources[row['path']]['current_sha256'],
                         'status': ('BLOCKED_APPROVAL' if self._pending(row, state) else
                                    'UNVERIFIED' if self._unknown(row) or stale_paths & feature_paths(row) else
                                    'REVIEWED_CURRENT' if reviewed else
                                    'REINSPECTED_NOT_VERIFIED' if different & feature_paths(row) else 'BASELINE_CONTRACT'),
                         'stale_paths': sorted(stale_paths & feature_paths(row)),
                         'decision': self._bound_decision(row, state)} for row in features]
            tasks = []
            for tid, row in self._tasks.items():
                if tid not in tids:
                    continue
                progress = state['progress'][tid]
                blocks = self._blocks({tid}, state)
                recorded = progress['status']
                status = recorded
                if recorded != 'CANCELLED_BY_USER':
                    if any(self._pending(feature, state) for feature in blocks):
                        status = 'BLOCKED_APPROVAL'
                    elif recorded == 'VERIFIED' and not reviewed:
                        status = 'UNVERIFIED'
                tasks.append({**row, **progress, 'status': status, 'recorded_status': recorded,
                              'blocked_features': [feature['id'] for feature in blocks],
                              'blocking_reason': ('Scoped approval is absent or denied' if status == 'BLOCKED_APPROVAL'
                                                  else progress.get('note') if status == 'BLOCKED_ENVIRONMENT'
                                                  else None)})
            selected_checks = {sel for row in tasks for sel in row['checks']}
            proof_tasks = {selector(sel)[0] for sel in selected_checks}
            return deepcopy({
                'schema': 1, 'goal_id': self.goal_id, 'mission_sha256': self.binding,
                'request_sha256': self._spec['request_sha256'], 'revision': self._spec['revision'],
                'current_revision': revision(self.project),
                'admitted_at': state['admitted_at'], 'sources': sources, 'features': features, 'tasks': tasks,
                'requirements': {rid: row for rid, row in self._plan['requirements'].items()
                                 if any(task['requirement_id'] == rid for task in tasks)},
                'checks': {sel: {'sha256': value, 'baseline': self._spec['baseline_receipts'].get(sel)}
                           for sel, value in self._spec['checks'].items() if selector(sel)[0] in proof_tasks},
                'refresh': state.get('refresh'),
                'instruction': 'Reinspect stale paths before redispatch. Implement each admitted TODO explicitly. '
                               'Retain the original behavior and replay sealed checks, including negative controls. '
                               'Independent QA must inspect baseline assertions and compare any changed tests '
                               'with the old oracle before submitting review-input. No new permission is granted.',
            })


def scoped_input(project, name, limit):
    path = Path(name)
    if path.is_absolute():
        name = path.relative_to(project).as_posix()
    require(not any(part.casefold() in DENY - {proof.STATE} or part.casefold().startswith('.env')
                    for part in name.split('/')), 'Private path is not a mission input document')
    path = source_path(project, name, evidence_source=True)
    require(path.stat().st_size <= limit, f'Input document exceeds its limit: {name}')
    return path.read_bytes().decode('utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--goal')
    actions = parser.add_subparsers(dest='action', required=True)
    actions.add_parser('list')
    init = actions.add_parser('init')
    init.add_argument('--plan', required=True)
    init.add_argument('--request-file', required=True)
    init.add_argument('--origin')
    snap = actions.add_parser('snapshot')
    snap.add_argument('--source', action='append', required=True)
    actions.add_parser('status')
    actions.add_parser('pre-edit').add_argument('--owner', required=True)
    step = actions.add_parser('step')
    step.add_argument('--task', required=True)
    step.add_argument('--status', required=True)
    step.add_argument('--note', default='')
    step.add_argument('--evidence')
    step.add_argument('--origin')
    actions.add_parser('integrate')
    reopen = actions.add_parser('reopen')
    reopen.add_argument('--owner')
    reopen.add_argument('--note', required=True)
    actions.add_parser('refresh').add_argument('--note', required=True)
    decision = actions.add_parser('decision')
    decision.add_argument('--feature', required=True)
    decision.add_argument('--verdict', choices=('approve', 'deny'), required=True)
    decision.add_argument('--response', required=True)
    decision.add_argument('--origin', required=True)
    actions.add_parser('review-input')
    actions.add_parser('review').add_argument('--evidence', required=True)
    args = parser.parse_args(argv)
    if args.action not in {'list', 'snapshot'} and args.goal is None:
        parser.error('--goal is required for this action (use list to find enrolled goals)')
    project = args.project.expanduser().resolve()
    try:
        if args.action == 'list':
            out = {'project': str(project), 'current_revision': revision(project),
                   'goal_ids': Memory(project, create=False).mission_ids()}
        elif args.action == 'snapshot':
            strings(args.source, 'Sources')
            out = snapshot(project, args.source)
        elif args.action == 'init':
            draft = strict_io.loads(scoped_input(project, args.plan, MAX_DOCUMENT).removeprefix('\ufeff'))
            require(isinstance(draft, dict) and draft.get('goal_id') == args.goal, 'Draft goal does not match --goal')
            request = scoped_input(project, args.request_file, MAX_GOAL)
            out = {'mission_sha256': initialize(project, draft, request, args.origin or args.request_file)}
        else:
            mission = open_mission(project, args.goal)
            if args.action == 'status':
                out = {**mission.context(), 'original_request': mission.request}
            elif args.action == 'pre-edit':
                require(mission.admit(args.owner), 'Owner is blocked or stale; read mission status and reinspect')
                out = {'admitted': True, 'owner': args.owner, 'mission_sha256': mission.binding}
            elif args.action == 'step':
                evidence = args.evidence
                if args.status == 'CANCELLED_BY_USER' and evidence:
                    evidence = {'response': scoped_input(project, evidence, 4000), 'origin': args.origin}
                out = mission.step(args.task, args.status, args.note, evidence)
            elif args.action == 'integrate':
                out = mission.integrate()
            elif args.action == 'reopen':
                out = mission.reopen(args.owner, args.note)
            elif args.action == 'refresh':
                out = mission.refresh(args.note)
            elif args.action == 'decision':
                out = mission.decision(args.feature, args.verdict, scoped_input(project, args.response, 8000), args.origin)
            elif args.action == 'review-input':
                out = mission.review_input()
            else:
                out = mission.accept_review(strict_io.loads(
                    scoped_input(project, args.evidence, MAX_DOCUMENT).removeprefix('\ufeff')))
        print(strict_io.canonical(out))
        return 0
    except (*CHECK_ERRORS, sqlite3.Error) as exc:
        print(strict_io.canonical({'status': 'MISSION_UNVERIFIED', 'error': str(exc)}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
