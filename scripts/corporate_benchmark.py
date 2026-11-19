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
from itertools import accumulate
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
PERFORMANCE_WORKLOADS = {'lookup': 'lookup 30000 20000', 'range-count': 'range_count 30000 20000 20731'}
RECOVERY_SCENARIOS = {'room-schedule', 'checkpoint-publish'}
RESILIENCE_REQUIRED = {'dedupe', 'retry', 'atomic', 'build-plan'} | RECOVERY_SCENARIOS


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
        environment['DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE'] = 'true'
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


def freeze(destination, baseline, candidate, models, *, tools=None, seconds=2400, credits=120, corpus=CORPUS,
           kind='development', seed=20261114, corporate_guard_goal=None):
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError("Use a new immutable experiment directory")
    if kind not in {'development','acceptance'}:raise ValueError('Declare development or acceptance experiment')
    if corporate_guard_goal is not None and (not isinstance(corporate_guard_goal, str)
            or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}', corporate_guard_goal)):
        raise ValueError('Declare a valid goal ID for the explicitly enrolled Corporate profile')
    if type(seed) is not int:raise ValueError('Execution-order seed must be an integer')
    if len(models) != 2 or len(set(models)) != 2 or any(not m or m == "auto" for m in models):
        raise ValueError("Pin two distinct concrete model IDs; Auto is not allowed")
    if not isinstance(seconds, int) or not 60 <= seconds <= 7200 or not isinstance(credits, int) or credits < 30:
        raise ValueError("Invalid common attempt bounds")
    rows = cases(corpus)
    guard_cases = None
    if corporate_guard_goal and kind == 'acceptance':
        guard_cases = sorted(case['id'] for case in rows if case['split'] == 'acceptance' and case.get('complexity'))
        if not guard_cases:
            raise ValueError('Guarded comparison requires predeclared substantial held cases')
    baseline, candidate = Path(baseline).resolve(), Path(candidate).resolve()
    for p, version in ((baseline, "4.1.0"), (candidate, "5.0.0")):
        if (p / "VERSION").read_text().strip() != version or not (p / "SKILL.md").is_file():
            raise ValueError("Wrong skill version: " + str(p))
    if corporate_guard_goal and not (candidate / 'scripts/copilot_guard.py').is_file():
        raise ValueError('The pinned candidate does not include the Corporate editor guard')
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
                       "Mixed complexity: two changes across independent existing components and six bounded acceptance changes. Synthetic projects exercise defined contracts and consumers at fixture scale.",
                       "Any acceptance case used to tune the harness becomes development data and requires a fresh declared comparison."]}
    if corporate_guard_goal:
        plan['corporate_guard_goal'] = corporate_guard_goal
    if guard_cases is not None:
        plan['corporate_guard_cases'] = guard_cases
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


BUILD_PLAN_CONTRACT = '''Public wire contract (UTF-8 JSON in, one JSON value out):
plan: {"op":"plan","jobs":[{"id":"compile","depends_on":[]},{"id":"pack","depends_on":["compile"]}]} -> {"order":["compile","pack"],"error":null}.
Job IDs are nonempty strings and case-sensitive. Each job includes a depends_on array of job ID strings, which may be empty. Repeated prerequisite references to the same ID impose one dependency. At each position select the earliest job in input order whose prerequisites have all been scheduled. An empty job array returns {"order":[],"error":null}.
Reject duplicate job IDs with {"order":[],"error":"duplicate-id"}, then reject unknown prerequisite IDs with {"order":[],"error":"missing-dependency"}, then reject any cycle, including self-dependency, with {"order":[],"error":"cycle"}. Never return a partial plan on error.
job_count: {"op":"job_count","jobs":[{"id":"compile","depends_on":[]}]} -> {"count":1}. This operation counts input records without validating dependency edges or unique IDs.
The public library entrypoint and the existing positional JSON CLI both return the same response shape. Planning does not execute jobs.
'''


BUILD_PLAN_SOURCE = '''using System;
using System.Linq;
using System.Text.Json;

public static class Rules
{
    public static string Evaluate(string text)
    {
        using var request = JsonDocument.Parse(text);
        var root = request.RootElement;
        var jobs = root.GetProperty("jobs");
        if (root.GetProperty("op").GetString() == "job_count")
            return JsonSerializer.Serialize(new { count = jobs.GetArrayLength() });

        var order = jobs.EnumerateArray().Select(job => job.GetProperty("id").GetString()).ToArray();
        return JsonSerializer.Serialize(new { order, error = (string?)null });
    }
}
'''


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


STOCK_CONTRACT = '''StockCsv.Parse(string csv) -> StockRow[] retains row order from headerless sku,warehouse,units CSV. Documents use LF or CRLF, may end with one newline, and can be empty. The first two fields may be quoted and contain commas or escaped double quotes written as two double quotes. Do not trim values or casing; fields contain no line breaks. Units are an unquoted nonnegative Int32.
StockProjection.Balance(StockRow[] rows, string warehouse) -> long sums the latest row for each distinct SKU in the chosen warehouse. The last row in input order wins, including zero. SKU and warehouse comparisons are case-sensitive. An absent warehouse or empty rows returns 0. Input arrays are unchanged.
Rules.Evaluate and the positional JSON CLI accept {"op":"balance","warehouse":"west","csv":"A,west,5"} and return {"total":5}. The Rules adapter composes the existing reader and projection. Keep both module exports and the StockRow record constructor and fields.
'''

STOCK_FILES = {
    'StockRow.cs': 'public sealed record StockRow(string Sku, string Warehouse, int Units);\n',
    'StockCsv.cs': r'''public static class StockCsv
{
    public static StockRow[] Parse(string csv) => csv.Split('\n', StringSplitOptions.RemoveEmptyEntries)
        .Select(line => line.TrimEnd('\r').Split(','))
        .Select(fields => new StockRow(fields[0], fields[1], int.Parse(fields[2])))
        .ToArray();
}
''',
    'StockProjection.cs': '''public static class StockProjection
{
    public static long Balance(StockRow[] rows, string warehouse) =>
        rows.Where(row => row.Warehouse == warehouse).Sum(row => (long)row.Units);
}
''',
    'Rules.cs': '''using System.Text.Json;

public static class Rules
{
    public static string Evaluate(string text)
    {
        using var request = JsonDocument.Parse(text);
        var root = request.RootElement;
        var rows = StockCsv.Parse(root.GetProperty("csv").GetString()!);
        return JsonSerializer.Serialize(new { total = StockProjection.Balance(rows, root.GetProperty("warehouse").GetString()!) });
    }
}
''',
}

TRIAGE_CONTRACT = '''rankTickets(tickets: Ticket[]): Ticket[] returns a new array ranked critical, high, normal, low, and then all other severities. Compare severity after trim().toLowerCase(). Keep input order within each rank and preserve every Ticket field. Do not mutate the original array or ticket objects.
groupTickets(tickets: Ticket[]): QueueSummary preserves input order of ticket IDs within an owner and owner groups in first occurrence order. Trim owner whitespace and compare names with toLowerCase(), preserving the first trimmed spelling for display. Null or blank owners go into unassigned in input order. Do not change input.
QueueSummary has {owners: [{name: string, ids: string[]}], unassigned: string[]}. The existing evaluate(text: string): string SDK and positional JSON CLI accept {"op":"queue","tickets":[{"id":"one","severity":"high","owner":"Lee"}]} -> {"owners":[{"name":"Lee","ids":["one"]}],"unassigned":[]}. Composition ranks then groups. Empty input returns two empty arrays. Keep both module exports and shared type declarations.
'''

TRIAGE_FILES = {
    'tickets.ts': '''export interface Ticket { id: string; severity: string; owner: string | null }
export interface QueueSummary { owners: {name: string; ids: string[]}[]; unassigned: string[] }
''',
    'rank.ts': '''import type { Ticket } from './tickets.ts';

export function rankTickets(tickets: Ticket[]): Ticket[] {
  return tickets.sort((left, right) => left.severity.localeCompare(right.severity));
}
''',
    'group.ts': '''import type { QueueSummary, Ticket } from './tickets.ts';

export function groupTickets(tickets: Ticket[]): QueueSummary {
  const owners = new Map<string, {name: string; ids: string[]}>();
  const unassigned: string[] = [];
  for (const ticket of tickets) {
    if (ticket.owner === null) {
      unassigned.push(ticket.id);
    } else {
      const group = owners.get(ticket.owner) ?? {name: ticket.owner, ids: []};
      group.ids.push(ticket.id);
      owners.set(ticket.owner, group);
    }
  }
  return {owners: [...owners.values()], unassigned};
}
''',
    'rules.ts': '''import { rankTickets } from './rank.ts';
import { groupTickets } from './group.ts';
import type { Ticket } from './tickets.ts';

export function evaluate(text: string): string {
  const request: {tickets: Ticket[]} = JSON.parse(text);
  return JSON.stringify(groupTickets(rankTickets(request.tickets)));
}
''',
}

PICK_LIST_CONTRACT = '''mergePickLines(lines: PickLine[]): PickLine[] returns a fresh array. Ignore zero-unit lines. For exact equal (zone, sku, packSize) tuples, sum units and emit one record in first positive-line occurrence order. Zone and SKU are nonempty, case-sensitive strings and may contain delimiters. Do not mutate input arrays or records.
countPackages(lines: PickLine[]): PackageLine[] returns a fresh array in the given order; it does not merge or discard lines. Each record has exactly zone, sku, packSize, packages, unusedUnits. Use the smallest nonnegative number of whole packages that cover the units. unusedUnits is the excess capacity. A zero-unit line has zero packages and zero unused units. Do not mutate input arrays or records.
units is a nonnegative safe integer; packSize is a positive safe integer. Inputs fit the safe integer range, including merged totals and resulting package capacity. No new input validation is required.
The existing evaluate(text: string): string SDK and positional JSON CLI use {"op":"pick","lines":[{"zone":"north","sku":"bolt","units":7,"packSize":4}]} -> {"packages":[{"zone":"north","sku":"bolt","packSize":4,"packages":2,"unusedUnits":1}]}. Composition merges first and counts packages second. An empty list returns {"packages":[]}. line_count returns {"count":N} from the original lines, including zero and duplicate lines, without processing them.
Keep both module exports and shared types. Only merge.ts and packages.ts may change production behavior. Keep the adapters, docs and configuration unchanged. Tests may be added or extended without weakening the original checks.
'''

