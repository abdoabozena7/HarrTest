#!/usr/bin/env python3
"""Real local CLI repair and restart demo; no LLM, paid service or CARLA run.

Writes only to a NEW requested output directory. Keeps failed and successful
receipts. The example uses legacy schema-2 coverage to avoid pretending an
independent human/agent reviewed this deterministic demonstration.
"""
from __future__ import annotations
import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import proof
import root_gate

APP = '''import json, sys
from pathlib import Path
command, filename = sys.argv[1:3]
p = Path(filename)
if command == 'save':
    value = int(sys.argv[3])
    PERSIST
    print(json.dumps({'ok': True}))
else:
    print(p.read_text() if p.exists() else 'null')
'''
PROBE = '''import json, os, subprocess, sys
from pathlib import Path
out = Path(os.environ['PROVE_IT_OUTPUT_DIR'])
state = out / 'actual-persistent-state.json'
values = [12] if sys.argv[1] == 'save' else [12, 0, -4, 12]
for expected in values:
    write = subprocess.run([sys.executable,'-S','app.py','save',str(state),str(expected)],capture_output=True,text=True)
    assert write.returncode == 0, write.stderr
    read = subprocess.run([sys.executable,'-S','app.py','read',str(state)],capture_output=True,text=True)
    assert read.returncode == 0, read.stderr
    actual = json.loads(read.stdout)
    assert actual == expected, f'Public CLI lost persisted state across restart: expected {expected}, observed {actual}'
report = {'persisted': True, 'value': 12, 'independent_process_reads': len(values)}
(out/'observed.json').write_text(json.dumps(report))
print(json.dumps(report))
'''


