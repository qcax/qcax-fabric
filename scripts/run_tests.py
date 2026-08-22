from pathlib import Path
import os, subprocess, sys, json
R=Path(__file__).resolve().parents[1]
src=[R/'packages/contracts/src',R/'packages/sdk/src',R/'packages/host/src']+[p/'src' for p in (R/'packages/plugins').iterdir() if p.is_dir()]
env=os.environ.copy(); env['PYTHONDONTWRITEBYTECODE']='1'; env['PYTHONPATH']=os.pathsep.join(map(str,src))
r=subprocess.run([sys.executable,'-m','unittest','discover','-s',str(R/'tests'),'-p','test_*.py','-v'],cwd='/',env=env,text=True,capture_output=True)
print(r.stdout); print(r.stderr,file=sys.stderr); sys.exit(r.returncode)