PICK_LIST_FILES = {
    'pick.ts': '''export interface PickLine { zone: string; sku: string; units: number; packSize: number }
export interface PackageLine { zone: string; sku: string; packSize: number; packages: number; unusedUnits: number }
''',
    'merge.ts': '''import type { PickLine } from './pick.ts';

export function mergePickLines(lines: PickLine[]): PickLine[] {
  return lines.map(line => ({...line}));
}
''',
    'packages.ts': '''import type { PackageLine, PickLine } from './pick.ts';

export function countPackages(lines: PickLine[]): PackageLine[] {
  return lines.map(({zone, sku, units, packSize}) => {
    const packages = Math.floor(units / packSize);
    return {zone, sku, packSize, packages, unusedUnits: packages * packSize - units};
  });
}
''',
    'rules.ts': '''import { mergePickLines } from './merge.ts';
import { countPackages } from './packages.ts';
import type { PickLine } from './pick.ts';

export function evaluate(text: string): string {
  const request: {op: string; lines: PickLine[]} = JSON.parse(text);
  if (request.op === 'line_count') return JSON.stringify({count: request.lines.length});
  if (request.op === 'pick') return JSON.stringify({packages: countPackages(mergePickLines(request.lines))});
  throw new Error('unsupported operation');
}
''',
}

CUE_REPORT_CONTRACT = '''The Rules.Evaluate(string text) API and positional JSON CLI accept:
{"op":"cues","cues":[{"id":"intro","start_ms":0,"end_ms":800}]} -> {"ids":["intro"],"covered_ms":800}.
CueOrder.Sort(IReadOnlyList<StudioCue>) returns the same records in ascending start order. Equal start times retain input order regardless of cue ID or end time. The input order and records are unchanged.
CueCoverage.TotalMilliseconds(IReadOnlyList<StudioCue>) returns the number of covered milliseconds across the union of all half-open intervals [start_ms,end_ms). Cues may be unsorted, disjoint, touching, overlapping, repeated, entirely contained in another cue, or zero-length. Zero-length cues still appear in ids.
Times are nonnegative signed 64-bit integer milliseconds with end_ms >= start_ms. Cue IDs are nonempty strings; duplicate IDs are allowed. An empty list gives {"ids":[],"covered_ms":0}.
cue_count returns {"count":N} for the number of input records, without evaluating cue order or coverage.
Preserve the shared StudioCue record and both component signatures. Only change CueOrder.cs and CueCoverage.cs for production behavior. Keep docs, adapters and project configuration unchanged. Tests may be added or extended without weakening existing checks.
'''

CUE_REPORT_FILES = {
    'StudioCue.cs': 'public sealed record StudioCue(string Id, long StartMs, long EndMs);\n',
    'CueOrder.cs': '''public static class CueOrder
{
    public static StudioCue[] Sort(IReadOnlyList<StudioCue> cues)
        => cues.OrderBy(cue => cue.StartMs).ThenBy(cue => cue.Id, StringComparer.Ordinal).ToArray();
}
''',
    'CueCoverage.cs': '''public static class CueCoverage
{
    public static long TotalMilliseconds(IReadOnlyList<StudioCue> cues)
        => cues.Sum(cue => cue.EndMs - cue.StartMs);
}
''',
    'Rules.cs': '''using System.Text.Json;

public static class Rules
{
    public static string Evaluate(string text)
    {
        using var document = JsonDocument.Parse(text);
        var request = document.RootElement;
        var input = request.GetProperty("cues");
        switch (request.GetProperty("op").GetString())
        {
            case "cue_count":
                return JsonSerializer.Serialize(new { count = input.GetArrayLength() });
            case "cues":
                var cues = input.EnumerateArray().Select(cue => new StudioCue(
                    cue.GetProperty("id").GetString()!,
                    cue.GetProperty("start_ms").GetInt64(),
                    cue.GetProperty("end_ms").GetInt64())).ToArray();
                return JsonSerializer.Serialize(new {
                    ids = CueOrder.Sort(cues).Select(cue => cue.Id),
                    covered_ms = CueCoverage.TotalMilliseconds(cues)
                });
            default:
                throw new ArgumentException("unsupported operation");
        }
    }
}
''',
}

TILE_WINDOW_CONTRACT = '''The evaluate(text: string): string API and positional JSON CLI accept:
{"op":"tiles","grid":[["a","b"],["c","d"]],"x":0,"y":0,"width":1,"height":2} -> {"tiles":["a","c"]}.
The grid is a rectangular array of string rows, possibly empty or of zero width. Coordinates are zero-based, x for columns and y for rows. Coordinates, nonnegative extents, and x+width and y+height are safe integers.
Intersect the original half-open rectangle [x,x+width) by [y,y+height) with the grid. Return the intersected cells in row-major order, retaining duplicates and empty cell strings. A zero extent or an empty intersection returns {"tiles":[]}.
tile_count returns {"count":N} for the total number of cells without applying a window.
Keep the exported SDK and CLI unchanged. Production changes belong in rules.ts. Keep docs, adapters and project configuration unchanged. Tests may be added or extended without weakening existing checks.
'''

TILE_WINDOW_SOURCE = '''export function evaluate(text: string): string {
  const { op, grid, x, y, width, height } = JSON.parse(text);
  const rows: string[][] = grid;
  if (op === 'tile_count') return JSON.stringify({count: rows.reduce((n, row) => n + row.length, 0)});
  if (op !== 'tiles') throw new Error('unsupported operation');
  const left = Math.max(0, x);
  const top = Math.max(0, y);
  return JSON.stringify({tiles: rows.slice(top, top + height).flatMap(row => row.slice(left, left + width))});
}
'''

RECIPE_SCALE_CONTRACT = '''The rules.evaluate(text: str) -> str API and positional JSON CLI accept:
{"op":"scale","from_servings":2,"to_servings":4,"ingredients":[{"label":"rice","units":4,"step":2}]} -> {"ingredients":[{"label":"rice","units":8}]}.
The source and target serving counts and each ingredient step are positive integers; units are nonnegative integers. For each ingredient, the scaled amount is the least integer multiple of step that is at least units * to_servings / from_servings. This is exact integer-rational scaling, including for large integer values. An exact multiple is kept, and zero stays zero.
Return a result row for each input ingredient in the same order. Preserve labels exactly, including duplicate labels. The empty ingredient list returns {"ingredients":[]}.
ingredient_count returns {"count":N} for the number of input ingredients. It does not require either serving count or inspect ingredients.
Keep the exported SDK and CLI unchanged. Production changes belong in rules.py. Keep docs, adapters and project configuration unchanged. Tests may be added or extended without weakening existing checks.
'''

RECIPE_SCALE_SOURCE = '''import json


def evaluate(text: str) -> str:
    request = json.loads(text)
    rows = request['ingredients']
    if request['op'] == 'ingredient_count':
        return json.dumps({'count': len(rows)})
    if request['op'] != 'scale':
        raise ValueError('unsupported operation')
    source, target = request['from_servings'], request['to_servings']
    return json.dumps({'ingredients': [
        {'label': row['label'], 'units': row['units'] * target // source}
        for row in rows
    ]})
'''

MUSEUM_ROUTE_CONTRACT = '''The rules.evaluate(text: str) -> str API and positional JSON CLI accept:
{"op":"route","galleries":{"hall":["prints"],"prints":[]},"start":"hall","goal":"prints"} -> {"path":["hall","prints"]}.
galleries maps gallery ID strings to ordered lists of one-way crossings to existing galleries. Crossings may repeat and may form cycles.
The path includes both endpoints and has the fewest crossings among directed routes. For equal-length paths, compare the positions of their crossings in each gallery's neighbor list at the first differing choice. Prefer the earlier listed crossing. The order of keys in galleries has no effect.
A known start equal to the goal returns a path containing only that gallery. Unreachable or unknown endpoints return {"path":[]}.
gallery_count returns {"count":N} from the number of keys in galleries. It does not require endpoints or inspect the neighbor lists.
Keep the exported SDK, CLI, and result shapes unchanged. Production changes belong in rules.py. Keep docs, adapters and project configuration unchanged. Tests may be added or extended without weakening existing checks.
'''

MUSEUM_ROUTE_SOURCE = '''import json


def find_route(galleries, current, goal, path):
    if current == goal:
        return path
    for neighbor in galleries[current]:
        if neighbor in path:
            continue
        route = find_route(galleries, neighbor, goal, [*path, neighbor])
        if route:
            return route
    return []


def evaluate(text: str) -> str:
    request = json.loads(text)
    galleries = request['galleries']
    if request['op'] == 'gallery_count':
        return json.dumps({'count': len(galleries)})
    if request['op'] != 'route':
        raise ValueError('unsupported operation')
    start, goal = request['start'], request['goal']
    if start not in galleries or goal not in galleries:
        return json.dumps({'path': []})
    return json.dumps({'path': find_route(galleries, start, goal, [start])})
'''

ROOM_SCHEDULE_CONTRACT = '''Rules.Evaluate(string text) and the positional JSON CLI accept a UTF-8 JSON request:
{"op":"schedule","requests":[{"id":"demo","start_min":60,"end_min":90}]} returns {"accepted":["demo"],"rejected":[]}.
Up to 64 requests refer to one room on the same day. IDs are unique nonempty strings. Both times are signed 32-bit integers.
Process requests in input order. Accept only windows with 0 <= start_min < end_min <= 1440. For other windows, reject with
{"id":ID,"error":"invalid_window"}. A valid window that intersects any previously accepted window is rejected with
{"id":ID,"error":"overlap"}. Windows are half-open: touching starts and ends do not conflict. Continue after every
rejection; a rejected window never blocks later requests. Keep both output lists in input order and always return both.
The existing request_count operation accepts the same requests array and returns {"count":N} without scheduling.
'''

ROOM_SCHEDULE_SOURCE = '''using System.Text.Json;

public static class Rules
{
    public static string Evaluate(string text)
    {
        using var document = JsonDocument.Parse(text);
        var input = document.RootElement;
        var requests = input.GetProperty("requests");
        if (input.GetProperty("op").GetString() == "request_count")
            return JsonSerializer.Serialize(new { count = requests.GetArrayLength() });

        var accepted = new List<string>();
        foreach (var request in requests.EnumerateArray())
            accepted.Add(request.GetProperty("id").GetString()!);
        return JsonSerializer.Serialize(new { accepted, rejected = Array.Empty<object>() });
    }
}
'''

CHECKPOINT_CONTRACT = '''rules.evaluate(text: str) -> str and the positional JSON CLI accept a request with op and store (a file path).
The UTF-8 JSON store and successful response both have exactly {"published":[...],"pending":null} or
{"published":[...],"pending":[...]}. Lists contain strings and retain order and duplicates. When the store
does not exist, the logical state is {"published":[],"pending":null}.
- status returns the current state without creating or changing the file.
- stage takes an items list, replaces only pending with that list, and persists the resulting state.
- publish replaces published with the pending list (including an empty list), clears pending to null, and
  persists the result. If pending is null, return the state without creating or changing the file.
- publish accepts an optional boolean fail_before_publish (default false). If true and a checkpoint is
  pending, raise RuntimeError before changing any store bytes. A later publish without the fault flag
  must be able to publish that checkpoint without restaging it. With no pending checkpoint the flag has
  no effect.
Inputs and existing stores have the documented shapes; the injected exception models an interruption before publication.
'''

