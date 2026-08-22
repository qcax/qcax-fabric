from pathlib import Path
import json, os, subprocess, sys, tempfile

ROOT=Path(__file__).resolve().parents[1]
ENV=os.environ.copy(); ENV['PYTHONDONTWRITEBYTECODE']='1'; ENV['PIP_DISABLE_PIP_VERSION_CHECK']='1'

def run(cmd):
    r=subprocess.run(cmd,cwd='/',env=ENV,text=True,capture_output=True)
    if r.returncode: raise RuntimeError(r.stdout+'\n'+r.stderr)
    return r.stdout.strip()

def norm(s): return s.replace('-','_').lower()

if len(sys.argv)<2: raise SystemExit('usage: generate_release_lock.py WHEELDIR [OUT] [RELEASE]')
wh=Path(sys.argv[1]).resolve(); out=Path(sys.argv[2]).resolve() if len(sys.argv)>2 else Path('release-lock.json').resolve(); release=sys.argv[3] if len(sys.argv)>3 else 'v0.1.0-alpha.1'
wheels=sorted(wh.glob('*.whl'))
if not wheels: raise SystemExit('no wheels')
with tempfile.TemporaryDirectory() as td:
    td=Path(td); venv=td/'venv'; run([sys.executable,'-m','venv',str(venv)]); py=venv/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    order=[]
    for key in ['qcax_fabric_contracts','qcax_fabric_sdk','qcax_fabric_host']:
        order += [p for p in wheels if norm(p.name).startswith(key)]
    order += [p for p in wheels if p not in order]
    for p in order: run([str(py),'-m','pip','install','--no-index','--no-deps',str(p)])
    entries=[]
    for p in order:
        r=json.loads(run([str(py),str(ROOT/'scripts/verify_installed_wheel.py'),str(p),str(venv)]))
        if r['status']!='PASS': raise RuntimeError(json.dumps(r))
        entries.append({
            'distribution_name':r['distribution_name'], 'distribution_version':r['distribution_version'],
            'wheel_filename':r['wheel'], 'wheel_sha256':r['wheel_sha256'],
            'installed_image_sha256':r['installed_image_sha256'], 'plugin_ids':r['plugin_ids'],
        })
    entries=sorted(entries,key=lambda x:(x['distribution_name'],x['wheel_filename']))
    lock={'schema':'qcax.release-lock/v1alpha1','release':release,'entries':entries}
    try:
        from jsonschema import Draft202012Validator
        schema=json.loads((ROOT/'spec/release-lock-v1alpha1.schema.json').read_text(encoding='utf-8'))
        errs=list(Draft202012Validator(schema).iter_errors(lock))
        if errs: raise RuntimeError('release-lock-schema:'+errs[0].message)
    except ImportError as exc:
        raise RuntimeError('jsonschema required for release-lock generation') from exc
    out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(lock,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(json.dumps({'status':'PASS','release':release,'entries':len(entries),'schema_valid':True,'out':str(out)},sort_keys=True))
