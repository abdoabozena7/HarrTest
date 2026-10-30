"""Offline regression tests for fail-closed installed-skill revision attestation."""
from __future__ import annotations

import base64
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import version_guard

REVISION = 'a' * 40


class VersionGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.contents = {
            'SKILL.md': b'---\nname: harrtest\n---\n',
            'VERSION': b'2.4.0\n',
            'scripts/version_guard.py': b'print("ok")\n',
        }
        for name, body in self.contents.items():
            f = self.root / name
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(body)
        self.tree = {'truncated': False, 'tree': [{'path': k, 'sha': version_guard.git_blob_sha(v), 'type':'blob'} for k,v in self.contents.items()]}

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, tree=None, version='2.4.0'):
        return version_guard.compare_installed(self.root, tree or self.tree, version, REVISION)

    def test_exact(self):
        self.assertEqual(self.check()['status'], 'LATEST_VERIFIED')

    def test_crlf_does_not_hide_mismatch(self):
        (self.root / 'SKILL.md').write_bytes(self.contents['SKILL.md'].replace(b'\n', b'\r\n'))
        r = self.check()
        self.assertEqual(r['status'], 'LATEST_VERIFIED')
        self.assertEqual(r['crlf_normalized_files'], 1)
        (self.root / 'SKILL.md').write_text('wrong skill')
        self.assertEqual(self.check()['status'], 'STOP_INSTALLED_SKILL_DIFFERS')

    def test_missing_file_is_not_latest(self):
        (self.root / 'SKILL.md').unlink()
        self.assertEqual(self.check()['missing'], ['SKILL.md'])

    def test_old_version_is_not_latest(self):
        (self.root / 'VERSION').write_text('2.3.0\n')
        self.assertEqual(self.check()['installed_version'], '2.3.0')
        self.assertEqual(self.check()['status'], 'STOP_INSTALLED_SKILL_DIFFERS')

    def test_extra_file_not_latest(self):
        (self.root / 'older-skill.md').write_text('old')
        self.assertIn('older-skill.md', self.check()['unexpected_files'])

    def test_generated_bytecode_ignored(self):
        p = self.root / 'scripts/__pycache__/version_guard.cpython-312.pyc'
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b'generated')
        self.assertEqual(self.check()['status'], 'LATEST_VERIFIED')

    def test_symlink_not_allowed(self):
        (self.root / 'SKILL.md').unlink()
        try:
            (self.root / 'SKILL.md').symlink_to(self.root / 'VERSION')
        except (OSError, NotImplementedError):
            self.skipTest('Symlinks unsupported')
        self.assertIn('SKILL.md', self.check()['modified'])

    def test_remote_tree_truncation_fails(self):
        t = copy.deepcopy(self.tree)
        t['truncated'] = True
        with self.assertRaisesRegex(ValueError, 'truncated'):
            self.check(t)

    def test_remote_traversal_fails(self):
        t = copy.deepcopy(self.tree)
        t['tree'][0]['path'] = '../secret'
        with self.assertRaisesRegex(ValueError, 'source path'):
            self.check(t)

    def test_remote_duplicate_path_fails(self):
        t = copy.deepcopy(self.tree)
        t['tree'].append(t['tree'][0].copy())
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            self.check(t)

    def test_remote_wrong_version_blob_rejected(self):
        def fetch(url):
            if '/git/ref/' in url: return {'object': {'sha': REVISION}}
            if '/git/trees/' in url: return self.tree
            return {'content': base64.b64encode(b'3.0.0\n').decode(), 'encoding': 'base64'}
        with self.assertRaisesRegex(ValueError, 'did not match'):
            version_guard.inspect(self.root, fetch=fetch)

    def test_inspect_mock_remote_passes(self):
        def fetch(url):
            if '/git/ref/' in url: return {'object': {'sha': REVISION}}
            if '/git/trees/' in url: return self.tree
            return {'content': base64.b64encode(self.contents['VERSION']).decode(), 'encoding': 'base64'}
        result = version_guard.inspect(self.root, fetch=fetch)
        self.assertEqual(result['status'], 'LATEST_VERIFIED')
        self.assertFalse(result['host_skill_invocation_verified'])


    def test_inspect_wrapped_github_base64_passes(self):
        # GitHub Git Blob JSON commonly uses base64 with embedded newlines.
        content = base64.b64encode(self.contents['VERSION']).decode()
        wrapped = content[:4] + '\n' + content[4:] + '\n'
        def fetch(url):
            if '/git/ref/' in url: return {'object': {'sha': REVISION}}
            if '/git/trees/' in url: return self.tree
            return {'content': wrapped, 'encoding': 'base64'}
        self.assertEqual(version_guard.inspect(self.root, fetch=fetch)['status'], 'LATEST_VERIFIED')

    def test_inspect_wrapped_crlf_base64_passes(self):
        content = base64.b64encode(self.contents['VERSION']).decode()
        def fetch(url):
            if '/git/ref/' in url: return {'object': {'sha': REVISION}}
            if '/git/trees/' in url: return self.tree
            return {'content': content[:4] + '\r\n' + content[4:] + '\r\n', 'encoding': 'base64'}
        self.assertEqual(version_guard.inspect(self.root, fetch=fetch)['status'], 'LATEST_VERIFIED')

    def test_inspect_malformed_base64_still_fails_closed(self):
        content = base64.b64encode(self.contents['VERSION']).decode()
        def fetch(url):
            if '/git/ref/' in url: return {'object': {'sha': REVISION}}
            if '/git/trees/' in url: return self.tree
            return {'content': content[:4] + '!' + content[4:], 'encoding': 'base64'}
        with self.assertRaisesRegex(Exception, 'base64'):
            version_guard.inspect(self.root, fetch=fetch)

    def test_fails_if_expected_skill_missing_in_tree(self):
        t = copy.deepcopy(self.tree)
        t['tree'] = [f for f in t['tree'] if f['path'] != 'SKILL.md']
        with self.assertRaisesRegex(ValueError, 'required'):
            self.check(t)


if __name__ == '__main__':
    unittest.main()
