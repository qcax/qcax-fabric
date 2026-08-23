#!/usr/bin/env python3
from pathlib import Path
import argparse,json,os,shutil,sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'release/tooling'))
from common import *
from build_candidate import deterministic_zip,collect_files,SOURCE_COMMIT,SOURCE_TREE,SOURCE_DATE_EPOCH
from finalize_payload import finalize
REH=Path(os.environ.get('QCAX_W8_REHEARSAL_DIR', str(ROOT/'.qcax-local/w8/rehearsal'))); REC=REH/'receipts'; OUT=Path(os.environ.get('QCAX_W8_SECOND_CANDIDATE_DIR', str(ROOT/'.qcax-local/w8/candidate-2')))
if OUT.exists(): shutil.rmtree(OUT)
OUT.mkdir()
c=load_json(ROOT/'release/policy/release-contract.json'); entries=[]; recs=[]
for row in package_rows(c):
 d=load_json(REC/(row['name']+'.json')); recs.append(d)
 b2=REH/'build2'/row['name']; w=next(b2.glob('*.whl')); s=next(b2.glob('*.tar.gz'))
 shutil.copy2(w,OUT/w.name); shutil.copy2(s,OUT/s.name)
 e=dict(d['lock_entry']); e['wheel_sha256']=sha256_file(w); e['sdist_sha256']=sha256_file(s); entries.append(e)
write_json(OUT/'release-lock.json',{'schema':'qcax.release-lock/clean-slate-rehearsal-v1','release':'v0.1.0-alpha.1','source_commit':SOURCE_COMMIT,'source_tree':SOURCE_TREE,'entries':entries})
deterministic_zip(OUT/'spec-bundle.zip',collect_files(ROOT/'spec','spec')+collect_files(ROOT/'release/policy','release/policy'))
deterministic_zip(OUT/'conformance-bundle.zip',collect_files(ROOT/'tests','tests')+collect_files(ROOT/'tools','tools')+collect_files(ROOT/'conformance','conformance'))
packages=[]; rels=[]
for i,e in enumerate(entries,1):
 sid=f'SPDXRef-Package-{i}'; packages.append({'name':e['distribution_name'],'SPDXID':sid,'versionInfo':e['distribution_version'],'downloadLocation':'NOASSERTION','filesAnalyzed':False,'licenseConcluded':'NOASSERTION','licenseDeclared':'Apache-2.0'}); rels.append({'spdxElementId':'SPDXRef-DOCUMENT','relationshipType':'DESCRIBES','relatedSpdxElement':sid})
write_json(OUT/'sbom.spdx.json',{'spdxVersion':'SPDX-2.3','dataLicense':'CC0-1.0','SPDXID':'SPDXRef-DOCUMENT','name':'QCAX-Fabric-W8-Local-Rehearsal','documentNamespace':'https://qcax.dev/spdx/local-w8/'+SOURCE_COMMIT,'creationInfo':{'created':'2026-08-23T03:36:47Z','creators':['Tool: QCAX-W8-local-rehearsal']},'packages':packages,'relationships':rels})
notes=ROOT/'release/templates/RELEASE_NOTES_TEMPLATE.md'; (OUT/'RELEASE_NOTES.md').write_text(notes.read_text() if notes.exists() else '# QCAX Fabric W8 local rehearsal\n')
import setuptools,packaging
pr=[]
for d,e in zip(recs,entries):
 x={k:v for k,v in d.items() if k!='lock_entry'}; x['wheel_sha256']=e['wheel_sha256']; x['sdist_sha256']=e['sdist_sha256']; pr.append(x)
write_json(OUT/'qcax-release-provenance.json',{'schema':'qcax.release-provenance/local-w8-v1','source_commit':SOURCE_COMMIT,'source_tree':SOURCE_TREE,'source_date_epoch':SOURCE_DATE_EPOCH,'release_tag_candidate':'v0.1.0-alpha.1','build_lane':'CURRENT_SANDBOX_TOOLCHAIN_REHEARSAL_NOT_PINNED_RELEASE_TOOLCHAIN','runtime':{'python':sys.version.split()[0],'setuptools':setuptools.__version__,'packaging':packaging.__version__},'intended_release_toolchain':(ROOT/'requirements/release.txt').read_text().splitlines(),'packages':pr})
finalize(OUT)
print(json.dumps({'status':'PASS','assets':len(list(OUT.iterdir()))},sort_keys=True))
