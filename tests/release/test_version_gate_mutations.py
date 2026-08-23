#!/usr/bin/env python3
from pathlib import Path
import json,os,shutil,subprocess,sys,tempfile
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
ENV={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
TAG='v0.1.0-alpha.1'
VERSION='0.1.0a1'
GOOD_COMMIT='1'*40

def run(root):
    return subprocess.run([sys.executable,str(root/'tools/validate_version_gate.py')],cwd=str(root),
                          capture_output=True,text=True,env=ENV,timeout=30)

def run_activation(root,args):
    return subprocess.run([sys.executable,str(root/'release/tooling/activate_contract.py'),*args],cwd=str(root),
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
        def contract_change(key,value):
            def fn(p):
                d=json.loads(p.read_text()); d['release_identity'][key]=value; p.write_text(json.dumps(d),encoding='utf-8')
            return fn
        mutate('VG_M8_DEMOTE_ACTIVE_IDENTITY','release/policy/release-contract.json',contract_change('status','HOLD_UNTIL_SEMANTIC_VERSION_GATE'))
        mutate('VG_M9_SELECTED_TAG_DRIFT','release/policy/release-contract.json',contract_change('selected_tag','v0.1.0-alpha.2'))
        mutate('VG_M10_SELECTED_VERSION_DRIFT','release/policy/release-contract.json',contract_change('selected_version','0.1.0a2'))
        def provider_change(fn):
            def inner(p):
                d=json.loads(p.read_text()); fn(d); p.write_text(json.dumps(d),encoding='utf-8')
            return inner
        mutate('VG_M11_PROVIDER_OVERALL_DRIFT','history/evidence/VERSION_PROVIDER_ABSENCE.json',provider_change(lambda d:d.__setitem__('overall','HOLD_PROVIDER_ABSENCE')))
        mutate('VG_M12_PYPI_STATUS_DRIFT','history/evidence/VERSION_PROVIDER_ABSENCE.json',provider_change(lambda d:d['pypi_direct_reads'][0].__setitem__('version_json_status',200)))
        mutate('VG_M13_GITHUB_RELEASE_STATUS_DRIFT','history/evidence/VERSION_PROVIDER_ABSENCE.json',provider_change(lambda d:d['github_direct_reads']['release_by_tag'].__setitem__('status_code',200)))
        mutate('VG_M14_SEARCH_MISS_ADMITTED','history/evidence/VERSION_PROVIDER_ABSENCE.json',provider_change(lambda d:d.__setitem__('pypi_search_observation_is_absence_proof',True)))

        clean=run(r)
        activation=[]
        good=run_activation(r,['--tag',TAG,'--commit',GOOD_COMMIT,'--verify-only'])
        good_payload=None
        if good.returncode==0:
            try: good_payload=json.loads(good.stdout)
            except Exception: pass
        activation.append({'id':'ACT_C1_VALID_VERIFY_ONLY','passed':good.returncode==0 and good_payload=={'commit':GOOD_COMMIT,'status':'ACTIVE','tag':TAG,'version':VERSION}})
        activation.append({'id':'ACT_C2_WRONG_TAG_REJECTED','passed':run_activation(r,['--tag','v0.1.0-alpha.2','--commit',GOOD_COMMIT,'--verify-only']).returncode!=0})
        activation.append({'id':'ACT_C3_SHORT_COMMIT_REJECTED','passed':run_activation(r,['--tag',TAG,'--commit','1234','--verify-only']).returncode!=0})
        activation.append({'id':'ACT_C4_UPPERCASE_COMMIT_REJECTED','passed':run_activation(r,['--tag',TAG,'--commit','A'*40,'--verify-only']).returncode!=0})
        activation.append({'id':'ACT_C5_MISSING_VERIFY_ONLY_REJECTED','passed':run_activation(r,['--tag',TAG,'--commit',GOOD_COMMIT]).returncode!=0})

        survivors=[x['id'] for x in cases if not x['killed']]
        failed_activation=[x['id'] for x in activation if not x['passed']]
        result={'status':'PASS' if not survivors and clean.returncode==0 and not failed_activation else 'FAIL',
                'mutations':len(cases),'killed':sum(x['killed'] for x in cases),'survivors':survivors,
                'activation_checks':len(activation),'activation_passed':sum(x['passed'] for x in activation),
                'activation_failures':failed_activation,'post_restore_validator_returncode':clean.returncode}
        print(json.dumps(result,sort_keys=True))
        if result['status']!='PASS': raise SystemExit(1)
if __name__=='__main__': main()
