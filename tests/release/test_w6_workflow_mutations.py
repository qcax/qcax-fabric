#!/usr/bin/env python3
from pathlib import Path
import json,os,shutil,subprocess,sys,tempfile
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
ENV={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
def run(root):
    return subprocess.run([sys.executable,str(root/'tools/validate_workflows.py')],cwd=str(root),env=ENV,capture_output=True,text=True,timeout=30)
def main():
    with tempfile.TemporaryDirectory() as td:
        r=Path(td)/'r'; shutil.copytree(ROOT,r); cases=[]
        def mutate(mid,rel,old,new):
            p=r/rel; before=p.read_bytes()
            try:
                s=p.read_text(encoding='utf-8')
                if old not in s: raise RuntimeError(mid+' anchor missing')
                p.write_text(s.replace(old,new,1),encoding='utf-8'); q=run(r); cases.append({'id':mid,'killed':q.returncode!=0})
            finally: p.write_bytes(before)
        mutate('W6_UNPIN_ACTION','.github/workflows/ci.yml','actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1','actions/checkout@v7')
        mutate('W6_ADD_PULL_REQUEST_TARGET','.github/workflows/ci.yml','  pull_request:\n','  pull_request_target:\n')
        mutate('W6_WRONG_ENVIRONMENT','.github/workflows/release-publish.yml','environment: github-release','environment: wrong-release')
        mutate('W6_REMOVE_ACTIONS_READ','.github/workflows/release-publish.yml','      actions: read\n      contents: write','      contents: write')
        mutate('W6_MISSING_TOOLING','.github/workflows/release-preflight.yml','release/tooling/activate_contract.py','release/tooling/does_not_exist.py')
        mutate('W6_PR_SKIP_FINALIZE','.github/workflows/conformance.yml','      - run: python release/tooling/finalize_payload.py release/generated/pr-candidate\n','')
        mutate('W6_FINALIZER_HARDCODE','release/tooling/finalize_payload.py','from build_candidate import SOURCE_COMMIT,SOURCE_TREE','SOURCE_COMMIT="74e6d62e633746676650d66c6789dd6f56621305"; SOURCE_TREE="fb2e4db4e268107c098750f3060c341b9dae7680"')
        extra=r/'.github/workflows/extra.yml'
        try:
            extra.write_text('name: extra\non: push\njobs: {}\n',encoding='utf-8'); q=run(r); cases.append({'id':'W6_EXTRA_WORKFLOW','killed':q.returncode!=0})
        finally:
            if extra.exists(): extra.unlink()
        clean=run(r); survivors=[x['id'] for x in cases if not x['killed']]
        result={'status':'PASS' if not survivors and clean.returncode==0 else 'FAIL','mutations':len(cases),'killed':sum(x['killed'] for x in cases),'survivors':survivors,'post_restore_validator_returncode':clean.returncode}
        print(json.dumps(result,sort_keys=True))
        if result['status']!='PASS': raise SystemExit(1)
if __name__=='__main__': main()
