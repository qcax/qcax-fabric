# QCAX Fabric

QCAX Fabric is a plugin-oriented agent/workflow harness reference architecture.

**Architecture law:** everything above the tiny host trusted-computing base (TCB) is plugin-shaped. The host contains only generic artifact/manifest admission, capability/dependency reconciliation, lifecycle/effect rollback, typed event dispatch, and BootLock enforcement. Authority-sensitive providers use the same public plugin contract but are `SYSTEM_PINNED` to an exact boot generation.

The repository targets `v0.1.0-alpha.1`. Public bootstrap evidence has been collected through GitHub pull-request CI; release assets, immutable prerelease publication, PyPI publication, external adapter conformance, independent security review, and production readiness remain separate gates unless explicitly evidenced.

See `docs/FINAL_ARCHITECTURE.md`, `docs/PLUGIN_AUTHOR_GUIDE.md`, and `github/SETUP_RUNBOOK.md`.

## Alpha1 implementation boundary

The current tree contains **8 implemented plugin packages**. The wider QCAX inventory contains **54 structurally pluginizable roles** (44 system roles, 6 adapter roles, and 4 application profiles), but structural pluginizability is not implementation completion. Prompt Hardener and Memory are first-party migration bases, not complete implementations of every historical subsystem.

`DURABLE` remains a reserved wire-contract value for forward compatibility, but **DURABLE events are reserved but unsupported in alpha1** until an event-store provider seam and its conformance vectors are implemented. The alpha1 host accepts only EPHEMERAL events.

## GitHub bootstrap boundary

The bootstrap tree enables six full-SHA-pinned workflows (`ci`, `conformance`, `dependency-review`, `codeql`, `scorecard`, and tag-gated `release-build`). The current bootstrap PR has produced passing live CI across the configured Linux, macOS, and Windows jobs, conformance, CodeQL, and dependency review. PyPI publishing remains hard-disabled until its separate namespace, Trusted Publisher, and protected-environment prestate gates are satisfied.
