#!/usr/bin/env python3
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import json,os,subprocess,sys,time
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
CMDS=(
 [sys.executable,str(ROOT/'tools/validate_repo.py')],
 [sys.executable,'-m','unittest','discover','-s',str(ROOT/'tests/semantics'),'-p','test_*.py'],
 [sys.executable,str(ROOT/'tests/release/test_w6_workflow_mutations.py')],
 [sys.executable,str(ROOT/'tests/release/test_w7_package_mutations.py')],
 [sys.executable,str(ROOT/'tests/release/test_version_gate_mutations.py')],
 [sys.executable,str(ROOT/'tests/release/test_authority_mutations.py')],
 [sys.executable,str(ROOT/'tests/release/test_w9_provider_mutations.py')],
)

def one(cmd):
    start=time.monotonic()
    p=subprocess.run(cmd,cwd=str(ROOT),env=env,capture_output=True,text=True,timeout=150)
    return {'cmd':' '.join(map(str,cmd)),'returncode':p.returncode,'seconds':round(time.monotonic()-start,3),
            'stdout':p.stdout.strip()[-8000:],'stderr':p.stderr.strip()[-2000:]}

def main():
    rows=[]
    first=one(CMDS[0]); rows.append(first)
    print(json.dumps({'progress':first['cmd'],'returncode':first['returncode'],'seconds':first['seconds']},sort_keys=True),flush=True)
    if first['returncode']:
        failed=[first['cmd']]
    else:
        with ThreadPoolExecutor(max_workers=len(CMDS)-1) as ex:
            futs={ex.submit(one,c):c for c in CMDS[1:]}
            for fut in as_completed(futs):
                row=fut.result(); rows.append(row)
                print(json.dumps({'progress':row['cmd'],'returncode':row['returncode'],'seconds':row['seconds']},sort_keys=True),flush=True)
        order={tuple(c):i for i,c in enumerate(CMDS)}
        rows.sort(key=lambda r:order.get(tuple(r['cmd'].split()),99))
        failed=[r['cmd'] for r in rows if r['returncode']]
    result={'schema':'qcax.aggregate-validation/4','status':'PASS' if not failed else 'FAIL',
            'runs':rows,'failed':failed,'wall_clock_proxy_seconds':max((r['seconds'] for r in rows),default=0)}
    print(json.dumps(result,sort_keys=True))
    raise SystemExit(1 if failed else 0)
if __name__=='__main__': main()
