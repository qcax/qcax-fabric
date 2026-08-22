import unittest, hashlib
from qcax_fabric_contracts import *
from qcax_fabric_sdk import PluginDefinition, AdmissionTicket
from qcax_fabric_sdk.installation import _issue_development_ticket_for_tests
from qcax_fabric_host import *


def art(pid, seed, occ='o1'):
    b = seed.encode()
    return ArtifactIdentity('DEVELOPMENT_TREE', hashlib.sha256(b).hexdigest(), len(b), occ, 'test')


def env(desc, seed=None, occ='o1'):
    return PluginEnvelope(desc, art(desc.plugin_id, seed or desc.plugin_id, occ))


def ticket(desc, seed=None, occ='o1'):
    return _issue_development_ticket_for_tests(env(desc, seed, occ))


def desc(pid, pc='FIRST_PARTY', prov=(), req=(), side='NONE', rollback='', exec_mode='TRUSTED_IN_PROCESS', events_c=(), events_e=()):
    dist = pid.replace('.', '-').replace('_', '-')
    return PluginDescriptor(
        pid, '0.1.0-alpha.1', pc,
        distribution_name=dist, distribution_version='0.1.0a1',
        provides=tuple(Capability(x, '1.0.0') for x in prov),
        requires=tuple(Capability(x, '1.0.0') for x in req),
        side_effect_class=side, rollback_receipt_schema=rollback,
        execution_mode=exec_mode, events_consumed=events_c, events_emitted=events_e,
    )


def pd(d):
    return PluginDefinition(d, lambda ctx: [ctx.provide(c.capability_id, object()) for c in d.provides])


