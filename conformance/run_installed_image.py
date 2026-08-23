#!/usr/bin/env python3
from pathlib import Path
import json,os,subprocess,sys,tempfile
ROOT=Path(__file__).resolve().parents[1]
def main():
    with tempfile.TemporaryDirectory() as td:
        candidate=Path(td)/'candidate'
        env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
        p=subprocess.run([sys.executable,str(ROOT/'release/tooling/build_candidate.py'),
                          '--mode','pr-exercise','--out',str(candidate),'--twin-builds','2'],
                          cwd=str(ROOT),env=env,capture_output=True,text=True,timeout=240)
        if p.returncode:
            print(json.dumps({'status':'FAIL','stage':'build','stderr':p.stderr[-2000:]})); return 1
        q=subprocess.run([sys.executable,str(ROOT/'conformance/run_exact_wheel_canaries.py'),str(candidate)],
                         cwd=str(ROOT),env=env,capture_output=True,text=True,timeout=240)
        if q.returncode:
            print(json.dumps({'status':'FAIL','stage':'canary','stderr':q.stderr[-2000:],'stdout':q.stdout[-2000:]})); return 1
        result=json.loads(q.stdout)
        print(json.dumps({'status':'PASS','candidate_assets':len(list(candidate.iterdir())),
                          'canary':result},sort_keys=True)); return 0
if __name__=='__main__':
    raise SystemExit(main())
