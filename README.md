# QCAX Fabric

QCAX Fabric is a plugin-oriented agent/workflow harness reference architecture.

**Architecture law:** everything above the tiny host trusted-computing base (TCB) is plugin-shaped. The host contains only generic artifact/manifest admission, capability/dependency reconciliation, lifecycle/effect rollback, typed event dispatch, and BootLock enforcement. Authority-sensitive providers use the same public plugin contract but are `SYSTEM_PINNED` to an exact boot generation.

The repository targets `v0.1.0-alpha.1`. Public bootstrap and protected-merge evidence have been collected through GitHub CI. Release status is provider-evidence-bound: this source tree defines the guarded alpha transaction but does not, by itself, assert that immutable publication occurred. Alpha exit requires the exact final main SHA, complete release payload, attestations, immutable publication, release verification, tag replay, and clean downloaded-release canaries to pass.

See `docs/FINAL_ARCHITECTURE.md`, `docs/PLUGIN_AUTHOR_GUIDE.md`, and `github/SETUP_RUNBOOK.md`.

## Alpha1 implementation boundary

The current tree contains **8 implemented plugin packages**. The wider QCAX inventory contains **54 structurally pluginizable roles** (44 system roles, 6 adapter roles, and 4 application profiles), but structural pluginizability is not implementation completion. Prompt Hardener and Memory are first-party migration bases, not complete implementations of every historical subsystem.

`DURABLE` remains a reserved wire-contract value for forward compatibility, but **DURABLE events are reserved but unsupported in alpha1** until an event-store provider seam and its conformance vectors are implemented. The alpha1 host accepts only EPHEMERAL events.

## GitHub release boundary

Six full-SHA-pinned workflows are enabled (`ci`, `conformance`, `dependency-review`, `codeql`, `scorecard`, and `release-build`). Release publication is fail-closed: an exact final main commit must pass the complete 30-asset preflight, exact-wheel canaries, sdist InstalledImage parity, SPDX coverage, and provenance/SBOM attestation verification before a separate guarded publish dispatch can create/resume the draft and publish the immutable prerelease once. The tag-triggered replay is verification-only with respect to the published tag/release/assets.

PyPI publishing remains hard-disabled until its separate namespace, Trusted Publisher, and protected-environment prestate gates are satisfied.
