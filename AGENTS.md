# AGENTS.md — QCAX Fabric clean-slate contributor map

Read in this order:
1. `spec/` — language-neutral protocol and schemas.
2. `docs/architecture/README.md` — authority/trust boundaries.
3. `release/policy/release-contract.json` — release contract.
4. `docs/release/OPERATOR_RUNBOOK.md` — irreversible publication process.
5. `conformance/README.md` — executable compatibility and mutation requirements.

Hard boundaries:
- `history/` and `*/generated/` are evidence/output only and MUST NOT become runtime or release-policy inputs.
- `.github/workflows/` is the only canonical workflow tree.
- No release identity is active while `release-contract.json` is HOLD.
- Third-party Actions use full commit SHAs only.
- Release builds use no shared cache.
- Never manually create the release tag or publish from the Releases page when the governed release workflow is active.
- Any material defect receives a failed-first regression/mutation before promotion.
