#!/usr/bin/env python3
from pathlib import Path
import base64,hashlib,importlib,json,sys,tempfile,unittest
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
for p in ('packages/contracts/src','packages/sdk/src','packages/host/src'):
    sys.path.insert(0,str(ROOT/p))
for p in sorted((ROOT/'packages/plugins').glob('*/src')):
    sys.path.insert(0,str(p))

from qcax_fabric_contracts import *
from qcax_fabric_contracts.canonical import canonical_bytes,CanonicalizationError
from qcax_fabric_sdk import PluginDefinition
from qcax_fabric_sdk.installation import _issue_development_ticket_for_tests,installed_image_digest_from_record_text,verify_installed_record
from qcax_fabric_host import *

ROWS=[
 ('authorization','qcax_plugin_authorization'),
 ('canonical_identity','qcax_plugin_canonical_identity'),
 ('hello_example','qcax_plugin_hello_example'),
 ('memory','qcax_plugin_memory'),
 ('prompt_hardener','qcax_plugin_prompt_hardener'),
 ('provenance','qcax_plugin_provenance'),
 ('source_admission','qcax_plugin_source_admission'),
 ('truth_policy','qcax_plugin_truth_policy'),
]

def dmap(d):
    cap=lambda c:{'capability_id':c.capability_id,'contract_version':c.contract_version}
    ev=lambda e:{'name':e.name,'mode':e.mode,'durability':e.durability,'contract_version':e.contract_version}
    return {
      'schema_version':d.schema_version,'plugin_id':d.plugin_id,'plugin_version':d.plugin_version,
      'plugin_class':d.plugin_class,'api_version':d.api_version,'distribution_name':d.distribution_name,
      'distribution_version':d.distribution_version,'provides':[cap(x) for x in d.provides],
      'requires':[cap(x) for x in d.requires],'events_consumed':[ev(x) for x in d.events_consumed],
      'events_emitted':[ev(x) for x in d.events_emitted],'permissions':list(d.permissions),
      'target_scopes':list(d.target_scopes),'side_effect_class':d.side_effect_class,
      'execution_mode':d.execution_mode,'config_schema':d.config_schema,'state_schema':d.state_schema,
      'rollback_receipt_schema':d.rollback_receipt_schema,
    }

def ticket(defn,occ='o1'):
    d=defn.descriptor; b=d.plugin_id.encode(); a=ArtifactIdentity('DEVELOPMENT_TREE',hashlib.sha256(b).hexdigest(),len(b),occ,'test')
    return _issue_development_ticket_for_tests(PluginEnvelope(d,a))

