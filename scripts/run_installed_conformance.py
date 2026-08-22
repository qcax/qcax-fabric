from pathlib import Path
import hashlib,json,os,shutil,site,subprocess,sys,tempfile
ROOT=Path(__file__).resolve().parents[1]
ENV=os.environ.copy(); ENV['PYTHONDONTWRITEBYTECODE']='1'
def run(cmd,cwd=None):
    r=subprocess.run(cmd,cwd=cwd or '/',env=ENV,text=True,capture_output=True)
    if r.returncode: raise SystemExit(r.stdout+'\n'+r.stderr)
    return r.stdout
with tempfile.TemporaryDirectory() as td:
    td=Path(td); wh=td/'wheels'
    receipt=json.loads(run([sys.executable,str(ROOT/'scripts/build_wheels.py'),str(wh)]))
    venv=td/'venv'; run([sys.executable,'-m','venv',str(venv)])
    py=venv/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    order=['qcax_fabric_contracts','qcax_fabric_sdk','qcax_fabric_host']
    wheels=list(wh.glob('*.whl'))
    def norm(s): return s.replace('-','_').lower()
    ordered=[]
    for key in order:
        ordered += [p for p in wheels if norm(p.name).startswith(key)]
    ordered += [p for p in wheels if p not in ordered]
    for p in ordered: run([str(py),'-m','pip','install','--no-index','--no-deps',str(p)])
    sp=Path(run([str(py),'-c','import site; print(site.getsitepackages()[0])']).strip())
    results=[]
    for p in ordered:
        out=run([str(py),str(ROOT/'scripts/verify_installed_wheel.py'),str(p),str(sp)])
        results.append(json.loads(out))
    if any(x['status']!='PASS' for x in results): raise SystemExit('installed verification failed')
    print(json.dumps({'status':'PASS','wheel_build':receipt,'verified_wheels':len(results),'record_entries':sum(x['verified_record_entries'] for x in results),'installed_images':{x['wheel']:x['installed_image_sha256'] for x in results}},sort_keys=True))
