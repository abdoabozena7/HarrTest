#!/usr/bin/env python3
"""Existing-code Copilot comparison with independent executable acceptance.

This evaluator is not a skill resource. It must remain outside all generation
workspaces and pinned skill packages. Local path permissions are cooperative
isolation, not a hostile-agent sandbox. No model is launched by preflight,
freeze, prepare, evaluate, or summarize.
"""
from __future__ import annotations

import argparse
import ast
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
import re
import shutil
import signal
import statistics
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "assets/corporate/cases.json"
ARMS = ("plain", "v4.1", "v5")
LANGUAGES = {"csharp", "typescript", "python", "cpp"}
SKIP = {".git", ".runtime-proof", ".github", ".agents", ".claude", "__pycache__", "bin", "obj", "node_modules"}
SKILL_EXCLUDES = {".git", "output", ".runtime-proof", ".agent_evidence", ".harrtest", ".harrtest-state", "runs", "tests", "node_modules"}
EVALUATOR_ONLY = {'scripts/corporate_benchmark.py','assets/corporate',
                  'references/v3-validation.md','references/v3.2-validation.md',
                  'references/v3.2.2-validation.md','references/v4-validation.md',
                  'references/v4.1-validation.md','references/v4.1-results.json','references/v5-validation.md'}
LAYER_NAMES = ("functionality", "preservation", "architecture", "security", "performance", "resilience")
GENERATION_OUTCOMES = {"COMPLETED", "FAILED", "TIMEOUT", "BLOCKED_UNVERIFIED", "UNVERIFIED", "INVALID"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value, *, exclusive=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x" if exclusive else "w", encoding="utf-8") as out:
        out.write(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def load(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key: " + key)
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding="utf-8-sig"), object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def cases(path=CORPUS):
    data = load(path)
    rows = data.get("cases", [])
    if data.get("schema") != 1 or len(rows) != 16:
        raise ValueError("Expected the complete 16-case corpus")
    if len({r["id"] for r in rows}) != 16:
        raise ValueError("Duplicate case ID")
    for split in ("development", "acceptance"):
        selected = [r for r in rows if r.get("split") == split]
        if len(selected) != 8 or any(sum(r["language"] == lang for r in selected) != 2 for lang in LANGUAGES):
            raise ValueError("Each split needs two cases for each of four languages")
    for row in rows:
        if not re.fullmatch(r"[a-z][a-z0-9-]{2,60}", row["id"]) or len(row.get("request", "")) < 30:
            raise ValueError("Invalid case")
    return rows


def package_bytecode(path, package):
    """Identify conventional import caches with a real sibling source file."""
    if not path.is_relative_to(package) or path.parent.name != '__pycache__' or path.is_symlink():
        return False
    match = re.fullmatch(r'(.+)\.(?:cpython|pypy)-[0-9]+(?:\.opt-[0-9]+)?\.pyc', path.name)
    if match is None:
        return False
    source = path.parent.parent / (match[1] + '.py')
    return source.is_file() and not source.is_symlink()


def tree(root, *, skill=False):
    root = Path(root).resolve()
    result = {}
    for directory, children, names in os.walk(root):
        children[:] = sorted(set(children) - (SKILL_EXCLUDES if skill else SKIP))
        if skill:
            children[:] = [name for name in children if (Path(directory)/name).relative_to(root).as_posix() not in EVALUATOR_ONLY]
        for name in sorted(names):
            p = Path(directory) / name
            rel = p.relative_to(root).as_posix()
            if p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction()):
                raise ValueError("Linked artifact is not accepted: " + rel)
            if name.startswith(".env") or name.endswith((".webm", ".mp4")):
                continue
            if (skill and package_bytecode(p, root)) or (not skill and name.endswith('.pyc')):
                continue
            if skill and rel in EVALUATOR_ONLY:
                continue
            result[rel] = sha(p)
    return result


def command(argv, cwd, timeout=120, *, env=None):
    started = time.monotonic()
    kwargs = {"cwd": str(cwd), "stdout": subprocess.PIPE, "stderr": subprocess.PIPE,
              "text": True, "encoding": "utf-8", "errors": "replace", "env": env}
    if os.name == "nt": kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
    else: kwargs['start_new_session'] = True
    p = subprocess.Popen([str(x) for x in argv], **kwargs)
    try:
        stdout, stderr = p.communicate(timeout=timeout)
        return {"argv": list(map(str, argv)), "exit_code": p.returncode,
                "stdout": stdout, "stderr": stderr, "seconds": time.monotonic() - started,
                "timed_out": False}
    except subprocess.TimeoutExpired:
        # Stop only the process tree started by this invocation. Do not leave
        # writers running behind a timed-out model attempt or evaluator.
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True, timeout=15)
        else:
            try: os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError: pass
        stdout, stderr = p.communicate(timeout=15)
        return {"argv": list(map(str, argv)), "exit_code": None, "stdout": stdout,
                "stderr": stderr, "seconds": time.monotonic() - started, "timed_out": True}


def preflight(tools=None):
    tools = tools or {}
    found = {k: tools.get(k) or shutil.which(k + (".cmd" if k == "copilot" and os.name == "nt" else ""))
             for k in ("copilot", "node", "python", "dotnet", "tsc")}
    found["python"] = found["python"] or sys.executable
    found["cxx"] = tools.get("cxx") or ([shutil.which("clang++") or shutil.which("g++")] if shutil.which("clang++") or shutil.which("g++") else None)
    for key in ("sdk", "runtime", "msvc_env", "identity_files", "node_types"):
        if tools.get(key):
            found[key] = tools[key]
    versions = {}
    for key in ("copilot", "node", "python", "dotnet", "tsc"):
        if found[key]:
            args = [found[key], "--list-sdks" if key == "dotnet" else "--version"]
            if key=='tsc' and str(found[key]).endswith('.js'):args=[found['node'],*args]
            versions[key] = command(args, ROOT, 30)
    if found["cxx"]:
        versions["cxx"] = command([*found["cxx"], "--version"], ROOT, 30)
    blocked = [k for k in ("copilot", "node", "python", "cxx") if not found[k]]
    if not found["dotnet"] or not versions["dotnet"]["stdout"].strip():
        blocked.append("dotnet-sdk")
    if not found['tsc'] or not found.get('node_types'):
        blocked.append('typescript-compiler-and-node-types')
    if found.get("sdk") and found.get("runtime"):
        versions["runtime"] = command([*found["runtime"], "--version"], ROOT, 30)
    return {"schema": 1, "tools": found, "versions": versions, "blocked": blocked,
            "platform": platform.platform(), "python": sys.version,
            "auth_probe": "Not performed; config/model catalog is not proof of account access.",
            "isolation": "Repository-local disabledSkills for plain; project skill precedence for skill arms; observed list required."}


def msvc_environment(path):
    """Read compiler setup into this subprocess only; never retain its environment output."""
    path = Path(path).resolve(strict=True)
    if path.suffix.lower() != ".bat" or any(c in str(path) for c in '\"%!\r\n'):
        raise ValueError("Expected the explicit trusted vcvars batch path")
    shell = Path(os.environ.get("COMSPEC", "C:/Windows/System32/cmd.exe")).resolve(strict=True)
    # list2cmdline escapes inner quotes with backslashes, which cmd does not
    # interpret like the C runtime. Construct this fixed environment-only
    # command with validated literal paths and no caller-supplied shell text.
    argv = '"' + str(shell) + '" /d /v:off /s /c "call "' + str(path) + '" >nul && set"'
    result = subprocess.run(argv,
                            capture_output=True, text=True, errors="replace", timeout=45)
    if result.returncode:
        raise ValueError("MSVC environment setup failed")
    environment = dict(os.environ)
    for line in result.stdout.splitlines():
        if "=" in line and not line.startswith("="):
            key, value = line.split("=", 1)
            environment[key] = value
    return environment


def generation_environment(workspace, tools):
    environment = msvc_environment(tools['msvc_env']) if tools.get('msvc_env') else dict(os.environ)
    scratch = workspace / '.runtime-proof' / 'scratch'
    scratch.mkdir(parents=True, exist_ok=False)
    for name in ('TEMP', 'TMP', 'TMPDIR'):
        environment[name] = str(scratch)
    environment['PYTHONDONTWRITEBYTECODE'] = '1'
    if tools.get('dotnet'):
        environment['PATH'] = str(Path(tools['dotnet']).parent) + os.pathsep + environment.get('PATH', '')
        environment['DOTNET_ROOT'] = str(Path(tools['dotnet']).parent)
        environment['DOTNET_NOLOGO'] = '1'
        environment['DOTNET_CLI_TELEMETRY_OPTOUT'] = '1'
    return environment


def replay_original_checks(workspace, evidence, meta, tools, candidate_manifest):
    """Run the original preservation oracle on byte-verified scratch copies."""
    baseline, candidate = evidence / 'existing-baseline', evidence / 'existing-candidate'
    baseline.mkdir()
    candidate.mkdir()
    for path, content in fixture(meta['case'], tools).items():
        (baseline / path).write_text(content, encoding='utf-8')
    for path in candidate_manifest:
        destination = candidate / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(workspace / path, destination)
    if tree(baseline) != meta['baseline'] or tree(candidate) != candidate_manifest:
        raise ValueError('Original test replay inputs differ from the frozen source manifests')
    oracle = 'check_existing.py'
    shutil.copyfile(baseline / oracle, candidate / oracle)
    executions = {}
    for role, directory in [('baseline', baseline), ('candidate', candidate)]:
        executions[role] = command([tools['python'], '-B', oracle], directory, 120,
                                   env=generation_environment(directory, tools))
    baseline_passed = executions['baseline']['exit_code'] == 0
    candidate_passed = executions['candidate']['exit_code'] == 0
    return {'check': 'preservation-existing-test-replay', 'oracle_sha256': meta['baseline'][oracle],
            'baseline_source_sha256': digest(meta['baseline']), 'candidate_source_sha256': digest(candidate_manifest),
            'execution': executions, 'passed': baseline_passed and candidate_passed,
            'status': 'UNVERIFIED' if not baseline_passed else 'PASS' if candidate_passed else 'FAIL'}


def freeze(destination, baseline, candidate, models, *, tools=None, seconds=2400, credits=120, corpus=CORPUS, kind='development', seed=20261114):
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError("Use a new immutable experiment directory")
    if kind not in {'development','acceptance'}:raise ValueError('Declare development or acceptance experiment')
    if type(seed) is not int:raise ValueError('Execution-order seed must be an integer')
    if len(models) != 2 or len(set(models)) != 2 or any(not m or m == "auto" for m in models):
        raise ValueError("Pin two distinct concrete model IDs; Auto is not allowed")
    if not isinstance(seconds, int) or not 60 <= seconds <= 7200 or not isinstance(credits, int) or credits < 30:
        raise ValueError("Invalid common attempt bounds")
    rows = cases(corpus)
    baseline, candidate = Path(baseline).resolve(), Path(candidate).resolve()
    for p, version in ((baseline, "4.1.0"), (candidate, "5.0.0")):
        if (p / "VERSION").read_text().strip() != version or not (p / "SKILL.md").is_file():
            raise ValueError("Wrong skill version: " + str(p))
    probe = preflight(tools)
    if probe["blocked"]:
        raise ValueError("Missing live toolchain: " + ", ".join(probe["blocked"]))
    destination.mkdir(parents=True)
    archive=destination/'evaluator'
    archive.mkdir()
    shutil.copy2(__file__,archive/'corporate_benchmark.py')
    shutil.copy2(corpus,archive/'cases.json')
    packages = {}
    for arm, source in (("v4.1", baseline), ("v5", candidate)):
        manifest = tree(source, skill=True)
        target = destination / "packages" / arm
        for rel in manifest:
            out = target / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / rel, out)
        packages[arm] = {"manifest": manifest, "sha256": digest(manifest)}
    plan = {"schema": 1, "kind":kind,"created_unix": time.time(), "corpus_sha256": sha(corpus), "cases": rows,
            "evaluator_sha256": sha(__file__), "models": models, "arms": list(ARMS), "repetitions": 2,
            "execution_seed":seed,"execution_order":balanced_execution_order(rows,models,seed),
            "execution_policy":"One generation then its independent evaluation at a time. Follow the frozen rotated arm order inside case/model/repetition blocks; no heavy tests during paired performance measurements.",
            "native_task_pin_policy":"All arms normalize explicit native task model and reasoning-effort overrides to the frozen session pins. Actual actor model and effort remain independently checked after execution.",
            "acceptance_attempts": 96, "budget": {"seconds": seconds, "max_ai_credits": credits},
            "packages": packages, "preflight": probe,
            "limits": ["Same wall/credit caps are not equal realized generation cost.",
                       "All task product modifications must come from actual Copilot tools.",
                       "Local source provenance is cooperative, not a hostile-writer sandbox.",
                       "Mixed complexity: two multi-component SDK/domain and CLI additions, six bounded acceptance changes. Related synthetic codebase families share existing APIs across development and acceptance; no unseen-family or enterprise-scale claim.",
                       "Any acceptance case used to tune the harness becomes development data and requires a fresh declared comparison."]}
    runtime_files = {}
    declared=[]
    for key in ('copilot','node','python','dotnet','tsc','msvc_env'):
        if probe['tools'].get(key):declared.append(probe['tools'][key])
    declared.extend(probe['tools'].get('cxx') or [])
    declared.extend(probe['tools'].get('identity_files') or [])
    for executable in declared:
        p=Path(executable)
        if not p.is_file():
            resolved=shutil.which(str(executable))
            if resolved:p=Path(resolved)
        if p.is_file():runtime_files[str(p.resolve())]=sha(p)
        elif executable in (probe['tools'].get('identity_files') or []):
            raise ValueError('Missing declared toolchain dependency: '+str(executable))
    for rel in probe["tools"].get("runtime", []):
        p = Path(rel)
        if p.is_file(): runtime_files[str(p.resolve())] = sha(p)
    if probe["tools"].get("sdk"):
        sdk = Path(probe["tools"]["sdk"]).resolve()
        for p in sdk.parent.rglob("*.js"):
            runtime_files[str(p.resolve())] = sha(p)
    if probe['tools'].get('tsc'):
        tsc=Path(probe['tools']['tsc']).resolve()
        # TypeScript's entrypoint delegates to adjacent compiler libraries and
        # default declaration files; bind those dependencies, not just a shim.
        if tsc.suffix=='.js':
            for p in tsc.parent.rglob('*'):
                if p.is_file():runtime_files[str(p.resolve())]=sha(p)
    if probe['tools'].get('node_types'):
        for p in Path(probe['tools']['node_types']).rglob('*'):
            if p.is_file():runtime_files[str(p.resolve())]=sha(p)
    plan["runtime_files"] = runtime_files
    save(destination / "protocol.json", plan, exclusive=True)
    save(destination / "seal.json", {"protocol_sha256": digest(plan)}, exclusive=True)
    return plan