class W8(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.defs={}; cls.tickets={}
        for folder,module in ROWS:
            m=importlib.import_module(module); cls.defs[module]=m.definition; cls.tickets[module]=ticket(m.definition)
    def host(self,trust_hello=True,external=False):
        locks=[]
        for m,d in self.defs.items():
            if d.descriptor.plugin_class=='SYSTEM_PINNED':
                t=self.tickets[m]
                for c in d.descriptor.provides:
                    locks.append(LockedProvider(c.capability_id,d.descriptor.plugin_id,t.envelope.artifact.sha256))
        trusted=[]
        hm='qcax_plugin_hello_example'
        if trust_hello:
            t=self.tickets[hm]; trusted.append(TrustedArtifact(t.envelope.descriptor.plugin_id,t.envelope.artifact.sha256))
        return PluginHost(BootLock('qcax/qcax-fabric','LOCAL_W8',tuple(locks),tuple(trusted),external,'w8'))
    def mount_core(self,h):
        order=['qcax_plugin_truth_policy','qcax_plugin_authorization','qcax_plugin_canonical_identity','qcax_plugin_provenance','qcax_plugin_source_admission','qcax_plugin_memory','qcax_plugin_prompt_hardener']
        for m in order: h.add(self.tickets[m],self.defs[m])
    def test_static_runtime_descriptor_exact_parity(self):
        for folder,module in ROWS:
            static=json.loads((ROOT/'packages/plugins'/folder/'src'/module/'qcax-plugin.json').read_text())
            self.assertEqual(static,dmap(self.defs[module].descriptor))
            self.assertEqual(plugin_descriptor_from_mapping(static),self.defs[module].descriptor)
    def test_core_capability_flow(self):
        h=self.host(); self.mount_core(h)
        self.assertEqual(h.service('qcax.truth.read')['target'],'qcax/qcax-fabric')
        self.assertFalse(h.service('qcax.authorization')('EXTERNAL_MUTATION'))
        self.assertTrue(h.service('qcax.source.admission')({'eligible':True}))
        self.assertFalse(h.service('qcax.source.admission')({'eligible':False}))
        mem=h.service('qcax.memory'); mem['put']('k','v',{'eligible':True}); self.assertEqual(mem['get']('k'),'v')
        with self.assertRaises(ValueError): mem['put']('bad','x',{'eligible':False})
        out=h.service('qcax.prompt.compile')('raw'); self.assertEqual(out['target'],'qcax/qcax-fabric'); self.assertFalse(out['external_mutation'])
    def test_hello_exact_trust_boundary(self):
        m='qcax_plugin_hello_example'; h=self.host(False); self.mount_core(h)
        with self.assertRaises(BootLockViolation): h.add(self.tickets[m],self.defs[m])
        h=self.host(True); self.mount_core(h); h.add(self.tickets[m],self.defs[m]); self.assertEqual(h.service('example.hello')('QCAX'),'hello QCAX')
    def test_external_mutation_fails_closed(self):
        d=PluginDescriptor('org.qcax.mut','0.1.0-alpha.1','FIRST_PARTY',distribution_name='qcax-mut',distribution_version='0.1.0a1',side_effect_class='EXTERNAL_MUTATION',rollback_receipt_schema='r')
        t=ticket(PluginDefinition(d))
        with self.assertRaises(BootLockViolation): self.host().add(t,PluginDefinition(d))
    def test_system_pinned_cannot_be_removed(self):
        h=self.host(); self.mount_core(h)
        with self.assertRaises(BootLockViolation): h.remove('org.qcax.truth-policy')
    def test_dependency_cycle_holds(self):
        a=PluginDescriptor('x.a','0.1.0-alpha.1','FIRST_PARTY',distribution_name='x-a',distribution_version='0.1.0a1',provides=(Capability('a'),),requires=(Capability('b'),))
        b=PluginDescriptor('x.b','0.1.0-alpha.1','FIRST_PARTY',distribution_name='x-b',distribution_version='0.1.0a1',provides=(Capability('b'),),requires=(Capability('a'),))
        da=PluginDefinition(a,lambda c:c.provide('a',1)); db=PluginDefinition(b,lambda c:c.provide('b',1)); h=self.host()
        h.add(ticket(da),da); h.add(ticket(db),db); self.assertEqual(h.state('x.a'),State.HOLD); self.assertEqual(h.state('x.b'),State.HOLD)
    def test_guard_without_handler_denies(self):
        h=self.host(); e=EventSpec('tool.execute','guard');
        with self.assertRaises(GuardDenied): h.dispatch(e,{'x':1})
        self.assertEqual(h.event_receipts[-1]['reason'],'NO_ACTIVE_GUARD_HANDLER')
    def test_durable_event_reserved(self):
        d=PluginDescriptor('x.e','0.1.0-alpha.1','FIRST_PARTY',distribution_name='x-e',distribution_version='0.1.0a1',events_emitted=(EventSpec('x.d','emit','DURABLE'),))
        de=PluginDefinition(d); h=self.host()
        with self.assertRaises(ManifestError): h.add(ticket(de),de)
    def test_canonicalization_profile(self):
        self.assertEqual(canonical_bytes({'b':1,'a':2}),canonical_bytes({'a':2,'b':1}))
        with self.assertRaises(CanonicalizationError): canonical_bytes({'x':1.2})
    def test_installed_record_tamper_and_unexpected_file(self):
        with tempfile.TemporaryDirectory() as td:
            r=Path(td); (r/'pkg').mkdir(); data=b'x'; (r/'pkg/a.py').write_bytes(data)
            h=base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip('=')
            rec=r/'RECORD'; rec.write_text(f'pkg/a.py,sha256={h},1\n')
            expected=installed_image_digest_from_record_text(rec.read_text())
            self.assertEqual(verify_installed_record(rec,r,expected)['status'],'PASS')
            (r/'pkg/extra.py').write_text('x'); self.assertEqual(verify_installed_record(rec,r,expected)['status'],'FAIL')
    def test_bootlock_order_invariant(self):
        a=LockedProvider('a','x.a','a'*64); b=LockedProvider('b','x.b','b'*64)
        x=PluginHost(BootLock('t','c',(a,b),(),False,'g')).generation_digest
        y=PluginHost(BootLock('t','c',(b,a),(),False,'g')).generation_digest
        self.assertEqual(x,y)

if __name__=='__main__': unittest.main(verbosity=2)
