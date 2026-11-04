"""Whole-request coverage inventory. Checks structure, never claims semantic understanding."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import strict_io


def inventory(request):
    result, start = [], 0
    for line in request.splitlines(keepends=True):
        end = start + len(line)
        if line.strip():
            result.append({'start': start, 'end': end, 'text': line.rstrip(),
                           'kind': 'requirement', 'requirement_ids': []})
        start = end
    return result


def validate(request, contract, goal):
    """All non-whitespace characters must be classified and separately reviewed."""
    segments = contract.get('request_segments')
    if not isinstance(segments, list) or not segments:
        raise ValueError('Request coverage segments are required for schema 3')
    required = {r['id'] for r in contract['requirements']}
    covered = bytearray(len(request))
    mapped = set()
    for segment in segments:
        if not isinstance(segment, dict):
            raise ValueError('Invalid coverage segment')
        start, end = segment.get('start'), segment.get('end')
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(request):
            raise ValueError('Invalid coverage range')
        if any(covered[start:end]):
            raise ValueError('Overlapping request segments')
        covered[start:end] = b'\x01' * (end - start)
        kind, ids = segment.get('kind'), segment.get('requirement_ids', [])
        if kind == 'requirement':
            if not isinstance(ids, list) or not ids or any(i not in required for i in ids):
                raise ValueError('Request requirement has no known acceptance mapping')
            mapped.update(ids)
        elif kind == 'context':
            if ids or not isinstance(segment.get('rationale'), str) or len(segment['rationale'].strip()) < 20:
                raise ValueError('Non-requirement text needs an explicit reviewed rationale')
        else:
            raise ValueError('Segment kind must be requirement or context')
    gaps = [i for i, char in enumerate(request) if not char.isspace() and not covered[i]]
    if gaps:
        raise ValueError(f'Original request contains unmapped text at character {gaps[0]}')
    user_required = {r['id'] for r in contract['requirements'] if r['source'] == 'user_request'}
    if not user_required.issubset(mapped):
        raise ValueError('A user requirement has no request-segment mapping')
    ref = contract.get('coverage_challenge', {})
    path = strict_io.scoped_path(goal, ref.get('file'))
    if not path.is_file() or path.stat().st_size > 2_000_000:
        raise ValueError('Invalid coverage challenge artifact')
    if hashlib.sha256(path.read_bytes()).hexdigest() != ref.get('sha256'):
        raise ValueError('Coverage challenge artifact changed')
    review = strict_io.load(path)
    if review.get('request_sha256') != contract['request_sha256']:
        raise ValueError('Coverage reviewer inspected a different original request')
    if review.get('segments_sha256') != strict_io.digest(segments):
        raise ValueError('Coverage reviewer inspected different segments')
    meaning = {'requirements': contract['requirements'], 'integration': contract['integration']}
    if review.get('acceptance_sha256') != strict_io.digest(meaning):
        raise ValueError('Coverage reviewer inspected different acceptance criteria')
    if (review.get('method') not in {'human', 'fresh-context-agent'}
            or not isinstance(review.get('reviewer'), str) or not review['reviewer'].strip()
            or not isinstance(review.get('planner'), str) or not review['planner'].strip()
            or review['reviewer'] == review['planner']):
        raise ValueError('Schema 3 requires a declared separate coverage reviewer')
    if review.get('unresolved_findings') != [] or review.get('verdict') != 'covered':
        raise ValueError('Coverage review still has unresolved findings')
    if not isinstance(review.get('observations'), str) or len(review['observations'].strip()) < 35:
        raise ValueError('Coverage review needs concrete observations, not a checkbox')
    return {'mode': 'FULL_TEXT_MAPPED_SEPARATE_REVIEW_DECLARED',
            'independence_authenticated': False,
            'limitation': 'Span coverage and reviewer identities do not prove semantic completeness or independent execution.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    args = parser.parse_args()
    try:
        request = args.request.read_text(encoding='utf-8')
        print(json.dumps({'request_sha256': hashlib.sha256(args.request.read_bytes()).hexdigest(),
                          'segments': inventory(request), 'acceptance_implied': False}, indent=2))
        return 0
    except (OSError, ValueError) as exc:
        print(str(exc)); return 2


if __name__ == '__main__':
    raise SystemExit(main())
