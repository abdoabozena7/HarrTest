#!/usr/bin/env python3
"""Read-only experiment-reservation planner; never authorizes or launches work.

Inputs describe an already-inspected source-of-truth policy and the *unchanged*
minimum meaningful experiment. Values and provenance MUST be independently
verified against actual admission controls. Do not use protected allowances.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
import json
from pathlib import Path
import sys


def amount(value, field: str, *, positive: bool = False) -> Decimal:
    if type(value) not in (int, float, str) or (isinstance(value, str) and not value.strip()):
        raise ValueError(f'{field} must be a finite numeric amount')
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f'{field} must be a finite numeric amount') from exc
    if not number.is_finite() or number < 0 or (positive and number == 0):
        raise ValueError(f'{field} must be {"positive" if positive else "nonnegative"} and finite')
    return number


def show(number: Decimal | None):
    return None if number is None else format(number, 'f')


def plan(policy: dict, experiment: dict) -> dict:
    """Plan arithmetic only; positive result is NOT a permit or acceptance proof."""
    if not isinstance(policy, dict) or not isinstance(experiment, dict):
        raise ValueError('policy and experiment must be objects')
    unit = policy.get('unit')
    if not isinstance(unit, str) or not unit or experiment.get('unit') != unit:
        raise ValueError('unit mismatch or missing unit')
    if type(policy.get('protected')) is not bool or policy['protected']:
        raise ValueError('policy must explicitly identify an unprotected resource pool')
    minimum = amount(policy.get('min_execution'), 'policy.min_execution', positive=True)
    maximum = amount(policy.get('max_execution'), 'policy.max_execution', positive=True)
    fixed = amount(policy.get('fixed_reserve'), 'policy.fixed_reserve')
    balance = amount(policy.get('spendable'), 'policy.spendable')
    if maximum < minimum:
        raise ValueError('policy maximum is below policy minimum')
    science_min = amount(experiment.get('minimum_meaningful_execution'), 'experiment.minimum_meaningful_execution', positive=True)
    preferred = amount(experiment.get('preferred_execution'), 'experiment.preferred_execution', positive=True)
    if preferred < max(science_min, minimum):
        raise ValueError('preferred execution is below the policy or scientific minimum')
    if preferred > maximum:
        raise ValueError('preferred execution exceeds policy maximum')
    if type(experiment.get('may_shorten_preferred')) is not bool:
        raise ValueError('experiment.may_shorten_preferred must be boolean')
    granularity = amount(experiment.get('execution_granularity', 1), 'experiment.execution_granularity', positive=True)
    margin = amount(experiment.get('unspent_margin', 0), 'experiment.unspent_margin')
    scientific_floor = max(minimum, science_min)
    effective_floor = scientific_floor if experiment['may_shorten_preferred'] else preferred
    policy_total = minimum + fixed
    useful_total = scientific_floor + fixed
    effective_total = effective_floor + fixed
    preferred_total = preferred + fixed
    room = balance - fixed - margin
    largest_candidate = max(Decimal(0), room)
    largest_candidate = (largest_candidate / granularity).to_integral_value(rounding=ROUND_FLOOR) * granularity
    candidate = min(preferred, maximum, largest_candidate)
    feasible = candidate >= effective_floor
    if not feasible:
        candidate = None
    total = (candidate + fixed) if candidate is not None else None
    return {
        'status': 'CANDIDATE_READ_ONLY_NOT_AUTHORIZED' if feasible else 'BLOCKED_RESOURCE_READ_ONLY',
        'unit': unit,
        'policy_minimum_total': show(policy_total),
        'meaningful_minimum_total': show(useful_total),
        'effective_minimum_total': show(effective_total),
        'preferred_total': show(preferred_total),
        'spendable': show(balance),
        'minimum_policy_shortfall': show(max(Decimal(0), policy_total - balance)),
        'minimum_meaningful_shortfall': show(max(Decimal(0), useful_total + margin - balance)),
        'minimum_effective_shortfall': show(max(Decimal(0), effective_total + margin - balance)),
        'candidate_execution': show(candidate),
        'candidate_reservation': show(total),
        'unspent_if_admitted': show(balance - total) if total is not None else None,
        'protected_funds_used': False,
        'host_preflight_required': True,
        'authorization_granted': False,
        'changes_policy_or_thresholds': False,
        'warning': 'Only supplied arithmetic was checked: verify policy minima, meaningful goal length, trusted consent, current source, phase, actual host admission and final original acceptance separately.',
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('policy', type=Path)
    parser.add_argument('experiment', type=Path)
    args = parser.parse_args(argv)
    try:
        result = plan(json.loads(args.policy.read_text(encoding='utf-8-sig')),
                      json.loads(args.experiment.read_text(encoding='utf-8-sig')))
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({'status': 'INVALID_PLAN', 'error': str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'CANDIDATE_READ_ONLY_NOT_AUTHORIZED' else 1


if __name__ == '__main__':
    sys.exit(main())
