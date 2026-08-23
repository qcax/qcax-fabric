from __future__ import annotations
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess,sys,tarfile,tempfile,zipfile
from common import *
ROOT=Path(__file__).resolve().parents[2]
ADMITTED_FALLBACK_COMMIT='74e6d62e633746676650d66c6789dd6f56621305'
ADMITTED_FALLBACK_TREE='fb2e4db4e268107c098750f3060c341b9dae7680'
ADMITTED_FALLBACK_EPOCH=1787456207

def _git(*args):
    try:
        p=subprocess.run(['git',*args],cwd=str(ROOT),capture_output=True,text=True,timeout=10)
        return p.stdout.strip() if p.returncode==0 else ''
    except Exception:
        return ''

SOURCE_COMMIT=(os.environ.get('QCAX_SOURCE_COMMIT') or _git('rev-parse','HEAD') or ADMITTED_FALLBACK_COMMIT)
SOURCE_TREE=(os.environ.get('QCAX_SOURCE_TREE') or _git('rev-parse','HEAD^{tree}') or ADMITTED_FALLBACK_TREE)
SOURCE_DATE_EPOCH=int(os.environ.get('SOURCE_DATE_EPOCH') or _git('show','-s','--format=%ct','HEAD') or ADMITTED_FALLBACK_EPOCH)

IGNORE=shutil.ignore_patterns('build','dist','*.egg-info','__pycache__','*.pyc','*.pyo')

def normalize_mtime(root:Path):
    for p in sorted(root.rglob('*')):
        try: os.utime(p,(SOURCE_DATE_EPOCH,SOURCE_DATE_EPOCH),follow_symlinks=False)
        except OSError: pass
    os.utime(root,(SOURCE_DATE_EPOCH,SOURCE_DATE_EPOCH))

def semantic_zip_sha(path:Path):
    h=hashlib.sha256()
    with zipfile.ZipFile(path) as z:
        for n in sorted(z.namelist()):
            if n.endswith('/'): continue
            data=z.read(n); h.update(n.encode()+b'\0'+len(data).to_bytes(8,'big')+data)
    return h.hexdigest()

def semantic_sdist_sha(path:Path):
    h=hashlib.sha256()
    with tarfile.open(path,'r:*') as t:
        members=[m for m in t.getmembers() if m.isfile()]
        for m in sorted(members,key=lambda x:x.name):
            # Strip the generated top-level project-version directory.
            rel=m.name.split('/',1)[1] if '/' in m.name else m.name
            f=t.extractfile(m); data=f.read() if f else b''
            h.update(rel.encode()+b'\0'+len(data).to_bytes(8,'big')+data)
    return h.hexdigest()

def run(cmd,cwd,env):
    p=subprocess.run(cmd,cwd=str(cwd),env=env,capture_output=True,text=True,timeout=120)
    if p.returncode:
        raise ReleaseError(f"command failed {cmd}: {p.stderr[-2000:]}")
    return p

def _backend_call(cwd:Path,method:str,out:Path):
    from setuptools import build_meta
    old=Path.cwd(); old_epoch=os.environ.get('SOURCE_DATE_EPOCH')
    os.environ['SOURCE_DATE_EPOCH']=str(SOURCE_DATE_EPOCH)
    try:
        os.chdir(cwd)
        backend=build_meta._BuildMetaBackend()
        import io,contextlib
        sink=io.StringIO()
        with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            return getattr(backend,method)(str(out))
    finally:
        os.chdir(old)
        if old_epoch is None: os.environ.pop('SOURCE_DATE_EPOCH',None)
        else: os.environ['SOURCE_DATE_EPOCH']=old_epoch

def build_one(pkg_root:Path,out:Path):
    out.mkdir(parents=True,exist_ok=True)
    _backend_call(pkg_root,'build_wheel',out)
    _backend_call(pkg_root,'build_sdist',out)
    whls=sorted(out.glob('*.whl')); sdists=sorted(out.glob('*.tar.gz'))
    if len(whls)!=1 or len(sdists)!=1: raise ReleaseError(f'expected one wheel/sdist in {out}')
    return whls[0],sdists[0]

def build_from_sdist(sdist:Path,out:Path):
    out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        ex=Path(td)/'x'; ex.mkdir()
        with tarfile.open(sdist,'r:*') as tar:
            for m in tar.getmembers():
                pp=Path(m.name)
                if m.name.startswith('/') or '..' in pp.parts or '\\' in m.name: raise ReleaseError('unsafe sdist path')
            tar.extractall(ex,filter='data')
        roots=[p for p in ex.iterdir() if p.is_dir()]
        if len(roots)!=1: raise ReleaseError('sdist root count mismatch')
        _backend_call(roots[0],'build_wheel',out)
    whls=sorted(out.glob('*.whl'))
    if len(whls)!=1: raise ReleaseError('sdist-derived wheel count mismatch')
    return whls[0]

def clean_copy(src:Path,dst:Path):
    shutil.copytree(src,dst,ignore=IGNORE)
    normalize_mtime(dst)

