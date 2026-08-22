from pathlib import Path
import subprocess,sys,json,os
R=Path(__file__).resolve().parents[1]; env=os.environ.copy(); env['PYTHONDONTWRITEBYTECODE']='1'
cmds=[['validate_repo.py'],['run_tests.py'],['run_mutations.py']]; out=[]
for [s] in cmds:
 r=subprocess.run([sys.executable,str(R/'scripts'/s)],cwd='/',env=env,text=True,capture_output=True)
 out.append({'script':s,'returncode':r.returncode,'stdout':r.stdout.strip()[-2000:],'stderr':r.stderr.strip()[-1000:]})
 if r.returncode: print(json.dumps({'status':'FAIL','results':out},indent=2)); raise SystemExit(1)
print(json.dumps({'status':'PASS','commands':len(cmds),'results':out},indent=2))
