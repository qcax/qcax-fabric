#!/usr/bin/env python3
from pathlib import Path
import json,os,shutil,subprocess,sys,tempfile
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
ENV={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}

def run(root):
    return subprocess.run([sys.executable,str(root/'tools/validate_version_gate.py')],cwd=str(root),
                          capture_output=True,text=True,env=ENV,timeout=30)

def main():
    with tempfile.TemporaryDirectory() as td:
        r=Path(td)/'r'; shutil.copytree(ROOT,r)
        cases=[]
        def mutate(mid,rel,fn):
            p=r/rel; before=p.read_bytes()
            try:
                fn(p); q=run(r); cases.append({'id':mid,'killed':q.returncode!=0})
            finally:
                p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(before)
        def delete(mid,rel):
            p=r/rel; before=p.read_bytes()
            try:
                p.unlink(); q=run(r); cases.append({'id':mid,'killed':q.returncode!=0})
            finally:
                p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(before)
        delete('VG_M1_DELETE_PUBLIC_SCHEMA','spec/artifact-envelope-v1alpha1.schema.json')
        def schema_id(p):
            d=json.loads(p.read_text()); d['$id']='urn:mutant'; p.write_text(json.dumps(d),encoding='utf-8')
        mutate('VG_M2_SCHEMA_ID_DRIFT','spec/boot-lock-v1alpha1.schema.json',schema_id)
        mutate('VG_M3_ABI_PROMISE_DRIFT','docs/COMPATIBILITY_POLICY.md',lambda p:p.write_text(p.read_text().replace('qcax.fabric/v1alpha1','qcax.fabric/v2'),encoding='utf-8'))
        mutate('VG_M4_DISTRIBUTION_ID_DRIFT','packages/contracts/pyproject.toml',lambda p:p.write_text(p.read_text().replace('name = "qcax-fabric-contracts"','name = "qcax-fabric-contracts-mutant"',1),encoding='utf-8'))
        def plugin_id(p):
            d=json.loads(p.read_text()); d['plugin_id']='org.qcax.authorization-mutant'; p.write_text(json.dumps(d),encoding='utf-8')
        mutate('VG_M5_PLUGIN_ID_DRIFT','packages/plugins/authorization/src/qcax_plugin_authorization/qcax-plugin.json',plugin_id)
        mutate('VG_M6_PACKAGE_VERSION_DRIFT','packages/sdk/pyproject.toml',lambda p:p.write_text(p.read_text().replace('version = "0.1.0a1"','version = "0.1.0a2"',1),encoding='utf-8'))
        delete('VG_M7_DELETE_MIGRATION_NOTE','history/migration/FIRST_PUBLIC_ALPHA_MIGRATION.md')
        def activate(p):
            d=json.loads(p.read_text()); d['release_identity']['status']='ACTIVE'; p.write_text(json.dumps(d),encoding='utf-8')
        mutate('VG_M8_PREMATURE_ALPHA1_ACTIVATION','release/policy/release-contract.json',activate)
        clean=run(r); survivors=[x['id'] for x in cases if not x['killed']]
        result={'status':'PASS' if not survivors and clean.returncode==0 else 'FAIL','mutations':len(cases),
                'killed':sum(x['killed'] for x in cases),'survivors':survivors,'post_restore_validator_returncode':clean.returncode}
        print(json.dumps(result,sort_keys=True))
        if result['status']!='PASS': raise SystemExit(1)
if __name__=='__main__': main()