def package_plugin_ids(pkg:Path):
    ids=[]
    for p in pkg.glob('src/*/qcax-plugin.json'):
        d=json.loads(p.read_text()); ids.append(d['plugin_id'])
    return sorted(ids)

def install_identity(wheel:Path):
    with tempfile.TemporaryDirectory() as td:
        site=Path(td)/'site'; site.mkdir()
        with zipfile.ZipFile(wheel) as z:
            for n in z.namelist():
                pp=Path(n)
                if n.startswith('/') or '..' in pp.parts or '\\' in n: raise ReleaseError('unsafe wheel path')
            z.extractall(site)
        records=list(site.glob('*.dist-info/RECORD'))
        if len(records)!=1: raise ReleaseError('wheel RECORD count mismatch')
        sys.path[:0]=[str(ROOT/'packages/contracts/src'),str(ROOT/'packages/sdk/src')]
        from qcax_fabric_sdk.installation import installed_image_digest_from_record,verify_installed_record
        dig=installed_image_digest_from_record(records[0]); vr=verify_installed_record(records[0],site,dig)
        if vr['status']!='PASS': raise ReleaseError('wheel-root RECORD verification failed: '+repr(vr['errors']))
        return dig,vr['verified_record_entries'],vr['verified_bytes']

def deterministic_zip(out:Path,items:list[tuple[Path,str]]):
    dt=(2026,8,23,3,36,46)  # ZIP timestamps have two-second resolution.
    with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        seen=set()
        for src,arc in sorted(items,key=lambda x:x[1]):
            if arc in seen: raise ReleaseError('duplicate deterministic zip member '+arc)
            seen.add(arc); info=zipfile.ZipInfo(arc,dt); info.compress_type=zipfile.ZIP_DEFLATED; info.external_attr=(0o100644<<16)
            z.writestr(info,src.read_bytes())

def collect_files(base:Path,prefix:str):
    out=[]
    for p in base.rglob('*'):
        if p.is_file() and p.name not in {'.gitkeep'} and '__pycache__' not in p.parts and p.suffix not in {'.pyc','.pyo'}:
            out.append((p,f'{prefix}/{p.relative_to(base).as_posix()}'))
    return out

