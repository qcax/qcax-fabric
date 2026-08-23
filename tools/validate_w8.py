#!/usr/bin/env python3
from pathlib import Path
import argparse,hashlib,json,os,re,sys,zipfile
from packaging.utils import canonicalize_name,parse_wheel_filename,parse_sdist_filename
ROOT_DEFAULT=Path(__file__).resolve().parents[1]
CAND_DEFAULT=Path(os.environ.get('QCAX_W8_CANDIDATE_DIR', str(ROOT_DEFAULT/'.qcax-local/w8/candidate')))
RECEIPTS_DEFAULT=Path(os.environ.get('QCAX_W8_RECEIPTS_DIR', str(ROOT_DEFAULT/'.qcax-local/w8/rehearsal/receipts')))
HEX64=re.compile(r'^[0-9a-f]{64}$')
def sha256(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def gitblob(p):
 b=Path(p).read_bytes(); return hashlib.sha1(f'blob {len(b)}\0'.encode()+b).hexdigest()
def validate(root=ROOT_DEFAULT,candidate=CAND_DEFAULT):
 root=Path(root); candidate=Path(candidate); errors=[]; checks=0
 def ck(c,m):
  nonlocal checks; checks+=1
  if not c: errors.append(m)
 contract=json.loads((root/'release/policy/release-contract.json').read_text())
 projects=contract['package_set']['packages']; pkgs={canonicalize_name(x['name']) for x in projects if x.get('publish')}
 ck(len(pkgs)==11,'package set != 11')
 receipts=[]
 for row in projects:
  if not row.get('publish'): continue
  # Prefer receipts carried with a copied/mutation workspace; otherwise use explicit/local scratch receipts.
  alt=root/'history/evidence/W8_MUTATION_RECEIPTS'/(row['name']+'.json')
  p=alt if alt.is_file() else RECEIPTS_DEFAULT/(row['name']+'.json')
  ck(p.is_file(),'missing build receipt '+row['name'])
  if not p.is_file(): continue
  d=json.loads(p.read_text()); receipts.append(d)
  ck(d.get('wheel_twin_byte_identical') is True,'wheel twin failed '+row['name'])
  ck(d.get('sdist_semantic_twin_identical') is True,'sdist semantic twin failed '+row['name'])
  ck(d.get('sdist_derived_wheel_semantic_identical') is True,'sdist-derived wheel failed '+row['name'])
  ck(bool(HEX64.fullmatch(d.get('installed_image_sha256',''))),'installed identity malformed '+row['name'])
  ck((candidate/d['wheel']).is_file() and (candidate/d['sdist']).is_file(),'candidate distribution missing '+row['name'])
 # Source ledgers remain exact against admitted current commit.
 core=json.loads((root/'history/evidence/W8_CORE_SOURCE_BLOB_LEDGER.json').read_text())
 for r in core['files']: ck(gitblob(root/r['path'])==r['git_blob_sha'],'core source blob drift '+r['path'])
 plug=json.loads((root/'history/evidence/W8_PLUGIN_SOURCE_BLOB_LEDGER.json').read_text())
 for clean,v in plug['plugins'].items():
  mod=v['module']; base=root/'packages/plugins'/clean/'src'/mod
  ck(gitblob(base/'__init__.py')==v['source_blob_sha'],'plugin source blob drift '+clean)
  ck(gitblob(base/'qcax-plugin.json')==v['descriptor_blob_sha'],'plugin descriptor blob drift '+clean)
 # Candidate structure/hash graph.
 files=sorted([p for p in candidate.iterdir() if p.is_file()],key=lambda p:p.name) if candidate.is_dir() else []
 expected=2*len(pkgs)+len(contract['artifact_set']['singleton_controls'])
 ck(len(files)==expected,f'candidate asset count {len(files)} != {expected}')
 ck(len({p.name.casefold() for p in files})==len(files),'candidate case-fold collision')
 mf=candidate/'payload-manifest.json'; sums=candidate/'SHA256SUMS'
 ck(mf.is_file() and sums.is_file(),'manifest/checksums missing')
 if mf.is_file():
  m=json.loads(mf.read_text()); mmap={x['name']:x for x in m['members']}; primary=[p for p in files if p.name not in {'payload-manifest.json','SHA256SUMS'}]
  ck(set(mmap)=={p.name for p in primary},'manifest member set mismatch')
  for p in primary: ck(mmap.get(p.name,{}).get('sha256')==sha256(p) and mmap.get(p.name,{}).get('bytes')==p.stat().st_size,'manifest mismatch '+p.name)
 if sums.is_file():
  sm={};
  for line in sums.read_text().splitlines():
   if line.strip():
    try: dg,n=line.split('  ',1); sm[n]=dg
    except ValueError: errors.append('malformed SHA256SUMS line')
  ck('SHA256SUMS' not in sm,'checksum self-reference')
  for p in [x for x in files if x.name!='SHA256SUMS']: ck(sm.get(p.name)==sha256(p),'checksum mismatch '+p.name)
 wheels=[]; sdists=[]
 for p in files:
  try:
   if p.suffix=='.whl':
    d,v,_,_=parse_wheel_filename(p.name); wheels.append((canonicalize_name(str(d)),str(v),p))
   elif p.name.endswith('.tar.gz'):
    d,v=parse_sdist_filename(p.name); sdists.append((canonicalize_name(str(d)),str(v),p))
  except Exception as e: errors.append('distribution filename parse '+p.name)
 ck(len(wheels)==11 and {x[0] for x in wheels}==pkgs,'wheel set mismatch')
 ck(len(sdists)==11 and {x[0] for x in sdists}==pkgs,'sdist set mismatch')
 lockp=candidate/'release-lock.json'
 if lockp.is_file():
  lock=json.loads(lockp.read_text()); by={canonicalize_name(x['distribution_name']):x for x in lock['entries']}
  ck(set(by)==pkgs,'release-lock package set mismatch')
  for d,v,p in wheels: ck(by.get(d,{}).get('wheel_sha256')==sha256(p),'release-lock wheel hash mismatch '+d)
  for d,v,p in sdists: ck(by.get(d,{}).get('sdist_sha256')==sha256(p),'release-lock sdist hash mismatch '+d)
 sbp=candidate/'sbom.spdx.json'
 if sbp.is_file():
  sb=json.loads(sbp.read_text()); sbset={(canonicalize_name(x['name']),x['versionInfo']) for x in sb.get('packages',[])}
  ck(sbset=={(x,'0.1.0a1') for x in pkgs},'SBOM coverage mismatch')
 bundle_specs={
  'spec-bundle.zip': [(root/'spec', 'spec'), (root/'release/policy','release/policy')],
  'conformance-bundle.zip': [(root/'tests','tests'), (root/'tools','tools'), (root/'conformance','conformance')],
 }
 for zn,sources in bundle_specs.items():
  zp=candidate/zn
  ck(zp.is_file(),zn+' missing')
  if zp.is_file():
   try:
    expected={}
    for src,arcroot in sources:
     for q in src.rglob('*'):
      if q.is_file() and q.name!='.gitkeep' and '__pycache__' not in q.parts and q.suffix not in {'.pyc','.pyo'}:
       expected[(Path(arcroot)/q.relative_to(src)).as_posix()]=q.read_bytes()
    with zipfile.ZipFile(zp) as z:
     names=z.namelist(); ck(len(names)==len(set(names)),zn+' duplicate member')
     ck(not any(n.startswith('/') or '..' in Path(n).parts or '\\' in n for n in names),zn+' unsafe member'); ck(z.testzip() is None,zn+' CRC failure')
     ck(set(names)==set(expected),zn+' source member set mismatch')
     for n,b in expected.items(): ck(n in names and z.read(n)==b,zn+' source byte mismatch '+n)
   except Exception as e: errors.append(zn+' invalid zip: '+repr(e))
 can=root/'history/evidence/W8_INSTALLED_CANARY.json'
 ck(can.is_file(),'installed canary receipt missing')
 if can.is_file():
  c=json.loads(can.read_text()); ck(c.get('status')=='PASS','installed canary not PASS'); ck(len(c.get('distributions',[]))==11,'installed canary distribution count'); ck(len(c.get('entry_points',[]))==8,'installed canary entrypoint count'); ck(len(c.get('active_plugins',[]))==8,'installed canary active count')
 # Source tree must remain free of generated build/cache metadata.
 bad=[]
 for p in (root/'packages').rglob('*'):
  if p.name=='__pycache__' or p.suffix in {'.pyc','.pyo'} or p.name.endswith('.egg-info') or (p.is_dir() and p.name in {'build','dist'}): bad.append(str(p.relative_to(root)))
 ck(not bad,'source contamination: '+','.join(bad[:10]))
 blockers=json.loads((root/'history/evidence/W7_PROVIDER_READBACK_BLOCKERS.json').read_text())
 ck(all(v['state']=='INACCESSIBLE_CURRENT_CONNECTOR' for v in blockers['blocked_properties'].values()),'provider blockers changed without readback')
 # W8 qualification remains valid after the separately evidenced provider-gated identity transition.
 ri=contract.get('release_identity',{})
 ck(ri.get('status')=='ACTIVE','version identity is not ACTIVE after provider gate closure')
 ck(ri.get('selected_tag')=='v0.1.0-alpha.1','selected version tag drift')
 ck(ri.get('selected_version')=='0.1.0a1','selected version drift')
 provider=json.loads((root/'history/evidence/VERSION_PROVIDER_ABSENCE.json').read_text(encoding='utf-8'))
 ck(provider.get('overall')=='NO_PRIOR_ARTIFACT_PROVED','provider gate not closed')
 ck(provider.get('github_release_tag')=='ABSENT_DIRECT_PROVIDER_READ','GitHub direct absence evidence missing')
 ck(provider.get('pypi_identity')=='ABSENT_DIRECT_PROVIDER_READ','PyPI direct absence evidence missing')
 ck(provider.get('pypi_search_observation_is_absence_proof') is False,'search miss admitted as provider proof')
 return {'status':'PASS' if not errors else 'FAIL','checks':checks,'errors':errors}
if __name__=='__main__':
 ap=argparse.ArgumentParser()
 ap.add_argument('--candidate',default=str(CAND_DEFAULT))
 a=ap.parse_args()
 r=validate(ROOT_DEFAULT,Path(a.candidate)); print(json.dumps(r,sort_keys=True)); sys.exit(1 if r['errors'] else 0)
