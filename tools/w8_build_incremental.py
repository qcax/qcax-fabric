#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import argparse,json,shutil,sys,tempfile,os
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'release/tooling'))
from common import *
from build_candidate import (SOURCE_COMMIT,SOURCE_TREE,SOURCE_DATE_EPOCH,clean_copy,build_one,build_from_sdist,
    semantic_sdist_sha,semantic_zip_sha,install_identity,package_plugin_ids,deterministic_zip,collect_files)

OUT=Path(os.environ.get('QCAX_W8_CANDIDATE_DIR', str(ROOT/'.qcax-local/w8/candidate')))
REH=Path(os.environ.get('QCAX_W8_REHEARSAL_DIR', str(ROOT/'.qcax-local/w8/rehearsal')))
RECEIPTS=REH/'receipts'

def ensure():
    for p in (OUT,REH/'build1',REH/'build2',REH/'sdist-derived',RECEIPTS): p.mkdir(parents=True,exist_ok=True)

def build_pkg(row):
    ensure(); name=row['name']; receipt=RECEIPTS/(name+'.json')
    if receipt.exists():
        d=load_json(receipt)
        good=all((OUT/f).is_file() for f in (d['wheel'],d['sdist']))
        if good and sha256_file(OUT/d['wheel'])==d['wheel_sha256'] and sha256_file(OUT/d['sdist'])==d['sdist_sha256']:
            return {'status':'SKIP_VERIFIED','name':name}
    src=ROOT/row['path']; arts=[]
    for idx in (1,2):
        out=REH/f'build{idx}'/name
        if out.exists(): shutil.rmtree(out)
        out.mkdir(parents=True)
        with tempfile.TemporaryDirectory() as td:
            c=Path(td)/'pkg'; clean_copy(src,c); arts.append(build_one(c,out))
    (w1,s1),(w2,s2)=arts
    if w1.name!=w2.name or s1.name!=s2.name: raise ReleaseError('twin filename mismatch '+name)
    if w1.read_bytes()!=w2.read_bytes(): raise ReleaseError('wheel twins not byte-identical '+name)
    ssem1=semantic_sdist_sha(s1); ssem2=semantic_sdist_sha(s2)
    if ssem1!=ssem2: raise ReleaseError('sdist semantic twin mismatch '+name)
    dout=REH/'sdist-derived'/name
    if dout.exists(): shutil.rmtree(dout)
    dw=build_from_sdist(s1,dout)
    if dw.name!=w1.name or semantic_zip_sha(dw)!=semantic_zip_sha(w1): raise ReleaseError('sdist-derived wheel semantic mismatch '+name)
    shutil.copy2(w1,OUT/w1.name); shutil.copy2(s1,OUT/s1.name)
    installed_sha,record_count,verified_bytes=install_identity(w1)
    lock={'distribution_name':name,'distribution_version':'0.1.0a1','wheel_filename':w1.name,'wheel_sha256':sha256_file(w1),
          'sdist_filename':s1.name,'sdist_sha256':sha256_file(s1),'sdist_semantic_sha256':ssem1,
          'installed_image_sha256':installed_sha,'plugin_ids':package_plugin_ids(src),'dependencies':row.get('dependencies',[])}
    d={'schema':'qcax.w8-package-build-receipt/1','name':name,'wheel':w1.name,'wheel_sha256':sha256_file(w1),
       'wheel_twin_byte_identical':True,'sdist':s1.name,'sdist_sha256':sha256_file(s1),
       'sdist_twin_byte_identical':s1.read_bytes()==s2.read_bytes(),'sdist_semantic_sha256':ssem1,
       'sdist_semantic_twin_identical':True,'sdist_derived_wheel_semantic_identical':True,
       'installed_image_sha256':installed_sha,'verified_record_entries':record_count,'verified_bytes':verified_bytes,
       'lock_entry':lock,'actual_toolchain_lane':'CURRENT_SANDBOX_SETuptools_82.0.1_PACKAGING_25.0'}
    write_json(receipt,d); return {'status':'PASS','name':name}

