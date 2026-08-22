from pathlib import Path
import json, os, subprocess, sys, tempfile, time
ROOT=Path(__file__).resolve().parents[1]
ENV=os.environ.copy(); ENV['PYTHONDONTWRITEBYTECODE']='1'; ENV['PIP_DISABLE_PIP_VERSION_CHECK']='1'

def run(name,cmd):
    t=time.time(); r=subprocess.run(cmd,cwd='/',env=ENV,text=True,capture_output=True)
    rec={'name':name,'returncode':r.returncode,'seconds':round(time.time()-t,3),'stdout_tail':r.stdout[-6000:],'stderr_tail':r.stderr[-3000:]}
    if r.returncode:
        print(json.dumps({'status':'FAIL','failed':name,'results':results+[rec]},indent=2)); raise SystemExit(1)
    results.append(rec); return r.stdout.strip()

results=[]
with tempfile.TemporaryDirectory() as td:
    td=Path(td); std=td/'standard-wheels'; lock=td/'release-lock.json'
    run('repository-validator',[sys.executable,str(ROOT/'scripts/validate_repo.py')])
    run('unit-tests',[sys.executable,str(ROOT/'scripts/run_tests.py')])
    run('semantic-mutations',[sys.executable,str(ROOT/'scripts/run_mutations.py')])
    run('contract-conformance',[sys.executable,str(ROOT/'scripts/run_contract_conformance.py')])
    run('reference-wheel-repro',[sys.executable,str(ROOT/'scripts/run_reference_wheel_repro.py')])
    run('reference-installed-conformance',[sys.executable,str(ROOT/'scripts/run_installed_conformance.py')])
    run('reference-secure-canary',[sys.executable,str(ROOT/'scripts/run_secure_installed_canary.py')])
    run('standard-wheel-repro',[sys.executable,str(ROOT/'scripts/run_standard_build_repro.py'),str(std)])
    run('standard-release-lock',[sys.executable,str(ROOT/'scripts/generate_release_lock.py'),str(std),str(lock),'v0.1.0-alpha.1'])
    run('standard-secure-canary',[sys.executable,str(ROOT/'scripts/run_secure_installed_canary.py'),str(std)])
    run('out-of-tree-canary',[sys.executable,str(ROOT/'scripts/run_out_of_tree_canary.py'),str(std)])
    lock_data=json.loads(lock.read_text(encoding='utf-8'))
    summary={'status':'PASS','commands':len(results),'release_lock_entries':len(lock_data['entries']),'results':results}
    print(json.dumps(summary,indent=2))
