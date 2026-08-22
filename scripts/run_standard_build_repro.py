from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib, json, os, shutil, subprocess, sys, tempfile

ROOT=Path(__file__).resolve().parents[1]
ENV=os.environ.copy(); ENV['PYTHONDONTWRITEBYTECODE']='1'; ENV['SOURCE_DATE_EPOCH']='1787356800'; ENV['PIP_DISABLE_PIP_VERSION_CHECK']='1'
PACKAGES=[ROOT/'packages/contracts', ROOT/'packages/sdk', ROOT/'packages/host'] + sorted(p for p in (ROOT/'packages/plugins').iterdir() if p.is_dir())

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def build_one(src:Path, work:Path, out:Path):
    shutil.copytree(src,work)
    out.mkdir(parents=True,exist_ok=True)
    r=subprocess.run([sys.executable,'-m','pip','wheel','--no-deps','--no-build-isolation','-w',str(out),str(work)],cwd='/',env=ENV,text=True,capture_output=True)
    if r.returncode: raise RuntimeError(f'{src}: {r.stdout}\n{r.stderr}')
    ws=list(out.glob('*.whl'))
    if len(ws)!=1: raise RuntimeError(f'{src}: expected 1 wheel, got {len(ws)}')
    return ws[0]

def build_set(base:Path,out:Path):
    out.mkdir(parents=True,exist_ok=True); built=[]
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs=[]
        for i,src in enumerate(PACKAGES):
            futs.append(ex.submit(build_one,src,base/f'p{i:02d}-{src.name}',base/f'o{i:02d}'))
        for fut in as_completed(futs): built.append(fut.result())
    for p in built: shutil.copy2(p,out/p.name)
    wheels=sorted(out.glob('*.whl'))
    if len(wheels)!=len(PACKAGES): raise RuntimeError(f'wheel count {len(wheels)} != {len(PACKAGES)}')
    return {p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in wheels}

with tempfile.TemporaryDirectory() as td:
    td=Path(td); ra=build_set(td/'a',td/'wa'); rb=build_set(td/'b',td/'wb')
    same=ra==rb; mismatches=sorted(k for k in set(ra)|set(rb) if ra.get(k)!=rb.get(k))
    outdir=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else None
    if outdir:
        if outdir.exists(): shutil.rmtree(outdir)
        outdir.mkdir(parents=True)
        for p in (td/'wa').glob('*.whl'): shutil.copy2(p,outdir/p.name)
    result={'status':'PASS' if same else 'FAIL','builder':'pip-wheel-setuptools-no-build-isolation','source_date_epoch':ENV['SOURCE_DATE_EPOCH'],'distributions':len(ra),'byte_identical_twins':len(ra) if same else 0,'wheels':ra,'mismatches':mismatches,'output_dir':str(outdir) if outdir else None}
    print(json.dumps(result,sort_keys=True)); raise SystemExit(0 if same else 1)
