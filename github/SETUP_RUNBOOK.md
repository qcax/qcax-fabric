# GitHub setup runbook — execute only after explicit mutation authorisation

## A. Repository creation
1. Create public repository `qcax-fabric` under `qcax` and initialize `main` with one seed README commit. This single seed commit is required because the available connected GitHub mutation surface can create branches/trees/commits only when a parent/default-branch commit already exists; it cannot create the repository or a parentless root commit. Do not add a license or `.gitignore` during this seed step.
2. Read the seed `main` prestate, create a bootstrap branch from that exact commit, replace the branch tree with the reviewed staging tree, and record the resulting commit/tree SHA and complete file manifest.
3. Default branch `main`; enable squash merge, auto-delete merged branches, Discussions optional.

## B. Security before contribution
4. Enable private vulnerability reporting, dependency graph/Dependabot, secret scanning and push protection where available.
5. Configure Actions policy: explicit minimum permissions, only approved actions/reusable workflows.
6. Resolve every workflow action to a current full commit SHA before enabling `.github/workflows`; do not ship tag-only action refs.
7. Configure CODEOWNERS after actual GitHub owner/team identity is known; never invent a team in the staged file.

## C. Rulesets
8. Create main ruleset in Evaluate mode, then Active after one successful dry-run PR.
9. Require PR, resolved conversations, protected status checks, and no force-push/delete. In solo-maintainer bootstrap, use 0 required approvals and advisory CODEOWNERS; activate independent/code-owner approval only after a second eligible reviewer exists.
10. Add release-tag immutability rules and enable immutable releases if supported.

## D. CI canary
11. Open bootstrap PR rather than direct-pushing the first protected change.
12. Run cross-platform Python matrix, installed-wheel isolation, import-boundary lint, conformance vectors, semantic mutations and dependency review.
13. Record job/run IDs and exact commit SHA; failures remain separate evidence, not silently patched in release notes.

## E. Release
14. Build wheels/sdists in CI from the exact release commit; produce schema/conformance bundle and SBOM.
15. Use GitHub artifact attestations; verify them before release. Do not equate attestation with security correctness.
16. Publish Python distributions through PyPI Trusted Publishing/OIDC in a dedicated protected environment; no long-lived API token.
17. Create `v0.1.0-alpha.1` only after all alpha exit gates pass; freeze release assets/tag and emit detached QCAX provenance receipt.
