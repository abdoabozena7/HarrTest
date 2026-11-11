"""Gold's acceptance decisions on small controlled inputs, not an agent benchmark."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import golden
import proof
import strict_io


class GoldGate(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name).resolve()
        goal = self.project / 'root'
        goal.mkdir()
        original = goal / 'original-request.txt'
        original.write_text('Refunds at the cutoff must have an explicit result.', encoding='utf-8')
        self.spec = {'root_goal': 'root', 'golden': {
            'intake': 'intake.json', 'protocol': 'protocol.json', 'measurement': 'measurement.json'},
            'tasks': [{'proof_task': 'child'}]}
        request_sha = proof.file_hash(original)
        self.write('root/root-contract.json', {
            'request_sha256': request_sha, 'protocol': 'golden-v1', 'requirements': [{'id': 'cutoff'}]})
        self.intake = {'schema': 1, 'request_sha256': request_sha,
                       'interpretation': 'Enforce the refund window against the order timestamp.'}
        self.answer = self.retain('answer.txt', 'The user confirmed that 30 days inclusive qualifies.')
        self.intake.update({
            'requirements': [{'id': 'cutoff', 'meaning': 'Apply the inclusive cutoff',
                              'evidence': [self.answer]}],
            'edge_cases': [{'id': 'exact-day', 'requirement_ids': ['cutoff'],
                            'question': 'Does day 30 qualify?', 'resolution': 'Allow refunds at exactly 30 days.',
                            'source': 'user', 'evidence': [self.answer]}],
            'decisions': [{'id': 'boundary', 'requirement_ids': ['cutoff'],
                           'choice': 'Compare the cutoff inclusively', 'rationale': 'Match the confirmed boundary.',
                           'evidence': [self.answer]}],
        })
        self.write('intake.json', self.intake)
        self.protocol = {'schema': 1, 'mode': 'fixture',
                         'controls': {'runner': 'Identical CLI fixture', 'environment': 'Isolated temporary projects'},
                         'baseline': {'id': '3.2.2', 'source_sha256': 'a' * 64},
                         'cases': [
                             {'id': 'at-limit', 'expect': 'accept', 'oracle': 'Allow the requested action at the cutoff.'},
                             {'id': 'past-limit', 'expect': 'reject', 'oracle': 'Reject the action after the cutoff.'}],
                         'thresholds': {'min_candidate_correct': 2, 'max_candidate_false_accepts': 0,
                                        'min_correct_gain': 1}}
        self.write('protocol.json', self.protocol)
    def write(self, name, value):
        (self.project / name).write_text(strict_io.canonical(value), encoding='utf-8')

    def retain(self, name, text):
        path = self.project / name
        path.write_text(text, encoding='utf-8')
        return {'path': name, 'sha256': proof.file_hash(path)}

    def make_comparison(self, candidate):
        attempts = []
        for case in ('at-limit', 'past-limit'):
            for arm in ('baseline', 'candidate'):
                outcome = 'reject' if case == 'past-limit' and arm == 'candidate' else 'accept'
                record = {'case': case, 'variant': arm, 'outcome': outcome,
                          'source_sha256': candidate if arm == 'candidate' else 'a' * 64}
                attempts.append(self.record_attempt(record))
        return {'schema': 1, 'candidate': {'id': 'Gold candidate', 'source_sha256': candidate},
                'protocol_sha256': strict_io.digest(self.protocol), 'attempts': attempts}

    def record_attempt(self, record):
        prefix = record['case'] + '-' + record['variant']
        raw = self.retain(prefix + '.txt', 'Observed outcome: ' + record['outcome'])
        receipt = self.retain(prefix + '.json', strict_io.canonical({'schema': 1, **record, 'artifacts': [raw]}))
        return {**record, 'evidence': receipt}

    def test_intake_freezes_meanings_resolutions_decisions_and_protocol(self):
        initial = golden.validate_intake(self.project, self.spec)
        self.intake['edge_cases'][0]['source'] = 'pending'
        self.write('intake.json', self.intake)
        with self.assertRaisesRegex(ValueError, 'unresolved edge case'):
            golden.validate_intake(self.project, self.spec)
        self.intake['edge_cases'][0]['source'] = 'user'
        self.intake['decisions'][0]['evidence'] = []
        self.write('intake.json', self.intake)
        with self.assertRaisesRegex(ValueError, 'evidence is required'):
            golden.validate_intake(self.project, self.spec)
        self.intake['decisions'][0]['evidence'] = [self.answer]
        self.write('intake.json', self.intake)
        self.protocol['thresholds']['min_correct_gain'] = 0
        self.write('protocol.json', self.protocol)
        self.assertNotEqual(initial['protocol_sha256'], golden.validate_intake(self.project, self.spec)['protocol_sha256'])
        self.retain('answer.txt', 'Replaced answer differs from the cited user reply.')
        with self.assertRaisesRegex(ValueError, 'evidence changed'):
            golden.validate_intake(self.project, self.spec)

    def test_comparison_keeps_missing_errors_and_stale_evidence_out_of_success(self):
        from unittest.mock import patch
        candidate = 'b' * 64
        report = self.make_comparison(candidate)
        with patch.object(golden, 'source_identity', return_value=candidate):
            self.write('measurement.json', report)
            result = golden.validate_measurement(self.project, self.spec)
            self.assertTrue(result['passed'])
            self.assertEqual(result['baseline']['false_accepts'], 1)
            self.assertEqual(result['correct_gain_points'], 50)
            attempt = report['attempts'].pop()
            self.write('measurement.json', report)
            with self.assertRaisesRegex(ValueError, '1 missing of 4'):
                golden.validate_measurement(self.project, self.spec)
            report['attempts'].append({**attempt, 'outcome': 'error'})
            self.write('measurement.json', report)
            with self.assertRaisesRegex(ValueError, 'disagrees with its retained evaluator receipt'):
                golden.validate_measurement(self.project, self.spec)
            report['attempts'][-1] = self.record_attempt({
                k: v for k, v in report['attempts'][-1].items() if k != 'evidence'})
            self.write('measurement.json', report)
            result = golden.validate_measurement(self.project, self.spec)
            self.assertFalse(result['passed'])
            self.assertEqual(result['candidate']['errors'], 1)
            self.retain(attempt['case'] + '-' + attempt['variant'] + '.txt', 'Retained log was overwritten')
            with self.assertRaisesRegex(ValueError, 'evidence changed'):
                golden.validate_measurement(self.project, self.spec)
        with patch.object(golden, 'source_identity', return_value='c' * 64):
            with self.assertRaisesRegex(ValueError, 'stale for current sealed sources'):
                golden.validate_measurement(self.project, self.spec)

    def test_reject_everything_is_not_a_passing_comparison(self):
        from unittest.mock import patch
        candidate = 'b' * 64
        self.protocol['thresholds'].update(min_candidate_correct=1, min_correct_gain=0)
        self.write('protocol.json', self.protocol)
        report = self.make_comparison(candidate)
        report['attempts'] = [self.record_attempt({
            'case': row['case'], 'variant': row['variant'], 'source_sha256': row['source_sha256'],
            'outcome': 'reject'}) for row in report['attempts']]
        self.write('measurement.json', report)
        with patch.object(golden, 'source_identity', return_value=candidate):
            result = golden.validate_measurement(self.project, self.spec)
        self.assertEqual(result['candidate']['correct'], 1)
        self.assertEqual(result['candidate']['false_accepts'], 0)
        self.assertFalse(result['passed'])


if __name__ == '__main__':
    unittest.main()
