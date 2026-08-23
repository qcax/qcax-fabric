# QCAX Fabric Clean-Slate Release Operator Runbook

Status: alpha1 identity is ACTIVE and the W9 provider-facing tooling is merged. Publication remains held until current provider configuration gates, including all per-project PyPI OIDC environments and Trusted Publisher mappings, are directly verified. Do not infer publication readiness from ACTIVE identity or merged tooling alone.

## 0. Rebase the active cut
Read live `qcax/qcax-fabric` provider state and same-target admitted evidence. Record repository ID, main SHA/tree, open PRs, release/tag state, rulesets/environments, and action-pin ledger. If anything changed, invalidate only affected downstream evidence.

## 1. Activate release identity
Complete the semantic compatibility audit across protocol schemas, Python distributions, plugin IDs, entry-point group, descriptor schema, and public docs.
- If semantics remain the intended unpublished `0.1.0a1`, activation may retain `v0.1.0-alpha.1`.
- If material public contract/package identity changed, assign a new prerelease version/tag.
Write the selected identity to the release contract by reviewed PR. Do not hand-create the tag.

Current alpha1 checkpoint: `ACTIVE / v0.1.0-alpha.1 / 0.1.0a1`. Revalidate this state from the current release contract before any later release transaction.

## 2. Freeze source
Require protected `main`, no open release-affecting PRs, all required checks passing, and exact 40-hex main commit. Freeze the Git tree and source timestamp. Record package-set digest.

Before promotion, directly verify the effective main ruleset/bypass posture, required Actions SHA-pinning policy, immutable-release setting, `github-release` environment protections, all eleven exact PyPI publishing environments, and all eleven exact PyPI Trusted Publisher mappings. Historical inaccessible/blocker receipts are not current provider proof.

## 3. Run release-preflight
Dispatch only `.github/workflows/release-preflight.yml` from `main`, with exact commit and activated tag.
The workflow must:
- build two clean wheel sets without release cache;
- build/compare sdists semantically;
- derive wheels from sdists and compare installed identity;
- run all tests, mutations, installed-image and out-of-tree canaries;
- construct the local exact package index/wheelhouse;
- generate SPDX release SBOM from extracted wheel roots;
- finalize the derived artifact set `2*N + controls`;
- attest all assets and wheel SBOM;
- cryptographically verify build and wheel-SBOM attestations;
- upload one candidate artifact;
- after upload, write a separate preflight receipt binding the candidate artifact ID/digest to the payload-manifest digest and source/run identity, then upload that receipt separately.

Promotion requires a complete-success run and inspection of the candidate receipt. A preflight run is evidence only; it does not authorize publication.

## 4. Publish immutable GitHub release
Dispatch `release-publish.yml` from `main`. Required inputs:
- exact frozen source commit;
- activated release tag;
- exact successful preflight run ID;
- candidate artifact ID;
- candidate artifact SHA-256 digest;
- explicit confirmation string.

The `github-release` protected environment is the human irreversibility gate. The job re-reads main, preflight metadata, artifact metadata/digest, candidate payload and attestations before any provider mutation.

Provider algorithm:
1. classify current main/tag/release/draft/assets;
2. block wrong tag/release/asset identities;
3. create/resume only the exact draft;
4. reconcile only exact-name missing/mismatched draft assets;
5. block unexpected draft assets;
6. re-read provider state after every ambiguous write result;
7. publish once only when the draft asset set is exact;
8. require immutable provider readback;
9. verify release/tag/assets cryptographically with GitHub release attestations.

Never use blind `--clobber` recovery for a mismatched draft asset: deletion and upload are separate provider mutations and each must be followed by readback.

## 5. Require release replay
`release-replay.yml` triggers on `release: published`, including prereleases published from drafts. It checks out the published tag, runs full assurance, rebuilds independently without release cache, regenerates the SBOM, downloads the exact immutable release assets and performs class-aware deterministic/semantic comparison.

The workflow writes a tag/run/source-bound replay receipt and uploads it separately. No PyPI publication is allowed until replay and its receipt are PASS.

## 6. PyPI precheck
Confirm all intended project names and every exact Trusted Publisher mapping for `.github/workflows/pypi-publish.yml`.

The canonical project/environment map is `release/policy/pypi-publication-policy.json`. `qcax-fabric-contracts` retains environment `pypi`; every other project uses its own exact `pypi-*` environment. A current direct provider-configuration receipt is mandatory; the checked-in `W9_PROVIDER_CONFIGURATION_TEMPLATE.json` is deliberately HOLD and is not evidence.

For each of the 11 projects and its wheel/sdist:
- if the target filename is absent, stage it only under that project's missing directory;
- if present, accept only if SHA-256, PyPI Integrity API publisher kind/repository/workflow/environment, and cryptographically verified Trusted Publisher provenance are exact;
- any mismatch or unexpected target-version file is INCIDENT, not skip-existing.

The precheck emits a missing-only matrix of exact project/environment pairs. Verify internal dependency constraints use the coordinated release version. Verify GitHub immutable release and replay run/receipt again.

## 7. PyPI publication
PyPI is not a cross-project atomic transaction. Publish only the exact missing-only per-project distribution subsets. Do **not** rely on matrix scheduling, the official action/provider upload order, or dependency publication order as a correctness guarantee. A stopped run can expose an explicit partial state. Correctness comes from exact precheck, partial-state reconciliation, and complete postverification.

Each OIDC matrix job:
- is bound to exactly one project-specific GitHub environment;
- gets `id-token: write` only at job scope plus minimum `actions: read`;
- downloads the prechecked artifact;
- invokes the pinned official PyPA publisher on only that project's directory.

The OIDC publish job must not check out source, build packages, run arbitrary repository code, or receive broad `contents:write`.

On interruption:
- re-read PyPI project/release/Integrity state;
- classify exact already-published files;
- continue only exact missing files after renewed authorization.

On any wrong file/hash/publisher identity: stop and enter incident handling.

## 8. PyPI postverification
After every publication attempt for which precheck succeeded, including a partially failed or cancelled matrix, reconcile the actual PyPI state.

Download all present distributions from PyPI and verify:
- filename/project/version identity;
- exact SHA-256 against immutable candidate;
- exact PyPI Integrity API publisher kind/repository/workflow/environment;
- PEP 740 provenance/Trusted Publisher identity cryptographically;
- absence of unexpected target-version files.

If any file remains missing, record `PARTIAL_PYPI_PUBLICATION` (or `PYPI_ALL_MISSING` when appropriate); if any mismatch or unexpected file exists, record `INCIDENT`. Only a complete exact state may continue to:
- clean live-index installation of all eleven coordinated distributions;
- exact-wheel installed-image canary;
- out-of-tree plugin canary against PyPI-downloaded wheels.

Only then may a separately implemented completion receipt claim `RELEASE_COMPLETE`.

## 9. Claim ceiling
A successful release does not automatically establish production readiness, SLSA L3, independent security review, formal proof, external-adapter conformance, or untrusted-plugin sandbox security.