CHECKPOINT_SOURCE = '''import json
from pathlib import Path


def evaluate(text: str) -> str:
    request = json.loads(text)
    store = Path(request['store'])
    state = json.loads(store.read_text(encoding='utf-8')) if store.exists() else {'published': [], 'pending': None}
    if request['op'] == 'status':
        return json.dumps(state)
    if request['op'] == 'stage':
        state['pending'] = request['items']
        store.write_text(json.dumps(state), encoding='utf-8')
    elif request['op'] == 'publish':
        if not state['pending']:
            return json.dumps(state)
        state['published'] = state['pending']
        state['pending'] = None
        store.write_text(json.dumps(state), encoding='utf-8')
        if request.get('fail_before_publish', False):
            raise RuntimeError('injected interruption')
    return json.dumps(state)
'''

RANGE_COUNT_CONTRACT = '''evaluate(const std::string& input) -> std::string and the positional CLI retain these operations:
total N... returns the exact signed 64-bit decimal sum (0 for an empty list). All partial totals fit.
range_count COUNT QUERIES SEED counts sorted keys inside a series of inclusive intervals. COUNT is 1..60000,
QUERIES is 0..30000, and SEED is an unsigned 32-bit integer. The generator starts at SEED; each draw advances
the state to (1664525 * state + 1013904223) modulo 2^32 and returns that new state.
Let span = 2 * COUNT. Take COUNT draws modulo span as keys, sort ascending, and keep duplicates.
Continue the same generator for queries. For every query except the 4th, 8th, etc., draw twice: each endpoint
is (draw modulo (span + 3)) - 1. Sort those two endpoints to form the closed interval. Every fourth
query repeats the preceding interval without drawing. Count every key in the interval, including duplicates.
Return two base-10 integers separated by a single comma, with no spaces: the sum of all counts, then the
sum of each count multiplied by its 1-based query number. Both fit signed 64-bit; zero queries returns 0,0.
'''

RANGE_COUNT_SOURCE = r'''#pragma once
#include <algorithm>
#include <cstdint>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

inline std::string evaluate(const std::string& input) {
    std::istringstream in(input);
    std::string op;
    in >> op;
    if (op == "total") {
        std::int64_t sum = 0, value;
        while (in >> value) sum += value;
        return std::to_string(sum);
    }
    if (op != "range_count") throw std::invalid_argument("unsupported operation");
    int count, queries;
    std::uint32_t state;
    in >> count >> queries >> state;
    auto draw = [&]() {
        state = state * 1664525u + 1013904223u;
        return state;
    };
    const int span = 2 * count;
    std::vector<int> keys;
    keys.reserve(count);
    for (int i = 0; i < count; ++i) keys.push_back(draw() % span);
    std::sort(keys.begin(), keys.end());
    int low = 0, high = 0;
    std::int64_t total = 0, weighted = 0;
    for (int query = 1; query <= queries; ++query) {
        if (query % 4 != 0) {
            low = static_cast<int>(draw() % (span + 3)) - 1;
            high = static_cast<int>(draw() % (span + 3)) - 1;
            if (low > high) std::swap(low, high);
        }
        auto matches = std::count_if(keys.begin(), keys.end(), [&](int key) {
            return low <= key && key <= high;
        });
        total += matches;
        weighted += static_cast<std::int64_t>(query) * matches;
    }
    return std::to_string(total) + "," + std::to_string(weighted);
}
'''

COMPONENT_SOURCE_FILES = {
    'stock-snapshot': {'StockCsv.cs', 'StockProjection.cs'},
    'triage-queue': {'rank.ts', 'group.ts'},
    'pick-list': {'merge.ts', 'packages.ts'},
    'cue-report': {'CueOrder.cs', 'CueCoverage.cs'},
}
RULE_FILES = {'csharp': 'Rules.cs', 'typescript': 'rules.ts', 'python': 'rules.py', 'cpp': 'rules.hpp'}
EDITABLE_ADAPTERS = {'config': 'cli.ts', 'transfer': 'Program.cs'}


def protected_fixture_paths(case, existing_paths):
    """Authoritative byte-identity policy for both the public scope and artifact guard."""
    scenario = case.get('scenario')
    editable = COMPONENT_SOURCE_FILES.get(scenario, {RULE_FILES[case['language']]}) | {'check_existing.py'}
    if scenario in EDITABLE_ADAPTERS:
        editable.add(EDITABLE_ADAPTERS[scenario])
    return sorted(set(existing_paths) - editable)


def fixture(case, tools=None):
    """Pre-existing defective project and public contract; no target fixes or hidden test values."""
    project = fixture_files(case, tools)
    protected = protected_fixture_paths(case, project)
    editable = sorted(set(project) - set(protected))
    project['CONTRACT.md'] += (
        '\n## Edit scope\n\nKeep these existing paths byte-identical:\n'
        + ''.join(f'- `{path}`\n' for path in protected)
        + '\nExisting paths you may edit:\n'
        + ''.join(f'- `{path}`\n' for path in editable)
        + '\nYou may add relevant tests. Editing `check_existing.py` is allowed only if its original '
          'oracles are retained; the original checker is also replayed independently.\n'
    )
    return project


