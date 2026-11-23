#!/usr/bin/env python3
"""Deterministic execution-tier threshold contract for proportional HarrTest work.

Evaluates whether a task should run directly in the current agent (ordinary work)
or escalate to scoped subagents, parallel Team owners, Corporate root, or
user-requested git branch/worktree isolation. Read-only; never spawns workers,
creates branches, or authorizes permissions.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

import strict_io

PROTOCOL = 'execution-threshold-v1'
SCHEMA = 1
MAX_DELIVERABLES = 16

EXPLICIT_MODES = frozenset({
    'auto',
    'read_only_plan',
    'direct',
    'subagents',
    'team',
    'corporate',
})

TASK_KINDS = frozenset({
    'read_only',
    'data_or_script',
    'single_surface',
    'localized_change',
    'cross_cutting_change',
    'greenfield_product',
})

RISK_DOMAINS = frozenset({
    'security_boundary',
    'destructive_migration',
    'concurrency_or_recovery',
    'strict_performance_or_streaming',
    'visual_craft_system',
})

TOP_KEYS = frozenset({'schema', 'user_intent', 'task_signals'})
INTENT_KEYS = frozenset({
    'explicit_mode',
    'requested_subagents',
    'forbid_subagents',
    'requested_branch',
    'requested_worktree',
    'corporate_enrolled',
})
SIGNAL_KEYS = frozenset({
    'kind',
    'estimated_write_files',
    'independent_deliverables',
    'disjoint_write_scopes',
    'stable_interface',
    'independent_checks',
    'shared_public_contract',
    'high_risk_domains',
    'conflicting_checkouts',
})


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _bool_field(mapping: dict, key: str, default: bool = False) -> bool:
    value = mapping.get(key, default)
    _require(type(value) is bool, f'{key} must be an explicit boolean')
    return value


def _nonneg_int(mapping: dict, key: str, default: int, *, maximum: int | None = None) -> int:
    value = mapping.get(key, default)
    _require(type(value) is int and value >= 0, f'{key} must be a nonnegative integer')
    if maximum is not None:
        _require(value <= maximum, f'{key} exceeds bounded limit ({maximum})')
    return value


def evaluate(payload: dict, *, env: dict[str, str] | None = None) -> dict:
    """Evaluate user_intent and task_signals under execution-threshold-v1."""
    _require(isinstance(payload, dict), 'Threshold input must be a JSON object')
    unknown_top = set(payload) - TOP_KEYS
    _require(not unknown_top, 'Unknown threshold key(s): ' + ', '.join(sorted(unknown_top)))

    schema = payload.get('schema', SCHEMA)
    _require(type(schema) is int and schema == SCHEMA, f'Expected threshold schema {SCHEMA}')

    raw_intent = payload.get('user_intent', {})
    _require(isinstance(raw_intent, dict), 'user_intent must be a JSON object')
    unknown_intent = set(raw_intent) - INTENT_KEYS
    _require(not unknown_intent, 'Unknown user_intent key(s): ' + ', '.join(sorted(unknown_intent)))

    raw_signals = payload.get('task_signals')
    _require(isinstance(raw_signals, dict), 'task_signals must be a JSON object')
    unknown_signals = set(raw_signals) - SIGNAL_KEYS
    _require(not unknown_signals, 'Unknown task_signals key(s): ' + ', '.join(sorted(unknown_signals)))

    env_map = os.environ if env is None else env
    explicit_mode = raw_intent.get('explicit_mode', 'auto')
    _require(isinstance(explicit_mode, str) and explicit_mode in EXPLICIT_MODES,
             'user_intent.explicit_mode must be one of: ' + ', '.join(sorted(EXPLICIT_MODES)))

    requested_subagents = _bool_field(raw_intent, 'requested_subagents', False)
    forbid_subagents = _bool_field(raw_intent, 'forbid_subagents', False)
    requested_branch = _bool_field(raw_intent, 'requested_branch', False)
    requested_worktree = _bool_field(raw_intent, 'requested_worktree', False)
    default_enrolled = bool(str(env_map.get('HARRTEST_CORPORATE_GOAL', '')).strip())
    corporate_enrolled = _bool_field(raw_intent, 'corporate_enrolled', default_enrolled)

    _require(not (forbid_subagents and (requested_subagents or explicit_mode in {'subagents', 'team', 'corporate'})),
             'Contradictory user_intent: forbid_subagents conflicts with explicit subagent/team/corporate request')

    kind = raw_signals.get('kind')
    _require(isinstance(kind, str) and kind in TASK_KINDS,
             'task_signals.kind must be one of: ' + ', '.join(sorted(TASK_KINDS)))

    default_writes = 0 if kind == 'read_only' else 1
    estimated_write_files = _nonneg_int(raw_signals, 'estimated_write_files', default_writes, maximum=10_000)
    default_deliverables = 0 if (kind == 'read_only' or estimated_write_files == 0) else 1
    independent_deliverables = _nonneg_int(
        raw_signals, 'independent_deliverables', default_deliverables, maximum=MAX_DELIVERABLES
    )
    disjoint_write_scopes = _bool_field(raw_signals, 'disjoint_write_scopes', False)
    stable_interface = _bool_field(raw_signals, 'stable_interface', False)
    independent_checks = _bool_field(raw_signals, 'independent_checks', False)
    shared_public_contract = _bool_field(raw_signals, 'shared_public_contract', False)
    conflicting_checkouts = _bool_field(raw_signals, 'conflicting_checkouts', False)

    raw_risks = raw_signals.get('high_risk_domains', [])
    _require(isinstance(raw_risks, list) and all(isinstance(r, str) for r in raw_risks)
             and len(raw_risks) == len(set(raw_risks)),
             'task_signals.high_risk_domains must be a list of distinct domain names')
    unknown_risks = set(raw_risks) - RISK_DOMAINS
    _require(not unknown_risks,
             'Unknown high_risk_domains value(s): ' + ', '.join(sorted(unknown_risks)))
    risks = list(raw_risks)

    needs_branch = requested_branch
    needs_worktree = requested_worktree
    if requested_branch and requested_worktree:
        isolation_note = 'User explicitly requested both a dedicated git branch and an isolated worktree.'
    elif requested_worktree:
        isolation_note = 'User explicitly requested an isolated git worktree.'
    elif requested_branch:
        isolation_note = 'User explicitly requested a dedicated git branch.'
    elif conflicting_checkouts:
        isolation_note = (
            'User did not request a branch or worktree: stay on the current checkout and serialize '
            'conflicting steps, or ask explicit user confirmation before creating a worktree.'
        )
    else:
        isolation_note = 'Stay on the current branch and checkout; never create branches or worktrees unprompted.'

    split_candidates = independent_deliverables >= 2
    split_checks = (
        ('disjoint_write_scopes', disjoint_write_scopes),
        ('stable_interface', stable_interface),
        ('independent_checks', independent_checks),
        ('estimated_write_files>=2', estimated_write_files >= 2),
    )
    missing_split = [label for label, ok in split_checks if not ok]
    split_invariants_met = split_candidates and not missing_split

    if not split_candidates:
        split_rejected_reason = (
            'Parallel multi-owner splitting requires at least 2 independent deliverables; keeping 1 owner.'
            if explicit_mode == 'team' else None
        )
    elif missing_split:
        split_rejected_reason = (
            'Cannot split across multiple implementation owners without '
            + ', '.join(missing_split) + '; keeping 1 owner.'
        )
    else:
        split_rejected_reason = None

    consider_corporate = bool(shared_public_contract and 'destructive_migration' in risks)
    reasons: list[str] = []

    if explicit_mode == 'read_only_plan' or kind == 'read_only' or (
        estimated_write_files == 0 and explicit_mode not in {'subagents', 'team', 'corporate'} and not corporate_enrolled
    ):
        tier = 'read-only'
        needs_subagents = False
        needs_independent_qa = False
        max_owners = 0
        split_allowed = False
        ceremony = 'none'
        reasons.append('Read-only inspection, data query, or staged planning requires zero product edits or subagents.')
        contract_summary = (
            'Execute read-only in the current agent: inspect or fetch requested data directly, '
            'do not create .runtime-proof state, and do not spawn subagents or branches.'
        )
    elif corporate_enrolled or explicit_mode == 'corporate':
        tier = 'corporate'
        needs_subagents = True
        needs_independent_qa = True
        split_allowed = split_invariants_met
        max_owners = independent_deliverables if split_allowed else 1
        ceremony = 'corporate-v1'
        reasons.append(
            'HARRTEST_CORPORATE_GOAL is active.' if corporate_enrolled
            else 'User explicitly requested Corporate root verification.'
        )
        contract_summary = (
            f'Run Corporate root workflow (corporate-v1) with {max_owners} implementation owner(s), '
            'plan/coverage reviews, and independent QA.'
        )
    elif forbid_subagents or explicit_mode == 'direct':
        tier = 'direct'
        needs_subagents = False
        needs_independent_qa = False
        max_owners = 1
        split_allowed = False
        ceremony = 'none'
        reasons.append('User explicitly requested direct single-agent execution without subagent ceremony.')
        contract_summary = (
            'Execute directly in the current agent: make focused edits, run relevant checks inline, '
            'and skip .runtime-proof, quickstart, subagents, and unrequested branches.'
        )
    else:
        intrinsic_reasons: list[str] = []
        if kind == 'cross_cutting_change':
            intrinsic_reasons.append('cross-cutting behavioral change spans multiple module boundaries')
        if shared_public_contract and risks:
            intrinsic_reasons.append(
                'shared public contract combined with high-risk domain(s): ' + ', '.join(risks)
            )
        if shared_public_contract and estimated_write_files >= 4:
            intrinsic_reasons.append(f'shared public contract spans {estimated_write_files} write files')
        if 'destructive_migration' in risks:
            intrinsic_reasons.append('destructive migration requires baseline preservation and independent QA')
        if len(risks) >= 2:
            intrinsic_reasons.append('multiple high-risk domains intersect: ' + ', '.join(risks))
        if kind == 'greenfield_product' and (
            estimated_write_files >= 4 or split_invariants_met or 'visual_craft_system' in risks
        ):
            intrinsic_reasons.append('substantial multi-component or detail-reviewed greenfield product')
        if split_invariants_met and estimated_write_files >= 4 and kind not in {'data_or_script', 'single_surface'}:
            intrinsic_reasons.append(
                f'{independent_deliverables} disjoint deliverables with stable interface across {estimated_write_files} files'
            )

        user_requested_managed = requested_subagents or explicit_mode in {'subagents', 'team'}
        if not user_requested_managed and not intrinsic_reasons:
            tier = 'direct'
            needs_subagents = False
            needs_independent_qa = False
            max_owners = 1
            split_allowed = False
            ceremony = 'none'
            reasons.append(
                f'User did not request subagents and task ({kind}, {estimated_write_files} write file(s)) '
                'is within ordinary direct-execution threshold.'
            )
            contract_summary = (
                'Execute directly in the current agent: inspect needed context, edit/create files directly, '
                'run focused verification inline, and do not create .runtime-proof state, subagents, or branches.'
            )
        else:
            if user_requested_managed:
                reasons.append(f'User explicitly requested managed execution ({explicit_mode if explicit_mode != "auto" else "subagents"}).')
            reasons.extend(intrinsic_reasons)
            ceremony = 'team-v2' if kind == 'greenfield_product' else 'quickstart'
            can_parallelize = split_invariants_met and (
                explicit_mode == 'team'
                or requested_subagents
                or estimated_write_files >= 4
                or kind in {'cross_cutting_change', 'greenfield_product'}
            )
            if can_parallelize:
                tier = 'team-parallel'
                needs_subagents = True
                needs_independent_qa = True
                split_allowed = True
                max_owners = independent_deliverables
                contract_summary = (
                    f'Use {ceremony} with {max_owners} disjoint implementation owners and 1 independent QA worker '
                    'on the current checkout.'
                )
            else:
                tier = 'managed-single'
                needs_subagents = True
                needs_independent_qa = True
                split_allowed = False
                max_owners = 1
                contract_summary = (
                    f'Use {ceremony} with 1 implementation owner (impl) and 1 independent QA worker (qa); '
                    'do not split into multiple writers.'
                )

    return {
        'schema': SCHEMA,
        'protocol': PROTOCOL,
        'tier': tier,
        'needs_subagents': needs_subagents,
        'needs_independent_qa': needs_independent_qa,
        'needs_branch': needs_branch,
        'needs_worktree': needs_worktree,
        'max_implementation_owners': max_owners,
        'split_allowed': split_allowed,
        'split_rejected_reason': split_rejected_reason,
        'runtime_ceremony': ceremony,
        'consider_corporate': consider_corporate,
        'reasons': reasons,
        'isolation_note': isolation_note,
        'execution_contract': contract_summary,
    }


def payload_from_cli(args: argparse.Namespace) -> dict:
    if args.input is not None:
        return strict_io.loads(args.input.read_text(encoding='utf-8-sig'))
    if not args.kind:
        raise ValueError('Provide --input <json-path> or --kind <task-kind>')
    user_intent: dict[str, object] = {'explicit_mode': args.mode}
    if args.requested_subagents:
        user_intent['requested_subagents'] = True
    if args.forbid_subagents:
        user_intent['forbid_subagents'] = True
    if args.requested_branch:
        user_intent['requested_branch'] = True
    if args.requested_worktree:
        user_intent['requested_worktree'] = True
    if args.corporate_enrolled is not None:
        user_intent['corporate_enrolled'] = args.corporate_enrolled

    task_signals: dict[str, object] = {'kind': args.kind}
    if args.write_files is not None:
        task_signals['estimated_write_files'] = args.write_files
    if args.deliverables is not None:
        task_signals['independent_deliverables'] = args.deliverables
    if args.disjoint_scopes:
        task_signals['disjoint_write_scopes'] = True
    if args.stable_interface:
        task_signals['stable_interface'] = True
    if args.independent_checks:
        task_signals['independent_checks'] = True
    if args.shared_contract:
        task_signals['shared_public_contract'] = True
    if args.risk:
        task_signals['high_risk_domains'] = args.risk
    if args.conflicting_checkouts:
        task_signals['conflicting_checkouts'] = True
    return {'schema': SCHEMA, 'user_intent': user_intent, 'task_signals': task_signals}


def add_cli_arguments(parser: argparse.ArgumentParser, *, input_flag: str = '--input') -> None:
    parser.add_argument(input_flag, dest='input', type=Path,
                        help='Path to execution-threshold-v1 JSON payload')
    parser.add_argument('--kind', choices=sorted(TASK_KINDS),
                        help='Task classification when evaluating directly from CLI flags')
    parser.add_argument('--mode', default='auto', choices=sorted(EXPLICIT_MODES),
                        help='Explicit user intent mode (default: auto)')
    parser.add_argument('--write-files', type=int, help='Estimated product/test/doc files written')
    parser.add_argument('--deliverables', type=int, help='Count of genuinely independent deliverables')
    parser.add_argument('--disjoint-scopes', action='store_true',
                        help='Deliverables touch strictly disjoint write paths')
    parser.add_argument('--stable-interface', action='store_true',
                        help='Interface between deliverables is agreed before implementation')
    parser.add_argument('--independent-checks', action='store_true',
                        help='Each deliverable has its own runnable verification check')
    parser.add_argument('--shared-contract', action='store_true',
                        help='Task changes a shared public CLI/API/schema contract with external callers')
    parser.add_argument('--risk', action='append', choices=sorted(RISK_DOMAINS),
                        help='Applicable high-risk domain (repeatable)')
    parser.add_argument('--conflicting-checkouts', action='store_true',
                        help='Parallel steps cannot safely share one working tree')
    parser.add_argument('--requested-subagents', action='store_true',
                        help='User explicitly asked for subagents or independent QA')
    parser.add_argument('--forbid-subagents', action='store_true',
                        help='User explicitly asked for direct execution without subagents')
    parser.add_argument('--requested-branch', action='store_true',
                        help='User explicitly asked to create or switch a git branch')
    parser.add_argument('--requested-worktree', action='store_true',
                        help='User explicitly asked for an isolated git worktree')
    parser.add_argument('--corporate-enrolled', dest='corporate_enrolled', action='store_true', default=None,
                        help='Treat Corporate enrollment as active')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_cli_arguments(parser)
    args = parser.parse_args(argv)
    try:
        result = evaluate(payload_from_cli(args))
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({'status': 'INVALID_THRESHOLD_INPUT', 'error': str(exc)}, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
