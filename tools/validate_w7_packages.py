#!/usr/bin/env python3
from pathlib import Path
import hashlib, json, re, subprocess, sys, tomllib
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT=Path(__file__).resolve().parents[1]
errors=[]; checks=0

def check(cond,msg):
    global checks
    checks+=1
    if not cond: errors.append(msg)

def git_blob_sha(path:Path):
    # Prefer the committed Git object so checkout newline filters (notably
    # core.autocrlf on Windows runners) cannot masquerade as source drift.
    try:
        rel=path.resolve().relative_to(ROOT.resolve()).as_posix()
        proc=subprocess.run(
            ['git','rev-parse',f'HEAD:{rel}'], cwd=str(ROOT),
            capture_output=True, text=True, timeout=10,
        )
        sha=proc.stdout.strip()
        if proc.returncode==0 and re.fullmatch(r'[0-9a-f]{40}',sha):
            return sha
    except Exception:
        pass
    b=path.read_bytes()
    return hashlib.sha1(f"blob {len(b)}\0".encode()+b).hexdigest()

ledger=json.loads((ROOT/'history/evidence/W7_LIVE_PACKAGE_LEDGER.json').read_text())
projects=ledger['projects']
check(len(projects)==11,'expected exactly 11 publishable project manifests')

seen_names=[]; versions=set(); graph={}
for row in projects:
    name=row['name']; clean=ROOT/row['clean_path']; pp=clean/'pyproject.toml'
    check(pp.is_file(),f'missing {row["clean_path"]}/pyproject.toml')
    if not pp.is_file(): continue
    check(git_blob_sha(pp)==row['pyproject_blob_sha'],f'Git blob mismatch for {name}')
    data=tomllib.loads(pp.read_text(encoding='utf-8'))
    proj=data.get('project',{})
    got_name=canonicalize_name(proj.get('name',''))
    check(got_name==canonicalize_name(name),f'project name mismatch {name}')
    seen_names.append(got_name)
    versions.add(proj.get('version'))
    check(proj.get('version')=='0.1.0a1',f'coordinated version mismatch {name}')
    check(proj.get('requires-python')=='>=3.11',f'python floor mismatch {name}')
    check(proj.get('license')=='Apache-2.0',f'PEP639 license expression missing/mismatch {name}')
    check(proj.get('license-files')==['LICENSE','NOTICE'],f'license-files mismatch {name}')
    check((clean/'LICENSE').is_file() and (clean/'NOTICE').is_file(),f'legal files missing {name}')
    bs=data.get('build-system',{})
    check(bs.get('build-backend')=='setuptools.build_meta',f'build backend mismatch {name}')
    check(bs.get('requires')==['setuptools>=77'],f'build requirement mismatch {name}')
    deps=[]
    for raw in proj.get('dependencies',[]):
        req=Requirement(raw); dep=canonicalize_name(req.name); deps.append(dep)
        if dep.startswith('qcax-fabric-'):
            check(str(req.specifier)=='==0.1.0a1',f'internal dependency not exact-pinned {name}: {raw}')
    graph[got_name]=set(deps)
    is_plugin='plugin-' in got_name
    ep=data.get('project',{}).get('entry-points',{}).get('qcax.fabric.plugins',{})
    if is_plugin:
        check(len(ep)==1,f'plugin must expose exactly one qcax.fabric.plugins entry point {name}')
        if ep:
            value=next(iter(ep.values()))
            check(value.endswith(':definition'),f'plugin entry point must target definition {name}')
    else:
        check(not ep,f'non-plugin unexpectedly exposes plugin entry point {name}')

check(len(seen_names)==len(set(seen_names))==11,'normalized project names not unique')
check(versions=={'0.1.0a1'},f'package versions diverge: {sorted(versions)}')

# Internal dependency graph must reference admitted nodes and remain acyclic.
nodes=set(graph)
for src,deps in graph.items():
    for dep in deps:
        if dep.startswith('qcax-fabric-'):
            check(dep in nodes,f'{src} depends on non-admitted internal project {dep}')
state={}
def dfs(v,stack):
    state[v]=1
    for w in graph[v]:
        if w not in graph: continue
        if state.get(w)==1:
            errors.append('dependency cycle: '+' -> '.join(stack+[w])); continue
        if state.get(w)!=2: dfs(w,stack+[w])
    state[v]=2
for v in sorted(graph):
    if not state.get(v): dfs(v,[v])
checks+=1

# Path migration is explicit; clean paths must not accidentally restore the live hyphenated dirs.
mig=json.loads((ROOT/'history/evidence/W7_PATH_MIGRATION.json').read_text())
check(len(mig['mappings'])==8,'expected eight plugin path migrations')
for m in mig['mappings']:
    check((ROOT/m['clean_path']).is_dir(),f'clean plugin path missing {m["clean_path"]}')
    if m['clean_path']!=m['live_path']:
        check(not (ROOT/m['live_path']).exists(),f'live path silently restored into clean tree {m["live_path"]}')

# R11 PyPI semantics: correctness cannot depend on upload order.
stale=[]
for base in (ROOT/'release',ROOT/'docs'):
    for p in base.rglob('*'):
        if p.is_file():
            try: txt=p.read_text(encoding='utf-8').lower()
            except UnicodeDecodeError: continue
            if 'ordered pypi publication' in txt or 'ordered reconciled upload' in txt:
                stale.append(str(p.relative_to(ROOT)))
check(not stale,'stale ordered-PyPI semantics remain: '+','.join(stale))

# Version/release identity stays held during local qualification.
contract=json.loads((ROOT/'release/policy/release-contract.json').read_text())
ri=contract.get('release_identity',{})
check(ri.get('status')!='ACTIVE','release identity activated before continuity/provider gates')

# Provider promotion readbacks are load-bearing and must remain explicit blockers when inaccessible.
blockers=json.loads((ROOT/'history/evidence/W7_PROVIDER_READBACK_BLOCKERS.json').read_text())
required={'immutable_releases','actions_sha_pinning_required','release_environments','main_ruleset'}
check(required<=set(blockers.get('blocked_properties',{})), 'provider readback blocker set incomplete')
for key in required:
    check(blockers['blocked_properties'][key]['state']=='INACCESSIBLE_CURRENT_CONNECTOR',f'provider blocker not explicit: {key}')

print(json.dumps({'status':'PASS' if not errors else 'FAIL','checks':checks,'errors':errors},sort_keys=True))
sys.exit(1 if errors else 0)