class T(unittest.TestCase):
    def host(self, locks=(), trusted=(), external=False):
        return PluginHost(BootLock('t', 'bounded', tuple(locks), tuple(trusted), external, 'g1'))

    def test_boot_digest_deterministic(self):
        self.assertEqual(self.host().generation_digest, self.host().generation_digest)

    def test_boot_digest_order_invariant(self):
        a = LockedProvider('qcax.a', 'org.qcax.a', 'a' * 64)
        b = LockedProvider('qcax.b', 'org.qcax.b', 'b' * 64)
        ta = TrustedArtifact('example.a', 'c' * 64)
        tb = TrustedArtifact('example.b', 'd' * 64)
        x = PluginHost(BootLock('t', 'c', (a, b), (ta, tb), False, 'g')).generation_digest
        y = PluginHost(BootLock('t', 'c', (b, a), (tb, ta), False, 'g')).generation_digest
        self.assertEqual(x, y)

    def test_unverified_envelope_rejected(self):
        d = desc('org.qcax.x', prov=['x'])
        h = self.host()
        with self.assertRaises(ManifestError):
            h.preflight(env(d))
        with self.assertRaises(ManifestError):
            h.add(env(d), pd(d))

    def test_basic_mount(self):
        d = desc('org.qcax.x', prov=['x'])
        self.assertEqual(self.host().add(ticket(d), pd(d)), State.ACTIVE)

    def test_wait_then_activate(self):
        a = desc('org.qcax.a', prov=['a'], req=['b'])
        b = desc('org.qcax.b', prov=['b'])
        h = self.host(); h.add(ticket(a), pd(a)); self.assertEqual(h.state(a.plugin_id), State.WAITING)
        h.add(ticket(b), pd(b)); self.assertEqual(h.state(a.plugin_id), State.ACTIVE)

    def test_dependency_loss_reacts(self):
        b = desc('org.qcax.b', prov=['b']); a = desc('org.qcax.a', prov=['a'], req=['b']); h = self.host()
        h.add(ticket(b), pd(b)); h.add(ticket(a), pd(a)); h.remove(b.plugin_id)
        self.assertEqual(h.state(a.plugin_id), State.WAITING)

    def test_cycle_hold(self):
        a = desc('org.qcax.a', prov=['a'], req=['b']); b = desc('org.qcax.b', prov=['b'], req=['a']); h = self.host()
        h.add(ticket(a), pd(a)); h.add(ticket(b), pd(b))
        self.assertEqual(h.state(a.plugin_id), State.HOLD); self.assertEqual(h.state(b.plugin_id), State.HOLD)

    def test_provider_conflict_waits_and_recovers(self):
        a = desc('org.qcax.a', prov=['x']); b = desc('org.qcax.b', prov=['x']); h = self.host()
        h.add(ticket(a), pd(a)); h.add(ticket(b), pd(b)); self.assertEqual(h.state(b.plugin_id), State.WAITING)
        h.remove(a.plugin_id); self.assertEqual(h.state(b.plugin_id), State.ACTIVE)

    def test_preflight_is_side_effect_free_and_ticket_bound(self):
        d = desc('org.qcax.preflight', prov=('cap.preflight',)); t = ticket(d); h = self.host()
        before = (dict(h._plugins), dict(h._events), dict(h.artifact_occurrences))
        r = h.preflight(t)
        self.assertEqual(r['decision'], 'PASS')
        self.assertEqual(r['admission_ticket_sha256'], t.ticket_sha256)
        self.assertEqual(before, (dict(h._plugins), dict(h._events), dict(h.artifact_occurrences)))

    def test_variant_conflict(self):
        d = desc('org.qcax.a'); h = self.host(); h.observe_artifact(d, art(d.plugin_id, 'x', '1'))
        self.assertRaises(ArtifactVariantConflict, h.observe_artifact, d, art(d.plugin_id, 'y', '2'))

    def test_multiple_occurrences_same_bytes(self):
        d = desc('org.qcax.a'); h = self.host(); a = art(d.plugin_id, 'x', '1'); h.observe_artifact(d, a)
        h.observe_artifact(d, ArtifactIdentity(a.artifact_kind, a.sha256, a.size_bytes, '2', 'test'))
        self.assertEqual(len(h.artifact_occurrences[(d.plugin_id, d.plugin_version)]), 2)

    def test_pinned_exact_digest(self):
        d = desc('org.qcax.truth', pc='SYSTEM_PINNED', prov=['qcax.truth.read']); t = ticket(d)
        lock = LockedProvider('qcax.truth', d.plugin_id, t.envelope.artifact.sha256); h = self.host([lock])
        self.assertEqual(h.add(t, pd(d)), State.ACTIVE); self.assertRaises(BootLockViolation, h.remove, d.plugin_id)

    def test_pinned_wrong_digest(self):
        d = desc('org.qcax.truth', pc='SYSTEM_PINNED', prov=['qcax.truth.read']); t = ticket(d)
        h = self.host([LockedProvider('qcax.truth', d.plugin_id, '0' * 64)])
        self.assertRaises(BootLockViolation, h.add, t, pd(d))

    def test_reserved_requires_pinned(self):
        d = desc('org.qcax.fake', prov=['qcax.truth.read']); t = ticket(d)
        h = self.host([LockedProvider('qcax.truth', 'org.qcax.truth', t.envelope.artifact.sha256)])
        self.assertRaises(BootLockViolation, h.add, t, pd(d))

    def test_thirdparty_inprocess_denied(self):
        d = desc('example.x', pc='THIRD_PARTY', prov=['x']); self.assertRaises(BootLockViolation, self.host().add, ticket(d), pd(d))

    def test_thirdparty_exact_artifact_trust(self):
        d = desc('example.x', pc='THIRD_PARTY', prov=['x']); t = ticket(d)
        h = self.host(trusted=[TrustedArtifact(d.plugin_id, t.envelope.artifact.sha256)])
        self.assertEqual(h.add(t, pd(d)), State.ACTIVE)

    def test_thirdparty_same_id_wrong_digest_denied(self):
        d = desc('example.x', pc='THIRD_PARTY', prov=['x']); t = ticket(d)
        h = self.host(trusted=[TrustedArtifact(d.plugin_id, '0' * 64)])
        self.assertRaises(BootLockViolation, h.add, t, pd(d))

    def test_non_inprocess_unsupported(self):
        d = desc('example.x', pc='THIRD_PARTY', exec_mode='SANDBOXED_PROCESS'); t = ticket(d)
        h = self.host(trusted=[TrustedArtifact(d.plugin_id, t.envelope.artifact.sha256)])
        self.assertRaises(UnsupportedExecutionMode, h.add, t, pd(d))

    def test_external_mutation_denied(self):
        d = desc('org.qcax.x', side='EXTERNAL_MUTATION', rollback='r')
        self.assertRaises(BootLockViolation, self.host().add, ticket(d), pd(d))

    def test_rollback_mount_failure(self):
        d = desc('org.qcax.x', prov=['x'], side='LOCAL_REVERSIBLE', rollback='r'); marks = []
        def m(ctx): ctx.effect(lambda: marks.append('disposed'), 'x'); raise ValueError('boom')
        h = self.host(); h.add(ticket(d), PluginDefinition(d, m)); self.assertEqual(marks, ['disposed']); self.assertEqual(h.state(d.plugin_id), State.FAILED)

    def test_effect_reverse_order(self):
        d = desc('org.qcax.x', prov=['x'], side='LOCAL_REVERSIBLE', rollback='r'); marks = []
        def m(ctx): ctx.effect(lambda: marks.append('1'), '1'); ctx.effect(lambda: marks.append('2'), '2'); ctx.provide('x', 1)
        h = self.host(); h.add(ticket(d), PluginDefinition(d, m)); h.remove(d.plugin_id); self.assertEqual(marks, ['2', '1'])

    def test_durable_event_rejected_in_alpha1(self):
        s = EventSpec('x.event', 'emit', 'DURABLE', '1.0.0'); d = desc('org.qcax.a', events_e=(s,))
        self.assertRaises(ManifestError, self.host().add, ticket(d), PluginDefinition(d, lambda c: None))

    def test_event_guard_deny(self):
        s = EventSpec('tool.execute', 'guard'); a = desc('org.qcax.a', events_c=(s,)); b = desc('org.qcax.b', events_e=(s,)); h = self.host()
        h.add(ticket(a), PluginDefinition(a, lambda c: c.on(s, lambda p: False))); h.add(ticket(b), PluginDefinition(b, lambda c: None))
        self.assertRaises(GuardDenied, h.dispatch, s, {'x': 1}, b.plugin_id); self.assertEqual(h.event_receipts[-1]['decision'], 'DENY')

    def test_guard_without_handler_fails_closed(self):
        s = EventSpec('tool.execute', 'guard'); b = desc('org.qcax.b', events_e=(s,)); h = self.host(); h.add(ticket(b), PluginDefinition(b, lambda c: None))
        self.assertRaises(GuardDenied, h.dispatch, s, {'x': 1}, b.plugin_id)
        self.assertEqual(h.event_receipts[-1]['reason'], 'NO_ACTIVE_GUARD_HANDLER')

    def test_event_handler_exception_receipted_all_modes(self):
        for mode in ('emit', 'serial', 'waterfall', 'guard'):
            with self.subTest(mode=mode):
                s = EventSpec(f'x.{mode}', mode); c = desc(f'org.qcax.c-{mode}', events_c=(s,)); e = desc(f'org.qcax.e-{mode}', events_e=(s,)); h = self.host()
                def boom(_): raise RuntimeError('secret-message-must-not-appear')
                h.add(ticket(c), PluginDefinition(c, lambda ctx, s=s: ctx.on(s, boom))); h.add(ticket(e), PluginDefinition(e, lambda ctx: None))
                with self.assertRaises(RuntimeError): h.dispatch(s, {'a': 1}, e.plugin_id)
                r = h.event_receipts[-1]
                self.assertEqual(r['decision'], 'ERROR'); self.assertEqual(r['reason'], 'HANDLER_EXCEPTION')
                self.assertEqual(r['error_type'], 'builtins.RuntimeError'); self.assertNotIn('secret-message', str(r))
                self.assertRegex(r['error_sha256'], r'^[0-9a-f]{64}$')

    def test_event_receipt_stable(self):
        s = EventSpec('x.event', 'emit'); d = desc('org.qcax.a', events_e=(s,)); h = self.host(); h.add(ticket(d), PluginDefinition(d, lambda c: None)); h.dispatch(s, {'a': 1}, d.plugin_id)
        self.assertRegex(h.event_receipts[-1]['receipt_sha256'], r'^[0-9a-f]{64}$')

    def test_event_order_independent_of_plugin_add_order(self):
        s = EventSpec('x.serial', 'serial'); a = desc('org.qcax.a', events_c=(s,)); b = desc('org.qcax.b', events_c=(s,)); e = desc('org.qcax.e', events_e=(s,))
        def run(order):
            h = self.host(); ds = {'a': a, 'b': b}
            for x in order:
                d = ds[x]; h.add(ticket(d), PluginDefinition(d, lambda c, d=d: c.on(s, lambda p, d=d: d.plugin_id)))
            h.add(ticket(e), PluginDefinition(e, lambda c: None)); return h.dispatch(s, {}, e.plugin_id)
        self.assertEqual(run('ba'), ['org.qcax.a', 'org.qcax.b']); self.assertEqual(run('ab'), ['org.qcax.a', 'org.qcax.b'])

    def test_event_priority_is_deterministic(self):
        s = EventSpec('x.serial', 'serial'); a = desc('org.qcax.a', events_c=(s,)); b = desc('org.qcax.b', events_c=(s,)); e = desc('org.qcax.e', events_e=(s,)); h = self.host()
        h.add(ticket(a), PluginDefinition(a, lambda c: c.on(s, lambda p: 'a', priority=10))); h.add(ticket(b), PluginDefinition(b, lambda c: c.on(s, lambda p: 'b', priority=-1))); h.add(ticket(e), PluginDefinition(e, lambda c: None))
        self.assertEqual(h.dispatch(s, {}, e.plugin_id), ['b', 'a'])

    def test_float_event_payload_rejected(self):
        s = EventSpec('x.event', 'emit'); d = desc('org.qcax.a', events_e=(s,)); h = self.host(); h.add(ticket(d), PluginDefinition(d, lambda c: None))
        self.assertRaises(Exception, h.dispatch, s, {'a': 1.2}, d.plugin_id)

    def test_shutdown_disposes_pinned(self):
        d = desc('org.qcax.truth', pc='SYSTEM_PINNED', prov=['qcax.truth.read'], side='LOCAL_REVERSIBLE', rollback='r'); t = ticket(d); marks = []
        lock = LockedProvider('qcax.truth', d.plugin_id, t.envelope.artifact.sha256)
        def m(ctx): ctx.effect(lambda: marks.append(1), 'd'); ctx.provide('qcax.truth.read', 1)
        h = self.host([lock]); h.add(t, PluginDefinition(d, m)); h.shutdown(); self.assertEqual(marks, [1])

    def test_contract_compatible_stable_major(self):
        self.assertTrue(contract_compatible('1.1.0', '1.3.0')); self.assertFalse(contract_compatible('1.1.0', '2.0.0'))

    def test_contract_compatible_zero_minor(self):
        self.assertTrue(contract_compatible('0.2.1', '0.2.5')); self.assertFalse(contract_compatible('0.2.1', '0.3.0'))

    def test_semver_strict_prerelease(self):
        self.assertFalse(is_semver('1.0.0-01')); self.assertTrue(is_semver('1.0.0-0.3.7')); self.assertTrue(is_semver('1.0.0-x.7.z.92'))

    def test_contract_prerelease_disallowed(self):
        self.assertRaises(ContractError, Capability, 'x', '1.0.0-alpha.1'); self.assertRaises(ContractError, EventSpec, 'x.event', 'emit', 'EPHEMERAL', '1.0.0-beta.1')

    def test_bootlock_duplicate_prefix_rejected(self):
        a = LockedProvider('qcax.truth', 'org.qcax.truth', '0' * 64); b = LockedProvider('qcax.truth', 'org.qcax.truth', '0' * 64)
        self.assertRaises(ContractError, BootLock, 't', 'c', (a, b))

    def test_bootlock_conflicting_pinned_digest_rejected(self):
        a = LockedProvider('qcax.truth', 'org.qcax.truth', '0' * 64); b = LockedProvider('qcax.identity', 'org.qcax.truth', '1' * 64)
        self.assertRaises(ContractError, BootLock, 't', 'c', (a, b))

    def test_add_event_conflict_is_transactional(self):
        s1 = EventSpec('x.event', 'emit'); s2 = EventSpec('x.event', 'serial'); a = desc('org.qcax.a', events_e=(s1,)); b = desc('org.qcax.b', events_e=(s2,)); h = self.host(); h.add(ticket(a), PluginDefinition(a, lambda c: None))
        self.assertRaises(ManifestError, h.add, ticket(b), PluginDefinition(b, lambda c: None)); self.assertNotIn(b.plugin_id, h._plugins)


