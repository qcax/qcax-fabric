#!/usr/bin/env python3
from pathlib import Path
import json,os,subprocess,sys,yaml
import jsonschema
ROOT=Path(__file__).resolve().parents[1]
env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
runs=[]; errors=[]

def run(rel,*args):
    p=subprocess.run([sys.executable,str(ROOT/rel),*map(str,args)],cwd=str(ROOT),
                     env=env,capture_output=True,text=True,timeout=150)
    runs.append({'script':rel,'returncode':p.returncode,'stdout':p.stdout.strip(),'stderr':p.stderr.strip()[-1000:]})
    if p.returncode: errors.append(f'{rel} failed')
    return p

for rel in ('tools/validate_authority_boundaries.py','tools/validate_workflows.py',
            'tools/validate_w7_packages.py','tools/validate_version_gate.py','tools/validate_w9_provider.py'):
    run(rel)

required_public=(
 'README.md','CITATION.cff','CODE_OF_CONDUCT.md','CONTRIBUTING.md','GOVERNANCE.md','SECURITY.md','SUPPORT.md',
 '.github/ISSUE_TEMPLATE/bug.yml','.github/ISSUE_TEMPLATE/rfc.yml','.github/pull_request_template.md',
)
required_isolation=(
 'adapters/acp/ADAPTER_PLAN.json','adapters/cordis/ADAPTER_PLAN.json','adapters/inspect/ADAPTER_PLAN.json',
 'adapters/langgraph/ADAPTER_PLAN.json','adapters/temporal/ADAPTER_PLAN.json',
 'profiles/forecasting/PROFILE_PLAN.json','profiles/leadfinder/PROFILE_PLAN.json',
 'profiles/mathematics/PROFILE_PLAN.json','profiles/research/PROFILE_PLAN.json',
)
for rel in required_public+required_isolation:
    if not (ROOT/rel).is_file(): errors.append(f'required preserved repository path missing: {rel}')

json_count=0; schema_count=0
for p in ROOT.rglob('*.json'):
    if any(x in p.parts for x in ('release','conformance')) and 'generated' in p.parts: continue
    try:
        d=json.loads(p.read_text(encoding='utf-8')); json_count+=1
        if p.name.endswith('.schema.json') or '$schema' in d:
            jsonschema.Draft202012Validator.check_schema(d); schema_count+=1
    except Exception as exc:
        errors.append(f'JSON/schema parse {p.relative_to(ROOT)}: {exc}')
for p in (ROOT/'.github/workflows').glob('*.yml'):
    try: yaml.safe_load(p.read_text(encoding='utf-8'))
    except Exception as exc: errors.append(f'workflow YAML parse {p.name}: {exc}')

py_count=0
for p in ROOT.rglob('*.py'):
    if any(part in {'release/generated','conformance/generated'} for part in p.parts): continue
    try: compile(p.read_text(encoding='utf-8'),str(p),'exec'); py_count+=1
    except Exception as exc: errors.append(f'compile {p.relative_to(ROOT)}: {exc}')

bad=[]
for p in ROOT.rglob('*'):
    if p.name=='__pycache__' or p.suffix in {'.pyc','.pyo'} or p.name.endswith('.egg-info'):
        bad.append(str(p.relative_to(ROOT)))
if bad: errors.append('generated cache/build metadata: '+','.join(bad[:12]))

print(json.dumps({'status':'PASS' if not errors else 'FAIL','subruns':runs,
                  'json_files':json_count,'schemas':schema_count,'python_files':py_count,'errors':errors},sort_keys=True))
sys.exit(1 if errors else 0)
