#!/usr/bin/env python3
from pathlib import Path
import ast,json,re,sys
ROOT=Path(__file__).resolve().parents[1]
errors=[]; checks=0
def ck(cond,msg):
    global checks
    checks+=1
    if not cond: errors.append(msg)

# Runtime/source must not import evidence, generated outputs, tests or tools.
for p in sorted((ROOT/'packages').rglob('*.py')):
    try: tree=ast.parse(p.read_text(encoding='utf-8'),filename=str(p))
    except SyntaxError as exc:
        ck(False,f'syntax error {p.relative_to(ROOT)}: {exc}'); continue
    for n in ast.walk(tree):
        mods=[]
        if isinstance(n,ast.Import): mods=[a.name for a in n.names]
        elif isinstance(n,ast.ImportFrom) and n.module: mods=[n.module]
        for mod in mods:
            ck(not any(mod==x or mod.startswith(x+'.') for x in ('history','tests','tools','release.generated','conformance.generated')),
               f'{p.relative_to(ROOT)} imports noncanonical module {mod}')

# Canonical generated roots are output-only.
for rel in ('release/generated','conformance/generated'):
    d=ROOT/rel
    ck(d.is_dir(),f'missing generated root {rel}')
    if d.is_dir():
        extra=[p.relative_to(ROOT).as_posix() for p in d.rglob('*') if p.is_file() and p.name!='.gitkeep']
        ck(not extra,f'generated source contamination {extra[:8]}')

# No old workflow mirror or repository-local scratch.
ck(not (ROOT/'github/workflows-ready').exists(),'forbidden workflow mirror exists')
ck('.qcax-local/' in (ROOT/'.gitignore').read_text(encoding='utf-8'),'local rehearsal scratch is not ignored')
ck(not (ROOT/'.qcax-local').exists(),'local rehearsal scratch leaked into source tree')

# Portable public source: reject sandbox/host-specific absolute paths in canonical text.
scan_roots=['packages','tests','tools','release','conformance','spec','docs','.github']
sandbox_marker='/mnt'+'/data'
for rel in scan_roots:
    d=ROOT/rel
    if not d.exists(): continue
    for p in d.rglob('*'):
        if not p.is_file(): continue
        try: text=p.read_text(encoding='utf-8')
        except UnicodeDecodeError: continue
        ck(sandbox_marker not in text,f'sandbox path leaked into {p.relative_to(ROOT)}')
        ck(re.search(r'(?<![A-Za-z0-9_])[A-Za-z]:\\\\',text) is None,f'Windows absolute path leaked into {p.relative_to(ROOT)}')

# Basic secret-pattern rejection for public source.
secret_patterns=[
    r'gh[pousr]_[A-Za-z0-9]{20,}',r'github_pat_[A-Za-z0-9_]{20,}',
    r'AKIA[0-9A-Z]{16}',r'AIza[0-9A-Za-z_-]{20,}',
    r'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'
]
for rel in scan_roots:
    d=ROOT/rel
    if not d.exists(): continue
    for p in d.rglob('*'):
        if not p.is_file(): continue
        try: text=p.read_text(encoding='utf-8')
        except UnicodeDecodeError: continue
        for pat in secret_patterns:
            ck(re.search(pat,text) is None,f'credential-like material in {p.relative_to(ROOT)}')

# Release identity may be ACTIVE only when the bounded direct-provider gate is recorded;
# publication authority remains fail-closed and separate.
contract=json.loads((ROOT/'release/policy/release-contract.json').read_text(encoding='utf-8'))
ri=contract.get('release_identity',{})
ck(ri.get('status')=='ACTIVE','release identity is not ACTIVE after provider gate closure')
ck(ri.get('selected_tag')=='v0.1.0-alpha.1','selected release tag drift')
ck(ri.get('selected_version')=='0.1.0a1','selected release version drift')
provider=ROOT/'history/evidence/VERSION_PROVIDER_ABSENCE.json'
ck(provider.is_file(),'version provider absence receipt missing')
if provider.is_file():
    pd=json.loads(provider.read_text(encoding='utf-8'))
    ck(pd.get('overall')=='NO_PRIOR_ARTIFACT_PROVED','provider gate not closed')
    ck(pd.get('github_release_tag')=='ABSENT_DIRECT_PROVIDER_READ','GitHub direct provider evidence missing')
    ck(pd.get('pypi_identity')=='ABSENT_DIRECT_PROVIDER_READ','PyPI direct provider evidence missing')
    ck(pd.get('pypi_search_observation_is_absence_proof') is False,'search miss admitted as provider proof')
    gh=pd.get('github_direct_reads',{})
    ck(gh.get('tag_ref',{}).get('status_code')==404,'GitHub tag-ref direct absence missing')
    ck(gh.get('release_by_tag',{}).get('status_code')==404,'GitHub release-by-tag direct absence missing')
    rows=pd.get('pypi_direct_reads',[])
    ck(len(rows)==11,'PyPI direct-provider row count drift')
    ck(all(x.get('project_json_status')==404 and x.get('version_json_status')==404 and x.get('simple_index_status')==404 for x in rows),'PyPI direct-provider absence incomplete')
auth=ROOT/'history/evidence/BRANCH_PR_AUTHORIZATION_RECEIPT.json'
ck(auth.is_file(),'branch/PR authorization receipt missing')
if auth.is_file():
    a=json.loads(auth.read_text(encoding='utf-8'))
    not_auth=set(a.get('not_authorized',[]))
    for x in ('main direct write','merge','tag','GitHub Release','PyPI','repository settings','rulesets','environments','secrets','deployment'):
        ck(x in not_auth,f'authorization receipt missing prohibition: {x}')

# Test-only ticket helper must not be exported by public SDK.
sdk=(ROOT/'packages/sdk/src/qcax_fabric_sdk/__init__.py').read_text(encoding='utf-8')
ck('_issue_development_ticket_for_tests' not in sdk,'private test admission helper exported')

print(json.dumps({'status':'PASS' if not errors else 'FAIL','checks':checks,'errors':errors},sort_keys=True))
sys.exit(1 if errors else 0)
