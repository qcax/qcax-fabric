from pathlib import Path
import json,re,sys,tomllib
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from contract_conformance_lib import run_contract_conformance
errors=[]; checks=0
def ok(cond,msg):
 global checks; checks+=1
 if not cond: errors.append(msg)
# JSON parse
for p in ROOT.rglob('*.json'):
 try: json.loads(p.read_text(encoding='utf-8')); ok(True,'')
 except Exception as e: ok(False,f'{p}: {e}')
# package metadata / PEP 639 string license
for p in ROOT.glob('packages/**/pyproject.toml'):
 d=tomllib.loads(p.read_text(encoding='utf-8')); pr=d['project']; ok(pr.get('license')=='Apache-2.0',f'{p}: license expression'); ok('license-files' in pr,f'{p}: license-files'); ok(pr.get('requires-python')=='>=3.11',f'{p}: requires-python')
# import boundaries
host=(ROOT/'packages/host/src/qcax_fabric_host/host.py').read_text(encoding='utf-8')
for forbidden in ['prompt_hardener','memoryfabric','leadfinder','langgraph','temporal','cordisadapter']:
 ok(forbidden not in host.lower(),f'host special-cases {forbidden}')
for p in ROOT.glob('packages/plugins/*/src/*/*.py'):
 t=p.read_text(encoding='utf-8'); ok('qcax_fabric_host' not in t,f'plugin imports host: {p}')
 own=p.parent.name
 for m in re.findall(r'qcax_plugin_[a-z0-9_]+',t): ok(m==own,f'plugin imports sibling {m}: {p}')
# Workflow enablement is fail-closed and state-bound. R5-authorized trees may
# enable only the explicitly declared, full-SHA-pinned workflow set.
wf=ROOT/'.github/workflows'
state_path=ROOT/'github/PUBLICATION_STATE.json'
state=json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {}
enabled=sorted(p.name for p in wf.glob('*.yml')) if wf.exists() else []
if enabled:
 ok(state.get('state')=='R5_AUTHORIZED_PREPUBLICATION_READY','enabled workflows without R5 authorized publication state')
 ok(enabled==sorted(state.get('enabled_workflows',[])),'enabled workflow set differs from publication state')
else:
 ok(state.get('state')!='R5_AUTHORIZED_PREPUBLICATION_READY' or not state.get('enabled_workflows'),'R5 state declares workflows but none enabled')
# source hygiene -- generated packaging/cache material is never source
gen_dirs=[p for p in ROOT.rglob('*') if p.is_dir() and (p.name in {'__pycache__','build','dist'} or p.name.endswith('.egg-info'))]
bad_files=[p for p in ROOT.rglob('*') if p.is_file() and (p.suffix in {'.pyc','.pyo'} or '__pycache__' in p.parts)]
ok(not gen_dirs,f'generated directories: {gen_dirs[:5]}'); ok(not bad_files,f'generated cache files: {bad_files[:5]}')
# workflow-ready policy
sha_re=re.compile(r'^[0-9a-f]{40}$')
uses_re=re.compile(r'^\s*-?\s*uses:\s*([^@\s]+)@([^\s#]+)',re.M)
for p in sorted((ROOT/'github/workflows-ready').glob('*.yml')):
 t=p.read_text(encoding='utf-8'); ok('pull_request_target' not in t,f'unsafe pull_request_target: {p}')
 for action,ref in uses_re.findall(t):
  if action.startswith('./'): continue
  ok(bool(sha_re.fullmatch(ref)),f'non-SHA action pin {action}@{ref} in {p}')
# action pin ledger shape and enabled-workflow exact source parity
ledger=json.loads((ROOT/'github/ACTION_PIN_LEDGER.json').read_text());
pin_map={(x['action'],x['sha']) for x in ledger['pins']}
for row in ledger['pins']: ok(bool(sha_re.fullmatch(row['sha'])),f'bad action pin: {row}')
for p in sorted(wf.glob('*.yml')) if wf.exists() else []:
 ready=ROOT/'github/workflows-ready'/p.name
 ok(ready.exists(),f'enabled workflow missing reviewed mirror: {p.name}')
 if ready.exists(): ok(p.read_bytes()==ready.read_bytes(),f'enabled workflow differs from reviewed mirror: {p.name}')
 for action,ref in uses_re.findall(p.read_text(encoding='utf-8')):
  if action.startswith('./'): continue
  ok((action,ref) in pin_map,f'enabled workflow pin absent from ledger: {action}@{ref}')
# setup checklist DAG/executors
cl=json.loads((ROOT/'github/IMPLEMENTATION_CHECKLIST.json').read_text()); ids=[x['id'] for x in cl['steps']]; ok(cl['step_count']==len(cl['steps'])==len(set(ids)),'checklist ids/count');
valid_exec=set(json.loads((ROOT/'github/EXECUTOR_CAPABILITY_MATRIX.json').read_text())['executors'])
seen=set()
for row in cl['steps']:
 ok(row['executor'] in valid_exec,f'bad executor {row["id"]}'); ok(all(d in ids for d in row['depends_on']),f'bad dependency {row["id"]}'); seen.add(row['id'])

# Normative schema + Python binding + receipt conformance. This is part of
# release admission, not an optional side test.
cc=run_contract_conformance(ROOT)
checks += cc.get('checks',0)
if cc.get('status')!='PASS':
 errors.extend('contract-conformance:'+x for x in cc.get('errors',[]))

# Public claim boundaries must distinguish structural roles from implemented packages
# and must not advertise durable events before an event-store implementation exists.
readme=(ROOT/'README.md').read_text(encoding='utf-8')
ok('8 implemented plugin packages' in readme,'README missing implemented plugin package count')
ok('54 structurally pluginizable roles' in readme,'README missing structural role boundary')
ok('DURABLE events are reserved but unsupported in alpha1' in readme,'README overclaims durable events')

# REPO_TREE parity excluding itself
tree=ROOT/'github/REPO_TREE.txt'
actual=sorted(p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file() and p!=tree and '.git' not in p.relative_to(ROOT).parts)
expected=[x for x in tree.read_text(encoding='utf-8').splitlines() if x.strip()] if tree.exists() else []
ok(expected==actual,'github/REPO_TREE.txt stale')
print(json.dumps({'status':'PASS' if not errors else 'FAIL','checks':checks,'errors':errors},sort_keys=True)); sys.exit(1 if errors else 0)