def frozen(experiment):
    experiment = Path(experiment).resolve()
    plan = load(experiment / "protocol.json")
    if digest(plan) != load(experiment / "seal.json")["protocol_sha256"]:
        raise ValueError("Protocol was changed after freezing")
    if plan["evaluator_sha256"] != sha(__file__):
        raise ValueError("Evaluator changed; run the retained experiment/evaluator/corporate_benchmark.py or freeze a new trial")
    if not (experiment/'evaluator/corporate_benchmark.py').is_file() or sha(experiment/'evaluator/corporate_benchmark.py')!=plan['evaluator_sha256']:
        raise ValueError('Retained evaluator changed or is missing')
    if sha(experiment/'evaluator/cases.json')!=plan['corpus_sha256']:
        raise ValueError('Retained case corpus changed')
    for path, expected in plan.get("runtime_files", {}).items():
        if not Path(path).is_file() or sha(path) != expected:
            raise ValueError("Pinned toolchain/transport dependency changed")
    for arm in ("v4.1", "v5"):
        if tree(experiment / "packages" / arm, skill=True) != plan["packages"][arm]["manifest"]:
            raise ValueError("Frozen skill package changed")
    return experiment, plan


MONTHLY_REPORT_CONTRACT = '''Public wire contract (evaluate accepts JSON text and returns JSON text):
month: {"op":"month","ledger":"<file-path>","month":"2025-03"} -> {"ids":["entry"],"total_cents":12} for a ledger containing [{"id":"entry","recorded_at":"2025-03-16T14:01:00Z","amount_cents":12}].
The queried month must be a string of the form YYYY-MM with year 0001 through 9999 and month 01 through 12. Missing or malformed month values raise ValueError.
Each recorded_at must be a valid calendar date and whole-second time in the form YYYY-MM-DDTHH:MM:SSZ or YYYY-MM-DDTHH:MM:SS±HH:MM. Offsets have hours 00 to 23 and minutes 00 to 59. Hours 24 and leap seconds are invalid. Missing, non-string, malformed, or timezone-less timestamps anywhere in the ledger raise ValueError. A timestamp whose UTC result is out of the supported year range also raises ValueError.
Month membership uses UTC. For example, 2025-04-01T00:10:00+01:00 belongs to March UTC. Return matching IDs in ledger order and sum their signed integer amount_cents. An empty result returns {"ids":[],"total_cents":0}.
entry_count: {"op":"entry_count","ledger":"<file-path>"} -> {"count":1} for the one-entry ledger above. This operation counts the records without parsing timestamps.
Both operations are read-only. The CLI takes JSON text as its first positional argument and prints the returned JSON.
'''


MONTHLY_REPORT_SOURCE = '''import json
from pathlib import Path


def summarize(entries, month):
    selected = [entry for entry in entries if entry['recorded_at'][:7] == month]
    return {'ids': [entry['id'] for entry in selected],
            'total_cents': sum(entry['amount_cents'] for entry in selected)}


def evaluate(text):
    request = json.loads(text)
    entries = json.loads(Path(request['ledger']).read_text(encoding='utf-8'))
    if request['op'] == 'entry_count':
        return json.dumps({'count': len(entries)})
    if request['op'] == 'month':
        return json.dumps(summarize(entries, request['month']))
    raise ValueError('unsupported operation')
'''


def fixture(case, tools=None):
    """Pre-existing defective project and ordinary public contract; no target fixes."""
    tools = tools or {}
    lang = case["language"]
    signature={'python':'rules.evaluate(text: str) -> str','typescript':'evaluate(text: string): string','csharp':'Rules.Evaluate(string text) -> string','cpp':'evaluate(const std::string& input) -> std::string'}[lang]
    common = {"ARCHITECTURE.md": "The core Rules module owns domain behavior. The CLI is only an adapter.\nPreserve the public " + signature + " API. No external packages or services.\nDo not put domain cases into the CLI or change this contract to bypass acceptance.\n",
              ".gitignore": "bin/\nobj/\n__pycache__/\n.runtime-proof/\n.github/copilot/settings.local.json\n"}
    common['RUNTIME.md']='Python3.10+ is available. Node22+ runs TypeScript directly with --experimental-strip-types. C# targets net10.0. C++ targets C++17. The supplied process environment contains the pinned local toolchains. Existing checks: python check_existing.py.\n'
    common['RUNTIME.md']+='The existing checker uses .runtime-proof/scratch within the project. The supplied process also sets TEMP, TMP and TMPDIR to this location for other standard temporary-file APIs.\n'
    contracts={
        'csharp': '''Public wire contract (UTF-8 JSON in, one JSON value out):
refund: {"op":"refund","age":2,"window":30} -> true; age/window are nonnegative integer days.
tenant: {"op":"tenant","tenant":"B","id":"same","accounts":[{"tenant":"A","id":"same","balance":8},{"tenant":"B","id":"same","balance":21}]} -> 21. Tenant and account keys are strings named exactly tenant and id; no authorized match returns null.
credit: {"op":"credit","left":4,"amount":3} -> {"balance":7,"accepted":true}. Rejected amount returns the original balance with accepted:false, not an exception. Ledger values fit signed64-bit.
transfer: {"op":"transfer","left":30,"right":4,"amount":6} -> {"left":24,"right":10,"accepted":true}. Amount must be strictly positive and affordable. Rejection returns both original balances and accepted:false.
transfer_many (when requested): {"op":"transfer_many","left":30,"right":4,"amounts":[6,5]} -> {"left":19,"right":15,"accepted":true}. Reject atomically on any invalid/unaffordable amount; an empty list is a successful no-op.
The original CLI takes the JSON text as its first positional argument. A requested --input-file option takes a UTF-8 JSON file path; do not echo malformed content or stack traces on errors.
''',
        'typescript': '''Public wire contract (UTF-8 JSON in; evaluate returns text):
limit: {"op":"limit"} -> {"limit":10}; supplied limit is a nonnegative integer and zero is meaningful.
config: {"op":"config","enabled":false,"limit":0,"label":""} -> {"enabled":false,"limit":0,"label":""}. Omitted keys default to true,10,"default". Supplied enabled is boolean, limit a nonnegative integer, label a string; null uses the default.
path: {"op":"path","root":"<absolute-directory>","name":"nested/file.txt"} -> normalized absolute nested path. The result must remain inside root; escaping names are rejected by throwing. The evaluator's independent consumer renders exceptions as ERROR.
framing: {"op":"framing","message":"hello"} -> a single JSON-line record with exactly the message string preserved, followed by one newline. Message can contain arbitrary quotes, backslashes, Unicode and embedded newlines.
The original CLI takes JSON text as its first positional argument. A requested --config option takes a UTF-8 JSON file path. The SDK is shared by both paths; malformed JSON or unreadable files require a nonzero CLI exit and concise diagnostic without content or stack traces.
''',
        'python': '''Public wire contract (evaluate accepts JSON text and returns JSON text):
batch: {"op":"batch","store":"<file-path>","events":[{"id":"original","amount":3}]} -> {"balance":3,"seen":["original"]}. Missing file begins with balance0/seen[]. Stored schema is exactly balance (integer) and seen (ordered event-ID string list). Amounts are nonnegative integers; negative amounts raise ValueError and must not corrupt committed state. Each event ID identifies one logical event across process restarts.
The optional event field fail_after:true raises RuntimeError immediately AFTER that event has been durably committed, before later events. Retrying the same ID without fail_after must not apply that committed event twice. Preserve prior committed events and their order.
redact: {"op":"redact","data":{"user":"Ada","password":"private","nested":{"token":"private","safe":4}}} returns structured diagnostic JSON. Credential values under password/token/api_key must never be emitted at any nested list/dictionary depth. Removing keys or replacing values is allowed; preserve nonsensitive values/structure.
The original CLI takes JSON text as its first positional argument. Independent consumers render raised exceptions as ERROR; this sentinel is an evaluator presentation, not a required exception message.
''',
        'cpp': '''Public wire contract: evaluate consumes a space-delimited operation string and returns text.
bounds INDEX: INDEX is signed; the existing collection is [10,20,30]. Valid indexes0..2 return the exact value text. Invalid indexes throw a standard exception; the public adapter renders ERROR.
total N...: signed64-bit integers; each partial total is within signed64-bit. Return the exact decimal total. Empty total is0.
capacity CAP N...: nonnegative capacity and integer item sequence. Existing hit removes that prior occurrence then moves it to newest. Evict oldest to retain at most CAP entries. Return oldest-to-newest comma-separated integers; zero capacity returns empty text.
lookup COUNT QUERIES: COUNT>0 and QUERIES>=0. Existing sorted keys are0,2,...,2*(COUNT-1); queryi targets i%COUNT. Return signed64-bit sum of first matching indexes; missing keys contribute0. Repeated queries preserve results.
The original CLI takes the operation string as its first argument and prints returned text. Keep evaluate(const std::string&)->std::string compatible for other consumers.
''',
    }
    common['CONTRACT.md']=contracts[lang]
    scenario = case.get('scenario')
    if scenario == 'atomic':
        common['CONTRACT.md'] += ('When present, fail_after must be a JSON boolean. A non-boolean value raises ValueError during '
                                  'batch validation and leaves the store unchanged. False behaves like omission.\n')
    if scenario == 'month-report':
        common['CONTRACT.md'] = MONTHLY_REPORT_CONTRACT
    if tools:
        common['RUNTIME.md']+='Pinned executable paths: '+json.dumps({key:tools[key] for key in ['python','node','dotnet','cxx'] if tools.get(key)},sort_keys=True)+'\n'
    smoke = {
        'python': "text=json.dumps({'op':'batch','store':str(Path(temp)/'state.json'),'events':[{'id':'original','amount':3}]}); args=[sys.executable,'cli.py',text]; expected={'balance':3,'seen':['original']}",
        'typescript': "args=['node','--experimental-strip-types','cli.ts',json.dumps({'op':'limit'})]; expected={'limit':10}",
        'csharp': f"args=[{str(tools.get('dotnet') or 'dotnet')!r},'run','--project','Existing.csproj','--verbosity','quiet','--',json.dumps({{'op':'refund','age':2,'window':30}})]; expected=True",
        'cpp': "build=Path('.runtime-proof');build.mkdir(exist_ok=True); binary=build/('existing.exe' if os.name=='nt' else 'existing'); compiler=shutil.which('cl') if os.name=='nt' else (shutil.which('c++') or shutil.which('g++')); command=[compiler,'/nologo','/std:c++17','/EHsc','main.cpp','/Fo:'+str(build/'main.obj'),'/Fe:'+str(binary)] if os.name=='nt' else [compiler,'-std=c++17','main.cpp','-o',str(binary)];subprocess.run(command,check=True,capture_output=True);args=[str(binary.resolve()),'total 1 2 3'];expected=6",
    }[lang]
    if scenario == 'month-report':
        smoke = ("ledger=Path(temp)/'ledger.json'; "
                 "ledger.write_text(json.dumps([{'id':'old','recorded_at':'2025-03-16T14:01:00Z','amount_cents':12}])); "
                 "args=[sys.executable,'cli.py',json.dumps({'op':'month','ledger':str(ledger),'month':'2025-03'})]; "
                 "expected={'ids':['old'],'total_cents':12}")
    common['check_existing.py']='import json,os,shutil,subprocess,sys,tempfile\nfrom pathlib import Path\nscratch = Path(".runtime-proof/scratch")\nscratch.mkdir(parents=True, exist_ok=True)\nwith tempfile.TemporaryDirectory(dir=scratch) as temp:\n    '+smoke+'\n    result=subprocess.run(args,capture_output=True,text=True,check=True);lines=result.stdout.strip().splitlines();actual=json.loads(lines[-1]);assert actual==expected,(actual,expected);print("Existing public behavior checked")\n'
    if case.get('scenario')=='lookup':
        common['PERFORMANCE.md']='For lookup30000 sorted keys and20000 queries, preserve exact results and reduce median command wall time to at most70% of the unchanged baseline on the same machine/compiler/options. Use one warmup and five measurements per version; retain raw values and noise.\n'
    if lang == "python":
        if scenario == 'month-report':
            return {**common, 'rules.py': MONTHLY_REPORT_SOURCE,
                    'cli.py': 'from rules import evaluate\nimport sys\nprint(evaluate(sys.argv[1]))\n'}
        core = '''import json\nfrom pathlib import Path\n\ndef evaluate(text):\n    x = json.loads(text)\n    if x['op'] == 'redact':\n        return json.dumps(x['data'], sort_keys=True)\n    p = Path(x['store'])\n    state = json.loads(p.read_text()) if p.exists() else {'balance': 0, 'seen': []}\n    for event in x['events']:\n        state['balance'] += event['amount']\n        if event['amount'] < 0:\n            raise ValueError('negative amount')\n        state['seen'].append(event['id'])\n        p.write_text(json.dumps(state, sort_keys=True))\n        if event.get('fail_after'):\n            raise RuntimeError('injected interruption')\n    return json.dumps(state, sort_keys=True)\n'''
        return {**common, "rules.py": core, "cli.py": "from rules import evaluate\nimport sys\nprint(evaluate(sys.argv[1]))\n"}
    if lang == "typescript":
        core = '''import path from 'node:path';\nexport function evaluate(text: string): string {\n  const x = JSON.parse(text);\n  if (x.op === 'limit') return JSON.stringify({limit: x.limit || 10});\n  if (x.op === 'config') return JSON.stringify({enabled: x.enabled || true, limit: x.limit || 10, label: x.label || 'default'});\n  if (x.op === 'path') {\n    const p = path.resolve(x.root, x.name);\n    if (!p.startsWith(path.resolve(x.root))) throw new Error('outside root');\n    return p;\n  }\n  if (x.op === 'framing') return '{"message":"' + x.message + '"}\\n';\n  throw new Error('unsupported operation');\n}\n'''
        return {**common, "rules.ts": core, "cli.ts": "import { evaluate } from './rules.ts';\nconsole.log(evaluate(process.argv[2]));\n", "package.json": '{"type":"module","private":true}\n'}
    if lang == "csharp":
        core = '''using System;\nusing System.Text.Json;\npublic static class Rules {\n public static string Evaluate(string text) {\n  using var d = JsonDocument.Parse(text); var x = d.RootElement; string op=x.GetProperty("op").GetString()!;\n  if(op=="refund") return (x.GetProperty("age").GetInt32()<x.GetProperty("window").GetInt32()).ToString().ToLowerInvariant();\n  if(op=="tenant") { foreach(var a in x.GetProperty("accounts").EnumerateArray()) if(a.GetProperty("id").GetString()==x.GetProperty("id").GetString()) return a.GetProperty("balance").GetRawText(); return "null"; }\n  long left=x.GetProperty("left").GetInt64(), amount=x.GetProperty("amount").GetInt64();\n  if(op=="credit") return JsonSerializer.Serialize(new {balance=left+amount,accepted=true});\n  long right=x.GetProperty("right").GetInt64(); left-=amount;\n  if(left<0) return JsonSerializer.Serialize(new {left,right,accepted=false});\n  return JsonSerializer.Serialize(new {left,right=right+amount,accepted=true});\n }\n}\n'''
        project = '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable></PropertyGroup></Project>\n'
        return {**common, "Rules.cs": core, "Program.cs": "Console.WriteLine(Rules.Evaluate(args[0]));\n", "Existing.csproj": project}
    core = r'''#pragma once
#include <algorithm>
#include <cstdint>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
inline std::string evaluate(const std::string& input) {
 std::istringstream in(input); std::string op; in>>op;
 if(op=="bounds") {long long index; in>>index; std::vector<int> v{10,20,30}; return std::to_string(v[static_cast<std::size_t>(index)%v.size()]);}
 if(op=="total") {int sum=0; long long n; while(in>>n) sum+=static_cast<int>(n); return std::to_string(sum);}
 if(op=="capacity") {int cap;in>>cap;std::vector<int> cache;int value;while(in>>value){auto p=std::find(cache.begin(),cache.end(),value);if(p!=cache.end())cache.erase(p);cache.push_back(value);if(cap>0&&cache.size()>static_cast<std::size_t>(cap))cache.erase(cache.begin());}std::string out;for(int n:cache){if(!out.empty())out+=",";out+=std::to_string(n);}return out;}
 if(op=="lookup") {int count,queries;in>>count>>queries;std::vector<int> keys;for(int i=0;i<count;i++)keys.push_back(i*2);std::int64_t sum=0;for(int i=0;i<queries;i++){int target=i%count;auto p=std::find(keys.begin(),keys.end(),target);if(p!=keys.end())sum+=std::distance(keys.begin(),p);}return std::to_string(sum);}
 throw std::invalid_argument("unsupported operation");
}
'''
    return {**common, "rules.hpp": core, "main.cpp": '#include "rules.hpp"\n#include <iostream>\nint main(int argc,char**argv){try{std::cout<<evaluate(argv[1])<<"\\n";}catch(const std::exception&){std::cout<<"ERROR\\n";}}\n'}


