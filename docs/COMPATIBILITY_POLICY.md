# Compatibility and versioning

- Repository/release SemVer: `v0.1.0-alpha.1` pre-1.0; breaking changes are permitted but require release notes and migration notes.
- Plugin ABI string: `qcax.fabric/v1alpha1`; freeze only after external plugin evidence.
- Capability/event contracts: SemVer 2.0.0. Stable major versions are backward-compatible within major; 0.x requires matching major+minor in the alpha host.
- Python distributions: PEP 440 (`0.1.0a1`), mapped explicitly to public SemVer.
- Schemas: immutable URN `$id` per published version. Never repoint an existing schema ID to changed semantics.
- Breaking TCB/BootLock/schema changes require ADR + RFC + protected conformance/mutation delta + migration guide.