def build_all(candidate:Path,rehearsal_root:Path,tag:str):
    contract=load_json(ROOT/'release/policy/release-contract.json')
    rows=package_rows(contract)
    if len(rows)!=11: raise ReleaseError('expected 11 packages')
    if candidate.exists(): shutil.rmtree(candidate)
    if rehearsal_root.exists(): shutil.rmtree(rehearsal_root)
    candidate.mkdir(parents=True); rehearsal_root.mkdir(parents=True)
    b1=rehearsal_root/'build1'; b2=rehearsal_root/'build2'; derived=rehearsal_root/'sdist-derived'; b1.mkdir(); b2.mkdir(); derived.mkdir()
    results=[]; lock_entries=[]
    receipts_dir=rehearsal_root/'receipts'; receipts_dir.mkdir(parents=True,exist_ok=True)
    for row in rows:
        src=ROOT/row['path']
        if not (src/'pyproject.toml').is_file(): raise ReleaseError('package root incomplete '+row['path'])
        arts=[]
        for idx,outroot in ((1,b1),(2,b2)):
            with tempfile.TemporaryDirectory() as td:
                c=Path(td)/'pkg'; clean_copy(src,c); out=outroot/row['name']; out.mkdir(parents=True)
                arts.append(build_one(c,out))
        (w1,s1),(w2,s2)=arts
        if w1.name!=w2.name or s1.name!=s2.name: raise ReleaseError('twin filename mismatch '+row['name'])
        wheel_equal=w1.read_bytes()==w2.read_bytes()
        if not wheel_equal: raise ReleaseError('wheel twins not byte-identical '+row['name'])
        ssem1=semantic_sdist_sha(s1); ssem2=semantic_sdist_sha(s2)
        if ssem1!=ssem2: raise ReleaseError('sdist normalized semantic mismatch '+row['name'])
        # Build a wheel from candidate sdist and compare semantic installed artifact surface.
        dw=build_from_sdist(s1,derived/row['name'])
        if dw.name!=w1.name: raise ReleaseError('sdist-derived wheel filename mismatch '+row['name'])
        wsem1=semantic_zip_sha(w1); wsemd=semantic_zip_sha(dw)
        if wsem1!=wsemd: raise ReleaseError('sdist-derived wheel semantic mismatch '+row['name'])
        shutil.copy2(w1,candidate/w1.name); shutil.copy2(s1,candidate/s1.name)
        installed_sha,record_count,verified_bytes=install_identity(w1)
        lock_entries.append({
          'distribution_name':row['name'],'distribution_version':'0.1.0a1',
          'wheel_filename':w1.name,'wheel_sha256':sha256_file(w1),
          'sdist_filename':s1.name,'sdist_sha256':sha256_file(s1),'sdist_semantic_sha256':ssem1,
          'installed_image_sha256':installed_sha,'plugin_ids':package_plugin_ids(src),
          'dependencies':row.get('dependencies',[])
        })
        result={'schema':'qcax.w8-package-build-receipt/2','name':row['name'],'wheel':w1.name,'wheel_sha256':sha256_file(w1),'wheel_twin_byte_identical':True,
                'sdist':s1.name,'sdist_sha256':sha256_file(s1),'sdist_twin_byte_identical':s1.read_bytes()==s2.read_bytes(),
                'sdist_semantic_sha256':ssem1,'sdist_semantic_twin_identical':True,
                'sdist_derived_wheel_semantic_identical':True,'installed_image_sha256':installed_sha,
                'verified_record_entries':record_count,'verified_bytes':verified_bytes}
        result['lock_entry']=lock_entries[-1]
        write_json(receipts_dir/(row['name']+'.json'),result)
        results.append({k:v for k,v in result.items() if k!='lock_entry'})
    # Controls.
    release_lock={'schema':'qcax.release-lock/clean-slate-rehearsal-v1','release':tag,'source_commit':SOURCE_COMMIT,'source_tree':SOURCE_TREE,'entries':lock_entries}
    write_json(candidate/'release-lock.json',release_lock)
    spec_items=collect_files(ROOT/'spec','spec')+collect_files(ROOT/'release/policy','release/policy')
    deterministic_zip(candidate/'spec-bundle.zip',spec_items)
    conf_items=collect_files(ROOT/'tests','tests')+collect_files(ROOT/'tools','tools')+collect_files(ROOT/'conformance','conformance')
    deterministic_zip(candidate/'conformance-bundle.zip',conf_items)
    # Provisional local SPDX 2.3 inventory. Canonical release SBOM remains Anchore-generated in GitHub preflight.
    packages=[]; rels=[]
    for i,e in enumerate(lock_entries,1):
        sid=f'SPDXRef-Package-{i}'
        packages.append({'name':e['distribution_name'],'SPDXID':sid,'versionInfo':e['distribution_version'],'downloadLocation':'NOASSERTION','filesAnalyzed':False,'licenseConcluded':'NOASSERTION','licenseDeclared':'Apache-2.0'})
        rels.append({'spdxElementId':'SPDXRef-DOCUMENT','relationshipType':'DESCRIBES','relatedSpdxElement':sid})
    sbom={'spdxVersion':'SPDX-2.3','dataLicense':'CC0-1.0','SPDXID':'SPDXRef-DOCUMENT','name':'QCAX-Fabric-W8-Local-Rehearsal',
          'documentNamespace':'https://qcax.dev/spdx/local-w8/'+SOURCE_COMMIT,
          'creationInfo':{'created':'2026-08-23T03:36:47Z','creators':['Tool: QCAX-W8-local-rehearsal']},'packages':packages,'relationships':rels}
    write_json(candidate/'sbom.spdx.json',sbom)
    notes=ROOT/'release/templates/RELEASE_NOTES_TEMPLATE.md'
    (candidate/'RELEASE_NOTES.md').write_text(notes.read_text() if notes.exists() else '# QCAX Fabric local W8 rehearsal\n')
    import setuptools,packaging
    prov={'schema':'qcax.release-provenance/local-w8-v1','source_commit':SOURCE_COMMIT,'source_tree':SOURCE_TREE,'source_date_epoch':SOURCE_DATE_EPOCH,
          'release_tag_candidate':tag,'build_lane':'CURRENT_SANDBOX_TOOLCHAIN_REHEARSAL_NOT_PINNED_RELEASE_TOOLCHAIN',
          'runtime':{'python':sys.version.split()[0],'setuptools':setuptools.__version__,'packaging':packaging.__version__},
          'intended_release_toolchain':(ROOT/'requirements/release.txt').read_text().splitlines(),
          'packages':results}
    write_json(candidate/'qcax-release-provenance.json',prov)
    return {'packages':results,'release_lock':release_lock,'candidate':str(candidate)}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--out',required=True)
    ap.add_argument('--twin-builds',type=int,default=2)
    ap.add_argument('--mode',choices=('release','pr-exercise','replay'),default='release')
    ap.add_argument('--replay',action='store_true',help='compatibility alias for --mode replay')
    a=ap.parse_args()
    mode='replay' if a.replay else a.mode
    if a.twin_builds!=2: raise ReleaseError('W8 currently requires exactly two independent clean builds')
    tag=os.environ.get('QCAX_RELEASE_TAG','v0.1.0-alpha.1')
    commit=os.environ.get('QCAX_EXPECTED_COMMIT',SOURCE_COMMIT); require_commit(commit)
    if commit!=SOURCE_COMMIT: raise ReleaseError(f'checkout/source commit {SOURCE_COMMIT} differs from expected {commit}')
    rr=build_all(Path(a.out),Path(a.out).parent/(Path(a.out).name+'-rehearsal'),tag)
    print(json.dumps({'status':'PASS','mode':mode,'packages':len(rr['packages']),'candidate':rr['candidate'],
                      'source_commit':SOURCE_COMMIT,'source_tree':SOURCE_TREE},sort_keys=True))
if __name__=='__main__': main()
