#!/usr/bin/env python3
from pathlib import Path
import json,tomllib,sys,re
ROOT=Path(__file__).resolve().parents[1]
EXPECTED_SCHEMA_IDS={'artifact-envelope-v1alpha1.schema.json': 'urn:qcax:schema:artifact-envelope:v1alpha1', 'boot-lock-v1alpha1.schema.json': 'urn:qcax:schema:boot-lock:v1alpha1', 'installation-receipt-v1alpha1.schema.json': 'https://qcax.dev/schemas/installation-receipt-v1alpha1.json', 'plugin-descriptor-v1alpha1.schema.json': 'urn:qcax:schema:plugin-descriptor:v1alpha1', 'release-lock-v1alpha1.schema.json': 'https://qcax.dev/schemas/release-lock-v1alpha1.json'}
EXPECTED_DISTS=['qcax-fabric-contracts', 'qcax-fabric-sdk', 'qcax-fabric-host', 'qcax-fabric-plugin-authorization', 'qcax-fabric-plugin-canonical-identity', 'qcax-fabric-plugin-memory', 'qcax-fabric-plugin-prompt-hardener', 'qcax-fabric-plugin-provenance', 'qcax-fabric-plugin-source-admission', 'qcax-fabric-plugin-truth-policy', 'qcax-fabric-plugin-hello-example']
EXPECTED_PLUGIN_IDS=['org.qcax.authorization', 'org.qcax.canonical-identity', 'example.qcax.hello', 'org.qcax.memory', 'org.qcax.prompt-hardener', 'org.qcax.provenance', 'org.qcax.source-admission', 'org.qcax.truth-policy']
EXPECTED_ENTRY_NAMES=['authorization', 'canonical_identity', 'hello_plugin', 'memory', 'prompt_hardener', 'provenance', 'source_admission', 'truth_policy']
EXPECTED_TAG='v0.1.0-alpha.1'
EXPECTED_VERSION='0.1.0a1'
errors=[]; checks=0
def ck(c,m):
 global checks
 checks+=1
 if not c: errors.append(m)

# Five current public schema identities must be preserved at their public paths.
for name,sid in EXPECTED_SCHEMA_IDS.items():
 p=ROOT/'spec'/name
 ck(p.is_file(),'missing public schema '+name)
 if p.is_file():
  try: d=json.loads(p.read_text(encoding='utf-8'))
  except Exception as exc: errors.append('invalid public schema '+name+': '+repr(exc)); continue
  ck(d.get('$id')==sid,'schema identity drift '+name)
  ck(d.get('$schema')=='https://json-schema.org/draft/2020-12/schema','schema dialect drift '+name)

compat=ROOT/'docs/COMPATIBILITY_POLICY.md'
ck(compat.is_file(),'compatibility policy missing')
if compat.is_file():
 t=compat.read_text(encoding='utf-8')
 ck('qcax.fabric/v1alpha1' in t,'plugin ABI compatibility promise missing')
 ck(EXPECTED_VERSION in t and EXPECTED_TAG in t,'version mapping missing')
 ck('Never repoint an existing schema ID to changed semantics.' in t,'schema immutability promise missing')

# Package identities/versions and plugin discovery contract.
contract=json.loads((ROOT/'release/policy/release-contract.json').read_text(encoding='utf-8'))
rows=[x for x in contract['package_set']['packages'] if x.get('publish')]
ck([x['name'] for x in rows]==EXPECTED_DISTS,'distribution project set/order drift')
versions=[]; plugin_ids=[]; entry_names=[]
for row in rows:
 p=ROOT/row['path']/'pyproject.toml'
 ck(p.is_file(),'missing pyproject '+row['name'])
 if not p.is_file(): continue
 py=tomllib.loads(p.read_text(encoding='utf-8'))
 ck(py['project']['name']==row['name'],'project name drift '+row['name'])
 versions.append(py['project']['version'])
 eps=py['project'].get('entry-points',{}).get('qcax.fabric.plugins',{})
 entry_names.extend(eps.keys())
 for src in (ROOT/row['path']/'src').glob('*/qcax-plugin.json'):
  d=json.loads(src.read_text(encoding='utf-8')); plugin_ids.append(d['plugin_id'])
  ck(d.get('api_version')=='qcax.fabric/v1alpha1','plugin ABI drift '+d.get('plugin_id','?'))
ck(len(versions)==11 and set(versions)=={EXPECTED_VERSION},'coordinated package version drift')
ck(sorted(plugin_ids)==sorted(EXPECTED_PLUGIN_IDS),'plugin identity set drift')
ck(sorted(entry_names)==sorted(EXPECTED_ENTRY_NAMES),'entry-point discovery set drift')

mig=ROOT/'history/migration/FIRST_PUBLIC_ALPHA_MIGRATION.md'
ck(mig.is_file(),'first-public-alpha migration note missing')
if mig.is_file():
 mt=mig.read_text(encoding='utf-8').lower()
 ck('first published qcax fabric alpha' in mt,'migration note does not state first-public-alpha intent')
 ck('does not claim' in mt and 'pypi' in mt and 'github' in mt,'migration note claim ceiling missing')

