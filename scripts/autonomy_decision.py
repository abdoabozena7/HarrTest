#!/usr/bin/env python3
"""Advisory, read-only handler for interruptions in outcome-first agent workflows.

Inputs must be checked against real host, policy, and user approval sources.
This file cannot authenticate user consent, extend limits, or authorize work.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


EVENTS = frozenset({
    'OPTIONAL_CONSULTATION_UNAVAILABLE',
    'REQUIRED_APPROVAL_UNAVAILABLE',
    'SOFT_TIME_ESTIMATE_EXCEEDED',
    'COMMAND_TIMEOUT',
    'HOST_HARD_LIMIT',
    'RESOURCE_ADMISSION_DENIED',
    'NO_PROGRESS',
})


def decide(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError('Expected JSON object')
    event = payload.get('event')
    if event not in EVENTS:
        raise ValueError('Unknown event; distinguish soft timeout, hard limit, and real approval')
    can_continue = payload.get('authorized_independent_work')
    if type(can_continue) is not bool:
        raise ValueError('authorized_independent_work must be an explicit boolean')

    if event == 'OPTIONAL_CONSULTATION_UNAVAILABLE':
        decision = 'CONTINUE_AUTONOMOUSLY' if can_continue else 'SKIP_OPTIONAL_CONSULTATION'
        next_action = ('Make a reversible, reasonable decision within existing authority, '
                       'record the assumption, and continue; the failed UI request does not prove the user is absent.')
    elif event == 'REQUIRED_APPROVAL_UNAVAILABLE':
        decision = 'CONTINUE_OTHER_AUTHORIZED_WORK' if can_continue else 'AWAIT_EXPLICIT_APPROVAL'
        next_action = ('Do not perform the gated action or interpret timeout as consent. '
                       'Continue only independent pre-authorized work; preserve an actionable approval request.')
    elif event == 'SOFT_TIME_ESTIMATE_EXCEEDED':
        decision = 'CONTINUE_GOAL_WORK' if can_continue else 'CHECK_ACTUAL_AUTHORITY'
        next_action = ('Do not treat an agent-created time estimate as a mission deadline. '
                       'Continue with a progress checkpoint if execution remains authorized.')
    elif event == 'COMMAND_TIMEOUT':
        decision = 'DIAGNOSE_AND_RETRY_IF_JUSTIFIED' if can_continue else 'CHECKPOINT_PAUSE'
        next_action = ('Determine whether the owned process is still running, terminate only owned hung work '
                       'when permitted, inspect evidence, and retry only with a changed hypothesis or safe backoff.')
    elif event == 'HOST_HARD_LIMIT':
        decision = 'CHECKPOINT_FOR_RESUME'
        next_action = ('Honor the actual host limit; persist goal, validated progress, first pending gate, '
                       'permissions, failure evidence and exact resume action. Do not promise background execution.')
    elif event == 'RESOURCE_ADMISSION_DENIED':
        decision = 'CONTINUE_OTHER_AUTHORIZED_WORK' if can_continue else 'AWAIT_EXTERNAL_AUTHORIZATION'
        next_action = ('Do not raise quotas or alter project/resource ledgers; continue only independently '
                       'authorized steps and request a scoped grant for the blocked action.')
    else:  # NO_PROGRESS
        decision = 'REPLAN_WITH_FALSIFIABLE_NEXT_STEP' if can_continue else 'CHECKPOINT_STALLED'
        next_action = ('Avoid identical retries or audit loops. Choose a new testable hypothesis/independent '
                       'goal action, or preserve a truthful stalled handoff.')

    return {
        'event': event,
        'decision': decision,
        'next_action': next_action,
        'may_continue_previously_authorized_independent_work': can_continue and event != 'HOST_HARD_LIMIT',
        'grants_new_permission': False,
        'gated_action_is_authorized': False,
        'root_goal_verified': 'NOT_EVALUATED',
        'must_preserve_completed_work': True,
        'read_only_advice': True,
        'limitations': ('The caller must validate event classification, independent authority, genuine host limits '
                        'and original acceptance separately. Never infer consent or root success from this advice.'),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path,
                        help='JSON facts from an independently validated host/policy state')
    args = parser.parse_args(argv)
    try:
        result = decide(json.loads(args.input.read_text(encoding='utf-8-sig')))
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({'status': 'INVALID_INPUT', 'error': str(exc)}, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0  # Advisory output only, never a passed acceptance or authorization.


if __name__ == '__main__':
    sys.exit(main())