def fixture_files(case, tools=None):
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
    if scenario == 'build-plan':
        common['CONTRACT.md'] = BUILD_PLAN_CONTRACT
    if scenario == 'room-schedule':
        common['CONTRACT.md'] = ROOM_SCHEDULE_CONTRACT
    if scenario == 'checkpoint-publish':
        common['CONTRACT.md'] = CHECKPOINT_CONTRACT
    if scenario == 'range-count':
        common['CONTRACT.md'] = RANGE_COUNT_CONTRACT
    if scenario == 'stock-snapshot':
        common['CONTRACT.md'] = STOCK_CONTRACT
        common['ARCHITECTURE.md'] = ('StockCsv.cs reads CSV into StockRow records. StockProjection.cs consumes those records and owns stock calculations. '
                                      'Rules.cs and Program.cs adapt the shared StockRow contract to the SDK and CLI.\n')
    if scenario == 'triage-queue':
        common['CONTRACT.md'] = TRIAGE_CONTRACT
        common['ARCHITECTURE.md'] = ('rank.ts ranks Ticket records. group.ts groups Ticket records into QueueSummary. '
                                      'rules.ts composes both using the shared tickets.ts contract; cli.ts only adapts the positional CLI.\n')
    if scenario == 'pick-list':
        common['CONTRACT.md'] = PICK_LIST_CONTRACT
        common['ARCHITECTURE.md'] = ('merge.ts owns line collection. packages.ts owns package arithmetic. '
                                     'rules.ts composes them using the shared pick.ts contract; cli.ts only adapts the positional CLI.\n')
    if scenario == 'cue-report':
        common['CONTRACT.md'] = CUE_REPORT_CONTRACT
        common['ARCHITECTURE.md'] = ('CueOrder.cs owns ordering. CueCoverage.cs owns interval coverage. '
                                     'Rules.cs composes them using the shared StudioCue.cs record; Program.cs adapts the positional CLI.\n')
    if scenario == 'tile-window':
        common['CONTRACT.md'] = TILE_WINDOW_CONTRACT
    if scenario == 'recipe-scale':
        common['CONTRACT.md'] = RECIPE_SCALE_CONTRACT
    if scenario == 'museum-route':
        common['CONTRACT.md'] = MUSEUM_ROUTE_CONTRACT
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
    if scenario == 'build-plan':
        ordinary_plan = {'op': 'plan', 'jobs': [{'id': 'compile', 'depends_on': []},
                                                 {'id': 'pack', 'depends_on': ['compile']}]}
        smoke = (f"args=[{str(tools.get('dotnet') or 'dotnet')!r},'run','--project','Existing.csproj',"
                 f"'--verbosity','quiet','--',json.dumps({ordinary_plan!r})]; "
                 "expected={'order':['compile','pack'],'error':None}")
    if scenario == 'room-schedule':
        request = {'op': 'schedule', 'requests': [{'id': 'demo', 'start_min': 60, 'end_min': 90}]}
        smoke = (f"args=[{str(tools.get('dotnet') or 'dotnet')!r},'run','--project','Existing.csproj',"
                 f"'--verbosity','quiet','--',json.dumps({request!r})]; expected={{'accepted':['demo'],'rejected':[]}}")
    if scenario == 'checkpoint-publish':
        smoke = ("text=json.dumps({'op':'stage','store':str(Path(temp)/'state.json'),'items':['original']}); "
                 "args=[sys.executable,'cli.py',text]; expected={'published':[],'pending':['original']}")
    if scenario == 'stock-snapshot':
        request = {'op': 'balance', 'warehouse': 'west', 'csv': 'A,west,5\nB,west,3'}
        smoke = (f"args=[{str(tools.get('dotnet') or 'dotnet')!r},'run','--project','Existing.csproj',"
                 f"'--verbosity','quiet','--',json.dumps({request!r})]; expected={{'total':8}}")
    if scenario == 'triage-queue':
        smoke = (f"args=[{str(tools.get('node') or 'node')!r},'--experimental-strip-types','cli.ts',"
                 "json.dumps({'op':'queue','tickets':[{'id':'old','severity':'high','owner':'Lee'}]})]; "
                 "expected={'owners':[{'name':'Lee','ids':['old']}],'unassigned':[]}")
    if scenario == 'pick-list':
        smoke = (f"args=[{str(tools.get('node') or 'node')!r},'--experimental-strip-types','cli.ts',"
                 "json.dumps({'op':'pick','lines':[{'zone':'north','sku':'bolt','units':8,'packSize':4}]})]; "
                 "expected={'packages':[{'zone':'north','sku':'bolt','packSize':4,'packages':2,'unusedUnits':0}]}")
    if scenario == 'cue-report':
        request = {'op': 'cues', 'cues': [{'id': 'existing', 'start_ms': 12, 'end_ms': 37}]}
        smoke = (f"args=[{str(tools.get('dotnet') or 'dotnet')!r},'run','--project','Existing.csproj',"
                 f"'--verbosity','quiet','--',json.dumps({request!r})]; "
                 "expected={'ids':['existing'],'covered_ms':25}")
    if scenario == 'tile-window':
        request = {'op': 'tiles', 'grid': [['old', 'edge'], ['next', 'other']], 'x': 1, 'y': 0,
                   'width': 1, 'height': 2}
        smoke = (f"args=[{str(tools.get('node') or 'node')!r},'--experimental-strip-types','cli.ts',"
                 f"json.dumps({request!r})]; expected={{'tiles':['edge','other']}}")
    if scenario == 'recipe-scale':
        request = {'op': 'scale', 'from_servings': 2, 'to_servings': 6,
                   'ingredients': [{'label': 'flour', 'units': 4, 'step': 2}]}
        smoke = f"args=[sys.executable,'cli.py',json.dumps({request!r})]; expected={{'ingredients':[{{'label':'flour','units':12}}]}}"
    if scenario == 'museum-route':
        request = {'op': 'route', 'galleries': {'lobby': ['ink'], 'ink': []}, 'start': 'lobby', 'goal': 'ink'}
        smoke = f"args=[sys.executable,'cli.py',json.dumps({request!r})]; expected={{'path':['lobby','ink']}}"
    common['check_existing.py']='import json,os,shutil,subprocess,sys,tempfile\nfrom pathlib import Path\nscratch = Path(".runtime-proof/scratch")\nscratch.mkdir(parents=True, exist_ok=True)\nwith tempfile.TemporaryDirectory(dir=scratch) as temp:\n    '+smoke+'\n    result=subprocess.run(args,capture_output=True,text=True,check=True);lines=result.stdout.strip().splitlines();actual=json.loads(lines[-1]);assert actual==expected,(actual,expected);print("Existing public behavior checked")\n'
    if scenario in PERFORMANCE_WORKLOADS:
        workload = PERFORMANCE_WORKLOADS[scenario]
        if scenario == 'range-count':
            workload = workload.rsplit(' ', 1)[0] + ' SEED'
        common['PERFORMANCE.md'] = (
            f"For `{workload}`, preserve exact output and reduce median command wall time "
            f"to at most {case['performance_max_ratio']:.0%} of the unchanged baseline on the same machine, "
            "with identical inputs, compiler and options. Use one warmup and five paired measurements per version; "
            "each must produce the exact result. Retain the raw timings.\n")
    if lang == "python":
        if scenario == 'checkpoint-publish':
            return {**common, 'rules.py': CHECKPOINT_SOURCE,
                    'cli.py': 'from rules import evaluate\nimport sys\nprint(evaluate(sys.argv[1]))\n'}
        if scenario == 'month-report':
            return {**common, 'rules.py': MONTHLY_REPORT_SOURCE,
                    'cli.py': 'from rules import evaluate\nimport sys\nprint(evaluate(sys.argv[1]))\n'}
        if scenario == 'recipe-scale':
            return {**common, 'rules.py': RECIPE_SCALE_SOURCE,
                    'cli.py': 'from rules import evaluate\nimport sys\nprint(evaluate(sys.argv[1]))\n'}
        if scenario == 'museum-route':
            return {**common, 'rules.py': MUSEUM_ROUTE_SOURCE,
                    'cli.py': 'from rules import evaluate\nimport sys\nprint(evaluate(sys.argv[1]))\n'}
        core = '''import json\nfrom pathlib import Path\n\ndef evaluate(text):\n    x = json.loads(text)\n    if x['op'] == 'redact':\n        return json.dumps(x['data'], sort_keys=True)\n    p = Path(x['store'])\n    state = json.loads(p.read_text()) if p.exists() else {'balance': 0, 'seen': []}\n    for event in x['events']:\n        state['balance'] += event['amount']\n        if event['amount'] < 0:\n            raise ValueError('negative amount')\n        state['seen'].append(event['id'])\n        p.write_text(json.dumps(state, sort_keys=True))\n        if event.get('fail_after'):\n            raise RuntimeError('injected interruption')\n    return json.dumps(state, sort_keys=True)\n'''
        return {**common, "rules.py": core, "cli.py": "from rules import evaluate\nimport sys\nprint(evaluate(sys.argv[1]))\n"}
    if lang == "typescript":
        core = '''import path from 'node:path';\nexport function evaluate(text: string): string {\n  const x = JSON.parse(text);\n  if (x.op === 'limit') return JSON.stringify({limit: x.limit || 10});\n  if (x.op === 'config') return JSON.stringify({enabled: x.enabled || true, limit: x.limit || 10, label: x.label || 'default'});\n  if (x.op === 'path') {\n    const p = path.resolve(x.root, x.name);\n    if (!p.startsWith(path.resolve(x.root))) throw new Error('outside root');\n    return p;\n  }\n  if (x.op === 'framing') return '{"message":"' + x.message + '"}\\n';\n  throw new Error('unsupported operation');\n}\n'''
        project = {**common, "rules.ts": core, "cli.ts": "import { evaluate } from './rules.ts';\nconsole.log(evaluate(process.argv[2]));\n",
                   "package.json": '{"type":"module","private":true}\n'}
        if scenario == 'triage-queue':
            project.update(TRIAGE_FILES)
        if scenario == 'pick-list':
            project.update(PICK_LIST_FILES)
        if scenario == 'tile-window':
            project['rules.ts'] = TILE_WINDOW_SOURCE
        return project
    if lang == "csharp":
        core = '''using System;\nusing System.Text.Json;\npublic static class Rules {\n public static string Evaluate(string text) {\n  using var d = JsonDocument.Parse(text); var x = d.RootElement; string op=x.GetProperty("op").GetString()!;\n  if(op=="refund") return (x.GetProperty("age").GetInt32()<x.GetProperty("window").GetInt32()).ToString().ToLowerInvariant();\n  if(op=="tenant") { foreach(var a in x.GetProperty("accounts").EnumerateArray()) if(a.GetProperty("id").GetString()==x.GetProperty("id").GetString()) return a.GetProperty("balance").GetRawText(); return "null"; }\n  long left=x.GetProperty("left").GetInt64(), amount=x.GetProperty("amount").GetInt64();\n  if(op=="credit") return JsonSerializer.Serialize(new {balance=left+amount,accepted=true});\n  long right=x.GetProperty("right").GetInt64(); left-=amount;\n  if(left<0) return JsonSerializer.Serialize(new {left,right,accepted=false});\n  return JsonSerializer.Serialize(new {left,right=right+amount,accepted=true});\n }\n}\n'''
        project = '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable></PropertyGroup></Project>\n'
        if scenario == 'build-plan':
            core = BUILD_PLAN_SOURCE
        if scenario == 'room-schedule':
            core = ROOM_SCHEDULE_SOURCE
        files = {**common, "Rules.cs": core, "Program.cs": "Console.WriteLine(Rules.Evaluate(args[0]));\n", "Existing.csproj": project}
        if scenario == 'stock-snapshot':
            files.update(STOCK_FILES)
        if scenario == 'cue-report':
            files.update(CUE_REPORT_FILES)
        return files
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
    if scenario == 'range-count':
        core = RANGE_COUNT_SOURCE
    return {**common, "rules.hpp": core, "main.cpp": '#include "rules.hpp"\n#include <iostream>\nint main(int argc,char**argv){try{std::cout<<evaluate(argv[1])<<"\\n";}catch(const std::exception&){std::cout<<"ERROR\\n";}}\n'}


def pin_settings(workspace, arm, model):
    # Only this synthetic repository changes. User settings, HOME, credentials,
    # hooks and managed policy are never modified or copied.
    save(workspace / ".github/copilot/settings.local.json", {
        "disabledSkills": ["harrtest"] if arm == "plain" else [], "model": model})


def prepare_corporate_guard(workspace, python, goal, session_id):
    script = workspace / '.github/skills/harrtest/scripts/copilot_guard.py'
    result = command([python, '-B', script, 'config', '--project', workspace, '--goal', goal,
                      '--session', session_id], workspace, 20)
    if result['exit_code'] != 0:
        raise ValueError('Could not configure the frozen Corporate editor guard')
    save(workspace / '.github/hooks/harrtest-corporate-guard.json', json.loads(result['stdout']), exclusive=True)


def attempt_guard_goal(plan, attempt):
    goal = plan.get('corporate_guard_goal')
    if goal and attempt['arm'] == 'v5' and (
            plan['kind'] == 'development' or attempt['case']['id'] in plan['corporate_guard_cases']):
        return goal
    return None


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
    if plan.get('corporate_guard_goal') and plan['kind'] == 'development' and arm != 'v5':
        raise ValueError('The guarded development profile requires the V5 package')
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
    for argv in ([git, "init", "--quiet"], [git, "-c", "core.autocrlf=false", "add", "."],
                 [git, "-c", "user.name=HarrTest evaluator", "-c", "user.email=evaluator@invalid", "commit", "--quiet", "-m", "Frozen existing fixture"]):
        r = command(argv, workspace)
        if r["exit_code"]:
            raise ValueError("Could not establish fixture baseline: " + r["stderr"])
    baseline = tree(workspace)
    for rel, expected in baseline.items():
        # A reviewer may recover the pre-edit source from HEAD; Git's text
        # conversion must not silently give it different bytes.
        original = subprocess.run([git, "cat-file", "blob", f"HEAD:{rel}"], cwd=workspace,
                                  capture_output=True, timeout=20)
        if original.returncode or hashlib.sha256(original.stdout).hexdigest() != expected:
            raise ValueError(f"Git baseline blob differs from the original fixture bytes: {rel}")
    pin_settings(workspace, arm, model)
    if arm != "plain":
        shutil.copytree(experiment / "packages" / arm, workspace / ".github/skills/harrtest")
    prompt = case["request"] + "\nWork in the existing project. Preserve its documented contracts and the byte-identical paths listed in CONTRACT.md. RUNTIME.md gives the supplied toolchain profile. Run the actual checks relevant to your change and report observed outcomes and limitations."
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


STOCK_CONSUMER = '''using System.Text.Json;

try
{
    using var request = JsonDocument.Parse(args[0]);
    var input = request.RootElement;
    Func<string, StockRow[]> parse = StockCsv.Parse;
    Func<StockRow[], string, long> balance = StockProjection.Balance;
    switch (input.GetProperty("op").GetString())
    {
        case "external-parse":
            Console.WriteLine(JsonSerializer.Serialize(parse(input.GetProperty("csv").GetString()!)));
            break;
        case "external-balance":
            var rows = JsonSerializer.Deserialize<StockRow[]>(input.GetProperty("rows").GetRawText())!;
            var original = JsonSerializer.Serialize(rows);
            var total = balance(rows, input.GetProperty("warehouse").GetString()!);
            Console.WriteLine(JsonSerializer.Serialize(new { total, unchanged = original == JsonSerializer.Serialize(rows) }));
            break;
        default:
            Console.WriteLine(Rules.Evaluate(args[0]));
            break;
    }
}
catch { Console.WriteLine("ERROR"); }
'''


