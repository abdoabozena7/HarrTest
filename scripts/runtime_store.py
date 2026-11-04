"""Transactional local task coordination. Not an OS sandbox or a model client.

Leases fence cooperative workers; an arbitrary process can still modify files.
Unknown external effects require explicit reconciliation, never blind retries.
"""
from __future__ import annotations
from contextlib import contextmanager
import math
from pathlib import Path
import sqlite3
import time
import uuid
import strict_io


class RuntimeErrorState(ValueError):
    pass


def require(test, message):
    if not test:
        raise RuntimeErrorState(message)


def concrete(value, name):
    require(isinstance(value, str) and len(value.strip()) >= 3 and 'REPLACE_ME' not in value, f'Missing concrete {name}')
    return value


class Store:
    def __init__(self, path, *, clock=time.time):
        self.path = Path(path)
        require(not self.path.is_symlink(), 'Runtime database must not be a symlink')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        with self.transaction() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS meta(version INTEGER NOT NULL);
            INSERT INTO meta SELECT 1 WHERE NOT EXISTS(SELECT 1 FROM meta);
            CREATE TABLE IF NOT EXISTS goals(
              id TEXT PRIMARY KEY, spec TEXT NOT NULL, spec_hash TEXT NOT NULL, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS tasks(
              goal TEXT NOT NULL, id TEXT NOT NULL, spec TEXT NOT NULL,
              state TEXT NOT NULL, generation INTEGER NOT NULL DEFAULT 0,
              owner TEXT, token TEXT, expires REAL, handoff TEXT,
              PRIMARY KEY(goal,id), FOREIGN KEY(goal) REFERENCES goals(id));
            CREATE TABLE IF NOT EXISTS operations(
              key TEXT PRIMARY KEY, goal TEXT NOT NULL, task TEXT NOT NULL,
              arguments_hash TEXT NOT NULL, state TEXT NOT NULL, result TEXT);
            CREATE TABLE IF NOT EXISTS events(
              seq INTEGER PRIMARY KEY, at REAL NOT NULL, kind TEXT NOT NULL,
              body TEXT NOT NULL, previous TEXT NOT NULL, hash TEXT NOT NULL);
            CREATE TRIGGER IF NOT EXISTS immutable_events_update BEFORE UPDATE ON events
              BEGIN SELECT RAISE(ABORT,'Events are append only'); END;
            CREATE TRIGGER IF NOT EXISTS immutable_events_delete BEFORE DELETE ON events
              BEGIN SELECT RAISE(ABORT,'Events are append only'); END;
            ''')
            require(db.execute('SELECT version FROM meta').fetchall() == [(1,)], 'Unknown runtime schema')

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA busy_timeout=10000')
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            if db.in_transaction:
                db.commit()
        except BaseException:
            if db.in_transaction:
                db.rollback()
            raise
        finally:
            db.close()

    def event(self, db, kind, body):
        last = db.execute('SELECT seq,hash FROM events ORDER BY seq DESC LIMIT 1').fetchone()
        seq, previous = (last[0] + 1, last[1]) if last else (1, '0' * 64)
        at = self.clock()
        record = {'seq': seq, 'at': at, 'kind': kind, 'body': body, 'previous': previous}
        db.execute('INSERT INTO events VALUES(?,?,?,?,?,?)',
                   (seq, at, kind, strict_io.canonical(body), previous, strict_io.digest(record)))

    @staticmethod
    def validate(spec):
        import re
        require(isinstance(spec, dict) and type(spec.get('schema')) is int and spec['schema'] == 1, 'Workflow schema must be 1')
        require(isinstance(spec.get('goal_id'), str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', spec['goal_id']), 'Invalid goal_id')
        concrete(spec.get('root_goal'), 'root goal path')
        nodes = spec.get('tasks')
        require(isinstance(nodes, list) and nodes, 'Workflow needs tasks')
        ids = set()
        for node in nodes:
            require(isinstance(node, dict), 'Invalid task')
            tid = node.get('id')
            require(isinstance(tid, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', tid), 'Invalid task id')
            require(tid not in ids, 'Duplicate task id'); ids.add(tid)
            concrete(node.get('outcome'), 'outcome'); concrete(node.get('proof_task'), 'proof task')
            for key in ('depends_on', 'write_scope', 'read_scope', 'resources'):
                values = node.get(key, [])
                require(isinstance(values, list) and all(isinstance(v, str) and v for v in values), f'Invalid {key}')
                require(len(values) == len(set(values)), f'Duplicate {key}')
            for name in node.get('write_scope', []) + node.get('read_scope', []):
                strict_io.scope_key(name)
            require(node.get('role', 'implement') in {'investigate', 'implement', 'review', 'integrate'}, 'Invalid task role')
        graph = {n['id']: n.get('depends_on', []) for n in nodes}
        visited, visiting = set(), set()
        def visit(tid):
            require(tid not in visiting, 'Dependency cycle')
            if tid in visited:
                return
            visiting.add(tid)
            for dep in graph[tid]:
                require(dep in ids and dep != tid, 'Unknown/self dependency')
                visit(dep)
            visiting.remove(tid); visited.add(tid)
        for tid in graph:
            visit(tid)
        return spec

    def create(self, spec):
        self.validate(spec)
        with self.transaction() as db:
            existing = db.execute('SELECT spec_hash FROM goals WHERE id=?', (spec['goal_id'],)).fetchone()
            if existing:
                require(existing[0] == strict_io.digest(spec), 'Goal already exists with a different plan; preserve history')
                return False
            db.execute('INSERT INTO goals VALUES(?,?,?,?)',
                       (spec['goal_id'], strict_io.canonical(spec), strict_io.digest(spec), self.clock()))
            for node in spec['tasks']:
                db.execute('INSERT INTO tasks(goal,id,spec,state) VALUES(?,?,?,?)',
                           (spec['goal_id'], node['id'], strict_io.canonical(node), 'TODO'))
            self.event(db, 'WORKFLOW_CREATED', {'goal': spec['goal_id'], 'spec_hash': strict_io.digest(spec)})
        return True

    def goal(self, gid):
        with self.transaction() as db:
            row = db.execute('SELECT spec,spec_hash FROM goals WHERE id=?', (gid,)).fetchone()
            require(row is not None and strict_io.digest(strict_io.loads(row[0])) == row[1], 'Missing or changed workflow spec')
            return strict_io.loads(row[0])

    def rows(self, db, gid=None):
        query = 'SELECT goal,id,spec,state,generation,owner,token,expires,handoff FROM tasks'
        rows = db.execute(query + (' WHERE goal=?' if gid else ''), (gid,) if gid else ()).fetchall()
        keys = ['goal', 'id', 'spec', 'state', 'generation', 'owner', 'token', 'expires', 'handoff']
        result = [dict(zip(keys, row)) for row in rows]
        for row in result:
            row['spec'] = strict_io.loads(row['spec'])
        return result

    def inspect(self, gid):
        self.goal(gid)
        with self.transaction() as db:
            rows = self.rows(db, gid)
            by_id = {r['id']: r for r in rows}
            for row in rows:
                row['ready'] = row['state'] == 'TODO' and all(by_id[d]['state'] in {'IMPLEMENTED', 'VERIFIED'} for d in row['spec'].get('depends_on', []))
                row['lease_expired'] = row['state'] == 'RUNNING' and self.clock() >= row['expires']
                row.pop('token')  # Tokens are not public status evidence.
            return rows

    def claim(self, gid, tid, owner, seconds):
        concrete(owner, 'actual host/worker identity')
        require(type(seconds) in (int, float) and math.isfinite(seconds) and seconds > 0, 'A finite positive coordination lease is required')
        require(math.isfinite(self.clock() + seconds), 'Lease expiry overflows the clock')
        with self.transaction() as db:
            rows = self.rows(db)
            row = next((r for r in rows if r['goal'] == gid and r['id'] == tid), None)
            require(row is not None and row['state'] == 'TODO', 'Task not ready; expired workers require explicit reconciliation')
            deps = {r['id']: r for r in rows if r['goal'] == gid}
            require(all(deps[d]['state'] in {'IMPLEMENTED', 'VERIFIED'} for d in row['spec'].get('depends_on', [])), 'Dependency not implemented')
            for running in rows:
                if running['state'] == 'RUNNING' and strict_io.conflicts(row['spec'], running['spec']):
                    raise RuntimeErrorState(f'Resource/write conflict with {running["goal"]}/{running["id"]}; expired leases still need recovery')
            token = uuid.uuid4().hex
            generation = row['generation'] + 1
            db.execute('UPDATE tasks SET state=?,generation=?,owner=?,token=?,expires=? WHERE goal=? AND id=?',
                       ('RUNNING', generation, owner, token, self.clock() + seconds, gid, tid))
            self.event(db, 'TASK_CLAIMED', {'goal': gid, 'task': tid, 'generation': generation, 'owner': owner})
            return {'goal': gid, 'task': tid, 'generation': generation, 'owner': owner, 'token': token,
                    'lease_seconds': seconds, 'spec': row['spec'], 'permission_granted': False}

    def owned(self, db, gid, tid, token):
        row = next((r for r in self.rows(db, gid) if r['id'] == tid), None)
        require(row is not None and row['state'] == 'RUNNING' and row['token'] == token, 'Stale or foreign worker token')
        require(self.clock() < row['expires'], 'Lease expired; inspect actual process and reconcile effects before recovery')
        return row

    def heartbeat(self, gid, tid, token, seconds):
        require(type(seconds) in (int, float) and math.isfinite(seconds) and seconds > 0, 'Invalid lease extension')
        require(math.isfinite(self.clock() + seconds), 'Lease expiry overflows the clock')
        with self.transaction() as db:
            self.owned(db, gid, tid, token)
            db.execute('UPDATE tasks SET expires=? WHERE goal=? AND id=?', (self.clock() + seconds, gid, tid))
            self.event(db, 'LEASE_RENEWED', {'goal': gid, 'task': tid})

    def handoff(self, gid, tid, token, receipt):
        require(isinstance(receipt, dict) and receipt.get('sha256') and receipt.get('path'), 'Retained handoff artifact required')
        with self.transaction() as db:
            self.owned(db, gid, tid, token)
            pending = db.execute("SELECT key FROM operations WHERE goal=? AND task=? AND state='UNKNOWN_EFFECT'", (gid, tid)).fetchall()
            require(not pending, 'Unknown operation effects must be reconciled before handoff')
            db.execute('UPDATE tasks SET state=?,token=NULL,expires=NULL,handoff=? WHERE goal=? AND id=?',
                       ('IMPLEMENTED', strict_io.canonical(receipt), gid, tid))
            self.event(db, 'HANDOFF_RECORDED', {'goal': gid, 'task': tid, 'receipt': receipt})

    def recover(self, gid, tid, evidence):
        require(isinstance(evidence, dict) and evidence.get('sha256') and evidence.get('path'), 'Recovery needs retained process/effect inspection evidence')
        with self.transaction() as db:
            row = next((r for r in self.rows(db, gid) if r['id'] == tid), None)
            require(row is not None and row['state'] == 'RUNNING' and self.clock() >= row['expires'], 'Only an expired lease can recover')
            pending = db.execute("SELECT key FROM operations WHERE goal=? AND task=? AND state='UNKNOWN_EFFECT'", (gid, tid)).fetchall()
            require(not pending, 'Unknown external effects: reconcile before retry')
            db.execute('UPDATE tasks SET state=?,token=NULL,expires=NULL,owner=NULL WHERE goal=? AND id=?', ('TODO', gid, tid))
            self.event(db, 'EXPIRED_WORK_RECONCILED', {'goal': gid, 'task': tid, 'evidence': evidence})

    def verify(self, gid, tid, validator):
        # Hold coordinator transaction through validation to fence cooperative changes.
        with self.transaction() as db:
            row = next((r for r in self.rows(db, gid) if r['id'] == tid), None)
            require(row is not None and row['state'] in {'IMPLEMENTED', 'VERIFIED'}, 'No implemented handoff to verify')
            result = validator(row['spec'])
            require(isinstance(result, dict) and type(result.get('passed')) is bool, 'Verifier must return a typed result')
            state = 'VERIFIED' if result['passed'] else 'IMPLEMENTED'
            db.execute('UPDATE tasks SET state=? WHERE goal=? AND id=?', (state, gid, tid))
            self.event(db, 'TASK_EVIDENCE_CHECKED', {'goal': gid, 'task': tid, 'passed': result['passed'], 'verdict_sha256': strict_io.digest(result)})
            return result

    def operation(self, gid, tid, token, key, arguments_hash):
        concrete(key, 'operation key'); concrete(arguments_hash, 'operation input digest')
        with self.transaction() as db:
            self.owned(db, gid, tid, token)
            old = db.execute('SELECT goal,task,arguments_hash,state,result FROM operations WHERE key=?', (key,)).fetchone()
            if old:
                require(old[:3] == (gid, tid, arguments_hash), 'Idempotency key reused for a different action')
                return {'execute': False, 'state': old[3], 'result': strict_io.loads(old[4]) if old[4] else None}
            db.execute('INSERT INTO operations VALUES(?,?,?,?,?,NULL)', (key, gid, tid, arguments_hash, 'UNKNOWN_EFFECT'))
            self.event(db, 'OPERATION_INTENT', {'goal': gid, 'task': tid, 'key': key, 'arguments_hash': arguments_hash})
            return {'execute': True, 'state': 'UNKNOWN_EFFECT', 'authorization_implied': False}

    def reconcile(self, key, outcome, evidence):
        require(outcome in {'OBSERVED_DONE', 'OBSERVED_NOT_DONE'}, 'Explicit reconciliation outcome required')
        require(isinstance(evidence, dict) and evidence.get('sha256') and evidence.get('path'), 'Actual read-back evidence required')
        with self.transaction() as db:
            row = db.execute('SELECT state FROM operations WHERE key=?', (key,)).fetchone()
            require(row is not None and row[0] == 'UNKNOWN_EFFECT', 'Only unresolved effects may be reconciled')
            db.execute('UPDATE operations SET state=?,result=? WHERE key=?', (outcome, strict_io.canonical(evidence), key))
            self.event(db, 'OPERATION_RECONCILED', {'key': key, 'outcome': outcome, 'evidence': evidence})
            # Even OBSERVED_NOT_DONE is not automatically retried. A new explicitly
            # linked operation key is needed after reviewing the failed attempt.

    def audit(self):
        with self.transaction() as db:
            previous = '0' * 64
            records = []
            for seq, at, kind, body, prev, sha in db.execute('SELECT * FROM events ORDER BY seq'):
                data = strict_io.loads(body)
                record = {'seq': seq, 'at': at, 'kind': kind, 'body': data, 'previous': prev}
                require(seq == len(records) + 1 and prev == previous and strict_io.digest(record) == sha, 'Event history integrity failure')
                previous = sha; records.append({**record, 'hash': sha})
            return records