def pin_settings(workspace, arm, model):
    # Only this synthetic repository changes. User settings, HOME, credentials,
    # hooks and managed policy are never modified or copied.
    save(workspace / ".github/copilot/settings.local.json", {
        "disabledSkills": ["harrtest"] if arm == "plain" else [], "model": model})


def configuration_inputs(workspace):
    """Hash benchmark controls without retaining configuration contents/secrets."""
    workspace=Path(workspace).resolve();result={}
    package = workspace / '.github/skills/harrtest'
    for name in ('.github','.agents','.claude'):
        root=workspace/name
        if root.exists():
            for path in root.rglob('*'):
                if path.is_file() and not package_bytecode(path, package):
                    result[str(path)] = sha(path)
    home=Path.home()
    for root in (home/'.copilot',home/'.agents',home/'.claude'):
        names=['settings.json','copilot-instructions.md','mcp-config.json','permissions-config.json'] if root.name=='.copilot' else ['settings.json']
        for name in names:
            path=root/name;result[str(path)]=sha(path) if path.is_file() else None
        for directory in ('hooks','instructions'):
            path=root/directory
            if path.is_dir():
                for f in path.rglob('*'):
                    if f.is_file():result[str(f)]=sha(f)
        skills=root/'skills'
        if skills.is_dir():
            for f in skills.glob('*/SKILL.md'):
                if f.is_file():result[str(f)]=sha(f)
    return result


def validate_generation_inputs(before, after, outcome):
    outcome['configuration_inputs_before']=before
    outcome['configuration_inputs_after']=after
    changes=[p for p in sorted(set(before)|set(after)) if before.get(p)!=after.get(p)]
    outcome['configuration_drift']=changes
    if changes:
        outcome['status']='INVALID'
        outcome['reason']='Benchmark policy, instruction or skill inputs changed during generation'
    return outcome


def parent_identity_matches(requested, session_record, headers, workspace):
    try:
        uuid.UUID(requested)
        return (bool(headers) and requested==session_record.get('id')==headers[0].get('sessionId')
                and Path(headers[0]['context']['cwd']).resolve()==Path(workspace).resolve())
    except (ValueError,TypeError,KeyError):return False


def reasoning_pin_observation(events, expected='low'):
    """Track authoritative effort by actual actor; nullable call metadata is not a reset."""
    headers=[r['data'] for r in events if r.get('type')=='session.start' and not r.get('agentId')]
    parent=headers[0].get('sessionId') if headers else 'unknown-parent'
    states={parent:None};mismatches=[];missing=[]
    for row in events:
        kind=row.get('type');data=row.get('data',{});actor=row.get('agentId') or parent
        if kind=='subagent.started':states.setdefault(actor,None)
        if kind in {'session.start','subagent.configured','session.model_change'}:
            effort=data.get('reasoningEffort')
            states[actor]=effort if isinstance(effort,str) else None
            if isinstance(effort,str) and effort!=expected:
                mismatches.append({'actor':actor,'event':kind,'effort':effort})
        elif kind in {'model.call_start','model.model_call_started'} and states.get(actor) is None:
            missing.append({'actor':actor,'event':kind,'reason':'No current authoritative effort for this actor'})
    missing.extend({'actor':actor,'reason':'Final authoritative effort is unknown'} for actor,value in states.items() if value is None)
    return {'status':'FAIL' if mismatches else 'UNVERIFIED' if missing else 'PASS',
            'expected':expected,'actors':states,'mismatches':mismatches,'missing':missing}


def balanced_execution_order(rows, models, seed):
    blocks=[{'case':row['id'],'model':model,'repetition':repeat}
            for row in rows if row['split']=='acceptance' for model in models for repeat in (1,2)]
    random.Random(seed).shuffle(blocks)
    order=[]
    for index,block in enumerate(blocks):
        arms=list(ARMS[index%len(ARMS):]+ARMS[:index%len(ARMS)])
        order.extend({**block,'block':index,'arm':arm} for arm in arms)
    return order


@contextmanager
def exclusive_runtime(experiment):
    """OS-owned lock released on process exit, with no stale-lock deletion."""
    path=Path(experiment)/'runtime.lock'
    with path.open('a+b') as handle:
        if handle.tell()==0:handle.write(b'0');handle.flush()
        handle.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except (OSError,BlockingIOError) as exc:
            raise ValueError('Another generation/evaluation owns the experiment runtime') from exc
        try:yield
        finally:
            handle.seek(0)
            if os.name=='nt':msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(handle.fileno(),fcntl.LOCK_UN)


def next_execution(experiment, plan):
    for item in plan['execution_order']:
        attempt=Path(experiment)/'attempts'/f'{item["case"]}--{item["arm"]}--{plan["models"].index(item["model"])}--{item["repetition"]}'
        if not (attempt/'generation.json').is_file():return {'action':'generate','attempt':str(attempt),**item}
        if not (attempt/'latest-evaluation.json').is_file():return {'action':'evaluate','attempt':str(attempt),**item}
    return {'action':'complete','scope':'All96 generation outcomes and executable evaluations retained; independent quality reviews may remain.'}


def prepare(experiment, case_id, arm, model, repetition):
    experiment, plan = frozen(experiment)
    if arm not in ARMS or model not in plan["models"] or repetition not in (1, 2):
        raise ValueError("Attempt is outside the declared matrix")
    case = next((r for r in plan["cases"] if r["id"] == case_id), None)
    if not case:
        raise ValueError("Unknown case")
    attempt = experiment / "attempts" / f'{case_id}--{arm}--{plan["models"].index(model)}--{repetition}'
    attempt.mkdir(parents=True, exist_ok=False)
    workspace = attempt / "work"
    workspace.mkdir()
    for rel, content in fixture(case, toolchain(plan)).items():
        (workspace / rel).write_text(content, encoding="utf-8")
    git = shutil.which("git")
    if not git:
        raise ValueError("Git is required for immutable baseline")
    for argv in ([git, "init", "--quiet"], [git, "add", "."],
                 [git, "-c", "user.name=HarrTest evaluator", "-c", "user.email=evaluator@invalid", "commit", "--quiet", "-m", "Frozen existing fixture"]):
        r = command(argv, workspace)
        if r["exit_code"]:
            raise ValueError("Could not establish fixture baseline: " + r["stderr"])
    baseline = tree(workspace)
    pin_settings(workspace, arm, model)
    if arm != "plain":
        shutil.copytree(experiment / "packages" / arm, workspace / ".github/skills/harrtest")
    prompt = case["request"] + "\nWork in the existing project. Preserve its documented contracts. RUNTIME.md gives the supplied toolchain profile. Run the actual checks relevant to your change and report observed outcomes and limitations."
    if arm != "plain":
        prompt = "$harrtest\n" + prompt
    save(attempt / "attempt.json", {"schema": 1, "id": attempt.name, "case": case,
         "arm": arm, "model": model, "repetition": repetition, "baseline": baseline,
         "protocol_sha256": digest(plan), "prompt": prompt, "created_unix": time.time()}, exclusive=True)
    return attempt


