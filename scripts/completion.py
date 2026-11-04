"""Root-aware stop disposition. Ending a turn is never itself goal acceptance."""
from __future__ import annotations
from pathlib import Path
import strict_io


def inspect_roots(task, active):
    import root_gate
    import proof
    project = Path(proof.load(task / 'context.json')['project']).resolve()
    base = project / proof.STATE / root_gate.ROOT_DIR
    selected = active.get('root_goal')
    if selected:
        proof.identifier(selected, 'active root goal')
        chosen = strict_io.scoped_path(base, selected)
        contract = proof.load(chosen / 'root-contract.json')
        linked = {s['task_id'] for r in contract['requirements'] for s in r['satisfiers']}
        if task.name not in linked:
            raise ValueError('Selected root does not own the active child')
        goals = [chosen]
    else:
        goals = []
        if base.exists():
            for candidate in sorted(base.iterdir()):
                if candidate.is_symlink():
                    raise ValueError('Root-goal symlink is not permitted')
                if not candidate.is_dir():
                    continue
                contract = proof.load(candidate / 'root-contract.json')
                children = {s['task_id'] for r in contract['requirements'] for s in r['satisfiers']}
                if task.name in children:
                    goals.append(candidate)
    return [root_gate.check_root(goal) for goal in goals]


def hook(payload):
    import proof
    cwd = Path(payload.get('cwd') or Path.cwd())
    task, active = proof.find_active(cwd)
    if task is None:
        return {}
    session = payload.get('sessionId') or payload.get('session_id')
    if active.get('session_id') and session != active['session_id']:
        return {}
    # A host should not call stop hooks on cancellation; honor explicit signals too.
    if payload.get('user_requested_stop') is True or payload.get('stop_reason') in {'user_stop', 'cancelled', 'host_limit'}:
        proof.save(task / 'completion.json', {'disposition': 'HOST_STOPPED', 'root_goal_achieved': False})
        return {}
    result = proof.verify(task)
    if not (task / 'gate.json').exists():
        proof.save(task / 'gate.json', result)
    errors = list(result['errors'])
    try:
        roots = inspect_roots(task, active)
    except (ValueError, proof.ProofError, OSError, KeyError, TypeError) as exc:
        roots = []
        errors.append('Root binding cannot be verified: ' + str(exc))
    for root in roots:
        if not root['root_goal_achieved']:
            errors.extend(root.get('errors') or ['Original root goal remains unverified'])
    if active.get('root_required') is True and not roots:
        errors.append('Required original root is not bound to this session')
    verified = bool(roots) and all(r['root_goal_achieved'] for r in roots) and result['passed']
    report = {'at': proof.now(), 'child': result['status'], 'roots': roots,
              'root_goal_achieved': verified, 'errors': errors,
              'disposition': 'GOAL_COMPLETE' if verified else 'CHILD_ONLY' if not errors else 'CONTINUE'}
    # Do not overwrite historical child/root gate.json on a stop callback.
    proof.save(task / 'completion.json', report)
    if not errors:
        return {}
    if (task / 'blocked.json').exists():
        report['disposition'] = 'PAUSED_ACTION_REQUIRED'
        proof.save(task / 'completion.json', report)
        return {}
    signature = proof.digest({'errors': errors, 'source': result.get('source_digest'),
                              'checks': result.get('checks'), 'plan': result.get('plan')})
    previous = proof.load(task / 'hook-state.json') if (task / 'hook-state.json').exists() else {}
    forced = payload.get('stop_hook_active') is True or payload.get('stopHookActive') is True
    if forced and previous.get('signature') == signature:
        report['disposition'] = 'PAUSED_UNVERIFIED'
        proof.save(task / 'completion.json', report)
        proof.save(task / 'needs-attention.json', {'status': 'PAUSED_UNVERIFIED', 'errors': errors})
        return {}
    proof.save(task / 'hook-state.json', {'at': proof.now(), 'signature': signature})
    return {'decision': 'block', 'reason': 'HarrTest: original-goal completion is NOT verified. '
            'Continue the next authorized implementation or real validation. Preserve original '
            'requirements, failures and permissions. If genuinely blocked, record the exact '
            'action needed; never relabel child success as root completion. ' + '; '.join(errors[:6])}
