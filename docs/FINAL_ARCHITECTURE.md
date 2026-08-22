# QCAX Fabric final GitHub architecture — R4.4

## Architectural law
**Everything above the tiny generic host trusted-computing base is plugin-shaped.** The host contains only descriptor/schema validation, artifact/envelope admission, capability/dependency reconciliation, lifecycle/effect transactionality, typed event dispatch, exact identity bookkeeping, and BootLock enforcement. It contains no Prompt Hardener, Memory, WorkGraph, Registry, model, Drive, GitHub, research or application-domain special case.

Five authority-sensitive providers remain `SYSTEM_PINNED`: TruthPolicy, CanonicalIdentity, Provenance, SourceAdmission and Authorization. They use the same public plugin ABI but are exact-identity BootLock-bound for a boot generation. Upgrade is a new generation with SHADOW -> CANARY -> CUTOVER or ROLLBACK.

## Identity planes
- `PluginDescriptor`: static declared contract; no self-hash.
- transport artifact identity: exact release wheel/file SHA-256 and occurrence/provenance.
- `InstalledImageIdentity`: canonical digest of hashed wheel `RECORD` declarations after installed files verify; this is recomputable at runtime.
- `InstallationReceipt`: normative verifier output binding distribution/version, optional observed wheel SHA, InstalledImageIdentity and RECORD verification.
- `AdmissionTicket`: opaque verifier-issued capability binding the InstallationReceipt to a `PluginEnvelope`; the host rejects raw caller-constructed envelopes for executable admission.
- `PluginEnvelope`: descriptor + runtime artifact identity carried inside the AdmissionTicket.
- `BootLock`: exact pinned provider/trusted artifact identities, target, claim ceiling, mutation authorization and generation label.

Wheel SHA proves the bytes transported; InstalledImageIdentity proves the verified installed image selected for loading. They are intentionally distinct.

## Plugin lifecycle
`DISCOVERED -> VALIDATED -> WAITING_DEPENDENCIES -> MOUNTING -> ACTIVE -> QUIESCING -> UNMOUNTING -> UNLOADED`, with `HOLD/FAILED`. Add/mount is transactional; partial effects unwind. Provider conflicts wait rather than last-write-win, and reconcile after provider removal. Capability/event contracts use stable SemVer in v1alpha1. Handler order is explicit `(priority, plugin_id, registration_seq)`. Handler exceptions append deterministic ERROR receipts before propagation; `guard` denial appends DENY. Mandatory `guard` events fail closed when there is no active guard or any authorized handler denies. `DURABLE` is reserved but rejected by alpha1 until a durable event-store provider exists.

## Trust and execution modes
`TRUSTED_IN_PROCESS` is the only alpha execution mode. Permissions are declarations/policy inputs, not OS isolation. `THIRD_PARTY` and `ADAPTER` code needs exact InstalledImage BootLock trust. Metadata is verified and an AdmissionTicket is preflighted before `EntryPoint.load()` imports plugin code. `SANDBOXED_PROCESS` and `REMOTE` fail closed until independently implemented and attacked.

## Repository architecture
The public repository is a Python monorepo initially, with independently buildable `contracts`, `sdk`, `host`, and first-party plugin distributions. The normative interchange surface is language-neutral JSON/JSONL, JSON Schema, SHA-256 and SemVer. Python distribution versions use PEP 440. Plugins may depend on contracts+SDK, never host or sibling plugin implementations. The monorepo is a development convenience, not a trust boundary.

## Public base milestone
`v0.1.0-alpha.1` is a **working public plugin-development base** when clean GitHub checkout CI, independent-wheel installation, exact installed-image BootLock, semantic mutations, import-boundary checks, dependency review, active solo-safe ruleset, immutable complete release assets, release verification and a clean-release out-of-tree plugin canary all pass. PyPI, real external adapters, sandboxed untrusted plugins and production readiness are deliberately later gates.