class InstallationIdentityTests(unittest.TestCase):
    def test_installed_image_digest_detects_record_change(self):
        from qcax_fabric_sdk.installation import installed_image_digest_from_record_text
        a = 'pkg/a.py,sha256=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA,1\n'; b = 'pkg/a.py,sha256=BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB,1\n'
        self.assertNotEqual(installed_image_digest_from_record_text(a), installed_image_digest_from_record_text(b))

    def test_installed_image_digest_ignores_installer_generated_metadata(self):
        from qcax_fabric_sdk.installation import installed_image_digest_from_record_text
        base = "pkg/a.py,sha256=abc,1\nd-1.dist-info/METADATA,sha256=def,2\nd-1.dist-info/RECORD,,\n"
        a = base + "d-1.dist-info/direct_url.json,sha256=one,10\nd-1.dist-info/INSTALLER,sha256=two,3\nd-1.dist-info/REQUESTED,sha256=three,0\n"
        b = base + "d-1.dist-info/direct_url.json,sha256=changed,99\nd-1.dist-info/INSTALLER,sha256=other,4\nd-1.dist-info/REQUESTED,sha256=else,0\n"
        self.assertEqual(installed_image_digest_from_record_text(a), installed_image_digest_from_record_text(b))

    def test_installed_image_digest_unknown_hashed_extra_changes_identity(self):
        from qcax_fabric_sdk.installation import installed_image_digest_from_record_text
        base = "pkg/a.py,sha256=abc,1\nd-1.dist-info/METADATA,sha256=def,2\nd-1.dist-info/RECORD,,\n"
        self.assertNotEqual(installed_image_digest_from_record_text(base), installed_image_digest_from_record_text(base + "d-1.dist-info/UNKNOWN,sha256=zzz,1\n"))