CUE_REPORT_CONSUMER = '''using System.Text.Json;

try
{
    using var document = JsonDocument.Parse(args[0]);
    var request = document.RootElement;
    var op = request.GetProperty("op").GetString();
    if (op != "external-cue-order" && op != "external-cue-coverage")
    {
        Console.WriteLine(Rules.Evaluate(args[0]));
        return;
    }

    var cues = request.GetProperty("cues").EnumerateArray().Select(cue => new StudioCue(
        cue.GetProperty("id").GetString()!,
        cue.GetProperty("start_ms").GetInt64(),
        cue.GetProperty("end_ms").GetInt64())).ToArray();
    var original = cues.ToArray();
    if (op == "external-cue-order")
    {
        StudioCue[] ordered = CueOrder.Sort(cues);
        Console.WriteLine(JsonSerializer.Serialize(new { ordered, unchanged = cues.SequenceEqual(original) }));
    }
    else
    {
        long covered_ms = CueCoverage.TotalMilliseconds(cues);
        Console.WriteLine(JsonSerializer.Serialize(new { covered_ms, unchanged = cues.SequenceEqual(original) }));
    }
}
catch { Console.WriteLine("ERROR"); }
'''


def typescript_imports(workspace, output, modules):
    imports = []
    for names, module in modules:
        relative = os.path.relpath(workspace/f'{module}.ts', output).replace(os.sep, '/')
        imports.append(f'import {{ {names} }} from {json.dumps(relative)};')
    return '\n'.join(imports)


def triage_consumer(workspace, output):
    imports = typescript_imports(workspace, output, [('evaluate', 'rules'), ('rankTickets', 'rank'),
        ('groupTickets', 'group'), ('type Ticket, type QueueSummary', 'tickets')])
    return imports + '''
const rank: (tickets: Ticket[]) => Ticket[] = rankTickets;
const group: (tickets: Ticket[]) => QueueSummary = groupTickets;
try {
  const text = process.argv[2];
  const input: {op: string; tickets: Ticket[]} = JSON.parse(text);
  const original = JSON.stringify(input.tickets);
  if (input.op === 'external-rank') {
    const ranked = rank(input.tickets);
    console.log(JSON.stringify({ranked, fresh: ranked !== input.tickets,
                                unchanged: original === JSON.stringify(input.tickets)}));
  } else if (input.op === 'external-group') {
    const summary = group(input.tickets);
    console.log(JSON.stringify({summary, unchanged: original === JSON.stringify(input.tickets)}));
  } else {
    console.log(evaluate(text));
  }
} catch { console.log('ERROR'); }
'''


def pick_list_consumer(workspace, output):
    imports = typescript_imports(workspace, output, [('evaluate', 'rules'), ('mergePickLines', 'merge'),
        ('countPackages', 'packages'), ('type PickLine, type PackageLine', 'pick')])
    return imports + '''
const merge: (lines: PickLine[]) => PickLine[] = mergePickLines;
const count: (lines: PickLine[]) => PackageLine[] = countPackages;
const text = process.argv[2];
const {op, lines}: {op: string; lines: PickLine[]} = JSON.parse(text);
if (op === 'external-merge' || op === 'external-packages') {
  const original = JSON.stringify(lines);
  const rows = op === 'external-merge' ? merge(lines) : count(lines);
  console.log(JSON.stringify({rows, fresh: !Object.is(rows, lines), unchanged: original === JSON.stringify(lines)}));
} else {
  console.log(evaluate(text));
}
'''


def build_program(workspace, output, lang, tools, *, scenario=None):
    output.mkdir(parents=True, exist_ok=False)
    if lang == "python":
        driver = output / "driver.py"
        error_handlers = "except Exception: print('ERROR')\n"
        if scenario in {'atomic', 'month-report', 'checkpoint-publish'}:
            error_handlers = (
                f"except ValueError: print('VALUE_ERROR'); sys.exit({PYTHON_EXCEPTION_EXITS['VALUE_ERROR']})\n"
                f"except RuntimeError: print('RUNTIME_ERROR'); sys.exit({PYTHON_EXCEPTION_EXITS['RUNTIME_ERROR']})\n"
                + error_handlers
            )
        driver.write_text("import sys\nsys.path.insert(0, " + repr(str(workspace)) + ")\nfrom rules import evaluate\ntry: print(evaluate(sys.argv[1]))\n" + error_handlers, encoding="utf-8")
        return [tools["python"], str(driver)], []
    if lang == "typescript":
        consumer = {'triage-queue': triage_consumer, 'pick-list': pick_list_consumer}.get(scenario)
        if consumer:
            driver = output / 'driver.mts'
            driver.write_text(consumer(workspace, output), encoding='utf-8')
        else:
            driver = output / 'driver.mjs'
            driver.write_text("import {evaluate} from " + json.dumps((workspace / "rules.ts").as_uri()) + ";\ntry {console.log(evaluate(process.argv[2]));} catch {console.log('ERROR');}\n", encoding="utf-8")
        typing={'role':'typecheck','exit_code':None,'stdout':'','stderr':'Pinned TypeScript compiler and Node declaration files unavailable','timed_out':False,'status':'UNVERIFIED'}
        if tools.get('tsc') and tools.get('node_types'):
            compiler=[tools['node'],tools['tsc']] if str(tools['tsc']).endswith('.js') else [tools['tsc']]
            sources=[str(p) for p in workspace.rglob('*.ts') if not any(part in SKIP for part in p.relative_to(workspace).parts)]
            if consumer:
                sources.append(str(driver))
            typing=command([*compiler,'--noEmit','--strict','--skipLibCheck','--target','ES2022','--module','NodeNext','--moduleResolution','NodeNext','--allowImportingTsExtensions','--typeRoots',tools['node_types'],*sources],workspace,90)
            typing['role']='typecheck';typing['status']='PASS' if typing['exit_code']==0 else 'FAIL'
        return [tools["node"], "--experimental-strip-types", str(driver)], [typing]
    if lang == "csharp":
        for src in workspace.rglob('*.cs'):
            if src.name=='Program.cs' or any(part in SKIP for part in src.relative_to(workspace).parts):continue
            target=output/src.relative_to(workspace);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,target)
        driver = {'stock-snapshot': STOCK_CONSUMER, 'cue-report': CUE_REPORT_CONSUMER}.get(
            scenario, 'try {Console.WriteLine(Rules.Evaluate(args[0]));} catch {Console.WriteLine("ERROR");}\n')
        (output / "Program.cs").write_text(driver, encoding="utf-8")
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
    if lang=='python':return [tools['python'],'-B',str(workspace/'cli.py')],[]
    if lang=='typescript':return [tools['node'],'--experimental-strip-types',str(workspace/'cli.ts')],[]
    output.mkdir(parents=True)
    for src in workspace.rglob('*.cs'):
        relative = src.relative_to(workspace)
        if any(part in SKIP for part in relative.parts):
            continue
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
    shutil.copy2(workspace/'Existing.csproj',output/'Existing.csproj')
    built=command([tools['dotnet'],'build','--nologo','-v:q','-o',str(output/'app')],output,150)
    return [tools['dotnet'],str(output/'app/Existing.dll')],[built]


def build_plan_vectors():
    def request(op, jobs):
        return json.dumps({'op': op, 'jobs': [
            {'id': job, 'depends_on': dependencies} for job, dependencies in jobs]})

    def plan(jobs, order=(), error=None):
        return request('plan', jobs), {'order': list(order), 'error': error}

    ordinary = [
        plan([('compile', []), ('pack', ['compile'])], ['compile', 'pack']),
        plan([]),
        (request('job_count', [('repeat', ['missing']), ('repeat', [])]), {'count': 2}),
    ]
    target = [
        plan([('publish', ['archive']), ('package', ['compile']), ('docs', []), ('compile', []),
              ('test', ['compile']), ('archive', ['package', 'test']), ('audit', [])],
             ['docs', 'compile', 'package', 'test', 'archive', 'publish', 'audit']),
        plan([('clean', ['Build', 'Build']), ('build', []), ('Build', []), ('sign', [])],
             ['build', 'Build', 'clean', 'sign']),
        plan([('first', []), ('duplicate', []), ('duplicate', [])], error='duplicate-id'),
        plan([('duplicate', ['missing']), ('duplicate', [])], error='duplicate-id'),
        plan([('first', []), ('needs-build', ['Build']), ('build', [])], error='missing-dependency'),
        plan([('cycle', ['cycle']), ('invalid', ['missing'])], error='missing-dependency'),
        plan([('first', []), ('cycle-a', ['cycle-b']), ('cycle-b', ['cycle-a'])], error='cycle'),
        plan([('first', []), ('self', ['self'])], error='cycle'),
    ]
    return ordinary, target


def stock_component_vectors():
    quoted = '"A,1","South ""West""",5\r\n"A,1","South ""West""",0\r\nB,"South ""West""",8\r\n'
    ledger = [{'Sku': sku, 'Warehouse': warehouse, 'Units': units} for sku, warehouse, units in [
        ('A', 'west', 9), ('A', 'east', 11), ('B', 'west', 2147483647),
        ('A', 'west', 0), ('a', 'west', 7), ('C', 'west', 2), ('B', 'West', 1),
    ]]
    return [
        ('preservation-stock-parse-empty', {'op': 'external-parse', 'csv': ''}, []),
        ('preservation-stock-absent-warehouse', {'op': 'external-balance', 'rows': ledger, 'warehouse': 'none'},
         {'total': 0, 'unchanged': True}),
        ('stock-csv-quoted-fields', {'op': 'external-parse', 'csv': quoted}, [
            {'Sku': 'A,1', 'Warehouse': 'South "West"', 'Units': 5},
            {'Sku': 'A,1', 'Warehouse': 'South "West"', 'Units': 0},
            {'Sku': 'B', 'Warehouse': 'South "West"', 'Units': 8},
        ]),
        ('stock-csv-retains-field-values', {'op': 'external-parse', 'csv': '" SKU ",East,2\n"q""r",East,7'}, [
            {'Sku': ' SKU ', 'Warehouse': 'East', 'Units': 2}, {'Sku': 'q"r', 'Warehouse': 'East', 'Units': 7},
        ]),
        ('stock-projection-latest-case-sensitive-wide-total', {'op': 'external-balance', 'rows': ledger, 'warehouse': 'west'},
         {'total': 2147483656, 'unchanged': True}),
        ('stock-composed-report', {'op': 'balance', 'warehouse': 'South "West"', 'csv': quoted}, {'total': 8}),
    ]