def skill_inventory(copilot, workspace):
    r = command([copilot, "skill", "list", "--json"], workspace, 30)
    if r["exit_code"]:
        return r, None
    try: return r, json.loads(r["stdout"])
    except ValueError: return r, None


def skill_isolation(inventory, workspace, arm):
    """Require observed enabled/disabled state and selected path, not settings alone."""
    matches = []
    def visit(x):
        if isinstance(x, dict):
            if x.get("name") == "harrtest": matches.append(x)
            for value in x.values(): visit(value)
        elif isinstance(x, list):
            for value in x: visit(value)
    visit(inventory)
    if arm == "plain":
        return bool(matches) and all(x.get("enabled") is False or x.get("disabled") is True for x in matches)
    expected = (Path(workspace) / ".github/skills/harrtest").resolve()
    for row in matches:
        if row.get("enabled") is False or row.get("disabled") is True:
            continue
        location = row.get("path") or row.get("directory") or row.get("location")
        if location:
            p = Path(location)
            if p.name == "SKILL.md": p = p.parent
            if p.resolve() == expected: return True
    return False


def toolchain(plan):
    return plan["preflight"]["tools"]


PYTHON_EXCEPTION_EXITS = {'VALUE_ERROR': 65, 'RUNTIME_ERROR': 66}


def build_program(workspace, output, lang, tools, *, python_typed_errors=False):
    output.mkdir(parents=True, exist_ok=False)
    if lang == "python":
        driver = output / "driver.py"
        error_handlers = "except Exception: print('ERROR')\n"
        if python_typed_errors:
            error_handlers = (
                f"except ValueError: print('VALUE_ERROR'); sys.exit({PYTHON_EXCEPTION_EXITS['VALUE_ERROR']})\n"
                f"except RuntimeError: print('RUNTIME_ERROR'); sys.exit({PYTHON_EXCEPTION_EXITS['RUNTIME_ERROR']})\n"
                + error_handlers
            )
        driver.write_text("import sys\nsys.path.insert(0, " + repr(str(workspace)) + ")\nfrom rules import evaluate\ntry: print(evaluate(sys.argv[1]))\n" + error_handlers, encoding="utf-8")
        return [tools["python"], str(driver)], []
    if lang == "typescript":
        driver = output / "driver.mjs"
        driver.write_text("import {evaluate} from " + json.dumps((workspace / "rules.ts").as_uri()) + ";\ntry {console.log(evaluate(process.argv[2]));} catch {console.log('ERROR');}\n", encoding="utf-8")
        typing={'role':'typecheck','exit_code':None,'stdout':'','stderr':'Pinned TypeScript compiler and Node declaration files unavailable','timed_out':False,'status':'UNVERIFIED'}
        if tools.get('tsc') and tools.get('node_types'):
            compiler=[tools['node'],tools['tsc']] if str(tools['tsc']).endswith('.js') else [tools['tsc']]
            sources=[str(p) for p in workspace.rglob('*.ts') if not any(part in SKIP for part in p.relative_to(workspace).parts)]
            typing=command([*compiler,'--noEmit','--strict','--skipLibCheck','--target','ES2022','--module','NodeNext','--moduleResolution','NodeNext','--allowImportingTsExtensions','--typeRoots',tools['node_types'],*sources],workspace,90)
            typing['role']='typecheck';typing['status']='PASS' if typing['exit_code']==0 else 'FAIL'
        return [tools["node"], "--experimental-strip-types", str(driver)], [typing]
    if lang == "csharp":
        for src in workspace.rglob('*.cs'):
            if src.name=='Program.cs' or any(part in SKIP for part in src.relative_to(workspace).parts):continue
            target=output/src.relative_to(workspace);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,target)
        (output / "Program.cs").write_text('try {Console.WriteLine(Rules.Evaluate(args[0]));} catch {Console.WriteLine("ERROR");}\n', encoding="utf-8")
        (output / "Evaluator.csproj").write_text(fixture({"language": "csharp"})["Existing.csproj"], encoding="utf-8")
        built = command([tools["dotnet"], "build", "--nologo", "-v:q", "-o", str(output / "app")], output, 150)
        return [tools["dotnet"], str(output / "app/Evaluator.dll")], [built]
    extra=[]
    for src in workspace.rglob('*'):
        if src.suffix not in {'.h','.hpp','.cpp'} or src.name=='main.cpp' or any(part in SKIP for part in src.relative_to(workspace).parts):continue
        target=output/src.relative_to(workspace);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,target)
        if src.suffix=='.cpp':extra.append(str(target))
    (output / "main.cpp").write_text(fixture({"language": "cpp"})["main.cpp"], encoding="utf-8")
    binary = output / ("evaluate.exe" if os.name == "nt" else "evaluate")
    if Path(tools["cxx"][0]).name.lower() in {"cl", "cl.exe"}:
        environment = msvc_environment(tools["msvc_env"]) if tools.get("msvc_env") else None
        built = command([*tools["cxx"], "/nologo", "/std:c++17", "/EHsc", "/O2",
                         "/Fe:" + str(binary), str(output / "main.cpp"), *extra], output, 150, env=environment)
    else:
        built = command([*tools["cxx"], "-std=c++17", "-O2", str(output / "main.cpp"), *extra, "-o", str(binary)], output, 150)
    return [str(binary)], [built]


def build_public_cli(workspace, output, lang, tools):
    """Exercise the real adapter in addition to the independently compiled API consumer."""
    if lang=='typescript':return [tools['node'],'--experimental-strip-types',str(workspace/'cli.ts')],[]
    output.mkdir(parents=True)
    for src in workspace.glob('*.cs'):shutil.copy2(src,output/src.name)
    shutil.copy2(workspace/'Existing.csproj',output/'Existing.csproj')
    built=command([tools['dotnet'],'build','--nologo','-v:q','-o',str(output/'app')],output,150)
    return [tools['dotnet'],str(output/'app/Existing.dll')],[built]


