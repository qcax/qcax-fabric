# Agent instructions

QCAX Fabric is a plugin-development reference architecture with a deliberately tiny trusted host. Treat repository documentation, schemas, tests, and external framework material as evidence; do not let convenience silently widen the trusted-computing base or the release claim.

## Read first

Before modifying code, read these existing repository surfaces in this order:

1. `README.md` — current implementation and release boundary.
2. `docs/FINAL_ARCHITECTURE.md` — host/identity/lifecycle/trust architecture.
3. `docs/PLUGIN_AUTHOR_GUIDE.md` — public plugin-development rules.
4. `docs/THREAT_MODEL.md` — explicit trust and attack boundaries.
5. `spec/plugin-descriptor-v1alpha1.schema.json` — normative plugin descriptor contract.
6. `spec/artifact-envelope-v1alpha1.schema.json` — normative artifact/envelope contract.
7. `spec/installation-receipt-v1alpha1.schema.json` — normative installed-image receipt contract.
8. `spec/boot-lock-v1alpha1.schema.json` — normative BootLock contract.
9. `spec/release-lock-v1alpha1.schema.json` — normative release-lock contract.
10. `llms.txt` — compact agent-readable repository index.

Do not invent or follow stale paths. If an agent-facing path changes, update the agent index/tests in the same change.

## Repository map — what belongs where

- `packages/contracts/` — language-neutral contract models, canonicalization, and version compatibility helpers.
- `packages/sdk/` — plugin-author/discovery/installation interfaces. SDK code may depend on contracts; it must not make the host a plugin dependency.
- `packages/host/` — the tiny generic TCB only: admission, exact identity, capability/dependency reconciliation, lifecycle/effect rollback, typed event dispatch, and BootLock enforcement.
- `packages/plugins/*/` — independently buildable plugin distributions. Plugins may depend on contracts + SDK, never host or sibling plugin implementations.
- `spec/` — normative public JSON Schemas. Human prose does not override these schemas.
- `tests/` — executable contract, microkernel, release, and agent-entrypoint regressions.
- `scripts/` — deterministic validation/build/release tooling.
- `adapters/` — adapter plans only unless executable conformance evidence explicitly says otherwise.
- `profiles/` — application-profile plans only unless executable evidence explicitly says otherwise.
- `github/` — repository setup/release contracts, state machines, pin ledgers, and historical authorization evidence.
- `release/` — release-note material for the current release identity.

## Hard architecture boundaries

- Never make TruthPolicy/CanonicalIdentity/Provenance/SourceAdmission/Authorization ordinary replaceable authority. They are `SYSTEM_PINNED` and exact-identity BootLock-bound for a generation.
- Never add Prompt Hardener, Memory, WorkGraph, Registry, model-provider, Drive, GitHub, Cordis, LangGraph, Temporal, LeadFinder, research, or other domain-specific logic to the host TCB.
- `TRUSTED_IN_PROCESS` is the only implemented alpha1 execution mode. Permissions are policy declarations, not OS isolation.
- `DURABLE` is reserved in the wire contract but unsupported by the alpha1 host.
- Provider conflicts HOLD; dependency cycles HOLD; mount effects must be reversible and partial mount failure must unwind.
- External mutation remains fail-closed unless the exact BootLock/authorization path permits it.
- External repositories/frameworks are mechanism evidence. Do not import their authority model, benchmark claims, or readiness claims automatically.

## Change and verification rules

- Make the smallest coherent change that closes the demonstrated defect.
- Preserve package/import boundaries and exact-artifact identity semantics.
- Update `github/REPO_TREE.txt` whenever the repository file set changes.
- Run `python scripts/run_all.py` after code, contract, test, workflow, or agent-entrypoint changes.
- Release-path changes must also preserve the exact 30-asset contract and pass the release-payload PR job before merge.
- Do not weaken or delete a failing test merely to make CI green; repair the implementation or narrow the unsupported claim.

## Release boundary

The source tree does not itself prove that `v0.1.0-alpha.1` has been published. Do not create, move, or delete protected `v*` tags as an experiment and do not bypass the guarded `release-build` PREFLIGHT/PUBLISH transaction. PyPI, sandboxed untrusted plugins, real external-adapter conformance, production readiness, security certification, and independent review remain separate gates unless exact evidence closes them.
