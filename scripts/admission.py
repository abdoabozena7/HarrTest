#!/usr/bin/env python3
"""Read-only preflight for bounded autonomous work (not an authorization token).

This tool never starts work, grants permissions, edits budgets, or reserves resources.
A passing result ALWAYS requires the host's independent real admission gate.
"""
import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path


def number(value, label):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError(f'{label} must be a finite, nonnegative number')
    return float(value)


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('expiry must be an ISO 8601 timestamp')
    instant = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if instant.tzinfo is None:
        raise ValueError('expiry timestamp must include timezone')
    return instant.astimezone(timezone.utc)


def precheck(intent, policy, now=None):
    if not isinstance(intent, dict) or not isinstance(policy, dict):
        raise ValueError('intent and policy must be objects')
    action = intent.get('action')
    scope = policy.get('scope')
    if not isinstance(action, str) or not action.strip():
        raise ValueError('intent.action is required')
    if not isinstance(scope, list) or not scope or not all(isinstance(s, str) for s in scope):
        raise ValueError('policy.scope must be a nonempty list')
    requested = number(intent.get('requested_units'), 'requested_units')
    available = number(policy.get('remaining_units'), 'remaining_units')
    minimum = number(intent.get('minimum_reservation_units'), 'minimum_reservation_units')
    if requested < minimum:
        raise ValueError('requested_units is below the declared minimum reservation')
    unit = intent.get('unit')
    if not isinstance(unit, str) or not unit or unit != policy.get('unit'):
        raise ValueError('unit mismatch')
    protected = policy.get('protected', False)
    if type(protected) is not bool:
        raise ValueError('policy.protected must be boolean')
    now = now or datetime.now(timezone.utc)
    reasons = []
    if action not in scope:
        reasons.append('ACTION_OUTSIDE_DECLARED_SCOPE')
    if protected:
        reasons.append('PROTECTED_RESOURCE_REQUIRES_SEPARATE_AUTHORITY')
    expiry = policy.get('expires_at')
    if expiry is None:
        reasons.append('NO_EXPIRY_BOUND')
    elif now >= timestamp(expiry):
        reasons.append('DECLARED_ENVELOPE_EXPIRED')
    if requested > available:
        reasons.append('INSUFFICIENT_REMAINING_RESOURCE')
    provenance = policy.get('approval_provenance')
    if not isinstance(provenance, dict) or not provenance.get('source') or not provenance.get('evidence'):
        reasons.append('NO_RECORDED_APPROVAL_PROVENANCE')
    return {
        'status': 'BLOCKED_PRECHECK' if reasons else 'PRECHECK_OK_NOT_AUTHORIZED',
        'reasons': reasons,
        'action': action,
        'unit': unit,
        'requested_units': requested,
        'remaining_units': available,
        'after_if_admitted_units': available - requested if available >= requested else None,
        'external_host_gate_required': True,
        'mutates_ledger': False,
        'meaning': 'This is arithmetic and metadata validation only, not proof that the user granted authority or that the native host admitted a run.'
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('intent', type=Path)
    parser.add_argument('policy', type=Path)
    args = parser.parse_args()
    try:
        intent = json.loads(args.intent.read_text(encoding='utf-8-sig'))
        policy = json.loads(args.policy.read_text(encoding='utf-8-sig'))
        report = precheck(intent, policy)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({'status': 'INVALID_PRECHECK', 'error': str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0 if report['status'] == 'PRECHECK_OK_NOT_AUTHORIZED' else 1


if __name__ == '__main__':
    sys.exit(main())