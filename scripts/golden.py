#!/usr/bin/env python3
"""HarrTest Gold intake and matched comparison gates; no model client."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

import proof
import strict_io

PROTOCOL = 'golden-v1'
MODES = ('fixture', 'offline', 'live')
ARMS = ('baseline', 'candidate')
OUTCOMES = ('accept', 'reject')
MAX_JSON_BYTES = 4_000_000


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_record(project, name, label, *, expected_sha256=None):
    path = strict_io.scoped_path(project, name)
    require(path.is_file() and 0 < path.stat().st_size <= MAX_JSON_BYTES,
            f'{label}: expected a bounded nonempty JSON file')
    # Parse and fingerprint the same bytes, including concurrent file changes.
    raw = path.read_bytes()
    require(len(raw) <= MAX_JSON_BYTES, f'{label}: JSON file exceeds size limit')
    if expected_sha256 is not None:
        require(hashlib.sha256(raw).hexdigest() == expected_sha256, f'{label}: evidence changed')
    value = strict_io.loads(raw.decode('utf-8-sig'))
    require(isinstance(value, dict) and type(value.get('schema')) is int and value['schema'] == 1,
            f'{label}: expected schema 1')
    return value


def concrete(value, label, minimum=8):
    proof.meaningful(value, label, minimum)
    require(len(value) <= 12_000, f'{label}: narrow the description')


def sha256(value, label):
    require(isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value),
            f'{label}: expected a lowercase SHA-256 digest')


def evidence(project, row, label):
    require(isinstance(row, dict) and set(row) == {'path', 'sha256'},
            f'{label}: cite evidence as path and sha256')
    sha256(row['sha256'], label)
    path = strict_io.scoped_path(project, row['path'])
    require(path.is_file() and path.stat().st_size > 0, f'{label}: evidence is empty or not a file')
    require(proof.file_hash(path) == row['sha256'], f'{label}: evidence changed: {row["path"]}')
    return path


def rows(value, label):
    require(isinstance(value, list) and bool(value), f'{label}: expected nonempty records')
    ids = set()
    for item in value:
        require(isinstance(item, dict), f'{label}: expected an object')
        ident = item.get('id')
        proof.identifier(ident, label + ' ID')
        require(ident not in ids, f'{label}: duplicate ID {ident}')
        ids.add(ident)
    return value


def settings(spec):
    config = spec.get('golden')
    require(isinstance(config, dict) and set(config) == {'intake', 'protocol', 'measurement'},
            'Gold requires distinct intake, protocol, and measurement paths')
    require(all(isinstance(p, str) for p in config.values()), 'Gold paths must be strings')
    require(len({p.casefold() for p in config.values()}) == 3, 'Gold paths must be distinct')
    return config


def validate_protocol(project, spec):
    config = settings(spec)
    protocol = load_record(project, config['protocol'], 'Comparison protocol')
    # Results are expected to be written after registration, not during intake.
    strict_io.scoped_path(project, config['measurement'], must_exist=False)
    require(protocol.get('mode') in MODES, 'Comparison mode must be fixture, offline, or live')
    controls = protocol.get('controls')
    require(isinstance(controls, dict), 'Comparison requires declared shared conditions')
    for key in ('runner', 'environment'):
        concrete(controls.get(key), 'Comparison control: ' + key)
    baseline = protocol.get('baseline')
    require(isinstance(baseline, dict), 'Comparison requires baseline identity')
    concrete(baseline.get('id'), 'Baseline identity', 3)
    sha256(baseline.get('source_sha256'), 'Baseline source')
    cases = rows(protocol.get('cases'), 'Comparison cases')
    for case in cases:
        concrete(case.get('oracle'), f'{case["id"]} oracle')
        require(case.get('expect') in OUTCOMES, f'{case["id"]}: expected accept or reject')
    require({case['expect'] for case in cases} == set(OUTCOMES),
            'Comparison must exercise both allow and reject controls')
    bounds = protocol.get('thresholds')
    require(isinstance(bounds, dict), 'Comparison requires predeclared thresholds')
    limits = {
        'min_candidate_correct': (1, len(cases)),
        'max_candidate_false_accepts': (0, sum(c['expect'] == 'reject' for c in cases) - 1),
        'min_correct_gain': (-len(cases), len(cases)),
    }
    for key, (low, high) in limits.items():
        value = bounds.get(key)
        require(type(value) is int and low <= value <= high,
                f'{key}: expected an integer between {low} and {high}')
    return protocol


def validate_intake(project, spec):
    """Bind the interpretation, evidence bytes and comparison protocol to a plan."""
    config = settings(spec)
    goal = strict_io.scoped_path(project, spec['root_goal'])
    contract = proof.load(goal / 'root-contract.json')
    require(contract.get('protocol') == PROTOCOL, 'Root did not opt in to golden-v1')
    original = goal / 'original-request.txt'
    request_hash = proof.file_hash(original)
    intake = load_record(project, config['intake'], 'Gold intake')
    require(intake.get('request_sha256') == contract['request_sha256'] == request_hash,
            'Gold intake is for a different original request')
    concrete(intake.get('interpretation'), 'Whole-request interpretation', 20)
    required = {row['id'] for row in contract['requirements']}
    refs = {}

    def cite(row):
        items = row.get('evidence')
        require(isinstance(items, list) and bool(items), f'{row["id"]}: evidence is required')
        for item in items:
            require(isinstance(item, dict), f'{row["id"]}: expected an evidence reference')
            if item.get('path') not in refs:
                evidence(project, item, row['id'])
                refs[item['path']] = item['sha256']
            else:
                require(set(item) == {'path', 'sha256'} and refs[item['path']] == item['sha256'],
                        f'{row["id"]}: inconsistent evidence reference')

    meanings = rows(intake.get('requirements'), 'Requirement interpretations')
    require({row['id'] for row in meanings} == required, 'Interpret every sealed root requirement')
    for row in meanings:
        concrete(row.get('meaning'), f'{row["id"]} meaning')
        cite(row)

    def cover(name, check):
        covered = set()
        for row in rows(intake.get(name), name):
            ids = row.get('requirement_ids')
            require(isinstance(ids, list) and bool(ids) and
                    all(isinstance(i, str) and i in required for i in ids) and len(ids) == len(set(ids)),
                    f'{row["id"]}: link known, distinct root requirements')
            check(row)
            cite(row)
            covered.update(ids)
        require(covered == required, f'{name}: account for every root requirement')

    def edge(row):
        concrete(row.get('question'), f'{row["id"]} edge question')
        require(row.get('source') in ('user', 'repository_contract', 'not_applicable'),
                f'{row["id"]}: unresolved edge case; obtain an answer or cite a controlling contract')
        concrete(row.get('resolution'), f'{row["id"]} edge resolution')

    def decision(row):
        concrete(row.get('choice'), f'{row["id"]} decision')
        concrete(row.get('rationale'), f'{row["id"]} rationale')

    cover('edge_cases', edge)
    cover('decisions', decision)
    return {'intake_sha256': strict_io.digest(intake), 'evidence': refs,
            'protocol_sha256': strict_io.digest(validate_protocol(project, spec))}


def source_identity(project, spec):
    """Fingerprint the candidate behavior/check sources bound by all child contracts."""
    sources = {}
    for task in spec['tasks']:
        path = strict_io.scoped_path(project, task['proof_task'])
        _, actual_project, contract = proof.task_context(path)
        require(actual_project == Path(project).resolve(), 'Candidate child is outside this project')
        sources[path.name] = {
            'contract': proof.digest(contract),
            'source': proof.snapshot(actual_project, contract)['digest'],
            'verifier': proof.engine_hash(contract),
        }
    require(bool(sources), 'No sealed candidate sources')
    controllers = {name: proof.file_hash(proof.SKILL / 'scripts' / name)
                   for name in ('golden.py', 'root_gate.py', 'workflow.py', 'runtime_store.py')}
    return strict_io.digest({'sources': sources, 'gold_controllers': controllers})


def comparison_receipt(project, attempt, label):
    ref = attempt.get('evidence')
    path = evidence(project, ref, label)
    receipt = load_record(project, ref['path'], label, expected_sha256=ref['sha256'])
    fields = ('case', 'variant', 'outcome', 'source_sha256')
    require(all(receipt.get(k) == attempt[k] for k in fields),
            f'{label}: report disagrees with its retained evaluator receipt')
    artifacts = receipt.get('artifacts')
    require(isinstance(artifacts, list) and bool(artifacts),
            f'{label}: evaluator receipt needs retained raw output')
    for raw in artifacts:
        retained = evidence(project, raw, label)
        require(retained != path, f'{label}: evaluator receipt cannot cite itself as raw output')
    return path


def validate_measurement(project, spec):
    """Recompute the comparison; absent or inconclusive attempts never count as rejects."""
    protocol = validate_protocol(project, spec)
    protocol_hash = strict_io.digest(protocol)
    report = load_record(project, settings(spec)['measurement'], 'Comparison results')
    require(report.get('protocol_sha256') == protocol_hash, 'Results are for a different comparison protocol')
    candidate = report.get('candidate')
    require(isinstance(candidate, dict), 'Comparison requires candidate identity')
    concrete(candidate.get('id'), 'Candidate identity', 3)
    actual = source_identity(project, spec)
    require(candidate.get('source_sha256') == actual, 'Candidate results are stale for current sealed sources')
    source = {'baseline': protocol['baseline']['source_sha256'], 'candidate': actual}
    expected = {case['id']: case['expect'] for case in protocol['cases']}
    denominator = len(expected)
    attempts = report.get('attempts')
    require(isinstance(attempts, list), 'Comparison requires raw attempts')
    seen, used = set(), set()
    counts = {arm: dict(correct=0, false_accepts=0, false_rejects=0, errors=0) for arm in ARMS}
    for attempt in attempts:
        require(isinstance(attempt, dict), 'Malformed comparison attempt')
        case, arm, outcome = (attempt.get(k) for k in ('case', 'variant', 'outcome'))
        require(isinstance(case, str) and case in expected and arm in ARMS and
                outcome in (*OUTCOMES, 'error'), 'Unknown comparison case, variant, or outcome')
        require((case, arm) not in seen, f'Duplicate comparison attempt: {case}/{arm}')
        seen.add((case, arm))
        require(attempt.get('source_sha256') == source[arm], f'{case}/{arm}: wrong source identity')
        path = comparison_receipt(project, attempt, f'{case}/{arm}')
        path_key = str(path.resolve()).casefold()
        require(path_key not in used, 'Each comparison attempt needs its own retained record')
        used.add(path_key)
        metric = ('errors' if outcome == 'error' else 'correct' if outcome == expected[case] else
                  'false_accepts' if outcome == 'accept' else 'false_rejects')
        counts[arm][metric] += 1
    missing = sorted({(case, arm) for case in expected for arm in ARMS} - seen)
    require(not missing, f'Incomplete comparison: {len(missing)} missing of {denominator * 2} planned attempts: {missing[:8]}')
    for stats in counts.values():
        stats['planned'] = denominator
        stats['correct_rate'] = stats['correct'] / denominator
    gain = counts['candidate']['correct'] - counts['baseline']['correct']
    thresholds = protocol['thresholds']
    allow_controls = sum(result == 'accept' for result in expected.values())
    passed = (all(not count['errors'] for count in counts.values()) and
              counts['candidate']['false_rejects'] < allow_controls and
              counts['candidate']['correct'] >= thresholds['min_candidate_correct'] and
              counts['candidate']['false_accepts'] <= thresholds['max_candidate_false_accepts'] and
              gain >= thresholds['min_correct_gain'])
    return {'passed': passed, 'mode': protocol['mode'], 'protocol_sha256': protocol_hash,
            'candidate_source_sha256': actual, 'controls': protocol['controls'],
            'baseline': counts['baseline'], 'candidate': counts['candidate'],
            'correct_gain': gain, 'correct_gain_points': 100 * gain / denominator,
            'thresholds': thresholds, 'provenance_authenticated': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=Path('.'))
    commands = parser.add_subparsers(dest='action', required=True)
    for name in ('inspect', 'candidate', 'compare'):
        command = commands.add_parser(name)
        command.add_argument('--plan', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        project = args.project.resolve()
        spec = strict_io.load(args.plan)
        if args.action == 'inspect':
            result = validate_intake(project, spec)
        elif args.action == 'candidate':
            result = {'candidate_source_sha256': source_identity(project, spec)}
        else:
            result = validate_measurement(project, spec)
        print(json.dumps(result, indent=2))
        return 1 if result.get('passed') is False else 0
    except (ValueError, TypeError, KeyError, OSError, proof.ProofError) as exc:
        print(json.dumps({'status': 'NOT_VERIFIED', 'error': str(exc)}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
