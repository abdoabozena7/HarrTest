"""Deterministic input boundaries shared by the v3 local runtime."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path


def pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError(f'Duplicate JSON key: {key}')
        result[key] = value
    return result


def loads(value):
    return json.loads(value, object_pairs_hook=pairs,
                      parse_constant=lambda v: (_ for _ in ()).throw(ValueError(f'Nonfinite JSON value: {v}')))


def load(path):
    return loads(Path(path).read_text(encoding='utf-8-sig'))


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def scoped_path(root, name, *, must_exist=True):
    """Explicit relative paths, including all parent symlink checks, across OSes."""
    root = Path(root).resolve()
    if not isinstance(name, str) or not name or name.startswith('/') or '\\' in name or ':' in name:
        raise ValueError('Expected an explicit relative POSIX path')
    if any(part in {'', '.', '..'} for part in name.split('/')):
        raise ValueError('Path traversal or ambiguous relative path')
    cursor = root
    for part in name.split('/'):
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError('Symlink not permitted in scoped path')
    if not cursor.resolve().is_relative_to(root):
        raise ValueError('Path escapes declared root')
    if must_exist and not cursor.exists():
        raise ValueError(f'Missing scoped path: {name}')
    return cursor


def scope_key(value):
    """Conservative, case-insensitive path locking; no wildcard semantics."""
    if value == '.':
        return ''
    if not isinstance(value, str) or not value or value.startswith('/') or any(c in value for c in '\\:*?[]'):
        raise ValueError('Use explicit relative file/directory scopes, not globs')
    value = value.rstrip('/')
    if any(p in {'', '.', '..'} for p in value.split('/')):
        raise ValueError('Invalid file scope')
    return value.casefold()


def overlaps(left, right):
    a, b = scope_key(left), scope_key(right)
    return not a or not b or a == b or a.startswith(b + '/') or b.startswith(a + '/')


def conflicts(left, right):
    lw, rw = left.get('write_scope', []), right.get('write_scope', [])
    lr, rr = left.get('read_scope', []), right.get('read_scope', [])
    return (any(overlaps(a, b) for a in lw for b in rw + rr)
            or any(overlaps(a, b) for a in rw for b in lr)
            or bool(set(left.get('resources', [])) & set(right.get('resources', []))))
