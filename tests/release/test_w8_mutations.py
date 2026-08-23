#!/usr/bin/env python3
from pathlib import Path
import importlib.util,json,os,shutil,tempfile,zipfile,sys,hashlib
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]; CAND=Path(os.environ.get('QCAX_W8_CANDIDATE_DIR', str(ROOT/'.qcax-local/w8/candidate'))); RECEIPTS=Path(os.environ.get('QCAX_W8_RECEIPTS_DIR', str(ROOT/'history/evidence/W8_MUTATION_RECEIPTS')))
spec=importlib.util.spec_from_file_location('w8v',ROOT/'tools/validate_w8.py'); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

def setup(td):
 r=Path(td)/'root'; c=Path(td)/'cand'; shutil.copytree(ROOT,r); shutil.copytree(CAND,c)
 rr=r/'history/evidence/W8_MUTATION_RECEIPTS'
 shutil.rmtree(rr,ignore_errors=True)
 if not RECEIPTS.is_dir(): raise RuntimeError('mutation receipts missing: '+str(RECEIPTS))
 shutil.copytree(RECEIPTS,rr)
 return r,c

def run(mid,mut):
 with tempfile.TemporaryDirectory() as td:
  r,c=setup(td); mut(r,c); res=mod.validate(r,c); return {'id':mid,'killed':res['status']=='FAIL','errors':res['errors'][:4]}

def receipt_mut(name,key,val):
 def f(r,c):
  p=r/'history/evidence/W8_MUTATION_RECEIPTS'/(name+'.json'); d=json.loads(p.read_text()); d[key]=val; p.write_text(json.dumps(d,indent=2,sort_keys=True)+'\n')
 return f
def main():
    cases=[]
    cases.append(run('W8_M1_WHEEL_TWIN_FALSE',receipt_mut('qcax-fabric-contracts','wheel_twin_byte_identical',False)))
    cases.append(run('W8_M2_SDIST_SEMANTIC_FALSE',receipt_mut('qcax-fabric-sdk','sdist_semantic_twin_identical',False)))
    def core_drift(r,c): (r/'packages/contracts/src/qcax_fabric_contracts/canonical.py').write_text((r/'packages/contracts/src/qcax_fabric_contracts/canonical.py').read_text()+'# mutant\n')
    cases.append(run('W8_M3_CORE_SOURCE_DRIFT',core_drift))
    def plugin_drift(r,c):
     p=r/'packages/plugins/authorization/src/qcax_plugin_authorization/qcax-plugin.json'; d=json.loads(p.read_text()); d['plugin_id']='org.qcax.authorization-mutant'; p.write_text(json.dumps(d,indent=2,sort_keys=True)+'\n')
    cases.append(run('W8_M4_PLUGIN_DESCRIPTOR_DRIFT',plugin_drift))
    def delete_asset(r,c): next(c.glob('qcax_fabric_host-*.whl')).unlink()
    cases.append(run('W8_M5_MISSING_ASSET',delete_asset))
    def extra_asset(r,c): (c/'unexpected.bin').write_bytes(b'x')
    cases.append(run('W8_M6_UNEXPECTED_ASSET',extra_asset))
    def tamper_wheel(r,c):
     p=next(c.glob('qcax_fabric_sdk-*.whl')); p.write_bytes(p.read_bytes()+b'x')
    cases.append(run('W8_M7_TAMPER_WHEEL',tamper_wheel))
    def bad_lock(r,c):
     p=c/'release-lock.json'; d=json.loads(p.read_text()); d['entries'][0]['wheel_sha256']='0'*64; p.write_text(json.dumps(d,indent=2,sort_keys=True)+'\n')
    cases.append(run('W8_M8_RELEASE_LOCK_HASH',bad_lock))
    def bad_sbom(r,c):
     p=c/'sbom.spdx.json'; d=json.loads(p.read_text()); d['packages']=d['packages'][:-1]; p.write_text(json.dumps(d,indent=2,sort_keys=True)+'\n')
    cases.append(run('W8_M9_SBOM_COVERAGE',bad_sbom))
    def unsafe_zip(r,c):
     p=c/'spec-bundle.zip';
     with zipfile.ZipFile(p,'w') as z: z.writestr('../evil','x')
    cases.append(run('W8_M10_UNSAFE_ZIP',unsafe_zip))
    def omit_conformance_runner(r,c):
     p=c/'conformance-bundle.zip'
     with zipfile.ZipFile(p) as z:
      kept=[(n,z.read(n)) for n in z.namelist() if n!='conformance/run_mutations.py']
     with zipfile.ZipFile(p,'w',compression=zipfile.ZIP_DEFLATED) as z:
      for n,b in kept: z.writestr(n,b)
     dg=hashlib.sha256(p.read_bytes()).hexdigest(); size=p.stat().st_size
     mf=c/'payload-manifest.json'; d=json.loads(mf.read_text())
     for row in d['members']:
      if row['name']=='conformance-bundle.zip': row['sha256']=dg; row['bytes']=size
     mf.write_text(json.dumps(d,indent=2,sort_keys=True)+'\n')
     sums=c/'SHA256SUMS'; rows=[]
     for line in sums.read_text().splitlines():
      if not line.strip(): continue
      old,name=line.split('  ',1)
      if name=='conformance-bundle.zip': old=dg
      elif name=='payload-manifest.json': old=hashlib.sha256(mf.read_bytes()).hexdigest()
      rows.append(f'{old}  {name}')
     sums.write_text('\n'.join(rows)+'\n')
    cases.append(run('W8_M11_CONFORMANCE_RUNNER_OMISSION',omit_conformance_runner))
    def fake_provider(r,c):
     p=r/'history/evidence/W7_PROVIDER_READBACK_BLOCKERS.json'; d=json.loads(p.read_text()); d['blocked_properties']['immutable_releases']['state']='VERIFIED'; p.write_text(json.dumps(d,indent=2,sort_keys=True)+'\n')
    cases.append(run('W8_M12_FAKE_PROVIDER_PROMOTION',fake_provider))
    def active_version(r,c):
     p=r/'release/policy/release-contract.json'; d=json.loads(p.read_text()); d['release_identity']['status']='ACTIVE'; p.write_text(json.dumps(d,indent=2,sort_keys=True)+'\n')
    cases.append(run('W8_M13_PREMATURE_VERSION_ACTIVE',active_version))
    surv=[x['id'] for x in cases if not x['killed']]
    print(json.dumps({'status':'PASS' if not surv else 'FAIL','mutations':len(cases),'killed':sum(x['killed'] for x in cases),'survivors':surv},sort_keys=True))
    if surv: sys.exit(1)

if __name__=='__main__':
    main()
