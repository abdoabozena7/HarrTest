"""Source-bound acceptance for changes to existing software (corporate-v1).

This validates cooperative execution and review records, not arbitrary program
correctness or the honesty of a writer who controls the evidence store.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import statistics

import proof
import strict_io

PROTOCOL = 'corporate-v1'
LAYERS = ('functionality', 'preservation', 'architecture', 'security', 'performance', 'resilience')
CORE_LAYERS = {'functionality', 'preservation', 'architecture'}
MAX_DOCUMENT = 2_000_000


def require(condition, message):
    if not condition:
        raise ValueError(message)


def text(value, label):
    proof.meaningful(value, label, 12)


def instant(value):
    require(isinstance(value, str), 'An ISO timestamp is required')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(result.tzinfo is not None, 'Timestamps need an explicit timezone')
    return result


def document(path):
    require(path.is_file() and 0 < path.stat().st_size <= MAX_DOCUMENT,
            f'Missing or oversized document: {path.name}')
    result = strict_io.load(path)
    require(isinstance(result, dict), f'{path.name} must contain an object')
    return result


def rows(value, label, *, empty=False):
    require(isinstance(value, list) and (empty or bool(value)), f'{label} must be a list')
    result = {}
    for row in value:
        require(isinstance(row, dict), f'{label}: expected an object')
        proof.identifier(row.get('id'), label + ' ID')
        require(row['id'] not in result, f'{label}: duplicate ID {row["id"]}')
        result[row['id']] = row
    return result


def path(project, name, *, exists=True):
    result = strict_io.scoped_path(project, name, must_exist=exists)
    cursor = result
    while cursor != Path(project).resolve():
        if cursor.exists():
            require(not getattr(cursor.stat(), 'st_file_attributes', 0) & 0x400,
                    'Reparse points are not supported in Corporate source/evidence paths')
        cursor = cursor.parent
    return result


def source_snapshot(project, source_paths):
    """Include untracked inputs and explicit absent roots; never include evidence."""
    project = Path(project).resolve()
    require(isinstance(source_paths, list) and source_paths, 'Declare complete source_paths')
    require(len(source_paths) == len(set(source_paths)), 'Duplicate source root')
    files = {}
    for name in source_paths:
        require(name != '.' and name.split('/')[0] not in {'.git', proof.STATE},
                'Choose explicit implementation, configuration and verifier roots')
        root = path(project, name, exists=False)
        if not root.exists():
            files[name] = None
            continue
        for item in ([root] if root.is_file() else sorted(root.rglob('*'))):
            rel = item.relative_to(project).as_posix()
            if any(part in proof.SKIP_DIRS for part in Path(rel).parts):
                continue
            path(project, rel)
            if item.is_file():
                files[rel] = proof.file_hash(item)
    require(any(value is not None for value in files.values()), 'No source files in scope')
    return {'files': files, 'digest': proof.digest(files)}


def snapshot_valid(value):
    require(isinstance(value, dict) and isinstance(value.get('files'), dict) and value['files'],
            'Missing source manifest')
    require(value.get('digest') == proof.digest(value['files']), 'Source manifest digest mismatch')


def citation(project, ref):
    require(isinstance(ref, dict), 'Citation must be an object')
    source = path(project, ref.get('path'))
    require(source.is_file() and source.stat().st_size <= MAX_DOCUMENT,
            'Citation must name a bounded text file')
    require(proof.file_hash(source) == ref.get('sha256'), 'Citation changed or hash is missing')
    start, end = ref.get('start_line'), ref.get('end_line')
    lines = source.read_text(encoding='utf-8').splitlines()
    require(type(start) is int and type(end) is int and 1 <= start <= end <= len(lines),
            'Citation needs a valid one-based line range')
    excerpt = ref.get('excerpt')
    require(isinstance(excerpt, str) and excerpt.strip() and
            excerpt in '\n'.join(lines[start - 1:end]), 'Citation excerpt is absent from its range')
    if 'source_url' in ref:
        require(isinstance(ref['source_url'], str) and ref['source_url'].startswith('https://'),
                'External citations need an HTTPS source URL')
        text(ref.get('version'), 'External documentation version/context')
    return proof.file_hash(source)


def references(value, known, label):
    require(isinstance(value, list) and value and len(value) == len(set(value)) and
            all(item in known for item in value), label + ': cite distinct known evidence IDs')


def selector(value):
    require(isinstance(value, dict), 'Check reference must contain task_id and check_id')
    proof.identifier(value.get('task_id'), 'Proof task ID')
    proof.identifier(value.get('check_id'), 'Proof check ID')
    return value['task_id'], value['check_id']


def execution_reference(project, receipt):
    location = path(project, receipt)
    return {'receipt': receipt, 'sha256': proof.file_hash(location)}


def execution(project, ref, expected_source, *, latest=False):
    """Re-evaluate actual proof.py run output; never trust a reported pass bit."""
    require(isinstance(ref, dict), 'Execution needs a content-bound receipt reference')
    location = path(project, ref.get('receipt'))
    require(proof.file_hash(location) == ref.get('sha256'), 'Execution receipt changed')
    require(location.name == 'receipt.json', 'Expected an actual run receipt')
    receipt = document(location)
    run, task = location.parent, location.parents[3]
    require(task.parent == Path(project) / proof.STATE and
            location.parents[2].name == 'runs' and run.parent.name == receipt.get('check_id'),
            'Receipt must live in its proof task/check/run directory')
    actual_task, actual_project, contract = proof.task_context(task)
    require(actual_project == Path(project), 'Proof task belongs to a different project')
    check = proof.get_check(contract, receipt.get('check_id'))
    require(receipt.get('schema') == 1 and receipt.get('task_id') == contract['task_id'] and
            receipt.get('contract_hash') == proof.digest(contract) and
            receipt.get('check_hash') == proof.digest(check), 'Execution does not match sealed task/check')
    require(receipt.get('engine_hash') == proof.engine_hash(contract), 'Execution verifier changed')
    require(receipt.get('mode') == check['mode'] and receipt.get('role') == check['role'],
            'Execution mode/role differs from its contract')
    snapshot_valid(expected_source)
    declared_absent = proof.absent_source_paths(contract)
    expected_files = {key: value for key, value in expected_source['files'].items()
                      if value is not None or key in declared_absent}
    expected = {'files': expected_files, 'digest': proof.digest(expected_files)}
    require(receipt.get('source_before') == expected and receipt.get('source_after') == expected,
            'Execution source scope is incomplete, stale or changed during the run')
    require(receipt.get('command') == [proof.expand(arg, project, run, task) for arg in check['command']]
            and receipt.get('cwd') == str(proof.relative_file(project, check.get('cwd', '.'))),
            'Executed command or directory differs from its sealed check')
    require(all(receipt.get(flag) is False for flag in ('timeout', 'interrupted', 'overflow'))
            and receipt.get('spawn_error') is None and type(receipt.get('exit_code')) is int,
            'Execution is interrupted, unavailable or incomplete')
    started, ended = instant(receipt.get('started_at')), instant(receipt.get('ended_at'))
    require(started <= ended and ended <= datetime.now(timezone.utc), 'Execution timing is invalid')
    require(type(receipt.get('wall_seconds')) in (int, float) and
            math.isfinite(receipt['wall_seconds']) and receipt['wall_seconds'] >= 0,
            'Missing finite execution duration')
    artifacts, artifact_errors = proof.collect_artifacts(run, check)
    require(not artifact_errors and artifacts == receipt.get('artifacts'),
            'Execution artifacts or captured logs changed')
    errors = proof.evaluate_assertions(run, check)
    if receipt['exit_code'] not in check.get('expected_exit_codes', [0]):
        errors.append('Unexpected exit code')
    require(type(receipt.get('passed')) is bool and receipt['passed'] == (not errors),
            'Receipt pass claim disagrees with actual assertions')
    if latest:
        current = proof.load(task / 'latest' / (check['id'] + '.json'))
        require(current.get('run') == run.relative_to(task).as_posix() and
                current.get('receipt_hash') == ref['sha256'], 'A newer check attempt superseded this evidence')
    return {'selector': (contract['task_id'], check['id']), 'receipt': receipt,
            'check': check, 'run': run, 'passed': not errors, 'errors': errors}


def _load(project, goal, contract):
    require(contract.get('schema') == 4 and contract.get('protocol') == PROTOCOL,
            'Corporate requires a schema-4 corporate-v1 root')
    config = contract.get('corporate')
    require(isinstance(config, dict) and set(config) == {'plan', 'report'},
            'corporate must declare plan and report paths')
    plan_path = path(project, config['plan'])
    report_path = path(project, config['report'], exists=False)
    require(plan_path != report_path and plan_path.is_relative_to(Path(project) / proof.STATE)
            and report_path.is_relative_to(Path(project) / proof.STATE),
            'Keep distinct Corporate plan/report files in private project evidence')
    plan = document(plan_path)
    require(type(plan.get('schema')) is int and plan['schema'] == 1,
            'Expected Corporate plan schema 1')
    require(plan.get('request_sha256') == contract.get('request_sha256'),
            'Corporate plan belongs to another original request')
    text(plan.get('author'), 'Implementation author identity')
    instant(plan.get('created_at'))
    return plan_path, report_path, plan


def _baseline(project, plan):
    baseline = plan.get('baseline')
    require(isinstance(baseline, dict), 'Baseline is required before changes')
    snapshot_valid(baseline.get('source'))
    captured = instant(baseline.get('captured_at'))
    require(captured <= instant(plan['created_at']), 'Baseline must precede the plan')
    refs = baseline.get('checks')
    require(isinstance(refs, list) and refs, 'Baseline needs real execution evidence')
    known = baseline.get('known_failures', [])
    require(isinstance(known, list), 'known_failures must be explicit')
    known_by_hash = {}
    for failure in known:
        require(isinstance(failure, dict), 'Invalid known baseline failure')
        text(failure.get('reason'), 'Known failure reason')
        review = failure.get('review', {})
        require(review.get('method') in {'human', 'fresh-context-agent'} and
                review.get('reviewer') != plan['author'] and review.get('verdict') == 'ACKNOWLEDGED',
                'Known baseline failures need independent acknowledgement')
        text(review.get('reviewer'), 'Baseline failure reviewer')
        text(review.get('observations'), 'Baseline failure observation')
        digest = failure.get('receipt_sha256')
        require(isinstance(digest, str) and digest not in known_by_hash, 'Duplicate known failure')
        known_by_hash[digest] = failure
    result, used = {}, set()
    for ref in refs:
        item = execution(project, ref, baseline['source'])
        key = item['selector']
        require(key not in result, 'Duplicate baseline execution')
        require(instant(item['receipt']['ended_at']) <= captured, 'Baseline captured before its command ended')
        if not item['passed']:
            require(ref['sha256'] in known_by_hash, 'Unacknowledged baseline failure')
            used.add(ref['sha256'])
        result[key] = item
    require(used == set(known_by_hash), 'Known failure is not an actual failing baseline execution')
    return result


def validate(project, goal, contract):
    """Validate immutable scope before root sealing; a candidate report is not required."""
    project, goal = Path(project).resolve(), Path(goal).resolve()
    _, _, plan = _load(project, goal, contract)
    current = source_snapshot(project, plan.get('source_paths'))
    source_roots = [path(project, name, exists=False) for name in plan['source_paths']]
    context = rows(plan.get('context'), 'Context')
    require({row.get('role') for row in context.values()} >= {'architecture', 'contract', 'verification'},
            'Inspect architecture, contracts and verification policy')
    for row in context.values():
        citation(project, row.get('citation'))
    required = {row['id'] for row in contract['requirements']}
    requirements = rows(plan.get('requirements'), 'Requirement impact map')
    require(set(requirements) == required, 'Map every original root requirement')
    tasks = rows(plan.get('tasks'), 'Implementation tasks')
    owned = []
    for row in tasks.values():
        deps = row.get('depends_on')
        require(isinstance(deps, list) and len(deps) == len(set(deps)) and
                all(dep in tasks for dep in deps), 'Invalid task dependencies')
        outputs = row.get('outputs')
        require(isinstance(outputs, list) and outputs, 'Task needs bounded production outputs')
        for output in outputs:
            output_path = path(project, output, exists=False)
            require(any(output_path.is_relative_to(root) for root in source_roots),
                    'Declared implementation output lies outside the verification scope')
            require(not any(strict_io.overlaps(output, previous) for previous in owned),
                    'Implementation file ownership overlaps')
            owned.append(output)
    visited = set()
    def visit(tid, trail):
        require(tid not in trail, 'Implementation dependency cycle')
        if tid in visited:
            return
        for dep in tasks[tid]['depends_on']:
            visit(dep, trail | {tid})
        visited.add(tid)
    for tid in tasks:
        visit(tid, set())
    assigned = set()
    for row in requirements.values():
        references(row.get('tasks'), tasks, 'Requirement implementation')
        assigned.update(row['tasks'])
        impacts = row.get('impacts')
        require(isinstance(impacts, list) and impacts, 'Map actual impacted source/contracts')
        for impact in impacts:
            impact_path = path(project, impact, exists=False)
            require(any(impact_path.is_relative_to(root) for root in source_roots),
                    'Impacted source lies outside the verification scope')
    require(assigned == set(tasks), 'An implementation task is unrelated to the original request')
    for section in ('decisions', 'edge_cases'):
        entries = rows(plan.get(section), section)
        covered = set()
        for row in entries.values():
            references(row.get('requirement_ids'), required, section)
            covered.update(row['requirement_ids'])
            references(row.get('evidence'), context, section)
            if section == 'decisions':
                text(row.get('choice'), 'Decision choice')
                text(row.get('rationale'), 'Decision rationale')
            else:
                text(row.get('question'), 'Material edge question')
                text(row.get('resolution'), 'Resolved edge case')
                require(row.get('source') in {'user', 'repository_contract', 'not_applicable'},
                        'Resolve material unknowns before implementation')
        require(covered == required, section + ' do not cover all original requirements')
    layers = rows(plan.get('layers'), 'Quality layers')
    require(set(layers) == set(LAYERS), 'Assess exactly all six Corporate quality layers')
    criterion_coverage = set()
    for name, layer in layers.items():
        require(type(layer.get('applicable')) is bool, 'Layer applicability must be explicit')
        text(layer.get('rationale'), 'Layer impact/applicability rationale')
        references(layer.get('evidence'), context, 'Layer applicability')
        require(isinstance(layer.get('metrics', []), list), 'Layer metrics must be a list')
        require(name == 'performance' or not layer.get('metrics'), 'Numeric comparisons belong to the performance layer')
        require(name not in CORE_LAYERS or layer['applicable'], name + ' cannot be waived for an existing-code change')
        criteria = rows(layer.get('criteria'), name + ' criteria', empty=not layer['applicable'])
        if not layer['applicable']:
            require(not criteria and not layer.get('metrics'), 'Non-applicable layer cannot claim executable checks')
        for row in criteria.values():
            references(row.get('requirement_ids'), required, 'Criterion original requirements')
            criterion_coverage.update(row['requirement_ids'])
            for field in ('claim', 'oracle', 'counterexample'):
                text(row.get(field), name + '.' + field)
            selector(row.get('check'))
            selector(row.get('negative_check'))
            if name == 'preservation':
                selector(row.get('baseline_check'))
        if name == 'performance' and layer['applicable']:
            metrics = rows(layer.get('metrics'), 'Performance metrics')
            for metric in metrics.values():
                selector(metric.get('check'))
                selector(metric.get('baseline_check'))
                require(metric.get('direction') in {'lower', 'higher'}, 'Metric needs an improvement direction')
                require(isinstance(metric.get('unit'), str) and bool(metric['unit'].strip()), 'Metric unit is required')
                for key in ('samples_pointer', 'profile_pointer', 'unit_pointer'):
                    require(isinstance(metric.get(key), str) and metric[key].startswith('/'), 'Missing metric JSON pointer')
                path(project, metric.get('file'), exists=False)
                require(type(metric.get('minimum_samples')) is int and metric['minimum_samples'] >= 3,
                        'Performance needs repeated samples')
                for field in ('max_relative_regression', 'max_relative_mad'):
                    require(type(metric.get(field)) in (int, float) and math.isfinite(metric[field]) and
                            0 <= metric[field] < 1, 'Predeclare finite relative performance/noise bounds')
                references(metric.get('evidence'), context, 'Performance threshold rationale')
    require(criterion_coverage == required, 'Quality criteria do not cover all original requirements')
    _baseline(project, plan)
    if not (goal / 'root-seal.json').exists():
        require(current == plan['baseline']['source'], 'Baseline does not match the pre-change source at sealing')
    return plan


def seal_binding(project, goal, contract):
    project, goal = Path(project).resolve(), Path(goal).resolve()
    plan_path, _, plan = _load(project, goal, contract)
    checks = set()
    for layer in plan['layers']:
        for criterion in layer['criteria']:
            checks.update((selector(criterion['check']), selector(criterion['negative_check'])))
            if 'baseline_check' in criterion:
                checks.add(selector(criterion['baseline_check']))
        for metric in layer.get('metrics', []):
            checks.update((selector(metric['check']), selector(metric['baseline_check'])))
    frozen_checks = {}
    child_tasks = {task_id for task_id, _ in checks}
    child_tasks.update(link['task_id'] for requirement in contract.get('requirements', [])
                       for link in requirement.get('satisfiers', []))
    if 'integration' in contract:
        child_tasks.add(contract['integration']['task_id'])
    child_engines = {}
    for task_id in sorted(child_tasks):
        proof.identifier(task_id, 'Corporate child task ID')
        task = path(project, proof.STATE + '/' + task_id)
        _, actual_project, task_contract = proof.task_context(task)
        require(actual_project == project, 'Root child belongs to another project')
        child_engines[task_id] = {'contract_hash': proof.digest(task_contract),
                                 'engine_hash': proof.engine_hash(task_contract)}
    for task_id, check_id in sorted(checks):
        task = path(project, proof.STATE + '/' + task_id)
        _, actual_project, task_contract = proof.task_context(task)
        require(actual_project == project, 'Planned check belongs to another project')
        frozen_checks[task_id + '/' + check_id] = {
            'contract_hash': proof.digest(task_contract),
            'check_hash': proof.digest(proof.get_check(task_contract, check_id)),
            'engine_hash': proof.engine_hash(task_contract)}
    return {'plan_sha256': proof.file_hash(plan_path),
            'context': {row['id']: citation(project, row['citation']) for row in plan['context']},
            'baseline_digest': plan['baseline']['source']['digest'],
            'baseline_checks': {ref['receipt']: ref['sha256'] for ref in plan['baseline']['checks']},
            'checks': frozen_checks,
            'child_engines': child_engines,
            'engine': verifier_identity(contract)}


def verifier_identity(contract):
    """Pin the code actually interpreting a Corporate root, not release docs.

    Child check-specific dependencies are additionally bound by engine_hash
    in each selected check above. This remains a local integrity check, not
    authentication against a writer able to replace code and the root seal.
    """
    package = Path(__file__).resolve().parent
    names = {'corporate.py', 'root_gate.py', 'coverage.py', 'proof.py',
             'planning.py', 'strict_io.py'}
    if 'production_team' in contract:
        names.update(('team.py', 'team_v2.py'))
    files = {name: proof.file_hash(path(package, name)) for name in sorted(names)}
    return {'files': files, 'digest': proof.digest(files)}


def _review_row(row, expected, label):
    require(isinstance(row, dict), label + ': missing independent review')
    text(row.get('observations'), label + ' observations')
    require(row.get('verdict') != 'UNVERIFIED', label + ': independent review is UNVERIFIED')
    return row.get('verdict') == expected


def _metric(metric, before, after):
    values = []
    profiles = []
    for item in (before, after):
        require(metric['file'] in item['receipt']['artifacts'], 'Metric is not a captured execution artifact')
        data = strict_io.load(proof.relative_file(item['run'], metric['file']))
        profiles.append(proof.json_pointer(data, metric['profile_pointer']))
        require(proof.json_pointer(data, metric['unit_pointer']) == metric['unit'], 'Metric unit mismatch')
        samples = proof.json_pointer(data, metric['samples_pointer'])
        require(isinstance(samples, list) and len(samples) >= metric['minimum_samples'] and
                all(type(x) in (int, float) and math.isfinite(x) and x >= 0 for x in samples),
                'Metric samples must be repeated finite nonnegative numbers')
        median = statistics.median(samples)
        mad = statistics.median(abs(x - median) for x in samples)
        values.append({'median': median, 'relative_mad': mad / max(abs(median), 1e-12), 'count': len(samples)})
    require(profiles[0] == profiles[1] and isinstance(profiles[0], dict) and profiles[0],
            'Performance workload/runtime profile differs or is missing')
    before_value, after_value = values
    if any(v['relative_mad'] > metric['max_relative_mad'] for v in values):
        return {'id': metric['id'], 'status': 'UNVERIFIED', 'reason': 'Measurement noise exceeds sealed bound',
                'baseline': before_value, 'candidate': after_value}
    bound = before_value['median'] * (1 + metric['max_relative_regression'] if metric['direction'] == 'lower'
                                      else 1 - metric['max_relative_regression'])
    passed = after_value['median'] <= bound if metric['direction'] == 'lower' else after_value['median'] >= bound
    return {'id': metric['id'], 'status': 'PASS' if passed else 'FAIL',
            'baseline': before_value, 'candidate': after_value, 'allowed_bound': bound, 'unit': metric['unit']}


def check(project, goal, contract):
    project, goal = Path(project).resolve(), Path(goal).resolve()
    outcomes = {name: {'status': 'UNVERIFIED', 'errors': []} for name in LAYERS}
    errors = []
    try:
        plan = validate(project, goal, contract)
        binding = seal_binding(project, goal, contract)
        seal = document(goal / 'root-seal.json')
        require(seal.get('corporate') == binding,
                'Corporate plan/context/baseline/checks/verifier changed after root sealing')
        require(instant(plan['baseline']['captured_at']) <= instant(seal['sealed_at']),
                'Baseline was captured after root sealing')
        _, report_path, _ = _load(project, goal, contract)
        report = document(report_path)
        require(report.get('schema') == 1 and report.get('plan_sha256') == binding['plan_sha256'],
                'Report belongs to another plan')
        current = source_snapshot(project, plan['source_paths'])
        require(report.get('source') == current, 'Report source is stale or incomplete')
        refs = report.get('executions')
        require(isinstance(refs, list) and refs, 'Report needs actual check executions')
        executed = {}
        for ref in refs:
            item = execution(project, ref, current, latest=True)
            require(item['selector'] not in executed, 'Duplicate candidate check reference')
            require(instant(item['receipt']['started_at']) >= instant(seal['sealed_at']),
                    'Candidate execution predates the sealed acceptance contract')
            executed[item['selector']] = item
        review = report.get('review', {})
        require(review.get('method') in {'human', 'fresh-context-agent'} and
                review.get('reviewer') != plan['author'], 'An independent evidence/meaning reviewer is required')
        text(review.get('reviewer'), 'Actual reviewer identity')
        require(review.get('source_digest') == current['digest'] and
                review.get('plan_sha256') == binding['plan_sha256'] and
                review.get('report_sha256') == proof.digest({k: v for k, v in report.items() if k != 'review'}),
                'Reviewer inspected different source, plan or execution evidence')
        reviewed = instant(review.get('reviewed_at'))
        require(max(instant(item['receipt']['ended_at']) for item in executed.values()) <= reviewed <= datetime.now(timezone.utc),
                'Review must follow current actual executions')
        for section in ('decisions', 'edge_cases'):
            expected = rows(plan[section], section)
            actual = rows(review.get(section), 'Reviewed ' + section)
            require(set(actual) == set(expected), 'Independent review omits a consequential decision/edge case')
            for key in expected:
                require(_review_row(actual[key], 'PASS', section + '.' + key),
                        'Independent evidence relevance/meaning review rejected ' + key)
        reviewed_layers = rows(review.get('layers'), 'Reviewed layers')
        require(set(reviewed_layers) == set(LAYERS), 'Review must assess all six layers')
        baseline = _baseline(project, plan)
        used = set()
        for layer in plan['layers']:
            name = layer['id']
            result = outcomes[name]
            reviewed_layer = reviewed_layers[name]
            verdict = 'PASS' if layer['applicable'] else 'NOT_APPLICABLE'
            approved = _review_row(reviewed_layer, verdict, name)
            actual_rows = rows(reviewed_layer.get('criteria'), 'Reviewed criteria', empty=not layer['applicable'])
            expected_rows = rows(layer['criteria'], 'Planned criteria', empty=not layer['applicable'])
            require(set(actual_rows) == set(expected_rows), name + ': review criteria are missing or invented')
            if not layer['applicable']:
                result['status'] = 'NOT_APPLICABLE' if approved else 'FAIL'
                if not approved:
                    result['errors'].append('Independent review rejected the non-applicability claim')
                continue
            for cid, criterion in expected_rows.items():
                positive, negative = selector(criterion['check']), selector(criterion['negative_check'])
                require(positive in executed and negative in executed, name + ': required execution is missing')
                used.update((positive, negative))
                good, bad = executed[positive], executed[negative]
                require(good['check']['role'] in {'acceptance', 'regression'} and
                        bad['check']['role'] == 'negative_control', 'Criterion needs a normal check and actual negative control')
                if name == 'functionality':
                    require(good['check']['mode'] == 'live' and good['check']['role'] == 'acceptance',
                            'Functionality requires actual live acceptance')
                if name == 'preservation':
                    old_key = selector(criterion['baseline_check'])
                    require(old_key in baseline and baseline[old_key]['passed'],
                            'Preservation needs a successful pre-change baseline check')
                    old_check = baseline[old_key]['check']
                    replay_fields = ('command', 'cwd', 'mode', 'role', 'assertions', 'expected_exit_codes')
                    defaults = {'cwd': '.', 'expected_exit_codes': [0]}
                    require(all(old_check.get(field, defaults.get(field)) == good['check'].get(field, defaults.get(field))
                                for field in replay_fields),
                            'Preservation must replay the baseline command and unchanged assertions')
                if not good['passed'] or not bad['passed']:
                    result['errors'].append(cid + ': actual acceptance/negative control failed')
                if not _review_row(actual_rows[cid], 'PASS', name + '.' + cid):
                    result['errors'].append(cid + ': independent review found weak/incorrect evidence')
            if not approved:
                result['errors'].append('Independent component review did not pass')
            metrics = []
            for metric in layer.get('metrics', []):
                old, new = selector(metric['baseline_check']), selector(metric['check'])
                require(old in baseline and new in executed,
                        'Performance comparison needs baseline and candidate commands')
                used.add(new)
                if not baseline[old]['passed'] or not executed[new]['passed']:
                    result['errors'].append(metric['id'] + ': performance command did not satisfy its behavioral checks')
                    continue
                metrics.append(_metric(metric, baseline[old], executed[new]))
            if metrics:
                result['metrics'] = metrics
            result['status'] = ('FAIL' if result['errors'] or any(m['status'] == 'FAIL' for m in metrics)
                                else 'UNVERIFIED' if any(m['status'] == 'UNVERIFIED' for m in metrics) else 'PASS')
        require(used == set(executed), 'Report contains checks not mapped to a quality criterion/metric')
        errors.extend(name + ': ' + row['status'] for name, row in outcomes.items()
                      if row['status'] not in {'PASS', 'NOT_APPLICABLE'})
        return {'passed': not errors, 'status': 'PASS' if not errors else
                'FAIL' if any(row['status'] == 'FAIL' for row in outcomes.values()) else 'UNVERIFIED',
                'layers': outcomes, 'errors': errors, 'source': current, 'plan_sha256': binding['plan_sha256'],
                'limitation': 'Independent review identities are declared local evidence; this is not a hostile-writer trust boundary.'}
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, OSError, proof.ProofError) as exc:
        return {'passed': False, 'status': 'UNVERIFIED', 'layers': outcomes, 'errors': [str(exc)]}


def goal_project(goal):
    from root_gate import ROOT_DIR

    goal = Path(goal).absolute()
    require(goal.parent.name == ROOT_DIR and goal.parent.parent.name == proof.STATE,
            'Use a root goal under the project .runtime-proof/root-goals directory')
    project = goal.parents[2].resolve()
    proof.identifier(goal.name, 'Root goal ID')
    return project, path(project, f'{proof.STATE}/{ROOT_DIR}/{goal.name}')


def scaffold(goal, proof_task, baseline_checks, author):
    """Create draft documents from actual registered inputs and execution evidence."""
    import coverage
    import root_gate
    import team

    project, goal = goal_project(goal)
    require(not any((goal / name).exists() for name in ('root-contract.json', 'corporate-plan.json', 'root-seal.json')),
            'A Corporate draft or seal already exists. Continue with that attempt.')
    text(author, 'Actual planner identity')
    original = path(goal, 'original-request.txt')
    request_sha256 = proof.file_hash(original)
    state = team.load_state(project, goal.name)
    team_plan = state['plan']
    require(team_plan.get('schema') == 2 and team_plan.get('root_protocol') == PROTOCOL
            and team_plan.get('decomposition') == root_gate.REVIEWED_TEAM,
            'Register a reviewed Team schema 2 with root_protocol corporate-v1 first')
    binding = team.binding(project, goal.name, request_sha256)
    proof.identifier(proof_task, 'Integration proof task')
    require(proof_task != goal.name, 'Use a separate proof task for integration')
    task = path(project, f'{proof.STATE}/{proof_task}')
    _, actual_project, child = proof.task_context(task)
    require(actual_project == project and child['task_id'] == proof_task, 'Proof task does not belong to this project')
    root_gate.require_team_sources(project, child, root_gate.team_outputs(binding))
    source_paths = child['source_paths']
    baseline_source = source_snapshot(project, source_paths)
    require(all(baseline_source['files'].get(rel) == digest for rel, digest in state['baseline'].items()),
            'Current source differs from the registered Team baseline')
    require(baseline_checks and len(baseline_checks) == len(set(baseline_checks)),
            'Select distinct actual baseline checks')
    refs, known_failures, ended = [], [], []
    for check_id in baseline_checks:
        proof.identifier(check_id, 'Baseline check ID')
        proof.get_check(child, check_id)
        latest = document(path(task, f'latest/{check_id}.json'))
        run = path(task, latest['run'])
        receipt = (run / 'receipt.json').relative_to(project).as_posix()
        ref = execution_reference(project, receipt)
        observed = execution(project, ref, baseline_source, latest=True)
        require(observed['selector'] == (proof_task, check_id), 'Baseline selection resolves to another check')
        refs.append(ref)
        ended.append(instant(observed['receipt']['ended_at']))
        if not observed['passed']:
            known_failures.append({'receipt_sha256': ref['sha256'], 'reason': None, 'review': None})
    requirements = [{'id': rid, 'impacts': [], 'tasks': [owner['id'] for owner in team_plan['tasks']
                     if rid in owner['outcomes']]} for rid in team_plan['outcomes']]
    contract = proof.load(proof.SKILL / 'assets/templates/root-contract-v4.json')
    contract.update({'goal_id': goal.name, 'production_team': goal.name, 'request_sha256': request_sha256,
                     'scope_statement': None, 'coverage_review': None,
                     'request_segments': coverage.inventory(original.read_text(encoding='utf-8')),
                     'coverage_challenge': {'file': 'coverage-review.json', 'sha256': None},
                     'requirements': [{'id': row['id'], 'claim': None, 'oracle': None, 'source': None,
                                       'source_excerpt': None, 'evidence_mode': None, 'satisfiers': []}
                                      for row in requirements],
                     'integration': {'task_id': proof_task, 'requirement_id': None, 'scope': None},
                     'corporate': {field: (goal / f'corporate-{field}.json').relative_to(project).as_posix()
                                   for field in ('plan', 'report')}})
    plan = {'schema': 1, 'request_sha256': request_sha256, 'author': author,
            'created_at': proof.now(), 'source_paths': source_paths, 'context': [],
            'requirements': requirements, 'decisions': [], 'edge_cases': [],
            'tasks': [{key: owner[key] for key in ('id', 'outputs', 'depends_on')}
                      for owner in team_plan['tasks']],
            'baseline': {'source': baseline_source, 'checks': refs,
                         'captured_at': max(ended).isoformat(), 'known_failures': known_failures},
            'layers': [{'id': name, 'applicable': True if name in CORE_LAYERS else None,
                        'rationale': None, 'evidence': [], 'criteria': [], 'metrics': []} for name in LAYERS]}
    root_path, plan_path = goal / 'root-contract.json', goal / 'corporate-plan.json'
    proof.save(plan_path, plan, exclusive=True)
    proof.save(root_path, contract, exclusive=True)
    return {'status': 'DRAFT_UNVERIFIED', 'root': str(root_path), 'plan': str(plan_path),
            'proof_requirements': [row['id'] for row in child['requirements']],
            'proof_checks': [row['id'] for row in child['checks']],
            'unfilled': ['Root scope, requirement meaning and proof links, request-span mapping',
                         'Cited context, impacted paths, decisions, and resolved edge cases',
                         'Layer applicability, rationale, criteria, and applicable performance limits',
                         'Independent request coverage and Team review']
                        + (['Independent review of recorded baseline failures'] if known_failures else [])}


def coverage_input(goal):
    _, goal = goal_project(goal)
    root = document(path(goal, 'root-contract.json'))
    return {'request_sha256': proof.file_hash(path(goal, 'original-request.txt')),
            'segments_sha256': proof.digest(root['request_segments']),
            'acceptance_sha256': proof.digest({key: root[key] for key in ('requirements', 'integration')})}


def coverage_packet(goal):
    """Assign the pre-seal request coverage review against the current draft."""
    project, goal = goal_project(goal)
    require(not (goal / 'root-seal.json').exists(), 'Review request coverage before sealing the root')
    root_path = path(goal, 'root-contract.json')
    root = document(root_path)
    require(root.get('schema') == 4 and root.get('protocol') == PROTOCOL
            and root.get('goal_id') == root.get('production_team') == goal.name,
            'Use the matching Corporate root draft')
    expected = coverage_input(goal)
    require(root.get('request_sha256') == expected['request_sha256'], 'Original request differs from the draft')
    _, _, plan = _load(project, goal, root)
    text(plan.get('author'), 'Actual planner identity')
    request = path(goal, 'original-request.txt').as_posix()
    destination = path(goal, 'coverage-review.json', exists=False).as_posix()
    message = (
        f'Independently review coverage of {request} against {root_path.as_posix()}.\n'
        f'Current request, span and acceptance bindings: {json.dumps(expected, sort_keys=True)}.\n'
        'Inspect the actual source and project contracts that affect the meaning of the request. '
        'Check that every requirement, material edge case and preservation obligation has an observable '
        'criterion. Identify any weak assertion, unsupported assumption or omitted material requirement. '
        'Keep product files and the draft read-only. Only write the private review artifact at '
        f'{destination}. Include the three bindings above, method fresh-context-agent, '
        f'planner {json.dumps(plan["author"])}, your actual reviewer identity, concrete observations, '
        'unresolved_findings and verdict. Use covered only if there are no unresolved findings. '
        'Return the artifact path and verdict to the coordinator.')
    return {'task_name': 'coverage_review', 'fork_turns': 'none', 'message': message}


def bind_coverage(goal):
    """Link a reviewer-authored artifact after validating it against the draft."""
    import coverage

    project, goal = goal_project(goal)
    require(not (goal / 'root-seal.json').exists(), 'The root is already sealed')
    root_path = path(goal, 'root-contract.json')
    root = document(root_path)
    require(root.get('schema') == 4 and root.get('protocol') == PROTOCOL,
            'Use a Corporate root draft')
    review_file = path(goal, 'coverage-review.json')
    review = document(review_file)
    expected = coverage_input(goal)
    require(root.get('request_sha256') == expected['request_sha256'], 'Original request differs from the draft')
    require(all(review.get(key) == value for key, value in expected.items()),
            'Coverage review does not match the current request, span mapping and acceptance scope')
    root['coverage_challenge'] = {'file': review_file.name, 'sha256': proof.file_hash(review_file)}
    coverage.validate(path(goal, 'original-request.txt').read_text(encoding='utf-8'), root, goal)
    root['coverage_review'] = {'method': review['method'], 'rationale': review['observations'],
                               'unmapped_segments': []}
    proof.save(root_path, root)
    return {'status': 'COVERAGE_LINKED', 'root': str(root_path), 'root_sealed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    snapshot = sub.add_parser('snapshot')
    snapshot.add_argument('--project', type=Path, required=True)
    snapshot.add_argument('--source', action='append', required=True)
    receipt = sub.add_parser('execution-ref')
    receipt.add_argument('--project', type=Path, required=True)
    receipt.add_argument('--receipt', required=True)
    draft = sub.add_parser('scaffold')
    draft.add_argument('--goal', type=Path, required=True)
    draft.add_argument('--proof-task', required=True)
    draft.add_argument('--baseline-check', action='append', required=True)
    draft.add_argument('--author', required=True)
    for command in ('coverage-input', 'coverage-packet', 'bind-coverage'):
        sub.add_parser(command).add_argument('--goal', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'scaffold':
            result = scaffold(args.goal, args.proof_task, args.baseline_check, args.author)
        elif args.command == 'coverage-input':
            result = coverage_input(args.goal)
        elif args.command == 'coverage-packet':
            result = coverage_packet(args.goal)
        elif args.command == 'bind-coverage':
            result = bind_coverage(args.goal)
        elif args.command == 'snapshot':
            result = source_snapshot(args.project.resolve(), args.source)
        else:
            result = execution_reference(args.project.resolve(), args.receipt)
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError, proof.ProofError) as exc:
        print(str(exc))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
