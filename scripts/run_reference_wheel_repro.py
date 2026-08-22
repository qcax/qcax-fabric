from pathlib import Path
import hashlib, json, os, subprocess, sys, tempfile
ROOT=Path(__file__).resolve().parents[1]
ENV=os.environ.copy(); ENV['PYTHONDONTWRITEBYTECODE']='1'
def run(cmd):
    r=subprocess.run(cmd,cwd='/',env=ENV,text=True,capture_output=True)
    if r.returncode: raise RuntimeError(r.stdout+'\n'+r.stderr)
    return r.stdout.strip()
def snapshot(d):
    return {p.name:{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in sorted(d.glob('*.whl'))}
with tempfile.TemporaryDirectory() as td:
    td=Path(td); a=td/'a'; b=td/'b'
    ra=json.loads(run([sys.executable,str(ROOT/'scripts/build_wheels.py'),str(a)])); rb=json.loads(run([sys.executable,str(ROOT/'scripts/build_wheels.py'),str(b)]))
    sa=snapshot(a); sb=snapshot(b); ok=sa==sb and len(sa)==11
    print(json.dumps({'status':'PASS' if ok else 'FAIL','distributions':len(sa),'byte_identical_twins':len(sa) if ok else 0,'wheels':sa,'builder_receipts':[ra,rb]},sort_keys=True))
    raise SystemExit(0 if ok else 1)
