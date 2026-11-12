#!/usr/bin/env python3
"""Host-native greenfield/multi-milestone execution over HarrTest's real proof store.

The host chooses architecture, writes code and delegates. This controller validates
its plan, gates milestone advancement, selects ready nonconflicting work, and
reuses current proof. It neither calls models nor grants execution permission.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sqlite3
import sys
import proof
import root_gate
import strict_io
import workflow
from runtime_store import Store, require, concrete


def objects(value, label, *, empty=False):
    require(isinstance(value, list) and (empty or bool(value)), label + ' must be a list')
    require(all(isinstance(v, dict) for v in value), label + ' entries must be objects')
    return value


def names(value, label, *, empty=False):
    require(isinstance(value, list) and (empty or bool(value)), label + ' must be a list')
    require(all(isinstance(v, str) and v.strip() for v in value), label + ' must contain names')
    require(len(value) == len(set(value)), label + ' contains duplicates')
    return value


def ancestors(graph):
    result, active = {}, set()
    def visit(key):
        require(key not in active, 'Milestone dependency cycle')
        if key in result:
            return result[key]
        active.add(key)
        result[key] = set()
        for dep in graph[key]:
            require(dep in graph and dep != key, 'Unknown/self milestone dependency')
            result[key].add(dep)
            result[key].update(visit(dep))
        active.remove(key)
        return result[key]
    for key in graph:
        visit(key)
    return result


def validate_plan(spec):
    """Validate declarations. A valid plan is not proof of architecture quality."""
    Store.validate(spec)
    build = spec.get('build')
    require(isinstance(build, dict) and build.get('mode') in {'greenfield', 'extension'}, 'Declare build mode')
    architecture = build.get('architecture')
    require(isinstance(architecture, dict), 'Architecture decision is required')
    for field in ('runtime', 'selected_stack', 'rationale', 'deliverable'):
        concrete(architecture.get(field), 'architecture.' + field)
    names(architecture.get('constraints'), 'architecture.constraints')
    for option in objects(architecture.get('alternatives'), 'architecture.alternatives'):
        concrete(option.get('option'), 'alternative'); concrete(option.get('tradeoff'), 'tradeoff')
    host = build.get('host')
    require(isinstance(host, dict), 'Actual host capability declaration required')
    for flag in ('delegation_available', 'stronger_model_available'):
        require(type(host.get(flag)) is bool, 'Host capability must be explicit: ' + flag)
    concrete(host.get('evidence'), 'actual host capability evidence')
    require(type(host.get('max_parallel_workers')) is int and host['max_parallel_workers'] >= 1,
            'Declare the observed/authorized host concurrency, not an invented agent count')
    tasks = {n['id']: n for n in spec['tasks']}
    stages = objects(build.get('milestones'), 'build.milestones')
    ids = [s.get('id') for s in stages]
    for mid in ids:
        proof.identifier(mid, 'milestone')
    require(len(set(ids)) == len(ids), 'Duplicate milestone ID')
    owners, requirements = {}, set()
    graph = {}
    for stage in stages:
        mid = stage['id']
        concrete(stage.get('outcome'), mid + ' observable outcome')
        require(stage.get('kind') in {'vertical_slice', 'increment', 'delivery'}, 'Invalid milestone kind')
        assigned = names(stage.get('tasks'), mid + '.tasks')
        for tid in assigned:
            require(tid in tasks and tid not in owners, 'Task missing or assigned to multiple milestones')
            owners[tid] = mid
        requirements.update(names(stage.get('requirements'), mid + '.requirements'))
        graph[mid] = names(stage.get('depends_on'), mid + '.depends_on', empty=True)
        integration = stage.get('integration_task')
        require(integration in assigned and tasks[integration].get('role') == 'integrate',
                'Every milestone needs its own real integration child')
    require(set(owners) == set(tasks), 'Every task must belong to a milestone')
    parents = ancestors(graph)
    first = [s for s in stages if not s['depends_on']]
    final = [s for s in stages if s['kind'] == 'delivery']
    require(len(first) == 1 and first[0]['kind'] == 'vertical_slice', 'Start with one runnable vertical slice')
    require(len(final) == 1 and set(ids) - {final[0]['id']} == parents[final[0]['id']],
            'One final delivery must depend on all milestones')
    task_parents = ancestors({n['id']: n.get('depends_on', []) for n in tasks.values()})
    for stage in stages:
        join = stage['integration_task']
        require(set(stage['tasks']) - {join} <= task_parents[join], 'Stage integration must follow all of its tasks')
        for tid in stage['tasks']:
            for dep in tasks[tid].get('depends_on', []):
                require(owners[dep] == stage['id'] or owners[dep] in parents[stage['id']],
                        'Task dependency contradicts milestone order')
    for boundary in objects(build.get('interfaces', []), 'build.interfaces', empty=True):
        concrete(boundary.get('id'), 'interface ID')
        producer = boundary.get('producer')
        require(producer in tasks, 'Unknown interface producer')
        for consumer in names(boundary.get('consumers'), 'interface consumers'):
            require(consumer in tasks and producer in task_parents[consumer], 'Interface consumer must depend on producer')
        concrete(boundary.get('contract_file'), 'explicit interface contract file')
    for risk in objects(build.get('risks'), 'build.risks'):
        concrete(risk.get('failure'), 'risk failure'); concrete(risk.get('probe'), 'risk probe')
        require(risk.get('milestone') in graph, 'Risk must be tested in a declared milestone')
    return {'tasks': tasks, 'stages': stages, 'owners': owners, 'parents': parents,
            'requirements': requirements, 'final': final[0]['id']}


def binding(project, spec):
    project = Path(project).resolve()
    shape = validate_plan(spec)
    linked = workflow.validate_bindings(project, spec)
    if 'production_team' in linked:
        require(spec['build']['host']['delegation_available'],
                'A production team build needs the host native delegation capability')
    goal = strict_io.scoped_path(project, spec['root_goal'])
    root = proof.load(goal / 'root-contract.json')
    require(shape['requirements'] == {r['id'] for r in root['requirements']},
            'Milestones must cover exactly the original root requirements')
    for stage in shape['stages']:
        child = strict_io.scoped_path(project, shape['tasks'][stage['integration_task']]['proof_task'])
        contract = proof.load(child / 'contract.json')
        require(any(c['role'] == 'acceptance' and c['mode'] == 'live' for c in contract['checks']),
                'A build milestone needs actual live integration, not a mock/replay')
    final = next(m for m in shape['stages'] if m['id'] == shape['final'])
    final_child = Path(shape['tasks'][final['integration_task']]['proof_task']).name
    require(final_child == root['integration']['task_id'], 'Delivery must use the original root integration')
    interfaces = {}
    for interface in spec['build'].get('interfaces', []):
        path = strict_io.scoped_path(project, interface['contract_file'])
        require(path.is_file() and path.stat().st_size <= 256000, 'Interface contracts must be bounded files')
        interfaces[interface['contract_file']] = proof.file_hash(path)
    return {'workflow': linked, 'interfaces': interfaces}


def register(project, spec):
    # Validate all files/contracts before allocating coordinator state.
    bound = binding(project, spec)
    saved = dict(spec, _bindings=bound['workflow'], _build_bindings=bound)
    store = Store(strict_io.scoped_path(project, '.runtime-proof/workflows.sqlite', must_exist=False))
    created = store.create(saved)
    return {'status': 'BUILD_PLAN_REGISTERED', 'created': created, 'goal_id': spec['goal_id'],
            'root_goal_achieved': False, 'architecture_quality_proven': False}


def open_build(project, gid):
    database = strict_io.scoped_path(project, '.runtime-proof/workflows.sqlite')
    store = Store(database)
    spec = store.goal(gid)
    require(spec.get('_build_bindings') == binding(project, spec),
            'Build/root/interface contracts changed; preserve this revision and explicitly replan')
    return store, spec, validate_plan(spec)


def snapshot(project, store, spec, shape):
    rows = {r['id']: r for r in store.inspect(spec['goal_id'])}
    proof_rows = {}
    for tid, task in shape['tasks'].items():
        proof_rows[tid] = proof.verify(strict_io.scoped_path(project, task['proof_task']))
    accepted = set()
    for event in store.audit():
        body = event['body']
        if (event['kind'] == 'BUILD_MILESTONE_ACCEPTED' and body.get('goal') == spec['goal_id']
                and body.get('plan_hash') == strict_io.digest(spec)):
            accepted.add(body['milestone'])
    stages = []
    for stage in shape['stages']:
        group = shape['parents'][stage['id']] | {stage['id']}
        cumulative = [tid for tid in shape['tasks'] if shape['owners'][tid] in group]
        errors = []
        for tid in cumulative:
            if rows[tid]['state'] not in {'IMPLEMENTED', 'VERIFIED'}:
                errors.append(tid + ': no implemented handoff')
            errors.extend(tid + ': ' + e for e in proof_rows[tid]['errors'])
        stages.append({'id': stage['id'], 'passed': not errors, 'errors': errors,
                       'previously_accepted': stage['id'] in accepted, 'cumulative_tasks': cumulative})
    return {'rows': rows, 'proof': proof_rows, 'milestones': stages}


def frontier(spec, shape, state):
    by_id = {m['id']: m for m in state['milestones']}
    for stage in shape['stages']:
        if not by_id[stage['id']]['passed'] and all(by_id[d]['passed'] for d in stage['depends_on']):
            return stage
    return None


def checks_needed(shape, state, mid):
    stage = next((s for s in state['milestones'] if s['id'] == mid), None)
    require(stage is not None, 'Unknown milestone')
    needed, reusable, other = [], [], []
    for tid in stage['cumulative_tasks']:
        report = state['proof'][tid]
        for cid, check in report.get('checks', {}).items():
            item = {'task': tid, 'check': cid, 'proof_task': shape['tasks'][tid]['proof_task']}
            (reusable if check['passed'] else needed).append(item)
        if not report.get('checks') or (report.get('errors') and all(c['passed'] for c in report.get('checks', {}).values())):
            other.append({'task': tid, 'errors': report['errors']})
    return {'run_only_missing_failed_or_stale': needed, 'reuse_current_checks': reusable,
            'review_progress_or_contract_action': other, 'permission_granted': False,
            'note': 'Do not rerun fresh passing receipts for activity. Review artifacts and task progress separately.'}


def routing(tasks, host):
    group = []
    for task in tasks:
        if not any(strict_io.conflicts(task, existing) for existing in group):
            group.append(task)
        if len(group) >= (host['max_parallel_workers'] if host['delegation_available'] else 1):
            break
    return {'mode': 'parallel-native-host' if len(group) > 1 else 'serial-current-host',
            'task_ids': [t['id'] for t in group], 'agents_spawned': False,
            'model_advice': ('Use an already-authorized stronger host model only for unresolved architecture/review decisions.'
                             if host['stronger_model_available'] else 'Use the current host model; no second provider.'),
            'local_first': True, 'new_permission_or_spending_granted': False}


def repair_pending(store, spec, row):
    return row['state'] == 'TODO' and any(
        e['kind'] == 'BUILD_REPAIR_PLANNED' and e['body'].get('goal') == spec['goal_id']
        and e['body'].get('task') == row['id'] and e['body'].get('generation') == row['generation']
        for e in store.audit())


def next_action(project, store, spec, shape):
    state = snapshot(project, store, spec, shape)
    repairs = [r for r in state['rows'].values() if r['ready'] and repair_pending(store, spec, r)]
    if repairs:
        target = shape['owners'][repairs[0]['id']]
        return {'action': 'REPAIR_REGISTERED_DEFECT', 'milestone': target,
                'routing': routing([r['spec'] for r in repairs], spec['build']['host']),
                'checks': checks_needed(shape, state, target), 'root_goal_achieved': False}
    stage = frontier(spec, shape, state)
    if stage is None:
        result = root_gate.check_root(strict_io.scoped_path(project, spec['root_goal']))
        return {'action': 'DELIVER' if result['root_goal_achieved'] else 'REPAIR_ROOT_GAP', 'root': result}
    mid = stage['id']
    report = next(r for r in state['milestones'] if r['id'] == mid)
    rows = [state['rows'][tid] for tid in stage['tasks']]
    live = [r for r in rows if r['state'] == 'RUNNING']
    ready = [r['spec'] for r in rows if r['ready'] and not any(strict_io.conflicts(r['spec'], a['spec']) for a in live)]
    if live:
        action = ('RECONCILE_EXPIRED_WORKER' if any(r['lease_expired'] for r in live) else
                  'CONTINUE_AND_DISPATCH_READY' if ready else 'CONTINUE_ACTIVE_WORK')
    elif ready:
        action = 'IMPLEMENT_MILESTONE'
    else:
        action = 'REVALIDATE_CHANGED_MILESTONE' if report['previously_accepted'] else 'VERIFY_OR_REPAIR_MILESTONE'
    return {'action': action, 'milestone': mid, 'outcome': stage['outcome'],
            'routing': routing(ready, spec['build']['host']), 'checks': checks_needed(shape, state, mid),
            'previous_work_preserved': True, 'root_goal_achieved': False,
            'active_workers': [{'task': r['id'], 'owner': r['owner'], 'expired': r['lease_expired']} for r in live]}


def gate(project, store, spec, shape, mid):
    state = snapshot(project, store, spec, shape)
    report = next((m for m in state['milestones'] if m['id'] == mid), None)
    require(report is not None, 'Unknown milestone')
    final = mid == shape['final']
    root = root_gate.check_root(strict_io.scoped_path(project, spec['root_goal'])) if final else None
    result = {**report, 'root_goal_achieved': bool(final and report['passed'] and root['root_goal_achieved']),
              'status': 'MILESTONE_VERIFIED' if report['passed'] else 'MILESTONE_UNVERIFIED', 'root': root}
    if final and root and not root['root_goal_achieved']:
        result['passed'] = False; result['status'] = 'ROOT_GOAL_UNVERIFIED'
    if result['root_goal_achieved']:
        result['status'] = 'ROOT_GOAL_VERIFIED'
    signature = strict_io.digest({k: result[k] for k in ('id', 'passed', 'errors', 'root_goal_achieved')})
    sources = {tid: state['proof'][tid].get('source_digest') for tid in report['cumulative_tasks']}
    with store.transaction() as db:
        store.event(db, 'BUILD_MILESTONE_ACCEPTED' if result['passed'] else 'BUILD_MILESTONE_REJECTED',
                    {'goal': spec['goal_id'], 'milestone': mid, 'plan_hash': strict_io.digest(spec),
                     'result_hash': signature, 'sources': sources, 'root_goal_achieved': result['root_goal_achieved']})
    return result


def claim(project, store, spec, shape, tid, owner, seconds):
    require(tid in shape['tasks'], 'Unknown task')
    state = snapshot(project, store, spec, shape)
    target = shape['owners'][tid]
    by_id = {m['id']: m for m in state['milestones']}
    row = state['rows'][tid]
    repair = repair_pending(store, spec, row)
    require(repair or all(by_id[m]['passed'] for m in shape['parents'][target]),
            'Earlier milestone integration is missing or stale; do not advance')
    context = workflow.packet(project, spec, shape['tasks'][tid])
    context['build_context'] = {'milestone': target, 'architecture': spec['build']['architecture'],
                               'interfaces': [i for i in spec['build'].get('interfaces', [])
                                              if tid == i['producer'] or tid in i['consumers']],
                               'original_acceptance_unchanged': True}
    if 'golden' in spec:
        result = workflow.golden_claim(project, store, spec, shape['tasks'][tid], owner, seconds, context)
    else:
        result = store.claim(spec['goal_id'], tid, owner, seconds)
    result['packet'] = context
    result['repair_mode'] = repair
    return result


def reopen(project, store, spec, shape, tid, evidence, reason):
    require(tid in shape['tasks'], 'Unknown task'); concrete(reason, 'new falsifiable repair hypothesis')
    require(not proof.verify(strict_io.scoped_path(project, shape['tasks'][tid]['proof_task']))['passed'],
            'A repair needs a failed/stale current gate; changed requirements need a reviewed revision')
    artifact = workflow.artifact(project, evidence)
    descendants = ancestors({n['id']: n.get('depends_on', []) for n in shape['tasks'].values()})
    affected = {tid} | {k for k, parents in descendants.items() if tid in parents}
    with store.transaction() as db:
        rows = store.rows(db, spec['goal_id'])
        target_row = next(r for r in rows if r['id'] == tid)
        require(target_row['state'] in {'IMPLEMENTED', 'VERIFIED'} or
                (target_row['state'] == 'TODO' and target_row['generation'] > 0),
                'Only previously attempted work can be reopened; do not bypass initial milestone admission')
        generation = target_row['generation']
        require(not any(r['id'] in affected and r['state'] == 'RUNNING' for r in rows), 'Active downstream workers must stop and reconcile before repair')
        require(not db.execute("SELECT key FROM operations WHERE goal=? AND state='UNKNOWN_EFFECT'", (spec['goal_id'],)).fetchall(),
                'Reconcile unknown effects before repair')
        db.execute('UPDATE tasks SET state=?,token=NULL,expires=NULL,owner=NULL WHERE goal=? AND id=?', ('TODO', spec['goal_id'], tid))
        for dependent in affected - {tid}:
            db.execute("UPDATE tasks SET state='IMPLEMENTED' WHERE goal=? AND id=? AND state='VERIFIED'", (spec['goal_id'], dependent))
        store.event(db, 'BUILD_REPAIR_PLANNED', {'goal': spec['goal_id'], 'task': tid, 'reason': reason,
                    'evidence': artifact, 'affected': sorted(affected), 'generation': generation, 'acceptance_changed': False})
    return {'status': 'REPAIR_READY', 'task': tid, 'preserved_evidence': True, 'root_goal_achieved': False}


def bootstrap(project, gid, request):
    project = Path(project).resolve()
    proof.identifier(gid, 'goal ID')
    data = Path(request).read_bytes()
    require(len(data) <= 200000, 'Original request exceeds bounded intake; do not silently truncate')
    proof.meaningful(data.decode('utf-8-sig'), 'original request', 15)
    folder = strict_io.scoped_path(project, '.runtime-proof/root-goals/' + gid, must_exist=False)
    if folder.exists():
        require((folder / 'original-request.txt').is_file() and (folder / 'original-request.txt').read_bytes() == data,
                'Existing original request differs; never overwrite it on resume')
        created = False
    else:
        folder.mkdir(parents=True)
        (folder / 'original-request.txt').write_bytes(data); created = True
    import project_memory
    memory = project_memory.Memory(project)
    memory.bootstrap(folder.relative_to(project).as_posix() + '/original-request.txt', goal_id=gid)
    return {'status': 'INTAKE_PRESERVED_NOT_IMPLEMENTED', 'created': created,
            'goal': folder.relative_to(project).as_posix(), 'request_sha256': proof.file_hash(folder / 'original-request.txt'),
            'next': 'Host drafts architecture/acceptance; create only minimal setup, seal proof children/root, then register build plan.',
            'private_memory': str(memory.directory), 'project_complete': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    sub = parser.add_subparsers(dest='command', required=True)
    start = sub.add_parser('bootstrap'); start.add_argument('--goal', required=True); start.add_argument('--request-file', type=Path, required=True)
    for name in ('validate', 'init'):
        p = sub.add_parser(name); p.add_argument('--plan', type=Path, required=True)
    for name in ('next', 'status', 'checks', 'gate', 'claim', 'reopen'):
        p = sub.add_parser(name); p.add_argument('--goal', required=True)
        if name in {'checks', 'gate'}: p.add_argument('--milestone', required=True)
        if name in {'claim', 'reopen'}: p.add_argument('--task', required=True)
        if name == 'claim': p.add_argument('--worker', required=True); p.add_argument('--lease-seconds', type=float, required=True)
        if name == 'reopen': p.add_argument('--evidence', required=True); p.add_argument('--reason', required=True)
    args = parser.parse_args(argv)
    try:
        project = args.project.resolve(); require(project.is_dir(), 'Project directory does not exist')
        if args.command == 'bootstrap':
            result = bootstrap(project, args.goal, args.request_file)
        elif args.command in {'init', 'validate'}:
            spec = proof.load(args.plan)
            if args.command == 'init': result = register(project, spec)
            else:
                binding(project, spec); result = {'status': 'DECLARED_BUILD_PLAN_VALID', 'root_goal_achieved': False}
        else:
            store, spec, shape = open_build(project, args.goal)
            if args.command == 'next': result = next_action(project, store, spec, shape)
            elif args.command == 'status':
                state = snapshot(project, store, spec, shape)
                result = {'milestones': state['milestones'], 'stored_tasks': state['rows'], 'root_goal_achieved': False}
            elif args.command == 'checks': result = checks_needed(shape, snapshot(project, store, spec, shape), args.milestone)
            elif args.command == 'gate': result = gate(project, store, spec, shape, args.milestone)
            elif args.command == 'claim': result = claim(project, store, spec, shape, args.task, args.worker, args.lease_seconds)
            else: result = reopen(project, store, spec, shape, args.task, args.evidence, args.reason)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if args.command == 'gate' and not result['passed'] else 0
    except (ValueError, proof.ProofError, OSError, KeyError, TypeError, RecursionError, sqlite3.Error) as exc:
        print(json.dumps({'status': 'BUILD_NOT_VERIFIED', 'error': str(exc)}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
