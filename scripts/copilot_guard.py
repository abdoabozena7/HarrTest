"""Optional Copilot CLI preToolUse check for Corporate edits and dispatch."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from uuid import UUID

import corporate
import proof
import strict_io


WRITERS = ('create', 'edit', 'apply_patch', 'str_replace_editor')
GUARDED_TOOLS = (*WRITERS, 'task')
TASK_FIELDS = {'name', 'agent_type', 'mode', 'prompt', 'description', 'model', 'reasoning_effort'}
PATCH_DIRECTIVES = ('*** Add File: ', '*** Update File: ', '*** Delete File: ', '*** Move to: ')
MAX_EVENT_BYTES = 2_000_000


def patch_targets(body):
    if not isinstance(body, str):
        raise ValueError('Expected a native apply_patch body')
    lines = body.strip().splitlines()
    if not lines or lines[0] != '*** Begin Patch' or lines[-1] != '*** End Patch':
        raise ValueError('Missing patch boundary')
    targets = []
    has_file = False
    for line in lines[1:-1]:
        for directive in PATCH_DIRECTIVES:
            if line.startswith(directive):
                targets.append(line[len(directive):].strip())
                has_file |= directive != '*** Move to: '
                break
        else:
            if line.startswith('*** ') and line != '*** End of File':
                raise ValueError('Unsupported native patch directive')
    if not has_file:
        raise ValueError('No file edit in patch')
    return targets


def targets(tool, args):
    if isinstance(args, str) and not args.lstrip().startswith('*** Begin Patch'):
        args = strict_io.loads(args)
    if tool == 'apply_patch':
        return patch_targets(args.get('patch') if isinstance(args, dict) else args)
    if not isinstance(args, dict):
        raise ValueError('Expected structured native edit arguments')
    if tool == 'str_replace_editor' and args.get('command') == 'view':
        return []
    paths = [args[name] for name in ('path', 'file_path') if name in args]
    if len(paths) != 1:
        raise ValueError('Expected a single native edit path')
    return paths


def product_target(project, cwd, value):
    if not isinstance(value, str) or not value.strip() or '\x00' in value:
        raise ValueError('Invalid native edit path')
    name = Path(value)
    if name.anchor and not name.is_absolute():
        raise ValueError('Ambiguous native edit path')
    destination = (cwd / name).resolve()
    return destination.is_relative_to(project) and not destination.is_relative_to(project / proof.STATE)


def admission_is_current(project, goal):
    """Compare bounded records issued by Team packets against their current files."""
    team_dir = f'{proof.STATE}/teams/{goal}'
    goal_dir = f'{proof.STATE}/root-goals/{goal}'

    def record(name):
        return corporate.document(corporate.path(project, name))

    def bound_record(name):
        obj = record(name)
        digest = obj.pop('sha256')
        if strict_io.digest(obj) != digest:
            raise ValueError('Invalid Corporate evidence digest')
        return obj, digest

    admitted, _ = bound_record(f'{team_dir}/corporate-dispatch.json')
    state = record(f'{team_dir}/state.json')
    state_digest = state.pop('state_sha256')
    plan = state['plan']
    if (strict_io.digest(state) != state_digest or strict_io.digest(plan) != state['plan_sha256']
            or plan['id'] != goal or plan['schema'] != 2 or plan.get('host', {}).get('kind') != 'copilot'
            or plan.get('decomposition') != 'reviewed-v1' or plan.get('root_protocol') != corporate.PROTOCOL):
        return False
    review, review_digest = bound_record(f'{team_dir}/receipts/plan_review.json')
    if (review['id'] != 'plan_review' or review['verdict'] != 'pass' or review['state'] != state_digest
            or review['plan'] != state['plan_sha256'] or len(review['files']) != 1):
        return False
    evidence, evidence_digest = next(iter(review['files'].items()))
    if not evidence.startswith(f'{team_dir}/plan-review-evidence/'):
        return False
    review_file = corporate.path(project, evidence)
    if not (review_file.is_file() and 0 < review_file.stat().st_size <= corporate.MAX_DOCUMENT
            and proof.file_hash(review_file) == evidence_digest):
        return False
    contract = record(f'{goal_dir}/root-contract.json')
    seal = record(f'{goal_dir}/root-seal.json')
    request = corporate.path(project, f'{goal_dir}/original-request.txt')
    corporate_plan = corporate.path(project, contract['corporate']['plan'])
    if (contract['schema'] != 4 or contract['protocol'] != corporate.PROTOCOL
            or contract['goal_id'] != goal or contract['production_team'] != goal
            or contract.get('team_decomposition') != 'reviewed-v1'
            or not request.is_file() or request.stat().st_size > corporate.MAX_DOCUMENT
            or proof.file_hash(request) != contract['request_sha256']
            or seal['request_sha256'] != contract['request_sha256']
            or seal['root_hash'] != strict_io.digest(contract)
            or not corporate_plan.is_file() or corporate_plan.stat().st_size > corporate.MAX_DOCUMENT
            or seal['corporate']['plan_sha256'] != proof.file_hash(corporate_plan)
            or seal['reviewed_team'] != {'state_sha256': state_digest, 'review_sha256': review_digest}):
        return False
    if not (corporate.instant(review['at']) <= corporate.instant(seal['sealed_at'])
            <= corporate.instant(admitted['admitted_at']) <= datetime.now(timezone.utc)):
        return False
    return admitted['binding'] == {
        'root_hash': seal['root_hash'], 'seal_sha256': strict_io.digest(seal), 'sealed_at': seal['sealed_at'],
        'team_state_sha256': state_digest, 'team_review_sha256': review_digest,
    }


def deny(reason):
    return {'permissionDecision': 'deny', 'permissionDecisionReason': 'HarrTest: ' + reason}


def exact_plan_review(project, goal, args):
    """Allow the private review packet from the current registered Team."""
    if (not isinstance(args, dict) or args.keys() - TASK_FIELDS or args.get('name') != 'plan_review'
            or args.get('agent_type') not in ('general-purpose', 'task')
            or args.get('mode', 'sync') not in ('sync', 'background')
            or not all(isinstance(value, str) for value in args.values())):
        return False
    import team
    import team_v2

    state_path = corporate.path(project, f'{proof.STATE}/teams/{goal}/state.json')
    if not state_path.is_file() or state_path.stat().st_size > corporate.MAX_DOCUMENT:
        return False
    state = team.load_state(project, goal)
    plan = state['plan']
    if (plan.get('schema') != 2 or plan.get('host', {}).get('kind') != 'copilot'
            or plan.get('decomposition') != 'reviewed-v1' or plan.get('root_protocol') != corporate.PROTOCOL):
        return False
    original = corporate.path(project, f'{proof.STATE}/root-goals/{goal}/original-request.txt')
    if not original.is_file() or original.stat().st_size > corporate.MAX_DOCUMENT:
        return False
    team.binding(project, goal, proof.file_hash(original))
    packet = team_v2.plan_review_packet(project, state)
    return args.get('prompt') == packet['message'] and team.snapshot(project, state['baseline']) == state['baseline']


def ready(project, goal):
    try:
        return admission_is_current(project, goal)
    except (ValueError, TypeError, KeyError, AttributeError, OSError, proof.ProofError):
        return False


def decide_task(project, goal, args):
    if ready(project, goal):
        return {}
    try:
        if isinstance(args, str):
            args = strict_io.loads(args)
        if exact_plan_review(project, goal, args):
            return {}
    except (ValueError, TypeError, KeyError, AttributeError, OSError, RecursionError, proof.ProofError):
        pass
    return deny(f'Before dispatching a worker for {goal}, seal the reviewed Corporate root and run '
                f'team.py packets --team {goal}. Before sealing, dispatch only the exact plan_review '
                'packet returned by Team init.')


def decide(project, goal, session, event):
    if not isinstance(event, dict) or event.get('sessionId') != session or event.get('toolName') not in GUARDED_TOOLS:
        return {}
    try:
        cwd = Path(event['cwd'])
        if not cwd.is_absolute():
            return deny('The native action did not report an absolute project directory.')
        cwd = cwd.resolve()
        if not cwd.is_relative_to(project):
            return {}
        if event['toolName'] == 'task':
            return decide_task(project, goal, event.get('toolArgs'))
        paths = targets(event['toolName'], event['toolArgs'])
        # Resolve every path before deciding, including patch move destinations.
        product_paths = [product_target(project, cwd, name) for name in paths]
    except (ValueError, TypeError, KeyError, OSError, RuntimeError):
        return deny('The native edit did not report usable file paths.')
    if not any(product_paths) or ready(project, goal):
        return {}
    return deny(f'Seal the independently reviewed Corporate root for {goal} and run '
                f'team.py packets --team {goal} before editing product files.')


def config(project, goal, session):
    return {'version': 1, 'hooks': {'preToolUse': [{
        'type': 'command', 'matcher': '|'.join(GUARDED_TOOLS), 'exec': sys.executable,
        'args': ['-B', str(Path(__file__).resolve()), 'pre-tool', '--project', str(project),
                 '--goal', goal, '--session', session],
        'timeoutSec': 5,
    }]}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('config', 'pre-tool'))
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--goal', required=True)
    parser.add_argument('--session', required=True)
    args = parser.parse_args()
    project = args.project.resolve(strict=True)
    proof.identifier(args.goal, 'Corporate goal ID')
    if not project.is_dir() or str(UUID(args.session)) != args.session:
        parser.error('Use an existing checkout and the canonical Copilot session UUID')
    if args.action == 'config':
        result = config(project, args.goal, args.session)
    else:
        raw = sys.stdin.buffer.read(MAX_EVENT_BYTES + 1)
        try:
            event = strict_io.loads(raw) if len(raw) <= MAX_EVENT_BYTES else None
        except (ValueError, UnicodeError, RecursionError):
            event = None
        result = decide(project, args.goal, args.session, event)
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
