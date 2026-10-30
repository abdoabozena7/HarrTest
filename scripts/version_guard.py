#!/usr/bin/env python3
"""Read-only installed HarrTest vs GitHub main attestation (not host invocation proof).

This script does not update skills, bypass permissions, or claim an agent loaded it.
Requires public GitHub access; fails closed when remote verification is unavailable.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPO = 'abdoabozena7/HarrTest'
TEXT_EXTENSIONS = {'.md', '.txt', '.py', '.json', '.yaml', '.yml', '.html', '.svg', '.js', '.css', '.toml', '.xml', '.sh', '.ps1'}
IGNORED_PARTS = {'.git', '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache'}


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode('ascii') + b'\0' + data).hexdigest()


def fetch_json(url: str) -> dict:
    req = Request(url, headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'HarrTest-version-guard'})
    with urlopen(req, timeout=12) as response:
        return json.load(response)


def compare_installed(root: Path, tree: dict, remote_version: str, revision: str) -> dict:
    if not isinstance(tree, dict) or tree.get('truncated') is not False or not isinstance(tree.get('tree'), list):
        raise ValueError('Remote tree missing or truncated')
    if not isinstance(revision, str) or len(revision) != 40 or any(c not in '0123456789abcdef' for c in revision):
        raise ValueError('Invalid remote revision')
    entries = {}
    for item in tree['tree']:
        if item.get('type') != 'blob':
            continue
        key = item.get('path')
        if not isinstance(key, str) or not key or key.startswith('/') or '\\' in key or any(part in ('.', '..', '') for part in key.split('/')):
            raise ValueError('Invalid remote source path')
        if key in entries:
            raise ValueError('Duplicate remote source path')
        sha = item.get('sha')
        if not isinstance(sha, str) or len(sha) != 40 or any(c not in '0123456789abcdef' for c in sha):
            raise ValueError('Invalid remote blob hash')
        entries[key] = sha
    if 'VERSION' not in entries or 'SKILL.md' not in entries or 'scripts/version_guard.py' not in entries:
        raise ValueError('Remote tree lacks required skill files')
    if not isinstance(remote_version, str) or not remote_version.strip():
        raise ValueError('Empty remote version')
    root = Path(root)
    if not root.is_dir():
        raise ValueError('Installed skill directory is missing')
    local_version_path = root / 'VERSION'
    local_version = local_version_path.read_text(encoding='utf-8-sig').strip() if local_version_path.is_file() else None
    exact = 0
    normalized = 0
    missing, modified, extras = [], [], []
    for name, sha in sorted(entries.items()):
        file_path = root.joinpath(*PurePosixPath(name).parts)
        if file_path.is_symlink():
            modified.append(name)  # No symlink resolution outside installed root.
            continue
        if not file_path.is_file():
            missing.append(name)
            continue
        raw = file_path.read_bytes()
        if git_blob_sha(raw) == sha:
            exact += 1
            continue
        if file_path.suffix.lower() in TEXT_EXTENSIONS or name in {'VERSION', 'LICENSE', '.gitignore'}:
            try:
                text = raw.decode('utf-8-sig')
            except UnicodeDecodeError:
                text = None
            if text is not None and git_blob_sha(text.replace('\r\n', '\n').encode('utf-8')) == sha:
                normalized += 1
                continue
        modified.append(name)
    for path in root.rglob('*'):
        if path.is_dir():
            continue
        rel = path.relative_to(root)
        if any(part in IGNORED_PARTS for part in rel.parts) or path.suffix == '.pyc':
            continue
        if rel.as_posix() not in entries:
            extras.append(rel.as_posix())
    status = 'LATEST_VERIFIED' if (local_version == remote_version and not missing and not modified and not extras) else 'STOP_INSTALLED_SKILL_DIFFERS'
    return {'status': status, 'remote_version': remote_version, 'installed_version': local_version,
            'remote_revision': revision, 'remote_files': len(entries), 'exact_files': exact,
            'crlf_normalized_files': normalized, 'missing': missing, 'modified': modified,
            'unexpected_files': sorted(extras), 'read_only': True,
            'host_skill_invocation_verified': False,
            'warning': 'Confirm separate actual host skill invocation. Matching source files alone do not prove the model obeyed the skill or improved outcomes.'}


def inspect(root: Path, repo: str = REPO, fetch=fetch_json) -> dict:
    if not isinstance(repo, str) or '/' not in repo or any(not s or not all(c.isalnum() or c in '-_.' for c in s) for s in repo.split('/')) or len(repo.split('/')) != 2:
        raise ValueError('Expected GitHub owner/repo')
    base = f'https://api.github.com/repos/{repo}'
    ref = fetch(f'{base}/git/ref/heads/main')
    revision = ref['object']['sha']
    tree = fetch(f'{base}/git/trees/{revision}?recursive=1')
    version_entry = next((item for item in tree['tree'] if item.get('path') == 'VERSION' and item.get('type') == 'blob'), None)
    if not version_entry:
        raise ValueError('Remote VERSION is not present')
    blob = fetch(f'{base}/git/blobs/{version_entry["sha"]}')
    if blob.get('encoding') != 'base64' or not isinstance(blob.get('content'), str):
        raise ValueError('Invalid remote VERSION blob')
    version_bytes = base64.b64decode(blob['content'], validate=True)
    if git_blob_sha(version_bytes) != version_entry['sha']:
        raise ValueError('Remote VERSION contents did not match remote tree')
    version = version_bytes.decode('utf-8-sig').strip()
    return compare_installed(root, tree, version, revision)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installed', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--repo', default=REPO)
    args = parser.parse_args(argv)
    try:
        report = inspect(args.installed, args.repo)
    except (OSError, ValueError, KeyError, TypeError, UnicodeDecodeError, binascii.Error, URLError, HTTPError) as exc:
        print(json.dumps({'status': 'STOP_LATEST_UNVERIFIED', 'error': str(exc), 'read_only': True}, indent=2))
        return 2
    print(json.dumps(report, indent=2))
    return 0 if report['status'] == 'LATEST_VERIFIED' else 1


if __name__ == '__main__':
    sys.exit(main())
