#!/usr/bin/env python3
"""Summarize predeclared matched trials without dropping failures or claiming causal uplift.

Imported observations require independent review. This does not run paid models,
validate observer identity, or convert helper fixtures into live-agent results.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import strict_io

OUTCOMES = {'VERIFIED', 'FAILED', 'BLOCKED', 'TIMEOUT', 'NOT_RUN'}
MATCH_FIELDS = ('model', 'host', 'source', 'tools', 'permissions', 'evaluator')


def summarize(manifest, records):
    if not isinstance(manifest, dict) or type(manifest.get('schema')) is not int or manifest['schema'] != 1 or not isinstance(records, list):
        raise ValueError('Expected schema 1 manifest and records list')
    arms = manifest.get('arms')
    trials = manifest.get('trials')
    if not isinstance(arms, list) or len(arms) < 2 or len(set(arms)) != len(arms) or not all(isinstance(a,str) and a for a in arms):
        raise ValueError('At least two unique arms required')
    if not isinstance(trials, list) or not trials or any(not isinstance(t, dict) or not t.get('id') for t in trials):
        raise ValueError('Predeclare every assigned trial, including possible blocked runs')
    ids = [t['id'] for t in trials]
    if len(set(ids)) != len(ids): raise ValueError('Duplicate trial ID')
    index = {}
    for record in records:
        if not isinstance(record, dict): raise ValueError('Invalid trial record')
        key = record.get('trial'), record.get('arm')
        if key[0] not in ids or key[1] not in arms or key in index:
            raise ValueError('Unexpected or duplicate trial/arm record')
        if record.get('outcome') not in OUTCOMES or type(record.get('claimed_complete')) is not bool:
            raise ValueError('Typed outcome and completion claim required')
        if record.get('independent_pass') is not None and type(record['independent_pass']) is not bool:
            raise ValueError('independent_pass must be boolean or null, never a string')
        if record['outcome'] == 'VERIFIED' and (record.get('independent_pass') is not True or not record.get('evidence')):
            raise ValueError('VERIFIED needs independent observed success and evidence references')
        if record.get('evidence_class') not in {'live-agent', 'deterministic-fixture', 'replay'}:
            raise ValueError('Declare the actual evidence class')
        for field in MATCH_FIELDS:
            if not isinstance(record.get(field), str) or not record[field].strip():
                raise ValueError(f'Missing matched condition: {field}')
        for field in ('avoidable_interventions', 'policy_violations'):
            if type(record.get(field)) is not int or record[field] < 0:
                raise ValueError('Counters must be nonnegative integers')
        index[key] = record
    result = {}
    for arm in arms:
        observed = [index[(tid, arm)] for tid in ids if (tid, arm) in index]
        passed = sum(r['outcome'] == 'VERIFIED' for r in observed)
        claims = sum(r['claimed_complete'] for r in observed)
        evaluated_claims = sum(r['claimed_complete'] and r.get('independent_pass') is not None for r in observed)
        false_claims = sum(r['claimed_complete'] and r.get('independent_pass') is False for r in observed)
        result[arm] = {'assigned': len(ids), 'reported': len(observed), 'missing_not_run': len(ids)-len(observed),
                       'verified': passed, 'root_completion_rate': passed / len(ids),
                       'claimed_complete': claims, 'evaluated_claims': evaluated_claims,
                       'unreviewed_claims': claims-evaluated_claims, 'false_verified': false_claims,
                       'false_verification_rate_among_evaluated_claims': false_claims / evaluated_claims if evaluated_claims else None,
                       'avoidable_interventions': sum(r['avoidable_interventions'] for r in observed),
                       'policy_violations': sum(r['policy_violations'] for r in observed)}
    matched, mismatched = [], []
    for tid in ids:
        rows = [index.get((tid, arm)) for arm in arms]
        if all(rows) and all(all(row[k] == rows[0][k] for k in MATCH_FIELDS) for row in rows):
            matched.append(tid)
        else:
            mismatched.append(tid)
    live = bool(records) and all(r['evidence_class'] == 'live-agent' for r in records)
    policy_ok = all(v['policy_violations'] == 0 for v in result.values())
    return {'arms': result, 'matched_trials': matched, 'unmatched_or_missing': mismatched,
            'live_agent_evidence_only': live, 'permission_gate_passed': policy_ok,
            'behavioral_impact': 'CONTROLLED_OBSERVATIONS_NOT_CAUSAL_PROOF' if live and not mismatched else 'BEHAVIORAL_IMPACT_UNPROVEN',
            'release_recommended': False,
            'limitation': 'No significance or general reliability claim. Review evaluator independence, paired task-level uncertainty, hidden failures, repeated-trial correlation and held-out evaluation.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--results', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(summarize(strict_io.load(args.manifest), strict_io.load(args.results)), indent=2))
        return 0
    except (ValueError, OSError, TypeError, KeyError) as exc:
        print(json.dumps({'status': 'INVALID_EVALUATION', 'error': str(exc)})); return 2


if __name__ == '__main__': raise SystemExit(main())
