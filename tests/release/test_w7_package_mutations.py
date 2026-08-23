#!/usr/bin/env python3
from pathlib import Path
import json,os,shutil,subprocess,sys,tempfile
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
ENV={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
def run(root):
    return subprocess.run([sys.executable,str(root/'tools/validate_w7_packages.py')],cwd=str(root),capture_output=True,text=True,env=ENV,timeout=30)
def main():
    with tempfile.TemporaryDirectory() as td:
        r=Path(td)/'r'; shutil.copytree(ROOT,r); cases=[]
        def mutate(mid,rel,fn):
            p=r/rel; before=p.read_bytes()
            try: fn(p); q=run(r); cases.append({'id':mid,'killed':q.returncode!=0})
            finally: p.write_bytes(before)
        def replace(old,new):
            def fn(p):
                s=p.read_text(encoding='utf-8')
                if old not in s: raise RuntimeError(f'anchor missing {p}: {old}')
                p.write_text(s.replace(old,new,1),encoding='utf-8')
            return fn
        mutate('W7_M1_INTERNAL_DEP_UNPIN','packages/sdk/pyproject.toml',replace('qcax-fabric-contracts==0.1.0a1','qcax-fabric-contracts>=0.1.0a1'))
        mutate('W7_M2_VERSION_DRIFT','packages/host/pyproject.toml',replace('version = "0.1.0a1"','version = "0.1.0a2"'))
        mutate('W7_M3_LICENSE_DRIFT','packages/contracts/pyproject.toml',replace('license = "Apache-2.0"','license = "MIT"'))
        mutate('W7_M4_RESTORE_ORDERED_PYPI','release/policy/release-contract.json',replace('order-independent PyPI publication with reconciliation','ordered PyPI publication with reconciliation'))
        def activate(p):
            d=json.loads(p.read_text()); d['release_identity']['status']='ACTIVE'; p.write_text(json.dumps(d,indent=2,sort_keys=True)+'\n',encoding='utf-8')
        mutate('W7_M5_PREMATURE_VERSION_ACTIVATION','release/policy/release-contract.json',activate)
        d=r/'packages/plugins/canonical-identity'; existed=d.exists()
        try:
            d.mkdir(parents=True,exist_ok=True); q=run(r); cases.append({'id':'W7_M6_SILENT_LIVE_PATH_RESTORE','killed':q.returncode!=0})
        finally:
            if not existed:
                try:d.rmdir()
                except OSError:pass
        clean=run(r); survivors=[x['id'] for x in cases if not x['killed']]
        result={'status':'PASS' if not survivors and clean.returncode==0 else 'FAIL','mutations':len(cases),'killed':sum(x['killed'] for x in cases),'survivors':survivors,'post_restore_validator_returncode':clean.returncode}
        print(json.dumps(result,sort_keys=True))
        if result['status']!='PASS': raise SystemExit(1)
if __name__=='__main__': main()