# ACTIVE is permitted only after bounded direct public-provider absence evidence is recorded.
provider=ROOT/'history/evidence/VERSION_PROVIDER_ABSENCE.json'
ck(provider.is_file(),'version provider absence receipt missing')
provider_ok=False
if provider.is_file():
 try:
  pd=json.loads(provider.read_text(encoding='utf-8'))
 except Exception as exc:
  errors.append('invalid version provider absence receipt: '+repr(exc)); pd={}
 ck(pd.get('schema')=='qcax.version-provider-absence/1','provider receipt schema drift')
 ck(pd.get('target')=='qcax/qcax-fabric','provider receipt target drift')
 ck(pd.get('operation')=='READ_ONLY','provider receipt operation drift')
 ck(pd.get('overall')=='NO_PRIOR_ARTIFACT_PROVED','provider overall state not promoted')
 ck(pd.get('github_release_tag')=='ABSENT_DIRECT_PROVIDER_READ','GitHub provider state not direct-absence')
 ck(pd.get('pypi_identity')=='ABSENT_DIRECT_PROVIDER_READ','PyPI provider state not direct-absence')
 ck(pd.get('pypi_search_observation_is_absence_proof') is False,'search miss incorrectly admitted as absence proof')
 recorded=pd.get('recorded_utc')
 ck(isinstance(recorded,str) and recorded.endswith('Z'),'provider receipt recording timestamp missing')
 ident=pd.get('identity',{})
 ck(ident.get('distribution_count')==11,'provider distribution count drift')
 ck(ident.get('github_tag')==EXPECTED_TAG,'provider GitHub tag drift')
 ck(ident.get('python_version')==EXPECTED_VERSION,'provider Python version drift')
 gh=pd.get('github_direct_reads',{})
 tagrow=gh.get('tag_ref',{}); relrow=gh.get('release_by_tag',{})
 tag_url=f'https://api.github.com/repos/qcax/qcax-fabric/git/ref/tags/{EXPECTED_TAG}'
 rel_url=f'https://api.github.com/repos/qcax/qcax-fabric/releases/tags/{EXPECTED_TAG}'
 ck(tagrow.get('url')==tag_url and tagrow.get('status_code')==404,'GitHub direct tag-ref absence evidence invalid')
 ck(relrow.get('url')==rel_url and relrow.get('status_code')==404,'GitHub direct release-by-tag absence evidence invalid')
 pr=pd.get('pypi_direct_reads',[])
 ck(isinstance(pr,list) and len(pr)==11,'PyPI direct-read row count drift')
 if isinstance(pr,list):
  ck([x.get('project') for x in pr]==EXPECTED_DISTS,'PyPI direct-read project set/order drift')
  for x in pr:
   n=x.get('project','?')
   ck(x.get('project_json_url')==f'https://pypi.org/pypi/{n}/json','PyPI project JSON URL drift '+n)
   ck(x.get('version_json_url')==f'https://pypi.org/pypi/{n}/{EXPECTED_VERSION}/json','PyPI version JSON URL drift '+n)
   ck(x.get('simple_index_url')==f'https://pypi.org/simple/{n}/','PyPI Simple URL drift '+n)
   ck(x.get('project_json_status')==404,'PyPI project JSON absence not proven '+n)
   ck(x.get('version_json_status')==404,'PyPI version JSON absence not proven '+n)
   ck(x.get('simple_index_status')==404,'PyPI Simple absence not proven '+n)
 provider_ok=(pd.get('overall')=='NO_PRIOR_ARTIFACT_PROVED' and
              pd.get('github_release_tag')=='ABSENT_DIRECT_PROVIDER_READ' and
              pd.get('pypi_identity')=='ABSENT_DIRECT_PROVIDER_READ' and
              pd.get('pypi_search_observation_is_absence_proof') is False and
              isinstance(pr,list) and len(pr)==11 and
              [x.get('project') for x in pr]==EXPECTED_DISTS and
              all(x.get('project_json_status')==404 and x.get('version_json_status')==404 and x.get('simple_index_status')==404 for x in pr) and
              tagrow.get('status_code')==404 and relrow.get('status_code')==404)
ck(provider_ok,'direct provider no-prior-artifact proof incomplete')

ri=contract['release_identity']
ck(ri.get('status')=='ACTIVE','release identity is not ACTIVE after provider gate closure')
ck(ri.get('selected_tag')==EXPECTED_TAG,'selected release tag drift')
ck(ri.get('selected_version')==EXPECTED_VERSION,'selected release version drift')

provider_state='NO_PRIOR_ARTIFACT_PROVED' if provider_ok else 'HOLD_PROVIDER_ABSENCE'
status='FAIL' if errors else 'PASS'
print(json.dumps({'status':status,'checks':checks,'errors':errors,'provider_state':provider_state,
                   'local_semantic_continuity':'PASS' if not errors else 'FAIL'},sort_keys=True))
sys.exit(1 if errors else 0)
