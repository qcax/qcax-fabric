from pathlib import Path
import sys, hashlib, json
R=Path(__file__).resolve().parents[1]
src=[R/'packages/contracts/src',R/'packages/sdk/src',R/'packages/host/src']+[p/'src' for p in (R/'packages/plugins').iterdir() if p.is_dir()]
sys.path[:0]=list(map(str,src))
from qcax_fabric_contracts import *
from qcax_fabric_sdk import PluginDefinition, AdmissionTicket
from qcax_fabric_sdk.installation import _issue_development_ticket_for_tests, installed_image_digest_from_record_text
from qcax_fabric_host import *

def art(seed,occ='o'):
 b=seed.encode(); return ArtifactIdentity('DEVELOPMENT_TREE',hashlib.sha256(b).hexdigest(),len(b),occ,'x')
def make(pid='org.qcax.x',pc='FIRST_PARTY',prov=('x',),req=(),side='NONE',roll='',mode='TRUSTED_IN_PROCESS',ec=(),ee=()):
 d=PluginDescriptor(pid,'0.1.0-alpha.1',pc,distribution_name=pid.replace('.','-'),distribution_version='0.1.0a1',provides=tuple(Capability(x,'1.0.0') for x in prov),requires=tuple(Capability(x,'1.0.0') for x in req),side_effect_class=side,rollback_receipt_schema=roll,execution_mode=mode,events_consumed=ec,events_emitted=ee)
 e=PluginEnvelope(d,art(pid)); return d,_issue_development_ticket_for_tests(e)
def kill(name,fn):
 try: fn(); return {'id':name,'killed':False}
 except Exception: return {'id':name,'killed':True}
rows=[]
# F01/F02 trust-chain attacks.
d,t=make(); raw=t.envelope
rows.append(kill('raw_envelope_preflight_bypass',lambda:PluginHost(BootLock('t','c',())).preflight(raw)))
rows.append(kill('raw_envelope_add_bypass',lambda:PluginHost(BootLock('t','c',())).add(raw,PluginDefinition(d,lambda c:c.provide('x',1)))))
rows.append(kill('caller_constructed_ticket',lambda:AdmissionTicket(t.envelope,t.receipt,object())))
# Existing authority/safety attacks.
d,t=make(pc='THIRD_PARTY'); rows.append(kill('untrusted_inprocess',lambda:PluginHost(BootLock('t','c',())).add(t,PluginDefinition(d,lambda c:c.provide('x',1)))))
d,t=make(side='EXTERNAL_MUTATION',roll='r'); rows.append(kill('external_mutation_without_auth',lambda:PluginHost(BootLock('t','c',())).add(t,PluginDefinition(d,lambda c:c.provide('x',1)))))
d,t=make(pc='THIRD_PARTY',mode='SANDBOXED_PROCESS'); rows.append(kill('sandboxed_mode_not_implemented',lambda:PluginHost(BootLock('t','c',(),(TrustedArtifact(d.plugin_id,t.envelope.artifact.sha256),))).add(t,PluginDefinition(d,lambda c:c.provide('x',1)))))
d,t=make(pid='org.qcax.fake',prov=('qcax.truth.read',)); lock=LockedProvider('qcax.truth','org.qcax.truth',t.envelope.artifact.sha256); rows.append(kill('reserved_takeover',lambda:PluginHost(BootLock('t','c',(lock,))).add(t,PluginDefinition(d,lambda c:c.provide('qcax.truth.read',1)))))
d,t=make(pid='org.qcax.truth',pc='SYSTEM_PINNED',prov=('qcax.truth.read',)); lock=LockedProvider('qcax.truth',d.plugin_id,'0'*64); rows.append(kill('wrong_pinned_digest',lambda:PluginHost(BootLock('t','c',(lock,))).add(t,PluginDefinition(d,lambda c:c.provide('qcax.truth.read',1)))))
# Variants/cycles/contracts.
d,t=make(); H=PluginHost(BootLock('t','c',())); H.observe_artifact(d,t.envelope.artifact); rows.append(kill('variant_collision',lambda:H.observe_artifact(d,ArtifactIdentity('INSTALLED_IMAGE','f'*64,1,'o2','x'))))
rows.append(kill('float_canonicality',lambda:canonical_bytes({'x':1.2})))
rows.append(kill('bad_semver_core_zero',lambda:PluginDescriptor('org.qcax.z','01.0.0','FIRST_PARTY')))
rows.append(kill('bad_semver_prerelease_zero',lambda:PluginDescriptor('org.qcax.z','1.0.0-01','FIRST_PARTY')))
rows.append(kill('prerelease_contract_version',lambda:Capability('x','1.0.0-alpha.1')))
rows.append(kill('duplicate_lock_prefix',lambda:BootLock('t','c',(LockedProvider('x','org.qcax.a','0'*64),LockedProvider('x','org.qcax.a','0'*64)))))
# BootLock order must be canonical, not construction-order-dependent.
a=LockedProvider('a','org.qcax.a','a'*64); b=LockedProvider('b','org.qcax.b','b'*64)
rows.append({'id':'bootlock_order_identity_drift','killed':canonical_sha256(BootLock('t','c',(a,b)).public_record())==canonical_sha256(BootLock('t','c',(b,a)).public_record())})
# Dependency cycle.
a,ta=make('org.qcax.a',prov=('a',),req=('b',)); b,tb=make('org.qcax.b',prov=('b',),req=('a',)); h=PluginHost(BootLock('t','c',())); h.add(ta,PluginDefinition(a,lambda c:c.provide('a',1))); h.add(tb,PluginDefinition(b,lambda c:c.provide('b',1))); rows.append({'id':'dependency_cycle','killed':h.state(a.plugin_id)==State.HOLD and h.state(b.plugin_id)==State.HOLD})
# Missing declared service.
d,t=make(); rows.append(kill('missing_declared_service',lambda:PluginHost(BootLock('t','c',())).add(t,PluginDefinition(d,lambda c:None))))
# Guard and event failure receipts.
s=EventSpec('x.guard','guard'); a,ta=make('org.qcax.a',prov=(),ec=(s,)); b,tb=make('org.qcax.b',prov=(),ee=(s,)); h=PluginHost(BootLock('t','c',())); h.add(ta,PluginDefinition(a,lambda c:c.on(s,lambda p:False))); h.add(tb,PluginDefinition(b,lambda c:None)); rows.append(kill('guard_deny',lambda:h.dispatch(s,{'x':1},b.plugin_id)))
h=PluginHost(BootLock('t','c',())); h.add(tb,PluginDefinition(b,lambda c:None)); rows.append(kill('guard_zero_handler_fail_open',lambda:h.dispatch(s,{'x':1},b.plugin_id)))
for mode in ('emit','serial','waterfall','guard'):
 s=EventSpec('x.'+mode,mode); c,tc=make('org.qcax.c-'+mode,prov=(),ec=(s,)); e,te=make('org.qcax.e-'+mode,prov=(),ee=(s,)); h=PluginHost(BootLock('t','c',()))
 def boom(_): raise RuntimeError('boom')
 h.add(tc,PluginDefinition(c,lambda ctx,s=s:ctx.on(s,boom))); h.add(te,PluginDefinition(e,lambda ctx:None))
 try: h.dispatch(s,{},e.plugin_id)
 except RuntimeError: pass
 rows.append({'id':'event_error_receipt_'+mode,'killed':bool(h.event_receipts) and h.event_receipts[-1]['decision']=='ERROR' and 'boom' not in str(h.event_receipts[-1])})
