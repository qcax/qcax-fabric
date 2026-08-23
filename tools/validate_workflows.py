#!/usr/bin/env python3
from pathlib import Path
import yaml,re,json,sys,ast
ROOT=Path(__file__).resolve().parents[1]
errors=[]; checks=0
def ck(c,m):
 global checks; checks+=1
 if not c: errors.append(m)
contract=json.loads((ROOT/'release/policy/workflow-contract.json').read_text())
ledger=json.loads((ROOT/'release/policy/action-pin-ledger.json').read_text())
pins={x['action']:x['sha'] for x in ledger['pins']}
expected=set(contract['canonical_workflows']); actual={p.name for p in (ROOT/'.github/workflows').glob('*.yml')}
ck(actual==expected,f'workflow set mismatch: {sorted(actual)}')
ck(not (ROOT/'github/workflows-ready').exists(),'forbidden workflow mirror exists')
all_uses=[]
for p in sorted((ROOT/'.github/workflows').glob('*.yml')):
 text=p.read_text()
 try: d=yaml.load(text,Loader=yaml.BaseLoader)
 except Exception as e: ck(False,f'{p.name} YAML parse: {e}'); continue
 ck('pull_request_target' not in text,f'{p.name} uses pull_request_target')
 ck('actions/cache@' not in text,f'{p.name} uses release cache action')
 uses=re.findall(r'^\s*-?\s*uses:\s*([^\s#]+)',text,re.M)
 for u in uses:
  if u.startswith('./'): continue
  ck('@' in u,f'{p.name} action missing ref: {u}')
  if '@' not in u: continue
  act,sha=u.rsplit('@',1); all_uses.append((p.name,act,sha))
  ck(bool(re.fullmatch(r'[0-9a-f]{40}',sha)),f'{p.name} non-SHA action pin: {u}')
  parts=act.split('/')
  repo_action='/'.join(parts[:2]) if len(parts)>=2 else act
  ck(repo_action in pins,f'{p.name} action repository absent from ledger: {repo_action}')
  if repo_action in pins: ck(pins[repo_action]==sha,f'{p.name} pin differs from ledger: {repo_action}')
 for rel in re.findall(r'python(?:\s+-[^\s]+)*\s+((?:release/tooling|tools|conformance|tests)/[A-Za-z0-9_./-]+\.py)',text):
  ck((ROOT/rel).is_file(),f'{p.name} missing local Python interface {rel}')
ci=(ROOT/'.github/workflows/ci.yml').read_text(encoding='utf-8')
ck('unittest discover -s tests/semantics' in ci,'CI unittest discovery is not scoped to executable semantic tests')
conf=(ROOT/'.github/workflows/conformance.yml').read_text(encoding='utf-8')
ck('--mode pr-exercise' in conf,'PR candidate build does not use pr-exercise mode')
ck('release/tooling/finalize_payload.py release/generated/pr-candidate' in conf,'PR candidate is not finalized before verification')
ck(conf.index('release/tooling/build_candidate.py --mode pr-exercise') < conf.index('release/tooling/finalize_payload.py release/generated/pr-candidate') < conf.index('release/tooling/verify_candidate.py release/generated/pr-candidate'),'PR candidate build/finalize/verify order invalid')
fp=(ROOT/'release/tooling/finalize_payload.py').read_text(encoding='utf-8')
ck('from build_candidate import SOURCE_COMMIT,SOURCE_TREE' in fp,'payload finalizer does not bind dynamic checkout source identity')
ck('74e6d62e633746676650d66c6789dd6f56621305' not in fp and 'fb2e4db4e268107c098750f3060c341b9dae7680' not in fp,'payload finalizer hard-codes predecessor source identity')
ck('tools/validate_w8.py --candidate release/generated/pr-candidate' in conf,'PR lane missing W8 candidate validation')
ck('tests/release/test_w8_mutations.py' in conf,'PR lane missing W8 mutation harness')
ck((ROOT/'tools/validate_repo.py').is_file(),'CI validate_repo interface missing')
ck((ROOT/'tools/run_all.py').is_file(),'full-assurance run_all interface missing')
for rel in ('conformance/run_mutations.py','conformance/run_installed_image.py','conformance/run_exact_wheel_canaries.py','conformance/run_out_of_tree_canary.py','tools/validate_authority_boundaries.py'):
 ck((ROOT/rel).is_file(),f'conformance interface missing {rel}')
for x in ledger['pins']:
 ck(x.get('upstream_commit_resolved') is True,f"upstream pin not revalidated: {x['action']}")
pypi_policy=json.loads((ROOT/'release/policy/pypi-publication-policy.json').read_text(encoding='utf-8'))
for wfjob,env in contract['irreversible_environments'].items():
 wf,job=wfjob.split('/',1); d=yaml.load((ROOT/'.github/workflows'/wf).read_text(),Loader=yaml.BaseLoader)
 got=d['jobs'][job].get('environment')
 if wfjob=='pypi-publish.yml/publish':
  ck(got=='${{ matrix.environment }}',f'{wfjob} must use validated per-project matrix environment, got {got!r}')
  rows=pypi_policy.get('trusted_publishers') or []
  ck(len(rows)==11 and len({x.get("environment") for x in rows})==11,'PyPI per-project environment map must contain 11 unique environments')
  ck(rows and rows[0].get('environment')==env,'PyPI contracts environment must retain workflow-contract base environment')
 else:
  ck(got==env,f'{wfjob} environment {got!r} != {env!r}')
for wfjob,required in contract['permission_contracts'].items():
 wf,job=wfjob.split('/',1); d=yaml.load((ROOT/'.github/workflows'/wf).read_text(),Loader=yaml.BaseLoader)
 perms=d['jobs'][job].get('permissions',{}) or {}; got={f'{k}:{v}' for k,v in perms.items()}
 ck(set(required)<=got,f'{wfjob} permissions missing {sorted(set(required)-got)}')
required_ifaces={'activate_contract.py','build_candidate.py','verify_candidate.py','prepare_sbom_root.py','finalize_payload.py','verify_github_attestations.py','record_preflight_receipt.py','reconcile_preflight.py','publish_github.py','verify_github_release.py','assert_release_event.py','compare_replay.py','record_replay_receipt.py','pypi_integrity.py','pypi_precheck.py','pypi_postverify.py'}
ck({p.name for p in (ROOT/'release/tooling').glob('*.py')}>=required_ifaces,'W5 tooling interface set incomplete')
for p in list((ROOT/'release/tooling').glob('*.py'))+[Path(__file__)]:
 try: compile(p.read_text(),str(p),'exec')
 except Exception as e: ck(False,f'{p.relative_to(ROOT)} compile: {e}')
print(json.dumps({'status':'PASS' if not errors else 'FAIL','checks':checks,'uses_count':len(all_uses),'errors':errors},sort_keys=True))
sys.exit(1 if errors else 0)
