#!/usr/bin/env python3
"""Conjunctive numeric acceptance oracle; inputs are NOT authenticated evidence.

For each required gate in the independently preserved contract, evaluate the
actual numeric observation. Never replace all-of acceptance with averages or
percentiles; missing metrics, NaNs and duplicate gate declarations fail closed.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import sys

OPS = {
    '<': lambda a, b: a < b,
    '<=': lambda a, b: a <= b,
    '>': lambda a, b: a > b,
    '>=': lambda a, b: a >= b,
    '==': lambda a, b: a == b,
    '!=': lambda a, b: a != b,
}


def decimal(value):
    if type(value) not in (str, int, float):
        raise ValueError('numeric values must not be boolean or nonnumeric')
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError('invalid numeric value') from exc
    if not result.is_finite():
        raise ValueError('nonfinite numeric value')
    return result


def evaluate(contract, readings):
    if not isinstance(contract, dict) or not isinstance(readings, dict):
        raise ValueError('contract and readings must be objects')
    gates = contract.get('required_gates')
    observed = readings.get('observations')
    if not isinstance(gates, list) or not gates or not isinstance(observed, dict):
        raise ValueError('nonempty required_gates and observations object required')
    ids = [g.get('id') for g in gates if isinstance(g, dict)]
    if len(ids) != len(gates) or any(not isinstance(gid, str) or not gid for gid in ids) or len(set(ids)) != len(ids):
        raise ValueError('missing or duplicate gate identifiers')
    checks = []
    for gate in gates:
        gid = gate['id']
        op = gate.get('op')
        if op not in OPS:
            raise ValueError(f'{gid}: unknown comparator')
        threshold = decimal(gate.get('limit'))
        if gid not in observed:
            checks.append({'id': gid, 'passed': False, 'reason': 'MISSING_OBSERVATION'})
            continue
        try:
            actual = decimal(observed[gid])
        except ValueError:
            checks.append({'id': gid, 'passed': False, 'reason': 'INVALID_OR_NONFINITE_OBSERVATION'})
            continue
        ok = OPS[op](actual, threshold)
        checks.append({'id': gid, 'passed': ok, 'observed': str(actual),
                       'op': op, 'limit': str(threshold),
                       'reason': 'PASS' if ok else 'THRESHOLD_VIOLATED'})
    return {
        'status': 'ALL_DECLARED_GATES_PASS_UNAUTHENTICATED' if all(g['passed'] for g in checks) else 'FAIL_HARD_GATE',
        'passed': all(g['passed'] for g in checks),
        'checks': checks,
        'unverified_original_requirements_not_in_contract': 'unknown',
        'authoritative_contract_and_evidence_required': True,
        'meaning': 'This helper does not prove the contract is complete, the measurements are real, or the parent goal is accepted.',
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('contract', type=Path)
    parser.add_argument('readings', type=Path)
    args = parser.parse_args(argv)
    try:
        result = evaluate(json.loads(args.contract.read_text(encoding='utf-8-sig')),
                          json.loads(args.readings.read_text(encoding='utf-8-sig')))
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({'status': 'INVALID_GATE_INPUT', 'error': str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
