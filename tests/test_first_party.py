import unittest, hashlib
from qcax_fabric_contracts import *
from qcax_fabric_host import PluginHost, State, BootLockViolation
from qcax_fabric_sdk.installation import _issue_development_ticket_for_tests
from qcax_plugin_truth_policy import definition as truth
from qcax_plugin_canonical_identity import definition as identity
from qcax_plugin_provenance import definition as prov
from qcax_plugin_source_admission import definition as source
from qcax_plugin_authorization import definition as auth
from qcax_plugin_prompt_hardener import definition as prompt
from qcax_plugin_memory import definition as memory


def ticket(defn):
    b = (defn.descriptor.plugin_id + '|source').encode()
    e = PluginEnvelope(defn.descriptor, ArtifactIdentity('DEVELOPMENT_TREE', hashlib.sha256(b).hexdigest(), len(b), defn.descriptor.plugin_id, 'local-stage'))
    return _issue_development_ticket_for_tests(e)


class T(unittest.TestCase):
    def boot(self):
        ts = [ticket(x) for x in [truth, identity, prov, source, auth]]
        locks = []
        for t in ts:
            for cap in t.envelope.descriptor.provides:
                locks.append(LockedProvider(cap.capability_id, t.envelope.descriptor.plugin_id, t.envelope.artifact.sha256))
        h = PluginHost(BootLock('github-architecture', 'bounded', tuple(locks), (), False, 'alpha1-stage'))
        for d, t in zip([truth, identity, prov, source, auth], ts): h.add(t, d)
        return h

    def test_prompt_and_memory_plugins(self):
        h = self.boot(); h.add(ticket(prompt), prompt); h.add(ticket(memory), memory)
        c = h.service('qcax.prompt.compile')('build plugin'); self.assertEqual(c['target'], 'github-architecture')
        mem = h.service('qcax.memory'); mem['put']('k', 'v', {'eligible': True}); self.assertEqual(mem['get']('k'), 'v')

    def test_pinned_cannot_remove(self):
        h = self.boot(); self.assertRaises(BootLockViolation, h.remove, truth.descriptor.plugin_id)
