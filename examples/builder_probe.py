#!/usr/bin/env python3
"""Independent real HTTP/process/restart checks of the staged demo application."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler
import zipfile


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('phase', choices=['slice', 'persistence', 'delivery'])
    args = parser.parse_args()
    root = Path.cwd(); out = Path(os.environ['PROVE_IT_OUTPUT_DIR']); out.mkdir(parents=True, exist_ok=True)
    source = root / 'server.py'
    if args.phase == 'delivery':
        archive = out / 'release.zip'
        with zipfile.ZipFile(archive, 'w') as pack:
            pack.write(source, 'server.py'); pack.write(root / 'API.md', 'API.md')
        clean = out / 'clean-install'; clean.mkdir()
        with zipfile.ZipFile(archive) as pack:
            assert set(pack.namelist()) == {'server.py', 'API.md'}
            pack.extractall(clean)
        source = clean / 'server.py'
        assert source.read_bytes() == (root / 'server.py').read_bytes()
    expected_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    transcript = []
    processes = []
    report = {'phase': args.phase, 'passed': False, 'source_sha256': expected_hash,
              'runtime': 'actual loopback HTTP server subprocesses; no mocked responses',
              'requests': transcript, 'pids': processes}

    @contextmanager
    def launch(index):
        ready = out / f'ready-{index}.json'
        with (out / f'server-{index}.log').open('wb') as log:
            process = subprocess.Popen([sys.executable, '-S', str(source), '--store', str(out / 'state.json'),
                                        '--ready', str(ready)], cwd=source.parent, stdout=log, stderr=subprocess.STDOUT)
            processes.append(process.pid)
            try:
                deadline = time.monotonic() + 10
                while not ready.exists():
                    assert process.poll() is None, 'Actual server exited before readiness'
                    if time.monotonic() >= deadline: raise TimeoutError('Actual server did not become ready')
                    time.sleep(.03)
                info = json.loads(ready.read_text(encoding='utf-8'))
                assert info['pid'] == process.pid and info['sha256'] == expected_hash, 'Wrong server/source instance'
                yield info['url']
            finally:
                if process.poll() is None: process.terminate()
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)

    client = build_opener(ProxyHandler({}))
    def call(url, route, value=None, expected=200):
        request = Request(url + route, data=json.dumps(value).encode() if value is not None else None,
                          headers={'Content-Type': 'application/json'})
        try: response = client.open(request, timeout=5)
        except HTTPError as exc: response = exc
        with response:
            body = json.loads(response.read())
            assert response.headers['X-Source-SHA256'] == expected_hash, 'Stale server accepted'
            assert response.headers['X-Run-ID'] == os.environ['PROVE_IT_RUN_ID'], 'Wrong run identity'
            transcript.append({'route': route, 'sent': value, 'status': response.status, 'actual': body})
            assert response.status == expected, f'Expected HTTP {expected}, observed {response.status}'
        return body

    expected_item = {'id': 1, 'title': 'original goal survives restart'}
    try:
        with launch(1) as url:
            assert call(url, '/items') == {'items': []}
            assert call(url, '/items', {'title': expected_item['title']}, expected=201) == expected_item
            assert call(url, '/items') == {'items': [expected_item]}
            if args.phase != 'slice':
                call(url, '/items', {'title': ''}, expected=400)
                assert call(url, '/items') == {'items': [expected_item]}, 'Invalid input corrupted state'
        if args.phase != 'slice':
            with launch(2) as url:
                observed = call(url, '/items')
                assert observed == {'items': [expected_item]}, f'Restart lost persisted data: {observed}'
                call(url, '/absent', expected=404)
            report['restart_persisted'] = True
        report['passed'] = True
    except Exception as exc:
        report['failure'] = str(exc)
        raise
    finally:
        report['owned_servers_stopped'] = True
        (out / 'observed.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report, indent=2))


if __name__ == '__main__': main()