def finalize(tag):
    ensure(); c=load_json(ROOT/'release/policy/release-contract.json'); rows=package_rows(c)
    recs=[]
    for row in rows:
        p=RECEIPTS/(row['name']+'.json')
        if not p.is_file(): raise ReleaseError('missing package build receipt '+row['name'])
        recs.append(load_json(p))
    lock={'schema':'qcax.release-lock/clean-slate-rehearsal-v1','release':tag,'source_commit':SOURCE_COMMIT,'source_tree':SOURCE_TREE,
          'entries':[r['lock_entry'] for r in recs]}
    write_json(OUT/'release-lock.json',lock)
    deterministic_zip(OUT/'spec-bundle.zip',collect_files(ROOT/'spec','spec')+collect_files(ROOT/'release/policy','release/policy'))
    deterministic_zip(OUT/'conformance-bundle.zip',collect_files(ROOT/'tests','tests')+collect_files(ROOT/'tools','tools')+collect_files(ROOT/'conformance','conformance'))
    packages=[]; rels=[]
    for i,e in enumerate(lock['entries'],1):
        sid=f'SPDXRef-Package-{i}'
        packages.append({'name':e['distribution_name'],'SPDXID':sid,'versionInfo':e['distribution_version'],'downloadLocation':'NOASSERTION','filesAnalyzed':False,'licenseConcluded':'NOASSERTION','licenseDeclared':'Apache-2.0'})
        rels.append({'spdxElementId':'SPDXRef-DOCUMENT','relationshipType':'DESCRIBES','relatedSpdxElement':sid})
    sbom={'spdxVersion':'SPDX-2.3','dataLicense':'CC0-1.0','SPDXID':'SPDXRef-DOCUMENT','name':'QCAX-Fabric-W8-Local-Rehearsal',
          'documentNamespace':'https://qcax.dev/spdx/local-w8/'+SOURCE_COMMIT,'creationInfo':{'created':'2026-08-23T03:36:47Z','creators':['Tool: QCAX-W8-local-rehearsal']},
          'packages':packages,'relationships':rels}
    write_json(OUT/'sbom.spdx.json',sbom)
    notes=ROOT/'release/templates/RELEASE_NOTES_TEMPLATE.md'; (OUT/'RELEASE_NOTES.md').write_text(notes.read_text() if notes.exists() else '# QCAX Fabric W8 local rehearsal\n')
    import setuptools,packaging
    prov={'schema':'qcax.release-provenance/local-w8-v1','source_commit':SOURCE_COMMIT,'source_tree':SOURCE_TREE,'source_date_epoch':SOURCE_DATE_EPOCH,
          'release_tag_candidate':tag,'build_lane':'CURRENT_SANDBOX_TOOLCHAIN_REHEARSAL_NOT_PINNED_RELEASE_TOOLCHAIN',
          'runtime':{'python':sys.version.split()[0],'setuptools':setuptools.__version__,'packaging':packaging.__version__},
          'intended_release_toolchain':(ROOT/'requirements/release.txt').read_text().splitlines(),
          'packages':[{k:v for k,v in r.items() if k!='lock_entry'} for r in recs]}
    write_json(OUT/'qcax-release-provenance.json',prov)
    return {'status':'PASS','receipts':len(recs)}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--packages',nargs='*'); ap.add_argument('--finalize',action='store_true'); ap.add_argument('--reset',action='store_true')
    a=ap.parse_args(); c=load_json(ROOT/'release/policy/release-contract.json'); rows=package_rows(c)
    if a.reset:
        for p in (OUT,REH):
            if p.exists(): shutil.rmtree(p)
    chosen=set(a.packages or [])
    out=[]
    if chosen:
        by={r['name']:r for r in rows}; unknown=chosen-set(by)
        if unknown: raise ReleaseError('unknown packages: '+','.join(sorted(unknown)))
        for name in a.packages: out.append(build_pkg(by[name]))
    if a.finalize: out.append(finalize('v0.1.0-alpha.1'))
    print(json.dumps({'status':'PASS','operations':out},sort_keys=True))
if __name__=='__main__': main()
