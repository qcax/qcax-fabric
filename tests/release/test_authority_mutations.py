#!/usr/bin/env python3
from pathlib import Path
import json,os,shutil,subprocess,sys,tempfile
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
ENV={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
def run(root):
    return subprocess.run([sys.executable,str(root/'tools/validate_authority_boundaries.py')],cwd=str(root),env=ENV,capture_output=True,text=True,timeout=30)
def main():
    with tempfile.TemporaryDirectory() as td:
        r=Path(td)/'r'; shutil.copytree(ROOT,r); cases=[]
        def mutate(mid,rel,fn):
            p=r/rel; before=p.read_bytes()
            try: fn(p); q=run(r); cases.append({'id':mid,'killed':q.returncode!=0})
            finally: p.write_bytes(before)
        mutate('AUTH_M1_SANDBOX_PATH','tools/w8_build_incremental.py',lambda p:p.write_text(p.read_text()+'\n# '+('/mnt'+'/data')+'/mutant\n',encoding='utf-8'))
        mutate('AUTH_M2_RUNTIME_IMPORT_HISTORY','packages/host/src/qcax_fabric_host/host.py',lambda p:p.write_text('import history\n'+p.read_text(),encoding='utf-8'))
        gp=r/'release/generated/bad.py'
        try: gp.write_text('x=1\n',encoding='utf-8'); q=run(r); cases.append({'id':'AUTH_M3_GENERATED_SOURCE','killed':q.returncode!=0})
        finally:
            if gp.exists(): gp.unlink()
        d=r/'.qcax-local'; existed=d.exists(); p=d/'x'
        try: d.mkdir(parents=True,exist_ok=True); p.write_text('x',encoding='utf-8'); q=run(r); cases.append({'id':'AUTH_M4_LOCAL_SCRATCH_LEAK','killed':q.returncode!=0})
        finally:
            if p.exists():p.unlink()
            if not existed:
                try:d.rmdir()
                except OSError:pass
        def activate(p):
            d=json.loads(p.read_text()); d['release_identity']['status']='ACTIVE'; p.write_text(json.dumps(d),encoding='utf-8')
        mutate('AUTH_M5_RELEASE_ACTIVATION','release/policy/release-contract.json',activate)
        clean=run(r); survivors=[x['id'] for x in cases if not x['killed']]
        result={'status':'PASS' if not survivors and clean.returncode==0 else 'FAIL','mutations':len(cases),'killed':sum(x['killed'] for x in cases),'survivors':survivors,'post_restore_validator_returncode':clean.returncode}
        print(json.dumps(result,sort_keys=True))
        if result['status']!='PASS': raise SystemExit(1)
if __name__=='__main__': main()
