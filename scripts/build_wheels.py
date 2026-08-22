from pathlib import Path
import base64,csv,hashlib,io,json,shutil,sys,tomllib,zipfile
R=Path(__file__).resolve().parents[1]
OUT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else R/'wheelhouse'
PKGS=[R/'packages/contracts',R/'packages/sdk',R/'packages/host']+sorted((R/'packages/plugins').iterdir())
PKGS=[p for p in PKGS if (p/'pyproject.toml').is_file()]
FIXED=(2026,8,22,10,0,0)
def sha(data): return hashlib.sha256(data).hexdigest()
def b64sha(data): return base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip('=')
def norm_dist(s): return re_norm(s)
def re_norm(s):
    import re
    return re.sub(r'[-_.]+','_',s)
def metadata(project):
    lines=['Metadata-Version: 2.4',f"Name: {project['name']}",f"Version: {project['version']}"]
    if project.get('description'): lines.append(f"Summary: {project['description']}")
    if project.get('requires-python'): lines.append(f"Requires-Python: {project['requires-python']}")
    lic=project.get('license')
    if isinstance(lic,str): lines.append(f'License-Expression: {lic}')
    for lf in project.get('license-files',[]): lines.append(f'License-File: {lf}')
    for dep in project.get('dependencies',[]): lines.append(f'Requires-Dist: {dep}')
    return ('\n'.join(lines)+'\n\n').encode()
def build(pkg,dest):
    d=tomllib.loads((pkg/'pyproject.toml').read_text(encoding='utf-8')); pr=d['project']; name=pr['name']; version=pr['version']; dn=re_norm(name); dist=f'{dn}-{version}.dist-info'
    files={}
    src=pkg/'src'
    for p in sorted(src.rglob('*')):
        if p.is_file() and '__pycache__' not in p.parts and p.suffix not in {'.pyc','.pyo'}:
            files[p.relative_to(src).as_posix()]=p.read_bytes()
    files[f'{dist}/METADATA']=metadata(pr)
    files[f'{dist}/WHEEL']=b'Wheel-Version: 1.0\nGenerator: qcax-r4.4-reference-wheel\nRoot-Is-Purelib: true\nTag: py3-none-any\n\n'
    eps=d.get('project',{}).get('entry-points',{})
    if eps:
        text=[]
        for group, entries in eps.items():
            text.append(f'[{group}]')
            for k,v in sorted(entries.items()): text.append(f'{k} = {v}')
            text.append('')
        files[f'{dist}/entry_points.txt']=('\n'.join(text)+'\n').encode()
    for lf in pr.get('license-files',[]):
        p=pkg/lf
        if p.is_file(): files[f'{dist}/licenses/{lf}']=p.read_bytes()
    top=sorted({x.split('/')[0] for x in files if not x.startswith(dist+'/')})
    if top: files[f'{dist}/top_level.txt']=('\n'.join(top)+'\n').encode()
    rec=[]
    for path,data in sorted(files.items()): rec.append([path,'sha256='+b64sha(data),str(len(data))])
    rec.append([f'{dist}/RECORD','',''])
    sio=io.StringIO(newline=''); w=csv.writer(sio,lineterminator='\n'); w.writerows(rec); files[f'{dist}/RECORD']=sio.getvalue().encode()
    out=dest/f'{dn}-{version}-py3-none-any.whl'
    with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for path,data in sorted(files.items()):
            zi=zipfile.ZipInfo(path,FIXED); zi.compress_type=zipfile.ZIP_DEFLATED; zi.create_system=3; zi.external_attr=(0o100644 & 0xffff)<<16; zi.flag_bits=0
            z.writestr(zi,data,compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)
    return {'name':out.name,'sha256':sha(out.read_bytes()),'bytes':out.stat().st_size}
def one(dest):
    if dest.exists(): shutil.rmtree(dest)
    dest.mkdir(parents=True)
    return [build(p,dest) for p in PKGS]
if OUT.exists(): shutil.rmtree(OUT)
import tempfile
with tempfile.TemporaryDirectory() as td:
    a=Path(td)/'a'; b=Path(td)/'b'; ra=one(a); rb=one(b)
    if ra!=rb: raise SystemExit(json.dumps({'status':'FAIL','reason':'non-deterministic reference wheel','a':ra,'b':rb},sort_keys=True))
    OUT.mkdir(parents=True)
    for p in a.glob('*.whl'): shutil.copy2(p,OUT/p.name)
print(json.dumps({'status':'PASS','packages':len(PKGS),'wheels':ra,'deterministic_twin':True,'builder':'qcax-r4.4-reference-wheel','scope':'local prepublication conformance builder; GitHub release build must independently validate standard build frontend output'},sort_keys=True))