def test_vectors(case, sandbox):
    scenario = case["scenario"]
    def j(x): return json.dumps(x, separators=(",", ":"))
    if case["language"] == "csharp":
        ordinary = [(j({"op":"refund","age":2,"window":30}), "true"), (j({"op":"refund","age":31,"window":30}), "false")]
        if scenario == "refund": return ordinary, [(j({"op":"refund","age":30,"window":30}), "true"), (j({"op":"refund","age":0,"window":0}), "true")]
        if scenario == "tenant":
            accounts=[{"tenant":"A","id":"same","balance":8},{"tenant":"B","id":"same","balance":21}]
            return ordinary, [(j({"op":"tenant","tenant":"B","id":"same","accounts":accounts}), "21"), (j({"op":"tenant","tenant":"C","id":"same","accounts":accounts}), "null")]
        if scenario == "transfer":
            return ordinary + [(j({"op":"transfer","left":30,"right":4,"amount":6}), {"left":24,"right":10,"accepted":True})], [(j({"op":"transfer","left":3,"right":8,"amount":7}), {"left":3,"right":8,"accepted":False}), (j({"op":"transfer","left":3,"right":8,"amount":-1}), {"left":3,"right":8,"accepted":False}), (j({"op":"transfer_many","left":30,"right":4,"amounts":[6,5]}), {"left":19,"right":15,"accepted":True}), (j({"op":"transfer_many","left":10,"right":4,"amounts":[6,5]}), {"left":10,"right":4,"accepted":False}), (j({"op":"transfer_many","left":10,"right":4,"amounts":[1,-1]}), {"left":10,"right":4,"accepted":False})]
        return ordinary + [(j({"op":"credit","left":4,"amount":3}), {"balance":7,"accepted":True})], [(j({"op":"credit","left":4,"amount":n}), {"balance":4,"accepted":False}) for n in [0,-2,-999]]
    if case["language"] == "typescript":
        ordinary=[(j({"op":"limit"}),{"limit":10}),(j({"op":"limit","limit":3}),{"limit":3})]
        if scenario == "limit": return ordinary,[(j({"op":"limit","limit":0}),{"limit":0})]
        if scenario == "config": return ordinary,[(j({"op":"config","enabled":False,"limit":0,"label":""}),{"enabled":False,"limit":0,"label":""}),(j({"op":"config"}),{"enabled":True,"limit":10,"label":"default"})]
        if scenario == "framing": return ordinary,[(j({"op":"framing","message":s}),{"message":s}) for s in ['ordinary','quote"value','first\nsecond','\\','☃']]
        root=sandbox/'allowed';root.mkdir()
        return ordinary+[(j({"op":"path","root":str(root),"name":"nested/file.txt"}),str(root/'nested/file.txt'))],[(j({"op":"path","root":str(root),"name":"../allowed-neighbor/stolen"}),"ERROR"),(j({"op":"path","root":str(root),"name":"../outside"}),"ERROR")]
    if case["language"] == "cpp":
        ordinary=[("total 1 2 3", "6"),("bounds 1","20"),("capacity 2 1 2 3","2,3")]
        if scenario == "bounds": return ordinary,[("bounds -1","ERROR"),("bounds 3","ERROR"),("bounds 100000","ERROR")]
        if scenario == "total": return ordinary,[("total 2147483647 1","2147483648"),("total -2147483648 -1","-2147483649"),("total 4000000000 3000000000","7000000000")]
        if scenario == "capacity": return ordinary,[("capacity 0 1 2 3",""),("capacity 2 1 2 1","2,1"),("capacity 1 7 7 8","8")]
        # Exact reference result is calculated independently in Python.
        vectors=[]
        for n,q in [(10,25),(1,3),(30000,20000)]:
            expected=sum((i%n)//2 for i in range(q) if (i%n)%2==0)
            vectors.append((f"lookup {n} {q}",str(expected)))
        return ordinary,vectors
    # Persistent worker vectors are evaluated by a sequence below.
    return [], []


def parse_output(stdout):
    value = stdout.strip()
    try: return json.loads(value)
    except ValueError: return value


def same_value(actual, expected):
    """JSON value equality must not equate false with0 or true with1."""
    if type(actual) is not type(expected):return False
    if isinstance(expected,dict):return set(actual)==set(expected) and all(same_value(actual[k],v) for k,v in expected.items())
    if isinstance(expected,list):return len(actual)==len(expected) and all(same_value(a,b) for a,b in zip(actual,expected))
    return actual==expected


def nonsensitive_structure(value):
    """Ignore only permitted credential-value removal/replacement in the output.

    The expected nonsensitive structure is an independent literal oracle, not
    calculated by calling the implementation or by trusting its returned keys.
    Lists, empty containers, scalar values and scalar types remain observable.
    """
    if isinstance(value,dict):
        return {key:nonsensitive_structure(item) for key,item in value.items()
                if key not in {'password','token','api_key'}}
    if isinstance(value,list):return [nonsensitive_structure(item) for item in value]
    return value


def state_file_unchanged(check, path, original_sha256):
    check['input_file_sha256_before'] = original_sha256
    check['input_file_sha256_after'] = sha(path) if path.is_file() else None
    check['passed'] = check['passed'] and check['input_file_sha256_after'] == original_sha256


def check_monthly_report(exercise, evidence):
    initial = [
        {'id': 'first', 'recorded_at': '2025-03-08T12:00:00Z', 'amount_cents': 300},
        {'id': 'east', 'recorded_at': '2025-04-01T00:10:00+01:00', 'amount_cents': -40},
        {'id': 'west', 'recorded_at': '2025-03-31T23:45:00-02:00', 'amount_cents': 999},
        {'id': 'previous', 'recorded_at': '2025-02-28T22:00:00-03:30', 'amount_cents': 60},
    ]

    def report(label, entries, query, expected):
        ledger = evidence / f'{label}.json'
        ledger.write_text(json.dumps(entries), encoding='utf-8')
        before = sha(ledger)
        check = exercise(label, json.dumps({'ledger': str(ledger), **query}), expected)
        state_file_unchanged(check, ledger, before)

    report('preservation-entry-count', initial, {'op': 'entry_count'}, {'count': 4})
    report('preservation-empty-report', [], {'op': 'month', 'month': '2025-03'}, {'ids': [], 'total_cents': 0})
    report('utc-march-in-ledger-order', initial, {'op': 'month', 'month': '2025-03'},
           {'ids': ['first', 'east', 'previous'], 'total_cents': 320})
    report('utc-april-offset', initial, {'op': 'month', 'month': '2025-04'}, {'ids': ['west'], 'total_cents': 999})
    report('accept-valid-leap-day', [{'id': 'leap', 'recorded_at': '2024-02-29T23:00:00+00:00', 'amount_cents': -12}],
           {'op': 'month', 'month': '2024-02'}, {'ids': ['leap'], 'total_cents': -12})
    report('accept-first-supported-year', [{'id': 'first', 'recorded_at': '0001-01-01T00:00:00Z', 'amount_cents': 2}],
           {'op': 'month', 'month': '0001-01'}, {'ids': ['first'], 'total_cents': 2})
    report('accept-last-supported-year', [{'id': 'last', 'recorded_at': '9999-12-31T23:59:59Z', 'amount_cents': 3}],
           {'op': 'month', 'month': '9999-12'}, {'ids': ['last'], 'total_cents': 3})
    for label, month in [('month-out-of-range', '2025-13'), ('month-not-string', 202503),
                         ('month-shape', '2025-3'), ('month-year-zero', '0000-01')]:
        report(label, initial, {'op': 'month', 'month': month}, 'VALUE_ERROR')
    report('month-missing', initial, {'op': 'month'}, 'VALUE_ERROR')
    invalid = [('timestamp-naive', '2025-02-18T12:00:00'), ('timestamp-offset', '2025-02-18T12:00:00+00:99'),
               ('timestamp-calendar', '2025-02-29T12:00:00Z'), ('timestamp-not-string', 1),
               ('timestamp-year-zero', '0000-01-01T00:00:00Z'),
               ('timestamp-utc-underflow', '0001-01-01T00:00:00+01:00'),
               ('timestamp-utc-overflow', '9999-12-31T23:59:59-00:01')]
    for label, recorded_at in invalid:
        report(label, [initial[0], {'id': 'invalid', 'amount_cents': 3, 'recorded_at': recorded_at}],
               {'op': 'month', 'month': '2025-03'}, 'VALUE_ERROR')
    unparseable = [initial[0], {'id': 'missing', 'amount_cents': 3}]
    report('timestamp-missing', unparseable, {'op': 'month', 'month': '2025-03'}, 'VALUE_ERROR')
    report('preservation-count-does-not-parse-timestamps', unparseable, {'op': 'entry_count'}, {'count': 2})


def check_typed_batch_control(exercise, evidence):
    # Independent store copies ensure each malformed value follows a valid prefix.
    initial = b'{"balance":3,"seen":["old"]}'
    for label, invalid in [('string', 'false'), ('integer', 0), ('null', None)]:
        store = evidence / f'control-field-{label}.json'
        store.write_bytes(initial)
        before = sha(store)
        request = {'op': 'batch', 'store': str(store), 'events': [
            {'id': 'prefix', 'amount': 2}, {'id': 'final', 'amount': 7, 'fail_after': invalid}]}
        check = exercise(f'control-field-{label}', json.dumps(request), 'VALUE_ERROR')
        state_file_unchanged(check, store, before)
    store = evidence / 'control-field-false.json'
    exercise('control-field-false-is-valid', json.dumps({'op': 'batch', 'store': str(store),
             'events': [{'id': 'first', 'amount': 5, 'fail_after': False}]}), {'balance': 5, 'seen': ['first']})
    store = evidence / 'control-field-true.json'
    store.write_bytes(initial)
    request = {'op': 'batch', 'store': str(store), 'events': [
        {'id': 'prefix', 'amount': 2}, {'id': 'flagged', 'amount': 7, 'fail_after': True},
        {'id': 'unreached', 'amount': 11}]}
    check = exercise('control-field-true-commits-then-interrupts', json.dumps(request), 'RUNTIME_ERROR')
    committed_bytes = store.read_bytes() if store.is_file() else b''
    committed_state = parse_output(committed_bytes.decode('utf-8', errors='replace'))
    expected_state = {'balance': 12, 'seen': ['old', 'prefix', 'flagged']}
    check.update(persisted_expected=expected_state, persisted_observed=committed_state,
                 persisted_sha256=hashlib.sha256(committed_bytes).hexdigest() if committed_bytes else None)
    check['passed'] = check['passed'] and same_value(committed_state, expected_state)


def report_security_checks(checks, scope):
    rejected = [check for check in checks if check.get('expected') == 'VALUE_ERROR']
    ledger_reads = [check for check in checks if 'input_file_sha256_before' in check]
    ledger_intact = all(check['input_file_sha256_before'] == check['input_file_sha256_after'] for check in ledger_reads)
    passed = bool(rejected and ledger_reads) and all(check['passed'] for check in rejected) and ledger_intact
    return {'status': 'PASS' if passed else 'FAIL', 'scope': scope,
            'rejection_checks': [check['check'] for check in rejected],
            'integrity_checks': [check['check'] for check in ledger_reads]}


def evaluate_attempt(attempt):
    attempt = Path(attempt).resolve()
    experiment, plan = frozen(attempt.parents[1])
    with exclusive_runtime(experiment):
        if plan.get('kind') == 'acceptance':
            expected = next_execution(experiment, plan)
            if expected['action'] != 'evaluate' or Path(expected['attempt']) != attempt:
                raise ValueError('Follow the frozen interleaved execution order; next action: ' + json.dumps(expected))
            generation = load(attempt / 'generation.json')
            if not isinstance(generation, dict) or generation.get('status') not in GENERATION_OUTCOMES:
                raise ValueError('Retained generation outcome required before acceptance evaluation')
        return _evaluate_attempt(attempt)


def _evaluate_attempt(attempt):
    started = time.monotonic()
    attempt = Path(attempt).resolve()
    experiment, plan = frozen(attempt.parents[1])
    meta = load(attempt / "attempt.json")
    workspace = attempt / "work"
    before = tree(workspace)
    evidence = attempt / ("evaluation-" + uuid.uuid4().hex)
    evidence.mkdir()
    case = meta['case']
    scenario = case['scenario']
    invocation, builds = build_program(workspace, evidence / "build", case['language'], toolchain(plan),
                                       python_typed_errors=scenario in {'atomic', 'month-report'})
    checks = []
    performance = {'status':'UNVERIFIED','reason':'Independent applicability review/measurement required for non-benchmark-critical performance.'}
    build_ok = all(x["exit_code"] == 0 and not x["timed_out"] for x in builds if x.get('role')!='typecheck')
    typecheck=next((x for x in builds if x.get('role')=='typecheck'),None)
    def exercise(label, text, expected):
        raw = command([*invocation,text], evidence, 20)
        observed = raw["stdout"].strip() if isinstance(expected, str) else parse_output(raw["stdout"])
        exit_code = PYTHON_EXCEPTION_EXITS.get(expected, 0) if isinstance(expected, str) else 0
        check = {"check":label,"input":text,"expected":expected,"observed":observed,"execution":raw,
                 "passed":raw["exit_code"]==exit_code and not raw["timed_out"] and same_value(observed,expected)}
        checks.append(check)
        return check
    if build_ok:
        if scenario == 'month-report':
            check_monthly_report(exercise, evidence)
        elif case["language"] == "python":
            store=evidence/'state.json'
            def event(events,expected,label): exercise(label,json.dumps({"op":"batch","store":str(store),"events":events}),expected)
            event([{"id":"old","amount":3}],{"balance":3,"seen":["old"]},"ordinary-persistence")
            if scenario=='redact':
                text=json.dumps({'op':'redact','data':{'user':'Ada','password':'secret-A','nested':{'token':'secret-B','safe':4},
                    'items':[{'api_key':'secret-C','label':'invoice','active':False,'count':0},
                             {'safe':[None,{'note':'kept','token':'secret-D'}]}],'empty':[]}})
                expected={'user':'Ada','nested':{'safe':4},
                          'items':[{'label':'invoice','active':False,'count':0},{'safe':[None,{'note':'kept'}]}],
                          'empty':[]}
                raw=command([*invocation,text],evidence,20);observed=parse_output(raw['stdout'])
                safe=(same_value(nonsensitive_structure(observed),expected)
                      and all(s not in raw['stdout']+raw['stderr'] for s in ['secret-A','secret-B','secret-C','secret-D']))
                checks.append({'check':'nested-secret','execution':raw,'observed':observed,
                               'expected_nonsensitive_structure':expected,
                               'oracle':'No nested credential value emitted; every nonsensitive value, scalar type, list position and container shape matches the independent literal. Credential keys may be removed or their values replaced.',
                               'passed':raw['exit_code']==0 and safe})
            elif scenario=='dedupe': event([{'id':'old','amount':3}],{'balance':3,'seen':['old']},'duplicate-after-process-restart')
            elif scenario=='retry':
                event([{'id':'new','amount':5,'fail_after':True}],'ERROR','partial-interruption')
                event([{'id':'new','amount':5},{'id':'last','amount':2}],{'balance':10,'seen':['old','new','last']},'retry-after-committed-prefix')
            else:
                event([{'id':'good','amount':5},{'id':'bad','amount':-2}],'VALUE_ERROR','invalid-batch')
                exercise('state-unchanged',json.dumps({'op':'batch','store':str(store),'events':[]}),{'balance':3,'seen':['old']})
                check_typed_batch_control(exercise, evidence)
        else:
            ordinary,target=test_vectors(case,evidence)
            for i,(text,expected) in enumerate(ordinary): exercise('preservation-'+str(i),text,expected)
            for i,(text,expected) in enumerate(target): exercise('target-'+str(i),text,expected)
            if case['scenario'] in {'config','transfer'}:
                public,public_build=build_public_cli(workspace,evidence/'public-cli',case['language'],toolchain(plan))
                builds.extend(public_build)
                if all(x['exit_code']==0 for x in public_build):
                    option='--config' if case['scenario']=='config' else '--input-file'
                    inp={'op':'config','enabled':False,'limit':0,'label':''} if case['scenario']=='config' else {'op':'transfer_many','left':30,'right':4,'amounts':[6,5]}
                    expected={'enabled':False,'limit':0,'label':''} if case['scenario']=='config' else {'left':19,'right':15,'accepted':True}
                    input_file=evidence/'public-input.json';input_file.write_text(json.dumps(inp),encoding='utf-8')
                    raw=command([*public,option,str(input_file)],workspace,20)
                    observed=parse_output(raw['stdout'])
                    checks.append({'check':'public-file-adapter','expected':expected,'observed':observed,'execution':raw,'passed':raw['exit_code']==0 and same_value(observed,expected)})
                    text=ordinary[0][0];raw=command([*public,text],workspace,20)
                    observed=raw['stdout'].strip() if isinstance(ordinary[0][1],str) else parse_output(raw['stdout'])
                    checks.append({'check':'public-positional-preserved','expected':ordinary[0][1],'observed':observed,'execution':raw,'passed':raw['exit_code']==0 and same_value(observed,ordinary[0][1])})
                    sentinel='PRIVATE_INVALID_INPUT_7491';input_file.write_text('{'+sentinel,encoding='utf-8')
                    raw=command([*public,option,str(input_file)],workspace,20)
                    output=raw['stdout']+raw['stderr']
                    checks.append({'check':'public-malformed-no-leak','execution':raw,'passed':raw['exit_code'] not in {0,None} and sentinel not in output and len(output)<1200 and not re.search(r'(?m)^\s+at |Traceback|Unhandled exception|\nfile://',output)})
                    raw=command([*public,option,str(evidence/'missing.json')],workspace,20)
                    output=raw['stdout']+raw['stderr']
                    checks.append({'check':'public-missing-no-stack','execution':raw,'passed':raw['exit_code'] not in {0,None} and len(output)<1200 and not re.search(r'(?m)^\s+at |Traceback|Unhandled exception|\nfile://',output)})
                else:checks.append({'check':'public-cli-build','passed':False})
            if case.get('scenario')=='lookup':
                baseline_work=evidence/'baseline-work';baseline_work.mkdir()
                for rel,content in fixture(case, toolchain(plan)).items():(baseline_work/rel).write_text(content,encoding='utf-8')
                if tree(baseline_work)!=meta['baseline']:
                    raise ValueError('Performance baseline fixture differs from declared original source')
                old_invocation,old_builds=build_program(baseline_work,evidence/'baseline-build','cpp',toolchain(plan))
                builds.extend(old_builds)
                if all(x['exit_code']==0 for x in old_builds):
                    workload='lookup 30000 20000'
                    baseline_runs=[];candidate_runs=[]
                    for cmd,out in [(old_invocation,baseline_runs),(invocation,candidate_runs)]:
                        command([*cmd,workload],evidence,20)
                        for _ in range(5):out.append(command([*cmd,workload],evidence,20))
                    valid=all(x['exit_code']==0 and not x['timed_out'] for x in baseline_runs+candidate_runs)
                    ratio=statistics.median(x['seconds'] for x in candidate_runs)/statistics.median(x['seconds'] for x in baseline_runs) if valid else None
                    threshold=case['performance_max_ratio']
                    passed=valid and ratio<=threshold
                    performance={'status':'PASS' if passed else 'FAIL','baseline':baseline_runs,'candidate':candidate_runs,'median_ratio':ratio,'maximum_ratio':threshold,'warmup_per_version':1,'measured_repetitions':5,'workload':workload,'scope':'External process wall time, same machine/compiler/options; raw variation retained'}
                    checks.append({'check':'performance-relative','passed':passed,'expected_max_ratio':threshold,'observed_ratio':ratio})
                else:performance={'status':'UNVERIFIED','reason':'Baseline compiler failed'}
    replay = replay_original_checks(workspace, evidence, meta, toolchain(plan), before)
    checks.append(replay)
    after=tree(workspace)
    baseline=meta['baseline']
    allowed={'rules.py','rules.ts','Rules.cs','rules.hpp'}
    allowed.add('check_existing.py')
    if meta['case']['scenario']=='config':allowed.add('cli.ts')
    if meta['case']['scenario']=='transfer':allowed.add('Program.cs')
    protected=[r for r in baseline if r not in allowed]
    architecture=all(before.get(r)==baseline[r] for r in protected)
    test_path=workspace/'check_existing.py'
    tests_changed=before.get('check_existing.py')!=baseline.get('check_existing.py')
    # Existing tests may legitimately grow or be refactored. Their byte hash
    # is evidence of change, not a quality verdict. Retain only a minimal
    # executable assertion check here; independent review must assess oracle
    # preservation when tests change.
    try:
        nodes=ast.walk(ast.parse(test_path.read_text(encoding='utf-8-sig')))
        tests_have_observable_assertion=any(isinstance(n,ast.Assert) and isinstance(n.test,ast.Compare)
                                            and not all(isinstance(x,ast.Constant) for x in [n.test.left,*n.test.comparators])
                                            for n in nodes)
    except (OSError,SyntaxError):tests_have_observable_assertion=False
    architecture=architecture and tests_have_observable_assertion
    if meta['case']['language']=='typescript':
        architecture=architecture and typecheck is not None and typecheck.get('status')=='PASS'
    changed=[r for r in sorted(set(before)|set(baseline)) if before.get(r)!=baseline.get(r)]
    functionality=build_ok and bool(checks) and all(x['passed'] for x in checks)
    preservation=[x for x in checks if x['check'].startswith('preservation') or x['check'] in {'ordinary-persistence','public-positional-preserved'}]
    targeted=[x for x in checks if x not in preservation]
    security_relevant=scenario in {'tenant','path','redact','framing','credit','transfer','atomic','bounds'}
    resilience_relevant=scenario in {'dedupe','retry','atomic','transfer'}
    security = {'status': ('PASS' if targeted and all(x['passed'] for x in targeted) else 'FAIL') if security_relevant else 'NOT_APPLICABLE',
                'scope': 'Only case-specific isolation, input validation, framing, disclosure or bounds behavior; no general security certification.'}
    if case.get('security_scope'):
        security = report_security_checks(checks, case['security_scope'])
    layers={
        'functionality':{'status':'PASS' if functionality else 'FAIL','scope':'Independent public-API/CLI cases listed below; not all conceivable inputs.'},
        'preservation':{'status':'UNVERIFIED' if replay['status']=='UNVERIFIED' else 'PASS' if all(x['passed'] for x in preservation) else 'FAIL','checks':[x['check'] for x in preservation]},
        'architecture':{'status':'PASS' if architecture else 'FAIL','scope':'Frozen documented contract, build/dependency files and existing tests preserved; independent API consumer compiles/runs. Semantic architecture/clean-code review remains separate.'},
        'security':security,
        'performance':performance if scenario=='lookup' else {'status':'NOT_APPLICABLE','reason':'This frozen case declares no measured performance change; independent applicability review still required.'},
        'resilience':{'status':('PASS' if targeted and all(x['passed'] for x in targeted) else 'FAIL') if resilience_relevant else 'NOT_APPLICABLE','scope':'Only the declared state, interruption, replay or atomicity behaviors.'},
    }
    result={'schema':1,'attempt':meta['id'],'case':meta['case']['id'],'arm':meta['arm'],'model':meta['model'],
            'builds':builds,'checks':checks,'source_before':before,'source_after':after,'unchanged_by_evaluator':before==after,
            'changed_files':changed,'documented_contract_and_adapter_preserved':architecture,
            'existing_tests_changed':tests_changed,'existing_tests_have_observable_assertion':tests_have_observable_assertion,
            'type_correctness':typecheck.get('status') if typecheck else 'NOT_APPLICABLE',
            'test_oracle_preservation':'Independent semantic review required for changed tests' if tests_changed else 'Original test source unchanged',
            'functional_passed':functionality,'automated_artifact_layers':layers,
            'automated_artifact_passed':functionality and architecture and before==after and all(row['status'] in {'PASS','NOT_APPLICABLE'} for row in layers.values()),
            'performance':performance,'evaluation_seconds':time.monotonic()-started,
            'attribution':'Not inferred from output correctness; inspect retained native Copilot JSONL independently',
            'complete_quality_passed':False,'quality_status':'UNVERIFIED','evidence_directory':str(evidence)}
    # Functional truth is useful but cannot silently stand in for all six layers.
    save(evidence/'result.json',result)
    save(attempt/'latest-evaluation.json',{'path':str((evidence/'result.json').relative_to(attempt)),'sha256':sha(evidence/'result.json')})
    return result


TASK_PIN_HOOK = r'''
const recognizedEfforts = new Set(['none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max']);
function pinNativeTaskArguments(input, pins, audit) {
  const args = input.toolArgs;
  if (input.toolName !== 'task' || !args || typeof args !== 'object' || Array.isArray(args)) return;
  const modifiedArgs = {...args};
  const overrides = {};
  const fields = [
    ['model', pins.model, pins.models],
    ['reasoning_effort', pins.effort, recognizedEfforts],
  ];
  for (const [field, pinned, known] of fields) {
    if (!Object.hasOwn(args, field) || args[field] === pinned) continue;
    overrides[field] = {requested: known.has(args[field]) ? args[field] : '[unrecognized]', applied: pinned};
    modifiedArgs[field] = pinned;
  }
  if (!Object.keys(overrides).length) return;
  audit({tool: 'task', toolCallId: input.toolCallId ?? null, overrides});
  return {modifiedArgs};
}
'''


SDK_DRIVER = r'''import fs from 'node:fs';
import {pathToFileURL} from 'node:url';
import path from 'node:path';
''' + TASK_PIN_HOOK + r'''
const c=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const {CopilotClient,RuntimeConnection}=await import(pathToFileURL(c.sdk).href);
const client=new CopilotClient({mode:'copilot-cli',workingDirectory:c.workspace,
 env:{...process.env,HARRTEST_PARENT_SESSION_ID:c.sessionId},
 connection:RuntimeConnection.forStdio({path:c.runtime[0],args:[...c.runtime.slice(1),'--no-auto-update']})});
const write=(name,value)=>fs.writeFileSync(c.output+'/'+name,JSON.stringify(value,null,2));
const contained=(value,root)=>{const p=path.resolve(c.workspace,value);const r=path.resolve(root);return p===r||p.startsWith(r+path.sep);};
const permission=(request,invocation)=>{
 if(request.managedApprovalRequired||invocation.managedSettingsEnabled)return {kind:'no-result'};
 let allowed=false;
 const readable=p=>contained(p,c.workspace)||(c.readRoots||[]).some(r=>contained(p,r))||(c.exactReadFiles||[]).some(f=>path.resolve(c.workspace,p)===path.resolve(f));
 if(request.kind==='read')allowed=!!request.path&&readable(request.path);
 if(request.kind==='write'){
  const files=[request.fileName,...(request.fileEdits||[]).flatMap(x=>[x.before?.path,x.after?.path])].filter(Boolean);
  allowed=files.length>0&&files.every(p=>contained(p,c.workspace)&&!contained(p,c.workspace+'/.github/skills')&&!contained(p,c.workspace+'/.github/copilot'));
 }
 if(request.kind==='shell'){
  const text=request.fullCommandText||'';
  const paths=request.possiblePaths||[];
  allowed=paths.every(p=>readable(typeof p==='string'?p:p.path||''))&&
   !/(?:\.copilot|\.ssh|credential|git\s+push|--global|Invoke-WebRequest|curl\s|wget\s)/i.test(text);
 }
 fs.appendFileSync(c.output+'/permission-decisions.jsonl',JSON.stringify({kind:request.kind,allowed,toolCallId:request.toolCallId})+'\n');
 return allowed?{kind:'approve-once'}:{kind:'reject',feedback:'Outside this benchmark permission scope; use only the project, selected skill and supplied toolchain.'};
};
let session;let header;let headerResolve;
const nativeHeaderReady=new Promise(resolve=>{headerResolve=resolve;});
try {
 await client.start();
 const models=await client.listModels();write('models-observed.json',models);
 if(!models.some(m=>m.id===c.model))throw new Error('Pinned model not in authenticated catalog');
 const taskPins={model:c.model,effort:c.effort,models:new Set(models.map(m=>m.id))};
 const taskPinAudit=row=>fs.appendFileSync(c.output+'/task-pin-overrides.jsonl',JSON.stringify(row)+'\n');
 session=await client.createSession({sessionId:c.sessionId,model:c.model,allowedModels:[c.model],reasoningEffort:c.effort,workingDirectory:c.workspace,
 enableConfigDiscovery:true,enableFileHooks:true,enableHostGitOperations:true,enableSkills:true,
 trustWorkingDirectory:'session',disabledSkills:c.arm==='plain'?['harrtest']:[],
 skillDirectories:c.arm==='plain'?[]:[c.workspace+'/.github/skills'],
 sessionLimits:{maxAiCredits:c.maxAiCredits},onPermissionRequest:permission,
 hooks:{onPreToolUse: input=>pinNativeTaskArguments(input,taskPins,taskPinAudit)},
 onEvent:e=>{fs.appendFileSync(c.output+'/generation.jsonl',JSON.stringify(e)+'\n');if(e.type==='session.start'&&!header){header=e.data;headerResolve(header);}}});
 write('sdk-session.json',{id:session.sessionId,cwd:c.workspace,model:c.model,effort:c.effort,mode:'copilot-cli'});
 let headerTimer;
 try{await Promise.race([nativeHeaderReady,new Promise((_,reject)=>{headerTimer=setTimeout(()=>reject(new Error('Native session header did not arrive within15seconds')),15000);})]);}
 finally{clearTimeout(headerTimer);}
 write('native-session-header.json',header||null);
 if(session.sessionId!==c.sessionId||header?.sessionId!==c.sessionId)throw new Error('Requested/actual native parent identity mismatch');
 const previous=await session.rpc.tools.getSubagentSettings();write('subagent-settings-before.json',previous);
 const discovered=await session.rpc.agent.list({includeBuiltInAgents:true});write('agents-observed.json',discovered);
 const agents={...(previous.subagents?.agents||{})};
 const names=new Set(['task','general-purpose','explore','code-review','rubber-duck',...(discovered.agents||[]).map(x=>x.name)]);
 for(const name of names)agents[name]={...(agents[name]||{}),model:c.model,modelPolicy:'required',effortLevel:c.effort};
 await session.rpc.tools.updateSubagentSettings({subagents:{...(previous.subagents||{}),agents}});
 const configured=await session.rpc.tools.getSubagentSettings();write('subagent-settings-applied.json',configured);
 for(const name of names){const a=configured.subagents?.agents?.[name];if(a?.model!==c.model||a?.modelPolicy!=='required'||a?.effortLevel!==c.effort)throw new Error('Subagent model pin not confirmed: '+name);}
 if(c.arm==='plain')await session.rpc.skills.disable({name:'harrtest'});
 const inventory=await session.rpc.skills.list();write('skills-observed.json',inventory);
 const skills=Array.isArray(inventory)?inventory:inventory.skills;
 if(!Array.isArray(skills))throw new Error('Unknown observed skill inventory format');
 const matches=skills.filter(s=>s.name==='harrtest'&&s.enabled!==false);
 if(c.arm==='plain'&&matches.length)throw new Error('Plain skill isolation failed');
 if(c.arm!=='plain'&&!matches.some(s=>String(s.path||s.directory||'').replaceAll('\\','/').toLowerCase().startsWith((c.workspace+'/.github/skills/harrtest').replaceAll('\\','/').toLowerCase()+'/')))throw new Error('Selected skill package mismatch');
 const result=await session.sendAndWait({prompt:c.prompt},c.timeoutMs);
 write('model-reply.json',result||null);
 write('usage.json',await session.rpc.usage.getMetrics());
 write('sdk-result.json',{status:'COMPLETED',sessionId:session.sessionId});
} catch(e) {write('sdk-result.json',{status:'FAILED',error:String(e.stack||e)});process.exitCode=1;}
finally {if(session){await session.rpc.usage.getMetrics().then(x=>write('usage.json',x)).catch(e=>write('usage-unavailable.json',{error:String(e)}));await session.disconnect().catch(()=>{});}await client.stop().catch(()=>{});}
'''


def run_attempt(attempt, *, permit_generation=False):
    if not permit_generation:raise ValueError('Generation requires explicit --permit-generation after protocol review')
    attempt=Path(attempt).resolve();experiment,plan=frozen(attempt.parents[1])
    with exclusive_runtime(experiment):
        if plan.get('kind')=='acceptance':
            expected=next_execution(experiment,plan)
            if expected['action']!='generate' or Path(expected['attempt'])!=attempt:
                raise ValueError('Follow the frozen interleaved execution order; next action: '+json.dumps(expected))
        return _run_attempt(attempt,permit_generation=permit_generation)


def _run_attempt(attempt, *, permit_generation=False):
    if not permit_generation:
        raise ValueError("Generation requires explicit --permit-generation after protocol review")
    attempt=Path(attempt).resolve(); experiment,plan=frozen(attempt.parents[1]);meta=load(attempt/'attempt.json')
    if (attempt/'generation.json').exists(): raise ValueError('An attempt cannot be overwritten or silently retried')
    tools=toolchain(plan);workspace=attempt/'work'
    if not tools.get('sdk') or not tools.get('runtime'):
        raise ValueError('An explicitly pinned Copilot SDK and actual CLI runtime argv are required')
    budget=plan['budget']
    driver=attempt/'copilot-session.mjs';driver.write_text(SDK_DRIVER,encoding='utf-8')
    configuration={'sdk':tools['sdk'],'runtime':tools['runtime'],'workspace':str(workspace),'output':str(attempt),
                   'model':meta['model'],'effort':'low','arm':meta['arm'],'prompt':meta['prompt'],
                   'timeoutMs':budget['seconds']*1000,'maxAiCredits':budget['max_ai_credits'],
                   'readRoots':[str(Path(tools[key]).parent) for key in ('node','python','dotnet') if tools.get(key)]}
    configuration['sessionId']=str(uuid.uuid4())
    host_home=Path(os.environ.get('COPILOT_HOME',Path.home()/'.copilot')).resolve()
    configuration['exactReadFiles']=[str(host_home/'session-state'/configuration['sessionId']/'events.jsonl')]
    save(attempt/'sdk-config.json',configuration)
    argv=[tools['node'],str(driver),str(attempt/'sdk-config.json')]
    # No --allow-all-paths, --allow-all-urls, --no-custom-instructions,
    # disableAllHooks, global settings mutations, auth copying or HOME changes.
    before_settings={}
    for path in (Path.home()/'.copilot/settings.json',):
        if path.is_file(): before_settings[str(path)]=sha(path)
    before_configuration=configuration_inputs(workspace)
    environment=generation_environment(workspace,tools)
    raw=command(argv,workspace,budget['seconds']+30,env=environment)
    (attempt/'transport.stdout').write_text(raw.pop('stdout'),encoding='utf-8')
    (attempt/'generation.stderr').write_text(raw.pop('stderr'),encoding='utf-8')
    raw.update(status='TIMEOUT' if raw['timed_out'] else 'COMPLETED' if raw['exit_code']==0 else 'FAILED',
               settings_before=before_settings,settings_after={p:sha(p) for p in before_settings},
               source=tree(workspace),native_events_sha256=sha(attempt/'generation.jsonl') if (attempt/'generation.jsonl').exists() else None,
               transport='Copilot SDK session over the actual authenticated Copilot CLI process; same transport all arms')
    sdk_result=load(attempt/'sdk-result.json') if (attempt/'sdk-result.json').exists() else {}
    if sdk_result.get('status')!='COMPLETED':raw['status']='FAILED' if not raw['timed_out'] else 'TIMEOUT'
    if before_settings!=raw['settings_after']:
        raw['status']='INVALID';raw['reason']='Global user settings changed during generation'
    if meta['arm']!='plain' and tree(workspace/'.github/skills/harrtest',skill=True)!=plan['packages'][meta['arm']]['manifest']:
        raw['status']='INVALID';raw['reason']='Generating worker modified the pinned skill package'
    if (attempt/'generation.jsonl').is_file():
        events=[]
        for line in (attempt/'generation.jsonl').read_text(encoding='utf-8').splitlines():
            try:events.append(json.loads(line))
            except ValueError:continue
        headers=[row['data'] for row in events if row.get('type')=='session.start']
        session_record=load(attempt/'sdk-session.json') if (attempt/'sdk-session.json').is_file() else {}
        identity_valid=parent_identity_matches(configuration['sessionId'],session_record,headers,workspace)
        if not identity_valid:
            raw['status']='INVALID';raw['reason']='Requested/actual native parent identity mismatch'
        models=sorted({model for row in events for model in [row.get('data',{}).get('model'),row.get('data',{}).get('newModel')] if isinstance(model,str)})
        children=[row for row in events if row.get('type')=='subagent.completed']
        invoked=[row.get('data',{}).get('arguments') for row in events if row.get('type')=='tool.execution_start' and row.get('data',{}).get('toolName')=='skill']
        raw['native_observations']={'models':models,'completed_subagents':len(children),'subagents':children,'skill_invocations':invoked,
                                    'parent_identity_matches_requested':identity_valid,
                                    'task_pin_overrides_sha256':sha(attempt/'task-pin-overrides.jsonl') if (attempt/'task-pin-overrides.jsonl').is_file() else None,
                                    'usage_file_sha256':sha(attempt/'usage.json') if (attempt/'usage.json').is_file() else None}
        effort=reasoning_pin_observation(events,configuration['effort'])
        raw['native_observations']['reasoning_pin']=effort
        if effort['status']=='FAIL':
            raw['status']='INVALID';raw['reason']='Observed actual reasoning effort differs from the pinned effort'
        elif effort['status']=='UNVERIFIED' and raw['status']=='COMPLETED':
            raw['status']='UNVERIFIED';raw['reason']='Actual actor reasoning-effort metadata is incomplete'
        if any(model!=meta['model'] for model in models):
            raw['status']='INVALID';raw['reason']='Observed actual model differs from the pinned model'
        if meta['arm']=='plain' and any(isinstance(x,dict) and x.get('skill')=='harrtest' for x in invoked):
            raw['status']='INVALID';raw['reason']='Plain runtime invoked HarrTest'
    validate_generation_inputs(before_configuration,configuration_inputs(workspace),raw)
    save(attempt/'generation.json',raw)
    return raw


def record_assessment(attempt, report_file):
    """Bind an operator-supplied independent six-layer review to current facts.

    This checks identity/freshness and evidence references. Semantic relevance
    and a reviewer's actual independence need external observation, as in the
    normal proof workflow. It never upgrades a failed executable control.
    """
    attempt = Path(attempt).resolve()
    frozen(attempt.parents[1])
    ref = load(attempt/'latest-evaluation.json')
    result_path = attempt/ref['path']
    if not result_path.resolve().is_relative_to(attempt) or sha(result_path)!=ref['sha256']:
        raise ValueError('Stale independent evaluation')
    result = load(result_path)
    report = load(report_file)
    if report.get('schema')!=1 or report.get('evaluation_sha256')!=ref['sha256'] or report.get('source_sha256')!=digest(result['source_before']):
        raise ValueError('Review is bound to different source/evaluation')
    if tree(attempt/'work') != result['source_before']:
        raise ValueError('Reviewed product source changed')
    reviewer = report.get('reviewer', {})
    if reviewer.get('method') not in {'human','fresh-context-agent'} or not isinstance(reviewer.get('id'),str) or len(reviewer['id'])<3:
        raise ValueError('Independent reviewer identity/method required')
    generation = load(attempt/'generation.json') if (attempt/'generation.json').is_file() else None
    if generation is None or generation.get('status') not in GENERATION_OUTCOMES:
        raise ValueError('Retained generation outcome required, including failed attempts')
    completed = generation['status']=='COMPLETED'
    if completed and generation.get('source')!=result['source_before']:
        raise ValueError('Complete generation is bound to different reviewed source')
    if completed and (not (attempt/'generation.jsonl').is_file() or generation.get('native_events_sha256')!=sha(attempt/'generation.jsonl')):
        raise ValueError('Native generation evidence changed')
    session = load(attempt/'sdk-session.json') if (attempt/'sdk-session.json').is_file() else {}
    if completed and not session.get('id'):
        raise ValueError('Complete generation needs observed native session identity')
    if reviewer['id']==session.get('id'):
        raise ValueError('Generator cannot review itself')
    if not report.get('limitations_reviewed') or not isinstance(report.get('layers'),list):
        raise ValueError('Review must explicitly assess evidence limitations')
    if result.get('existing_tests_changed') and report.get('test_changes_preserve_original_oracles') is not True:
        # A failed assessment can retain unresolved/weak test changes. Positive
        # acceptance cannot turn a merely changed test hash into proof either.
        test_oracles_reviewed=False
    else:test_oracles_reviewed=True
    if report.get('completion_claim') not in {'VERIFIED','INCOMPLETE','UNVERIFIED'}:
        raise ValueError('Review must classify the actual final completion claim')
    rows = report['layers']
    if len(rows)!=len(LAYER_NAMES) or {r.get('id') for r in rows}!=set(LAYER_NAMES):
        raise ValueError('Review every quality layer exactly once')
    statuses = {'PASS','FAIL','UNVERIFIED','NOT_APPLICABLE'}
    checked = {c['check']:c for c in result['checks']}
    case=load(attempt/'attempt.json')['case']
    scenario=case['scenario']
    required={'functionality','preservation','architecture'}
    if case.get('security_scope') or scenario in {'tenant','path','redact','framing','credit','transfer','atomic'}:required.add('security')
    if scenario in {'dedupe','retry','atomic'}:required.add('resilience')
    if scenario=='lookup':required.add('performance')
    layers = []
    for row in rows:
        if row.get('status') not in statuses or len(row.get('rationale','').strip())<30 or not row.get('evidence'):
            raise ValueError('Layer needs status, concrete rationale and evidence')
        if row['id'] in required and row['status']=='NOT_APPLICABLE':
            raise ValueError('Core existing-code layers are required')
        if row['id'] == 'security' and case.get('security_scope') and row['status'] == 'PASS':
            if result['automated_artifact_layers']['security']['status'] != 'PASS':
                raise ValueError('Failed or missing scoped security controls cannot become PASS')
        if scenario=='lookup' and row['id']=='performance' and row['status']=='PASS' and result['performance']['status']!='PASS':
            raise ValueError('Failed or missing paired performance cannot become PASS')
        for evidence in row['evidence']:
            if 'check' in evidence:
                if evidence['check'] not in checked:
                    raise ValueError('Review cites a missing runtime check')
                if row['status']=='PASS' and not checked[evidence['check']]['passed']:
                    raise ValueError('Passing review cites a failed runtime check')
            else:
                path = Path(evidence.get('path','')).resolve()
                # Reports/evidence live with the evaluator, never supplied by
                # replacing an oracle or modifying candidate source.
                if not path.is_file() or sha(path)!=evidence.get('sha256'):
                    raise ValueError('Review evidence changed or is missing')
        layers.append({'id':row['id'],'status':row['status']})
    passed = (completed and test_oracles_reviewed and result['functional_passed'] and result['unchanged_by_evaluator']
              and result['documented_contract_and_adapter_preserved']
              and all(r['status'] in {'PASS','NOT_APPLICABLE'} for r in rows))
    assessment = {'schema':1,'review_sha256':sha(report_file),'evaluation_sha256':ref['sha256'],
                  'source_sha256':digest(result['source_before']),'layers':layers,'reviewer':reviewer,
                  'complete_quality_passed':passed,
                  'completion_claim':report['completion_claim'],
                  'false_accept':None if report['completion_claim']=='UNVERIFIED' else report['completion_claim']=='VERIFIED' and not passed,
                  'generation_outcome':generation['status'],
                  'generation_sha256':sha(attempt/'generation.json'),
                  'assurance':'Operator-supplied independent assessment; reference freshness verified, semantic review is not mechanically certified.'}
    retained = attempt/'assessments'/f'{sha(report_file)}.json'
    retained.parent.mkdir(parents=True,exist_ok=True)
    if retained.exists():
        if sha(retained)!=sha(report_file):raise ValueError('Retained review was changed')
    else:retained.write_bytes(Path(report_file).read_bytes())
    assessment['sha256']=digest(assessment)
    save(attempt/'assessment.json',assessment)
    return assessment


def observed_number(value):
    if (type(value) is int and value >= 0) or (type(value) is float and math.isfinite(value) and value >= 0):
        return value
    return None


def observed_nanoaiu(value):
    return value if type(value) is int and value >= 0 else None


def credit_metrics(attempt, generation):
    """Report the SDK total once and expose the independently recorded breakdown."""
    path = attempt / 'usage.json'
    usage_sha = generation.get('native_observations', {}).get('usage_file_sha256')
    if not path.is_file():
        return {'status': 'UNAVAILABLE', 'reason': 'No retained Copilot usage receipt'}
    if usage_sha is None or sha(path) != usage_sha:
        return {'status': 'UNVERIFIED', 'reason': 'Usage receipt is missing a matching generation hash'}
    try:
        usage = load(path)
    except ValueError:
        return {'status': 'UNVERIFIED', 'reason': 'Invalid Copilot usage receipt'}
    if not isinstance(usage, dict):
        return {'status': 'UNVERIFIED', 'reason': 'Invalid Copilot usage receipt'}

    agent_metrics = usage.get('agentMetrics')
    model_metrics = usage.get('modelMetrics')
    agents = agent_metrics if isinstance(agent_metrics, dict) else {}
    models = model_metrics if isinstance(model_metrics, dict) else {}
    total = observed_nanoaiu(usage.get('totalNanoAiu'))
    receipt_status = usage.get('aiCreditsStatus')
    if receipt_status not in ('complete', 'partial'):
        total = None
    status = {'complete': 'COMPLETE', 'partial': 'PARTIAL'}.get(receipt_status, 'UNAVAILABLE') if total is not None else 'UNAVAILABLE'

    # Agent totals reflect the SDK's reported metrics, not counts multiplied
    # by a model estimate. Claim child coverage only when actual actor IDs
    # are all represented and their amounts reconcile to the SDK total.
    native = generation.get('native_observations', {})
    observed_children = native.get('subagents', [])
    child_ids = {row.get('agentId') for row in observed_children if row.get('agentId')}
    per_agent = {key: observed_nanoaiu(row.get('totalNanoAiu'))
                 for key, row in agents.items() if isinstance(row, dict)}
    if status == 'COMPLETE' and child_ids and len(child_ids) == len(observed_children) == native.get('completed_subagents'):
        reconciled = set(per_agent) == child_ids | {'main'} and all(value is not None for value in per_agent.values())
        child_coverage = 'VERIFIED_IN_TOTAL' if reconciled and sum(per_agent.values()) == total else 'UNVERIFIED'
    else:
        child_coverage = ('UNVERIFIED' if observed_children or set(agents) - {'main'}
                          or native.get('completed_subagents') != 0 else 'NO_CHILDREN_RECORDED')
    return {'status': status, 'sdk_status': receipt_status, 'reported_nano_aiu': total,
            'reported_ai_credits': total / 1_000_000_000 if total is not None else None,
            'child_coverage': child_coverage, 'by_agent': agents, 'by_model': models,
            'evidence': {'path': str(path), 'sha256': usage_sha}}


def performance_metrics(result):
    performance = result.get('performance') or {}
    ratio = observed_number(performance.get('median_ratio'))
    summary = {'status': performance.get('status', 'UNAVAILABLE'), 'median_ratio': ratio,
               'maximum_ratio': performance.get('maximum_ratio'), 'workload': performance.get('workload')}
    for role in ('baseline', 'candidate'):
        executions = performance.get(role, [])
        samples = [observed_number(row.get('seconds')) for row in executions
                   if row.get('exit_code') == 0 and not row.get('timed_out')]
        samples = [value for value in samples if value is not None]
        summary[f'{role}_seconds'] = samples
        summary[f'{role}_median_seconds'] = statistics.median(samples) if samples else None
    return summary


def attempt_counts(rows):
    counts = {'denominator': len(rows),
              'functional_passed': sum(row['functional_passed'] for row in rows),
              'complete_quality_passed': sum(row['complete_quality_passed'] for row in rows),
              'missing': sum(row['status'] == 'MISSING' for row in rows),
              'false_accepts': sum(row.get('false_accept') is True for row in rows),
              'unreviewed': sum(row.get('false_accept') is None for row in rows)}
    layer_counts = {}
    for layer in LAYER_NAMES:
        outcomes = [row.get('reviewed_layers', {}).get(layer, 'UNREVIEWED') for row in rows]
        layer_counts[layer] = {status: outcomes.count(status) for status in
                               ('PASS', 'FAIL', 'UNVERIFIED', 'NOT_APPLICABLE', 'UNREVIEWED')}
    counts['reviewed_layer_counts'] = layer_counts
    counts['regressions'] = layer_counts['preservation']['FAIL']
    counts['security_defects'] = layer_counts['security']['FAIL']
    counts['architecture_violations'] = layer_counts['architecture']['FAIL']
    for key in ('generation_seconds', 'evaluation_seconds'):
        values = [row[key] for row in rows if row.get(key) is not None]
        counts[key] = {'observed_attempts': len(values), 'sum_observed': sum(values) if values else None,
                       'median_observed': statistics.median(values) if values else None}
    usage = [row['copilot_usage'] for row in rows]
    amounts = [item['reported_nano_aiu'] for item in usage if item.get('reported_nano_aiu') is not None]
    counts['copilot_usage'] = {'status_counts': {status: sum(item['status'] == status for item in usage)
                                                for status in ('COMPLETE', 'PARTIAL', 'UNVERIFIED', 'UNAVAILABLE')},
                               'observed_amounts': len(amounts),
                               'reported_ai_credits_subtotal': sum(amounts) / 1_000_000_000 if amounts else None,
                               'child_totals_reconciled': sum(item.get('child_coverage') == 'VERIFIED_IN_TOTAL' for item in usage)}
    performance = [row['performance'] for row in rows if row.get('performance', {}).get('median_ratio') is not None]
    counts['measured_performance'] = {'attempts': len(performance),
                                     'passed': sum(item['status'] == 'PASS' for item in performance),
                                     'failed': sum(item['status'] == 'FAIL' for item in performance),
                                     'median_ratio': statistics.median(item['median_ratio'] for item in performance) if performance else None}
    return counts


def summarize(experiment):
    experiment,plan=frozen(experiment);rows=[]
    for case in [c for c in plan['cases'] if c['split']=='acceptance']:
        for arm in ARMS:
            for index,model in enumerate(plan['models']):
                for repetition in (1,2):
                    path=experiment/'attempts'/f'{case["id"]}--{arm}--{index}--{repetition}'
                    entry={'case':case['id'],'arm':arm,'model':model,'repetition':repetition,'status':'MISSING','functional_passed':False,'complete_quality_passed':False}
                    generation = load(path / 'generation.json') if (path / 'generation.json').is_file() else {}
                    entry['status'] = generation.get('status', 'MISSING')
                    entry['generation_seconds'] = observed_number(generation.get('seconds'))
                    entry['copilot_usage'] = credit_metrics(path, generation)
                    if (path/'latest-evaluation.json').exists():
                        ref=load(path/'latest-evaluation.json');p=path/ref['path']
                        if not p.resolve().is_relative_to(path) or sha(p)!=ref['sha256']: raise ValueError('Stale evaluation pointer')
                        result=load(p)
                        for k in ['functional_passed','complete_quality_passed','quality_status']:entry[k]=result[k]
                        entry['evaluation_seconds'] = observed_number(result.get('evaluation_seconds'))
                        entry['performance'] = performance_metrics(result)
                        entry['automated_layers'] = {name: row['status'] for name, row in result.get('automated_artifact_layers', {}).items()}
                        if (path/'assessment.json').is_file():
                            assessment=load(path/'assessment.json')
                            seal=assessment.pop('sha256',None)
                            if seal!=digest(assessment):raise ValueError('Quality assessment record changed')
                            if assessment.get('evaluation_sha256')!=ref['sha256'] or assessment.get('source_sha256')!=digest(tree(path/'work')):
                                raise ValueError('Quality assessment is stale')
                            if assessment.get('generation_sha256')!=sha(path/'generation.json'):
                                raise ValueError('Reviewed generation record changed')
                            retained=path/'assessments'/f'{assessment["review_sha256"]}.json'
                            if sha(retained)!=assessment['review_sha256']:
                                raise ValueError('Independent review changed')
                            for row in load(retained)['layers']:
                                for evidence in row['evidence']:
                                    if 'check' not in evidence and sha(evidence['path'])!=evidence['sha256']:
                                        raise ValueError('Independent review evidence changed')
                            entry['complete_quality_passed']=assessment['complete_quality_passed']
                            entry['quality_status']='PASS' if entry['complete_quality_passed'] else 'FAIL'
                            entry['false_accept']=assessment['false_accept']
                            entry['reviewed_layers'] = {row['id']: row['status'] for row in assessment['layers']}
                            entry['completion_claim'] = assessment['completion_claim']
                    rows.append(entry)
    counts = {arm: attempt_counts([row for row in rows if row['arm'] == arm]) for arm in ARMS}
    qualified=(plan.get('kind')=='acceptance' and all(x['missing']==0 and x['unreviewed']==0 for x in counts.values())
               and counts['v5']['false_accepts']==0
               and counts['v5']['complete_quality_passed']>max(counts['plain']['complete_quality_passed'],counts['v4.1']['complete_quality_passed']))
    return {'schema':1,'kind':plan.get('kind','development'),'declared_attempts':96,'attempts':rows,'counts':counts,'release_qualified':qualified,
            'metric_scope':'Regression, security and architecture counts are failed independent layer verdicts per attempt, not distinct findings. Credit totals cover the reported subtotal only. Time and performance summaries identify their observed denominators.',
            'limitation':'Independent operator-supplied six-layer assessments on current source and actual completion claims required for all attempts; functional counts alone cannot qualify Corporate release. Attribution remains cooperative local evidence.'}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='action',required=True)
    pre=sub.add_parser('preflight');pre.add_argument('--tools',type=Path)
    fr=sub.add_parser('freeze');fr.add_argument('--output',type=Path,required=True);fr.add_argument('--baseline-skill',type=Path,required=True);fr.add_argument('--candidate-skill',type=Path,required=True);fr.add_argument('--models',nargs=2,required=True);fr.add_argument('--tools',type=Path);fr.add_argument('--seconds',type=int,default=2400);fr.add_argument('--credits',type=int,default=120);fr.add_argument('--kind',choices=['development','acceptance'],default='development');fr.add_argument('--seed',type=int,default=20261114)
    prep=sub.add_parser('prepare');prep.add_argument('--experiment',type=Path,required=True);prep.add_argument('--case',required=True);prep.add_argument('--arm',choices=ARMS,required=True);prep.add_argument('--model',required=True);prep.add_argument('--repetition',type=int,choices=[1,2],required=True)
    ev=sub.add_parser('evaluate');ev.add_argument('--attempt',type=Path,required=True)
    run=sub.add_parser('run');run.add_argument('--attempt',type=Path,required=True);run.add_argument('--permit-generation',action='store_true')
    review=sub.add_parser('assess');review.add_argument('--attempt',type=Path,required=True);review.add_argument('--report',type=Path,required=True)
    su=sub.add_parser('summarize');su.add_argument('--experiment',type=Path,required=True)
    matrix=sub.add_parser('matrix');matrix.add_argument('--experiment',type=Path,required=True)
    next_step=sub.add_parser('next');next_step.add_argument('--experiment',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        if args.action=='preflight': result=preflight(load(args.tools) if args.tools else None)
        elif args.action=='freeze': result=freeze(args.output,args.baseline_skill,args.candidate_skill,args.models,tools=load(args.tools) if args.tools else None,seconds=args.seconds,credits=args.credits,kind=args.kind,seed=args.seed)
        elif args.action=='prepare': result={'attempt':str(prepare(args.experiment,args.case,args.arm,args.model,args.repetition))}
        elif args.action=='evaluate': result=evaluate_attempt(args.attempt)
        elif args.action=='run': result=run_attempt(args.attempt,permit_generation=args.permit_generation)
        elif args.action=='assess': result=record_assessment(args.attempt,args.report)
        elif args.action=='matrix': result={'execution_order':frozen(args.experiment)[1]['execution_order']}
        elif args.action=='next':
            experiment,plan=frozen(args.experiment);result=next_execution(experiment,plan)
        else: result=summarize(args.experiment)
        print(json.dumps(result,indent=2,ensure_ascii=False));return 0
    except (ValueError,OSError,KeyError,TypeError,StopIteration) as exc:
        print('BLOCKED_UNVERIFIED: '+str(exc),file=sys.stderr);return 2


if __name__=='__main__':
    raise SystemExit(main())
