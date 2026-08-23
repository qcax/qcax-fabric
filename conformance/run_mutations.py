#!/usr/bin/env python3
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import json,os,subprocess,sys,time
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
SCRIPTS=(
 'tests/release/test_w6_workflow_mutations.py',
 'tests/release/test_w7_package_mutations.py',
 'tests/release/test_version_gate_mutations.py',
 'tests/release/test_authority_mutations.py',
 'tests/release/test_w9_provider_mutations.py',
)

def run_one(rel):
    start=time.monotonic()
    p=subprocess.run([sys.executable,str(ROOT/rel)],cwd=str(ROOT),
        env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'},capture_output=True,text=True,timeout=90)
    out=p.stdout.strip(); parsed=None
    if out:
        try: parsed=json.loads(out.splitlines()[-1])
        except Exception: parsed={'raw':out[-1000:]}
    return {'script':rel,'returncode':p.returncode,'seconds':round(time.monotonic()-start,3),
            'result':parsed,'stderr':p.stderr.strip()[-500:]}

def main():
    rows=[]
    with ThreadPoolExecutor(max_workers=len(SCRIPTS)) as ex:
        futs={ex.submit(run_one,rel):rel for rel in SCRIPTS}
        for fut in as_completed(futs):
            row=fut.result(); rows.append(row)
            print(json.dumps({'progress':row['script'],'returncode':row['returncode'],'seconds':row['seconds']},sort_keys=True),flush=True)
    rows.sort(key=lambda x:SCRIPTS.index(x['script']))
    failed=[x['script'] for x in rows if x['returncode']]
    total_mut=0; total_killed=0
    for row in rows:
        parsed=row.get('result') or {}; m=parsed.get('mutations',0)
        total_mut += m if isinstance(m,int) else len(m) if isinstance(m,list) else 0
        total_killed += int(parsed.get('killed',0) or 0)
    result={'schema':'qcax.mutation-aggregate/5','status':'PASS' if not failed else 'FAIL',
            'scripts':len(SCRIPTS),'mutations':total_mut,'killed':total_killed,'failed':failed,'runs':rows}
    print(json.dumps(result,sort_keys=True))
    if failed: raise SystemExit(1)
if __name__=='__main__': main()