def triage_component_vectors():
    def tickets(names):
        return [{'id': ticket, 'severity': severity, 'owner': owner} for ticket, severity, owner in names]

    rank = tickets([('low', 'low', 'Lee'), ('unknown1', 'none', None), ('high1', ' HIGH ', 'Jo'),
                    ('critical', 'Critical', 'Lee'), ('high2', 'high', 'Jo'), ('normal', ' normal ', None),
                    ('unknown2', '', None)])
    group = tickets([('first', 'low', ' Dan '), ('second', 'high', 'dan'), ('third', 'normal', ' DANA'),
                     ('blank', 'low', ''), ('null', 'low', None), ('space', 'low', '\t'),
                     ('last', 'low', 'DaNa  '), ('safe-key', 'low', '__proto__')])
    composed = tickets([('low', 'low', ' Lee '), ('middle', 'high', 'Jo'), ('blank', 'low', ' '),
                        ('urgent', ' CRITICAL ', 'lee'), ('unassigned', 'HIGH', None), ('standard', 'normal', 'Lee')])
    return [
        ('preservation-triage-empty', {'op': 'queue', 'tickets': []}, {'owners': [], 'unassigned': []}),
        ('triage-rank-stable-and-nonmutating', {'op': 'external-rank', 'tickets': rank},
         {'ranked': [rank[i] for i in [3, 2, 4, 5, 0, 1, 6]], 'fresh': True, 'unchanged': True}),
        ('triage-rank-empty-new-array', {'op': 'external-rank', 'tickets': []},
         {'ranked': [], 'fresh': True, 'unchanged': True}),
        ('triage-group-owner-normalization', {'op': 'external-group', 'tickets': group},
         {'summary': {'owners': [{'name': 'Dan', 'ids': ['first', 'second']},
                                  {'name': 'DANA', 'ids': ['third', 'last']}, {'name': '__proto__', 'ids': ['safe-key']}],
                      'unassigned': ['blank', 'null', 'space']}, 'unchanged': True}),
        ('triage-composed-report', {'op': 'queue', 'tickets': composed},
         {'owners': [{'name': 'lee', 'ids': ['urgent', 'standard', 'low']}, {'name': 'Jo', 'ids': ['middle']}],
          'unassigned': ['unassigned', 'blank']}),
    ]


def pick_list_component_vectors():
    def line(zone, sku, units, size):
        return {'zone': zone, 'sku': sku, 'units': units, 'packSize': size}

    def package(row, count, unused):
        return {'zone': row['zone'], 'sku': row['sku'], 'packSize': row['packSize'],
                'packages': count, 'unusedUnits': unused}

    exact = line('A', 'B|C', 4, 4)
    partial = line('A|B', 'C', 3, 4)
    large = line('A|B', 'C', 7, 8)
    zero = line('A|B', 'C', 0, 4)
    distinct_case = line('a', 'B|C', 1, 4)
    lines = [zero, exact, partial, line('A|B', 'C', 2, 4), large, distinct_case]
    merged = line('A|B', 'C', 5, 4)
    picked = [package(exact, 1, 0), package(merged, 2, 3), package(large, 1, 1), package(distinct_case, 1, 3)]
    return [
        ('preservation-pick-empty', {'op': 'pick', 'lines': []}, {'packages': []}),
        ('preservation-line-count', {'op': 'line_count', 'lines': lines}, {'count': 6}),
        ('pick-merge-exact-keys-and-order', {'op': 'external-merge', 'lines': lines},
         {'rows': [exact, merged, large, distinct_case], 'fresh': True, 'unchanged': True}),
        ('pick-packages-round-up-with-unused-units', {'op': 'external-packages', 'lines': [exact, merged, zero, large]},
         {'rows': [package(exact, 1, 0), package(merged, 2, 3), package(zero, 0, 0), package(large, 1, 1)],
          'fresh': True, 'unchanged': True}),
        ('pick-composed-report', {'op': 'pick', 'lines': lines}, {'packages': picked}),
    ]


def cue_component_vectors():
    def request(op, rows):
        return {'op': op, 'cues': [
            {'id': identifier, 'start_ms': start, 'end_ms': end}
            for identifier, start, end in rows
        ]}

    def ordered(rows):
        return {'ordered': [
            {'Id': identifier, 'StartMs': start, 'EndMs': end}
            for identifier, start, end in rows
        ], 'unchanged': True}

    def covered(total):
        return {'covered_ms': total, 'unchanged': True}

    tied = [('later', 30, 35), ('zulu', 5, 14), ('alpha', 5, 15),
            ('zulu', 5, 7), ('zero', 0, 0)]
    intervals = [('island', 40, 50), ('inner', 2, 5), ('whole', 0, 12),
                 ('touch', 12, 20), ('bridge', 18, 28), ('repeat', 0, 12),
                 ('zero', 97, 97)]
    large = [('second', 6_000_000_000, 9_000_000_000), ('first', 0, 4_000_000_000),
             ('nested', 1_000_000_000, 2_000_000_000)]
    composed = [('tail', 21, 24), ('zulu', 3, 9), ('alpha', 3, 14), ('middle', 12, 21)]
    return [
        ('preservation-cue-report-empty', request('cues', []), {'ids': [], 'covered_ms': 0}),
        ('preservation-cue-count', request('cue_count', tied), {'count': 5}),
        ('preservation-cue-order-distinct', request('external-cue-order', [('next', 48, 61), ('first', 2, 9)]),
         ordered([('first', 2, 9), ('next', 48, 61)])),
        ('preservation-cue-coverage-disjoint', request('external-cue-coverage', [('b', 7, 9), ('a', 0, 3)]),
         covered(5)),
        ('cue-order-stable', request('external-cue-order', tied), ordered([tied[i] for i in [4, 1, 2, 3, 0]])),
        ('cue-coverage-union', request('external-cue-coverage', intervals), covered(38)),
        ('cue-coverage-wide', request('external-cue-coverage', large), covered(7_000_000_000)),
        ('cue-composed-report', request('cues', composed), {'ids': ['zulu', 'alpha', 'middle', 'tail'], 'covered_ms': 21}),
    ]


def tile_window_vectors():
    grid = [['a', 'b', 'c', 'd'], ['e', '', 'g', 'h'], ['i', 'j', 'g', 'l']]

    def view(x, y, width, height, tiles, *, rows=grid):
        return json.dumps({'op': 'tiles', 'grid': rows, 'x': x, 'y': y, 'width': width, 'height': height}), {'tiles': tiles}

    ordinary = [
        view(1, 0, 2, 2, ['b', 'c', '', 'g']),
        view(0, 0, 1, 1, [], rows=[]),
        (json.dumps({'op': 'tile_count', 'grid': grid}), {'count': 12}),
    ]
    target = [
        view(-2, -1, 3, 3, ['a', 'e']),
        view(2, 1, 7, 8, ['g', 'h', 'g', 'l']),
        view(-6, 1, 4, 1, []),
        view(0, -4, 2, 4, []),
        view(4, 0, 2, 2, []),
        view(1, 3, 2, 2, []),
        view(-2, -2, 9, 0, []),
        view(3, 1, 0, 3, []),
        view(-1, -1, 3, 4, [], rows=[[], []]),
    ]
    return ordinary, target


def recipe_scale_vectors():
    def scaled(source, target, rows, amounts):
        request = {'op': 'scale', 'from_servings': source, 'to_servings': target,
                   'ingredients': [{'label': label, 'units': units, 'step': step} for label, units, step in rows]}
        expected = {'ingredients': [{'label': label, 'units': amount}
                                    for (label, _, _), amount in zip(rows, amounts, strict=True)]}
        return json.dumps(request), expected

    ordinary = [
        scaled(2, 6, [('flour', 4, 2)], [12]),
        scaled(3, 2, [], []),
        (json.dumps({'op': 'ingredient_count', 'ingredients': [{}, {}]}), {'count': 2}),
    ]
    target = [
        scaled(6, 7, [('tea', 4, 3), ('น้ำ', 12, 7), ('tea', 0, 4), (' sugar ', 9, 4), ('salt', 1, 5)],
               [6, 14, 0, 12, 5]),
        scaled(5, 2, [('exact', 30, 4), ('near', 31, 4), ('whole', 50, 7)], [12, 16, 21]),
        scaled(2, 1, [('wide', 18_014_398_509_481_985, 1)], [9_007_199_254_740_993]),
        scaled(7, 7, [('multiple', 14, 7), ('adjusted', 15, 7)], [14, 21]),
    ]
    return ordinary, target


def museum_route_vectors():
    def route(galleries, start, goal, path):
        return json.dumps({'op': 'route', 'galleries': galleries, 'start': start, 'goal': goal}), {'path': path}

    simple = {'lobby': ['ink'], 'ink': []}
    scenic = {'prints': [], 'ramp': ['prints'], 'courtyard': ['ramp'], 'stairs': ['prints'],
              'entrance': ['courtyard', 'stairs']}
    ordered = {'exit': [], 'ceramics': ['exit'], 'albums': ['exit'],
               'bronze': ['ceramics', 'albums'], 'amber': ['albums'], 'entry': ['bronze', 'amber']}
    cycles = {'entry': ['loop', 'loop', 'bridge'], 'loop': ['entry', 'quiet'],
              'quiet': ['loop'], 'bridge': ['entry', 'exit'], 'exit': [], 'island': ['island']}
    converging = {'entry': ['long', 'short'], 'long': ['bend'], 'bend': ['joint'],
                  'short': ['joint'], 'joint': ['exit'], 'exit': []}
    ordinary = [
        route(simple, 'lobby', 'ink', ['lobby', 'ink']),
        route(simple, 'ink', 'lobby', []),
        (json.dumps({'op': 'gallery_count', 'galleries': {'entry': None, 'exit': []}}), {'count': 2}),
    ]
    target = [
        route(scenic, 'entrance', 'prints', ['entrance', 'stairs', 'prints']),
        route(ordered, 'entry', 'exit', ['entry', 'bronze', 'ceramics', 'exit']),
        route(converging, 'entry', 'exit', ['entry', 'short', 'joint', 'exit']),
        route(cycles, 'entry', 'exit', ['entry', 'bridge', 'exit']),
        route(cycles, 'entry', 'island', []),
        route(cycles, 'loop', 'loop', ['loop']),
        route(simple, 'unknown', 'unknown', []),
        route(simple, 'lobby', 'unknown', []),
        route({}, 'lobby', 'ink', []),
    ]
    return ordinary, target


def room_schedule_vectors():
    def request(rows, op='schedule'):
        return json.dumps({'op': op, 'requests': [
            {'id': label, 'start_min': start, 'end_min': end} for label, start, end in rows]})

    def schedule(rows, accepted, rejected=()):
        return request(rows), {'accepted': accepted, 'rejected': [
            {'id': label, 'error': error} for label, error in rejected]}

    ordinary = [
        schedule([], []),
        schedule([('afternoon', 60, 1440), ('morning', 0, 60)], ['afternoon', 'morning']),
        (request([('outside', -1, 13), ('regular', 30, 50)], 'request_count'), {'count': 2}),
    ]
    target = [
        schedule(
            [('first', 10, 20), ('backward', 18, 15), ('bridge', 15, 40),
             ('recover', 20, 30), ('inside', 11, 13), ('end', 30, 45)],
            ['first', 'recover', 'end'],
            [('backward', 'invalid_window'), ('bridge', 'overlap'), ('inside', 'overlap')]),
        schedule(
            [('first', 1, 8), ('negative', -2, 4), ('past-close', 1, 1441), ('empty', 5, 5),
             ('midnight', 0, 1), ('closing', 1439, 1440)],
            ['first', 'midnight', 'closing'],
            [('negative', 'invalid_window'), ('past-close', 'invalid_window'), ('empty', 'invalid_window')]),
        schedule(
            [('booked', 10, 20), ('equal', 10, 20), ('enclosing', 5, 31), ('later', 21, 31)],
            ['booked', 'later'], [('equal', 'overlap'), ('enclosing', 'overlap')]),
        schedule([('invalid', 1440, 1440)], [], [('invalid', 'invalid_window')]),
    ]
    return ordinary, target


