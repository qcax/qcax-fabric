from pathlib import Path
import argparse,json,re,tarfile,zipfile
from packaging.utils import canonicalize_name,parse_wheel_filename,parse_sdist_filename
from common import *
from build_candidate import collect_files
ROOT=Path(__file__).resolve().parents[2]
def verify(root:Path):
    root=Path(root); c=load_json(ROOT/'release/policy/release-contract.json'); expected=expected_asset_count(c)
    files=sorted([p for p in root.iterdir() if p.is_file()],key=lambda p:p.name)
    if len(files)!=expected: raise ReleaseError(f'asset count {len(files)} != derived {expected}')
    if len({p.name.casefold() for p in files})!=len(files): raise ReleaseError('case-fold filename collision')
    mf=load_json(root/'payload-manifest.json'); mmap={x['name']:x for x in mf['members']}
    primary=[p for p in files if p.name not in {'payload-manifest.json','SHA256SUMS'}]
    if set(mmap)!={p.name for p in primary}: raise ReleaseError('payload manifest member set mismatch')
    for p in primary:
        r=mmap[p.name]
        if r['bytes']!=p.stat().st_size or r['sha256']!=sha256_file(p): raise ReleaseError('payload manifest mismatch '+p.name)
    sums={}
    for line in (root/'SHA256SUMS').read_text().splitlines():
        if line.strip():
            dig,name=line.split('  ',1); sums[name]=dig
    for p in primary+[root/'payload-manifest.json']:
        if sums.get(p.name)!=sha256_file(p): raise ReleaseError('SHA256SUMS mismatch '+p.name)
    if 'SHA256SUMS' in sums: raise ReleaseError('SHA256SUMS self-reference forbidden')
    pkgs={canonicalize_name(x['name']) for x in package_rows(c)}
    wheels=[]; sdists=[]
    for p in files:
        if p.suffix=='.whl':
            dist,ver,build,tags=parse_wheel_filename(p.name); wheels.append((canonicalize_name(str(dist)),str(ver),p))
        elif p.name.endswith('.tar.gz'):
            dist,ver=parse_sdist_filename(p.name); sdists.append((canonicalize_name(str(dist)),str(ver),p))
    if len(wheels)!=len(pkgs) or {x[0] for x in wheels}!=pkgs: raise ReleaseError('wheel package set mismatch')
    if len(sdists)!=len(pkgs) or {x[0] for x in sdists}!=pkgs: raise ReleaseError('sdist package set mismatch')
    if any(x[1]!='0.1.0a1' for x in wheels+sdists): raise ReleaseError('distribution version mismatch')
    lock=load_json(root/'release-lock.json')
    if len(lock['entries'])!=len(pkgs): raise ReleaseError('release lock entry count mismatch')
    by={canonicalize_name(x['distribution_name']):x for x in lock['entries']}
    if set(by)!=pkgs: raise ReleaseError('release lock package set mismatch')
    for dist,ver,p in wheels:
        if by[dist]['wheel_sha256']!=sha256_file(p): raise ReleaseError('release-lock wheel hash mismatch '+dist)
    for dist,ver,p in sdists:
        if by[dist]['sdist_sha256']!=sha256_file(p): raise ReleaseError('release-lock sdist hash mismatch '+dist)
    sb=load_json(root/'sbom.spdx.json')
    sbset={(canonicalize_name(x['name']),x['versionInfo']) for x in sb.get('packages',[])}
    if sbset!={(x,'0.1.0a1') for x in pkgs}: raise ReleaseError('SBOM package coverage mismatch')
    expected_bundles={
        'spec-bundle.zip': collect_files(ROOT/'spec','spec')+collect_files(ROOT/'release/policy','release/policy'),
        'conformance-bundle.zip': collect_files(ROOT/'tests','tests')+collect_files(ROOT/'tools','tools')+collect_files(ROOT/'conformance','conformance'),
    }
    for zname,items in expected_bundles.items():
        expected_map={arc:src.read_bytes() for src,arc in items}
        with zipfile.ZipFile(root/zname) as z:
            names=z.namelist()
            bad=[n for n in names if n.startswith('/') or '..' in Path(n).parts or '\\' in n]
            if bad: raise ReleaseError(zname+' unsafe member')
            if len(names)!=len(set(names)): raise ReleaseError(zname+' duplicate member')
            if z.testzip() is not None: raise ReleaseError(zname+' CRC failure')
            if set(names)!=set(expected_map): raise ReleaseError(zname+' source member set mismatch')
            for name,data in expected_map.items():
                if z.read(name)!=data: raise ReleaseError(zname+' source byte mismatch '+name)
    return {'status':'PASS','asset_count':len(files),'package_count':len(pkgs),'manifest_primary_members':len(primary)}
if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('root'); a=ap.parse_args(); print(json.dumps(verify(Path(a.root)),sort_keys=True))