def run_demo(project):
    project = Path(project).resolve()
    project.mkdir(parents=True, exist_ok=False)
    (project/'app.py').write_text(APP.replace('PERSIST', 'pass # bug: acknowledges save without persisting'))
    (project/'check.py').write_text(PROBE)
    goal = project/'.runtime-proof/root-goals/mission'; goal.mkdir(parents=True)
    request='Persist a result through the real command line. Verify restart and final integrated behavior.'
    (goal/'original-request.txt').write_text(request)
    requirements=[]
    for tid, phrase in [('save','Persist a result'),('integration','Verify restart and final integrated behavior')]:
        requirements.append({'id':'ROOT_'+tid.upper(),'claim':phrase+' is observed on actual code.',
             'oracle':'Independent process reads the exact integer saved by a preceding command process.',
             'source':'user_request','source_excerpt':phrase,'evidence_mode':'live',
             'satisfiers':[{'task_id':tid,'requirement_id':'R01'}]})
    root={'schema':2,'goal_id':'mission','request_sha256':proof.file_hash(goal/'original-request.txt'),
          'scope_statement':'A deterministic local example of real CLI persistence and restart verification, not model evaluation.',
          'coverage_review':{'method':'same-agent','rationale':'The fixed demo request maps to save plus restart and integration; this is not an independent LLM/human review.','unmapped_segments':[]},
          'requirements':requirements,'integration':{'task_id':'integration','requirement_id':'R01','scope':'Real persistence through separate processes on final source.'}}
    root_gate.validate(project,goal,root)
    proof.save(goal/'root-contract.json',root)
    proof.save(goal/'root-seal.json',{'root_hash':proof.digest(root),'request_sha256':root['request_sha256'],'sealed_at':proof.now()})
    for tid in ('save','integration'):
        task=project/'.runtime-proof'/tid;task.mkdir()
        child=proof.load(ROOT/'examples/cli-contract.json');child['task_id']=tid
        child['goal']='Verify persisted state through actual CLI save and separate-process read.'
        child['source_paths']=['app.py','check.py']
        child['requirements'][0].update(claim='Actual CLI persistence survives a separate process.',
            oracle='Compare the actual public read result with independent literal integer cases.',
            failure_example='A write acknowledges success but does not save anything.',
            negative_control_exception='The separate before-repair native CLI attempt fails for absent persistence; preserve its exact receipt.')
        check=child['checks'][0]
        check.update(command=['{python}','-S','check.py',tid],
            assertions=[{'type':'json','file':'observed.json','pointer':'/persisted','op':'eq','value':True},
                        {'type':'json','file':'observed.json','pointer':'/value','op':'eq','value':12}],
            artifacts=[{'glob':'observed.json','min_count':1,'min_bytes':10}])
        proof.validate_contract(child)
        proof.save(task/'contract.json',child);proof.save(task/'context.json',{'project':str(project),'root_goal':'mission'})
        proof.save(task/'seal.json',{'contract_hash':proof.digest(child),'engine_hash':proof.engine_hash(child)})
    proof.save(project/'.runtime-proof/active.json',{'task':'save','root_goal':'mission','root_required':True})
    plan={'schema':1,'goal_id':'mission','root_goal':'.runtime-proof/root-goals/mission','tasks':[
        {'id':'fix','outcome':'Repair real CLI persistence','proof_task':'.runtime-proof/save','depends_on':[],
         'write_scope':['app.py'],'read_scope':['check.py'],'resources':['demo-storage'],'context_files':['app.py','check.py']},
        {'id':'integration','role':'integrate','outcome':'Verify final integration after restart','proof_task':'.runtime-proof/integration',
         'depends_on':['fix'],'write_scope':[],'read_scope':['app.py','check.py'],'resources':['demo-storage']}]}
    proof.save(project/'.runtime-proof/workflow-plan.json',plan)
    def cli(command,*args,expected=0):
        argv=[sys.executable,'-S','-B',str(ROOT/'scripts/workflow.py'),'--project',str(project),command,*args]
        completed=subprocess.run(argv,capture_output=True,text=True,timeout=30)
        with (project/'.runtime-proof/demo-cli-transcript.log').open('a',encoding='utf-8') as stream:
            # Do not retain lease tokens in a shared transcript.
            public=[('<worker-token>' if i and argv[i-1]=='--token' else v) for i,v in enumerate(argv)]
            stream.write(json.dumps(public)+'\n'+ ('[claim response retained only in process memory]\n' if command=='claim' else completed.stdout)+completed.stderr)
        if completed.returncode != expected:
            raise AssertionError(f'{command} returned {completed.returncode}: {completed.stdout} {completed.stderr}')
        return completed.stdout
    cli('init','--plan',str(project/'.runtime-proof/workflow-plan.json'))
    claim=json.loads(cli('claim','--goal','mission','--task','fix','--worker','actual-local-demo-process','--lease-seconds','120'))
    cli('run-check','--goal','mission','--task','fix','--token',claim['token'],'--check','addition',expected=1)
    # Inspect the actual failure cause, not just any nonzero exit.
    latest=proof.load(project/'.runtime-proof/save/latest/addition.json')
    stderr=(project/'.runtime-proof/save'/latest['run']/'stderr.log').read_text()
    assert 'lost persisted state across restart' in stderr
    (project/'app.py').write_text(APP.replace('PERSIST', 'p.write_text(json.dumps(value))'))
    cli('run-check','--goal','mission','--task','fix','--token',claim['token'],'--check','addition')
    proof.update_step(project/'.runtime-proof/save','T01','VERIFIED','Executed a real save and independent process read; literal value twelve persisted.')
    (project/'.runtime-proof/save/handoff.txt').write_text('Observed missing persistence, fixed the write, and retained failed and successful subprocess evidence.')
    cli('handoff','--goal','mission','--task','fix','--token',claim['token'],'--evidence','.runtime-proof/save/handoff.txt')
    cli('verify','--goal','mission','--task','fix')
    child_hook=proof.hook({'cwd':str(project)})
    assert child_hook.get('decision')=='block',child_hook
    assert not root_gate.check_root(goal)['root_goal_achieved']
    # Every CLI command reopens SQLite: process restarts do not lose task state.
    join=json.loads(cli('claim','--goal','mission','--task','integration','--worker','actual-local-integration-process','--lease-seconds','120'))
    cli('run-check','--goal','mission','--task','integration','--token',join['token'],'--check','addition')
    proof.update_step(project/'.runtime-proof/integration','T01','VERIFIED','Verified multiple persisted values through fresh subprocesses using the final implementation.')
    (project/'.runtime-proof/integration/handoff.txt').write_text('Final CLI integration retained 12, 0, -4, and 12 across process restarts.')
    cli('handoff','--goal','mission','--task','integration','--token',join['token'],'--evidence','.runtime-proof/integration/handoff.txt')
    cli('verify','--goal','mission','--task','integration')
    passed=json.loads(cli('root','--goal','mission'));assert passed['root_goal_achieved']
    before=(project/'app.py').read_bytes();(project/'app.py').write_bytes(before+b'\n# changed after verification\n')
    stale=json.loads(cli('root','--goal','mission',expected=1));assert not stale['root_goal_achieved']
    (project/'app.py').write_bytes(before)
    assert proof.hook({'cwd':str(project)})=={}
    report={'status':'LOCAL_SUBPROCESS_DEMO_PASSED','initial_bug_reproduced':True,'repair_verified':True,
            'child_only_completion_blocked':True,'sqlite_reopened_between_commands':True,
            'final_root_verified':True,'post_run_source_drift_rejected':True,
            'scope':'Real local CLI, durable workflow and root/child gates. No LLM, host-native subagent, GUI or CARLA claim.',
            'root_report':passed}
    proof.save(project/'demo-result.json',report)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(run_demo(args.output),indent=2))