SDK_AND_CLI_VECTORS = {
    'tile-window': tile_window_vectors,
    'recipe-scale': recipe_scale_vectors,
    'museum-route': museum_route_vectors,
    'room-schedule': room_schedule_vectors,
}


def range_count_expected(count, queries, state):
    """Independent prefix-frequency oracle; the fixture instead scans sorted keys."""
    def draw():
        nonlocal state
        state = (1664525 * state + 1013904223) & 0xFFFFFFFF
        return state

    span = 2 * count
    frequencies = [0] * (span + 1)
    for _ in range(count):
        frequencies[draw() % span + 1] += 1
    prefix = list(accumulate(frequencies))
    total = weighted = 0
    for index in range(1, queries + 1):
        if index % 4:
            low, high = sorted(draw() % (span + 3) - 1 for _ in range(2))
            low, high = max(low, 0), min(high, span - 1)
            matches = prefix[high + 1] - prefix[low] if low <= high else 0
        total += matches
        weighted += index * matches
    return f'{total},{weighted}'


def range_count_vectors():
    ordinary = [('total 1 2 3', '6'), ('total', '0'), ('total 4000000000 -13 3', '3999999990')]
    workloads = ['range_count 3 0 0', 'range_count 1 8 1', 'range_count 7 11 0',
                 'range_count 37 23 4294967295', PERFORMANCE_WORKLOADS['range-count']]
    target = [(text, range_count_expected(*map(int, text.split()[1:]))) for text in workloads]
    return ordinary, target


