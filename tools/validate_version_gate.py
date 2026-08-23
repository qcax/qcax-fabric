#!/usr/bin/env python3
from pathlib import Path
import json,tomllib,sys,re
ROOT=Path(__file__).resolve().parents[1]
EXPECTED_SCHEMA_IDS={'artifact-envelope-v1alpha1.schema.json': 'urn:qcax:schema:artifact-envelope:v1alpha1', 'boot-lock-v1alpha1.schema.json': 'urn:qcax:schema:boot-lock:v1alpha1', 'installation-receipt-v1alpha1.schema.json': 'https://qcax.dev/schemas/installation-receipt-v1alpha1.json', 'plugin-descriptor-v1alpha1.schema.json': 'urn:qcax:schema:plugin-descriptor:v1alpha1', 'release-lock-v1alpha1.schema.json': 'https://qcax.dev/schemas/release-lock-v1alpha1.json'}
EXPECTED_DISTS=['qcax-fabric-contracts', 'qcax-fabric-sdk', 'qcax-fabric-host', 'qcax-fabric-plugin-authorization', 'qcax-fabric-plugin-canonical-identity', 'qcax-fabric-plugin-memory', 'qcax-fabric-plugin-prompt-hardener', 'qcax-fabric-plugin-provenance', 'qcax-fabric-plugin-source-admission', 'qcax-fabric-plugin-truth-policy', 'qcax-fabric-plugin-hello-example']
EXPECTED_PLUGIN_IDS=['org.qcax.authorization', 'org.qcax.canonical-identity', 'example.qcax.hello', 'org.qcax.memory', 'org.qcax.prompt-hardener', 'org.qcax.provenance', 'org.qcax.source-admission', 'org.qcax.truth-policy']
EXPECTED_ENTRY_NAMES=['authorization', 'canonical_identity', 'hello_plugin', 'memory', 'prompt_hardener', 'provenance', 'source_admission', 'truth_policy']
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
 ck('0.1.0a1' in t and 'v0.1.0-alpha.1' in t,'version mapping missing')
 ck('Never repoint an existing schema ID to changed semantics.' in t,'schema immutability promise missing')

# Package identities/versions and plugin discovery contract.
contract=json.loads((ROOT/'release/policy/release-contract.json').read_text())
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
ck(len(versions)==11 and set(versions)=={'0.1.0a1'},'coordinated package version drift')
ck(sorted(plugin_ids)==sorted(EXPECTED_PLUGIN_IDS),'plugin identity set drift')
ck(sorted(entry_names)==sorted(EXPECTED_ENTRY_NAMES),'entry-point discovery set drift')

mig=ROOT/'history/migration/FIRST_PUBLIC_ALPHA_MIGRATION.md'
ck(mig.is_file(),'first-public-alpha migration note missing')
if mig.is_file():
 mt=mig.read_text(encoding='utf-8').lower()
 ck('first published qcax fabric alpha' in mt,'migration note does not state first-public-alpha intent')
 ck('does not claim' in mt and 'pypi' in mt and 'github' in mt,'migration note claim ceiling missing')

# Release identity must remain held until provider no-prior-artifact proof exists.
ri=contract['release_identity']
ck(ri['status']=='HOLD_UNTIL_SEMANTIC_VERSION_GATE','release identity prematurely promoted')
provider=ROOT/'history/evidence/VERSION_PROVIDER_ABSENCE.json'
ck(provider.is_file(),'version provider absence receipt missing')
provider_state='MISSING'
if provider.is_file():
 pd=json.loads(provider.read_text())
 provider_state=pd.get('overall','MISSING')
 ck(pd.get('github_release_tag') in ('ABSENT_FRESH_PRIOR_READ','INACCESSIBLE_CURRENT_CONNECTOR'),'invalid GitHub provider state')
 ck(pd.get('pypi_identity') in ('INACCESSIBLE_CURRENT_CONNECTOR','ABSENT_DIRECT_PROVIDER_READ'),'invalid PyPI provider state')
 if pd.get('pypi_identity')=='ABSENT_DIRECT_PROVIDER_READ' and pd.get('github_release_tag')=='ABSENT_FRESH_PRIOR_READ':
  provider_state='NO_PRIOR_ARTIFACT_PROVED'
 else:
  provider_state='HOLD_PROVIDER_ABSENCE'

status='FAIL' if errors else ('PASS' if provider_state=='NO_PRIOR_ARTIFACT_PROVED' else 'PASS_WITH_HOLD')
print(json.dumps({'status':status,'checks':checks,'errors':errors,'provider_state':provider_state,
                   'local_semantic_continuity':'PASS' if not errors else 'FAIL'},sort_keys=True))
sys.exit(1 if errors else 0)