# DURABLE is reserved but unsupported in alpha host.
s=EventSpec('x.durable','emit','DURABLE'); d,t=make('org.qcax.d',prov=(),ee=(s,)); rows.append(kill('durable_claim_without_store',lambda:PluginHost(BootLock('t','c',())).add(t,PluginDefinition(d,lambda c:None))))
# InstalledImage stability and unknown additions.
_base="pkg/a.py,sha256=abc,1\nd-1.dist-info/METADATA,sha256=def,2\nd-1.dist-info/RECORD,,\n"
_a=_base+"d-1.dist-info/direct_url.json,sha256=one,10\nd-1.dist-info/INSTALLER,sha256=two,3\nd-1.dist-info/REQUESTED,sha256=three,0\n"
_b=_base+"d-1.dist-info/direct_url.json,sha256=changed,99\nd-1.dist-info/INSTALLER,sha256=other,4\nd-1.dist-info/REQUESTED,sha256=else,0\n"
rows.append({'id':'installer_metadata_identity_drift','killed':installed_image_digest_from_record_text(_a)==installed_image_digest_from_record_text(_b)})
rows.append({'id':'unknown_hashed_metadata_laundering','killed':installed_image_digest_from_record_text(_base)!=installed_image_digest_from_record_text(_base+"d-1.dist-info/UNKNOWN,sha256=zzz,1\n")})
# Mapping parser must fail closed on schema drift.
base={'schema_version':'qcax.plugin/v1alpha1','plugin_id':'example.x','plugin_version':'0.1.0-alpha.1','plugin_class':'THIRD_PARTY','api_version':'qcax.fabric/v1alpha1','distribution_name':'example-x','distribution_version':'0.1.0a1','provides':[],'requires':[],'events_consumed':[],'events_emitted':[],'permissions':[],'target_scopes':['*'],'side_effect_class':'NONE','execution_mode':'TRUSTED_IN_PROCESS','config_schema':'','state_schema':'','rollback_receipt_schema':''}
for mid,mut in [('missing_schema',lambda x:x.pop('schema_version')),('unknown_key',lambda x:x.__setitem__('oops',1)),('bad_event_id',lambda x:x['events_emitted'].append({'name':'BAD EVENT','mode':'emit','durability':'EPHEMERAL','contract_version':'1.0.0'}))]:
 x=dict(base); x={k:(list(v) if isinstance(v,list) else v) for k,v in x.items()}; mut(x); rows.append(kill('mapping_'+mid,lambda x=x:plugin_descriptor_from_mapping(x)))
status=all(x['killed'] for x in rows)
print(json.dumps({'status':'PASS' if status else 'FAIL','total':len(rows),'killed':sum(x['killed'] for x in rows),'survivors':[x['id'] for x in rows if not x['killed']],'results':rows},sort_keys=True)); sys.exit(0 if status else 1)