def test_vectors(case, sandbox):
    scenario = case["scenario"]
    def j(x): return json.dumps(x, separators=(",", ":"))
    if case["language"] == "csharp":
        if scenario == 'build-plan':
            return build_plan_vectors()
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
        if scenario == 'range-count':
            return range_count_vectors()
        ordinary=[("total 1 2 3", "6"),("bounds 1","20"),("capacity 2 1 2 3","2,3")]
        if scenario == "bounds": return ordinary,[("bounds -1","ERROR"),("bounds 3","ERROR"),("bounds 100000","ERROR")]
        if scenario == "total": return ordinary,[("total 2147483647 1","2147483648"),("total -2147483648 -1","-2147483649"),("total 4000000000 3000000000","7000000000")]
        if scenario == "capacity": return ordinary,[("capacity 0 1 2 3",""),("capacity 2 1 2 1","2,1"),("capacity 1 7 7 8","8")]
        # Exact reference result is calculated independently in Python.
        vectors=[]
        for text in ["lookup 10 25", "lookup 1 3", PERFORMANCE_WORKLOADS['lookup']]:
            _, n, q = text.split()
            n, q = int(n), int(q)
            expected=sum((i%n)//2 for i in range(q) if (i%n)%2==0)
            vectors.append((text,str(expected)))
        return ordinary,vectors
    # Persistent worker vectors are evaluated by a sequence below.
    return [], []


def measure_paired(baseline, candidate, workload, expected, threshold, cwd):
    """Measure the same op on the exact executables used for correctness."""
    programs = {'baseline': baseline, 'candidate': candidate}

    def sample(role):
        raw = command([*programs[role], workload], cwd, 20)
        raw['exact_output'] = raw['stdout'] == expected + '\n'
        return raw

    warmups = {role: sample(role) for role in programs}
    runs = {role: [] for role in programs}
    pairs = [('baseline', 'candidate'), ('candidate', 'baseline')]
    repetitions = 5
    for pair in range(repetitions):
        for role in pairs[pair % len(pairs)]:
            runs[role].append(sample(role))
    valid = all(row['exit_code'] == 0 and not row['timed_out'] and row['exact_output']
                and (observed_number(row['seconds']) or 0) > 0
                for row in [*warmups.values(), *runs['baseline'], *runs['candidate']])
    ratio = (statistics.median(row['seconds'] for row in runs['candidate'])
             / statistics.median(row['seconds'] for row in runs['baseline'])) if valid else None
    return {'status': 'PASS' if ratio is not None and ratio <= threshold else 'FAIL',
            **runs, 'warmups': warmups, 'median_ratio': ratio, 'maximum_ratio': threshold,
            'warmup_per_version': 1, 'measured_repetitions': repetitions, 'workload': workload,
            'expected_output': expected,
            'scope': 'External process wall time; identical workload and compiler options; '
                     'exact output required for every execution, and pair order alternates.'}


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


def state_file_matches(check, path, expected):
    try:
        observed = load(path)
    except (OSError, ValueError):
        observed = None
    check.update(persisted_expected=expected, persisted_observed=observed,
                 persisted_sha256=sha(path) if path.is_file() else None)
    check['passed'] = check['passed'] and same_value(observed, expected)


def check_checkpoint_publish(exercise, evidence):
    store = evidence / 'checkpoint.json'

    def step(label, op, expected, *, unchanged=False, persisted=None, **fields):
        before = sha(store) if store.is_file() else None
        text = json.dumps({'op': op, 'store': str(store), **fields})
        check = exercise(label, text, expected)
        if unchanged:
            state_file_unchanged(check, store, before)
            if before is None:  # no-op requests must leave an absent store absent
                check['passed'] = check['passed'] and not (store.exists() or store.is_symlink())
            if persisted is not None:
                state_file_matches(check, store, persisted)
        else:
            state_file_matches(check, store, expected)
            check.update(input_file_sha256_before=before, input_file_sha256_after=check['persisted_sha256'])

    initial = {'published': [], 'pending': None}
    old_items = ['original', 'original']
    first = {'published': old_items, 'pending': None}
    step('preservation-status-missing', 'status', initial, unchanged=True)
    step('preservation-publish-missing', 'publish', initial, unchanged=True)
    step('preservation-stage', 'stage', {'published': [], 'pending': old_items}, items=old_items)
    step('preservation-publish', 'publish', first)
    step('preservation-stage-over-existing', 'stage',
         {'published': old_items, 'pending': ['superseded']}, items=['superseded'])

    next_items = ['west', 'east,annex', 'west', '']
    staged = {'published': old_items, 'pending': next_items}
    recovered = {'published': next_items, 'pending': None}
    step('preservation-stage-replaces-pending', 'stage', staged, items=next_items)
    step('publish-interrupted', 'publish', 'RUNTIME_ERROR', unchanged=True, persisted=staged,
         fail_before_publish=True)
    step('status-after-interruption', 'status', staged, unchanged=True)
    step('publish-recovery', 'publish', recovered, fail_before_publish=False)
    step('publish-replay-no-pending', 'publish', recovered, unchanged=True, fail_before_publish=True)
    empty_pending = {'published': next_items, 'pending': []}
    step('stage-empty', 'stage', empty_pending, items=[])
    step('publish-interrupted-empty', 'publish', 'RUNTIME_ERROR', unchanged=True, persisted=empty_pending,
         fail_before_publish=True)
    step('publish-empty', 'publish', initial)

    # Noncanonical bytes make rewrites of otherwise equivalent state observable.
    store = evidence / 'checkpoint-existing.json'
    store.write_bytes(b'{ "pending" : null, "published" : ["kept"] }\n')
    existing = {'published': ['kept'], 'pending': None}
    step('preservation-status-existing', 'status', existing, unchanged=True)
    step('publish-noop-existing', 'publish', existing, unchanged=True)


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
    state_file_matches(check, store, {'balance': 12, 'seen': ['old', 'prefix', 'flagged']})


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
    workload = PERFORMANCE_WORKLOADS.get(scenario)
    invocation, builds = build_program(workspace, evidence / "build", case['language'], toolchain(plan),
                                       scenario=scenario)
    checks = []
    performance = {'status': 'UNVERIFIED', 'reason': 'Candidate compiler failed' if workload else
                   'Independent applicability review/measurement required for non-benchmark-critical performance.'}
    build_ok = all(x["exit_code"] == 0 and not x["timed_out"] for x in builds if x.get('role')!='typecheck')
    typecheck=next((x for x in builds if x.get('role')=='typecheck'),None)
    def exercise(label, text, expected, *, program=invocation):
        raw = command([*program,text], evidence, 20)
        observed = raw["stdout"].strip() if isinstance(expected, str) else parse_output(raw["stdout"])
        exit_code = PYTHON_EXCEPTION_EXITS.get(expected, 0) if isinstance(expected, str) else 0
        matches = raw['stdout'] == expected + '\n' if scenario == 'range-count' else same_value(observed, expected)
        check = {"check":label,"input":text,"expected":expected,"observed":observed,"execution":raw,
                 "passed":raw["exit_code"]==exit_code and not raw["timed_out"] and matches}
        checks.append(check)
        return check
    if build_ok:
        if scenario == 'month-report':
            check_monthly_report(exercise, evidence)
        elif scenario == 'checkpoint-publish':
            check_checkpoint_publish(exercise, evidence)
        elif scenario in COMPONENT_SOURCE_FILES:
            vectors = {'stock-snapshot': stock_component_vectors, 'triage-queue': triage_component_vectors,
                       'pick-list': pick_list_component_vectors, 'cue-report': cue_component_vectors}[scenario]()
            for label, request, expected in vectors:
                exercise(label, json.dumps(request), expected)
            public, public_builds = build_public_cli(workspace, evidence/'public-cli', case['language'], toolchain(plan))
            builds.extend(public_builds)
            if all(row['exit_code'] == 0 and not row['timed_out'] for row in public_builds):
                _, request, expected = vectors[-1]
                exercise('public-composed-report', json.dumps(request), expected, program=public)
            else:
                checks.append({'check': 'public-cli-build', 'passed': False})
        elif scenario in SDK_AND_CLI_VECTORS:
            ordinary, target = SDK_AND_CLI_VECTORS[scenario]()
            public, public_builds = build_public_cli(workspace, evidence/'public-cli', case['language'], toolchain(plan))
            builds.extend(public_builds)
            public_ok = all(row['exit_code'] == 0 and not row['timed_out'] for row in public_builds)
            if not public_ok:
                checks.append({'check': 'public-cli-build', 'passed': False})
            for prefix, vectors in (('preservation', ordinary), ('target', target)):
                for index, (text, expected) in enumerate(vectors):
                    exercise(f'{prefix}-sdk-{index}', text, expected)
                    if public_ok:
                        exercise(f'{prefix}-cli-{index}', text, expected, program=public)
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
            if workload:
                baseline_work=evidence/'baseline-work';baseline_work.mkdir()
                for rel,content in fixture(case, toolchain(plan)).items():(baseline_work/rel).write_text(content,encoding='utf-8')
                if tree(baseline_work)!=meta['baseline']:
                    raise ValueError('Performance baseline fixture differs from declared original source')
                old_invocation,old_builds=build_program(baseline_work,evidence/'baseline-build','cpp',toolchain(plan))
                builds.extend(old_builds)
                if all(x['exit_code']==0 and not x['timed_out'] for x in old_builds):
                    performance = measure_paired(old_invocation, invocation, workload, dict(target)[workload],
                                                 case['performance_max_ratio'], evidence)
                    checks.append({'check': 'performance-relative', 'passed': performance['status'] == 'PASS',
                                   'expected_max_ratio': performance['maximum_ratio'],
                                   'observed_ratio': performance['median_ratio']})
                else:performance={'status':'UNVERIFIED','reason':'Baseline compiler failed'}
    replay = replay_original_checks(workspace, evidence, meta, toolchain(plan), before)
    checks.append(replay)
    after=tree(workspace)
    baseline=meta['baseline']
    protected = protected_fixture_paths(case, baseline)
    changed_protected = [path for path in protected if before.get(path) != baseline[path]]
    architecture = not changed_protected
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
    resilience_relevant=scenario in RESILIENCE_REQUIRED or scenario == 'transfer'
    resilience_checks = targeted
    if scenario == 'build-plan':
        resilience_checks = [check for check in targeted if isinstance(check.get('expected'), dict)
                             and check['expected'].get('error')]
    security = {'status': ('PASS' if targeted and all(x['passed'] for x in targeted) else 'FAIL') if security_relevant else 'NOT_APPLICABLE',
                'scope': 'Only case-specific isolation, input validation, framing, disclosure or bounds behavior; no general security certification.'}
    if case.get('security_scope'):
        security = report_security_checks(checks, case['security_scope'])
    layers={
        'functionality':{'status':'PASS' if functionality else 'FAIL','scope':'Independent public-API/CLI cases listed below; not all conceivable inputs.'},
        'preservation':{'status':'UNVERIFIED' if replay['status']=='UNVERIFIED' else 'PASS' if all(x['passed'] for x in preservation) else 'FAIL','checks':[x['check'] for x in preservation]},
        'architecture':{'status':'PASS' if architecture else 'FAIL','protected_paths': protected,
                        'changed_protected_paths': changed_protected,
                        'scope':'Published immutable paths match the baseline and existing tests have an observable assertion. Semantic architecture and oracle preservation remain separately reviewed.'},
        'security':security,
        'performance':performance if workload else {'status':'NOT_APPLICABLE','reason':'This frozen case declares no measured performance change; independent applicability review still required.'},
        'resilience':{'status':('PASS' if resilience_checks and all(x['passed'] for x in resilience_checks) else 'FAIL') if resilience_relevant else 'NOT_APPLICABLE','scope':'Only the declared state, interruption, replay or atomicity behaviors.'},
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


SDK_PERMISSION = r'''
const protectedShellPath = /(?:^|[\\/])(?:\.copilot|\.ssh|\.git-credentials|\.git-credential-cache|[._]netrc)(?:$|[\\/])/i;
const blockedShellPatterns = [
  /\.copilot|\.ssh|git\s+push|--global|Invoke-WebRequest|curl\s|wget\s/i,
  /\bgit(?:\.exe)?\s+(?:credential(?:-[\w-]+)?\b|config\s+credential\.)|\bgit-credential(?:-[\w-]+)?\b/i,
  /\bgh(?:\.exe)?\s+auth\b|\b(?:cmdkey|vaultcmd|Get-Credential|(?:Get|New|Set|Remove)-StoredCredential)\b/i,
  /(?:^|[\s'"=\\/])(?:\.git-credentials|\.git-credential-cache|[._]netrc)(?=$|[\s'"\\/])/i,
];

function benchmarkPermission(request, invocation, c, audit) {
  const decide = (kind, reason) => {
    audit({kind:request.kind, toolCallId:request.toolCallId, allowed:kind==='approve-once', decision:kind, reason});
    return kind === 'reject'
      ? {kind, feedback:'Outside this benchmark permission scope; use only the project, selected skill and supplied toolchain.'}
      : {kind};
  };
  if (request.managedApprovalRequired || invocation.managedSettingsEnabled || request.requestSandboxBypass) {
    return decide('no-result', 'host-approval-required');
  }
  const contained = (value, root) => {
    if (typeof value !== 'string' || !value) return false;
    const p = path.resolve(c.workspace, value);
    const r = path.resolve(root);
    return p === r || p.startsWith(r + path.sep);
  };
  const readable = p => contained(p,c.workspace) || (c.readRoots || []).some(r=>contained(p,r)) ||
    (typeof p === 'string' && !!p && (c.exactReadFiles || []).some(f=>path.resolve(c.workspace,p)===path.resolve(f)));
  let allowed = false;
  if (request.kind === 'read') allowed = readable(request.path);
  if (request.kind === 'write') {
    const files = [request.fileName, ...(request.fileEdits || []).flatMap(x=>[x.before?.path,x.after?.path])].filter(Boolean);
    allowed = files.length > 0 && files.every(p=>contained(p,c.workspace) &&
      !contained(p,c.workspace+'/.github/skills') && !contained(p,c.workspace+'/.github/copilot'));
  }
  if (request.kind === 'shell') {
    const paths = (request.possiblePaths || []).map(p=>typeof p === 'string' ? p : p?.path);
    if (paths.some(p=>!readable(p))) return decide('reject', 'path-outside-scope');
    if (paths.some(p=>protectedShellPath.test(p))) return decide('reject', 'protected-shell-path');
    if (blockedShellPatterns.some(pattern=>pattern.test(request.fullCommandText || ''))) {
      return decide('reject', 'blocked-shell-pattern');
    }
    allowed = true;
  }
  return allowed ? decide('approve-once', 'within-scope') : decide('reject', 'kind-or-path-outside-scope');
}
'''


SDK_DRIVER = r'''import fs from 'node:fs';
import {pathToFileURL} from 'node:url';
import path from 'node:path';
''' + TASK_PIN_HOOK + SDK_PERMISSION + r'''
const c=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const {CopilotClient,RuntimeConnection}=await import(pathToFileURL(c.sdk).href);
const env={...process.env,HARRTEST_PARENT_SESSION_ID:c.sessionId};
if(c.corporateGuardGoal)env.HARRTEST_CORPORATE_GOAL=c.corporateGuardGoal;
const client=new CopilotClient({mode:'copilot-cli',workingDirectory:c.workspace,
 env,
 connection:RuntimeConnection.forStdio({path:c.runtime[0],args:[...c.runtime.slice(1),'--no-auto-update']})});
const write=(name,value)=>fs.writeFileSync(c.output+'/'+name,JSON.stringify(value,null,2));
const permission=(request,invocation)=>benchmarkPermission(request,invocation,c,
 row=>fs.appendFileSync(c.output+'/permission-decisions.jsonl',JSON.stringify(row)+'\n'));
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
    guard_goal = attempt_guard_goal(plan, meta)
    if guard_goal:
        configuration['corporateGuardGoal'] = guard_goal
        prepare_corporate_guard(workspace, tools['python'], guard_goal, configuration['sessionId'])
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
    if 'corporateGuardGoal' in configuration:
        raw['corporate_guard_goal'] = configuration['corporateGuardGoal']
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
                                    'permission_decisions_sha256':sha(attempt/'permission-decisions.jsonl') if (attempt/'permission-decisions.jsonl').is_file() else None,
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
    if scenario in RESILIENCE_REQUIRED:required.add('resilience')
    if scenario in PERFORMANCE_WORKLOADS:required.add('performance')
    layers = []
    for row in rows:
        if row.get('status') not in statuses or len(row.get('rationale','').strip())<30 or not row.get('evidence'):
            raise ValueError('Layer needs status, concrete rationale and evidence')
        if row['id'] in required and row['status']=='NOT_APPLICABLE':
            raise ValueError('Core existing-code layers are required')
        if row['id'] == 'security' and case.get('security_scope') and row['status'] == 'PASS':
            if result['automated_artifact_layers']['security']['status'] != 'PASS':
                raise ValueError('Failed or missing scoped security controls cannot become PASS')
        if scenario == 'build-plan' and row['id'] == 'resilience' and row['status'] == 'PASS':
            if result['automated_artifact_layers']['resilience']['status'] != 'PASS':
                raise ValueError('Failed invalid-plan controls cannot become PASS')
        if scenario in RECOVERY_SCENARIOS and row['id'] == 'resilience' and row['status'] == 'PASS':
            if result['automated_artifact_layers']['resilience']['status'] != 'PASS':
                raise ValueError('Failed or missing recovery controls cannot become PASS')
        if scenario in PERFORMANCE_WORKLOADS and row['id']=='performance' and row['status']=='PASS' and result['performance']['status']!='PASS':
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
    result = {'schema':1,'kind':plan.get('kind','development'),'declared_attempts':96,'attempts':rows,'counts':counts,'release_qualified':qualified,
            'metric_scope':'Regression, security and architecture counts are failed independent layer verdicts per attempt, not distinct findings. Credit totals cover the reported subtotal only. Time and performance summaries identify their observed denominators.',
            'limitation':'Independent operator-supplied six-layer assessments on current source and actual completion claims required for all attempts; functional counts alone cannot qualify Corporate release. Attribution remains cooperative local evidence.'}
    if 'corporate_guard_cases' in plan:
        result['candidate_profile'] = {'corporate_guard_cases': plan['corporate_guard_cases'],
                                       'enrollment_arm': 'v5', 'goal': plan['corporate_guard_goal']}
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='action',required=True)
    pre=sub.add_parser('preflight');pre.add_argument('--tools',type=Path)
    fr=sub.add_parser('freeze');fr.add_argument('--output',type=Path,required=True);fr.add_argument('--baseline-skill',type=Path,required=True);fr.add_argument('--candidate-skill',type=Path,required=True);fr.add_argument('--models',nargs=2,required=True);fr.add_argument('--tools',type=Path);fr.add_argument('--seconds',type=int,default=2400);fr.add_argument('--credits',type=int,default=120);fr.add_argument('--kind',choices=['development','acceptance'],default='development');fr.add_argument('--seed',type=int,default=20261114)
    fr.add_argument('--corporate-guard-goal', help='Enroll V5 on substantial held cases or in a development trial')
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
        elif args.action=='freeze': result=freeze(args.output,args.baseline_skill,args.candidate_skill,args.models,tools=load(args.tools) if args.tools else None,seconds=args.seconds,credits=args.credits,kind=args.kind,seed=args.seed,corporate_guard_goal=args.corporate_guard_goal)
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
