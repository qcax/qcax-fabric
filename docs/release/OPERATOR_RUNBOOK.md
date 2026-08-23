# QCAX Fabric Clean-Slate Release Operator Runbook

Status: R10 architecture/implementation seed. Do not execute publication while `release_identity.status` is HOLD.

## 0. Rebase the active cut
Read live `qcax/qcax-fabric` provider state and Drive same-target evidence. Record repository ID, main SHA/tree, open PRs, release/tag state, rulesets/environments, and action-pin ledger. If anything changed, invalidate only affected downstream evidence.

## 1. Activate release identity
Complete the semantic compatibility audit across protocol schemas, Python distributions, plugin IDs, entry-point group, descriptor schema, and public docs.
- If semantics remain the intended unpublished `0.1.0a1`, activation may retain `v0.1.0-alpha.1`.
- If material public contract/package identity changed, assign a new prerelease version/tag.
Write the selected identity to the release contract by reviewed PR. Do not hand-create the tag.

## 2. Freeze source
Require protected `main`, no open release-affecting PRs, all required checks passing, and exact 40-hex main commit. Freeze the Git tree and source timestamp. Record package-set digest.

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
- upload one candidate artifact;
- after upload, write a separate preflight receipt binding the candidate artifact ID/digest to the payload-manifest digest and source/run identity, then upload that receipt separately.

Promotion requires a complete-success run and independent inspection of the candidate receipt.

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
8. verify immutable release, tag binding, exact downloaded assets and GitHub release attestation.

## 5. Require release replay
`release-replay.yml` triggers on `release: published`, including prereleases published from drafts. It checks out the published tag, runs full assurance, rebuilds independently without release cache, regenerates the SBOM and performs class-aware deterministic/semantic comparison against the immutable release.
No PyPI publication is allowed until replay is PASS.

## 6. PyPI precheck
Confirm all intended project names and Trusted Publisher mappings for `.github/workflows/pypi-publish.yml` + environment `pypi`.
For each of the 11 projects and its wheel/sdist:
- if target filename is absent, stage it for upload;
- if present, accept only if SHA-256 and Trusted Publisher provenance are exact;
- any mismatch is INCIDENT, not skip-existing.
Verify internal dependency constraints use the coordinated release version.
Verify GitHub immutable release and replay run again.

## 7. PyPI publication
PyPI is not a cross-project atomic transaction. Publish the exact missing-only distribution subset. Do **not** rely on the official action/provider upload order as a correctness or dependency-availability guarantee; a stopped run can expose an explicit partial state. Correctness comes from exact precheck, partial-state reconciliation, and complete postverification.

The OIDC `publish` job must only download the prechecked artifact and invoke the pinned official PyPA publisher. No source checkout, build, code execution, or broad `contents:write` permission in the OIDC job.

On interruption:
- re-read PyPI Simple/Integrity state;
- classify exact already-published files;
- continue only exact missing files.
On any wrong file/hash/publisher identity: stop and enter incident handling.

## 8. PyPI postverification
Download all published distributions from PyPI. Verify:
- filename/project/version identity;
- exact SHA-256 against immutable candidate;
- PEP 740 provenance/Trusted Publisher identity;
- clean index-only installation of contracts, SDK, all plugins and host;
- installed-image and out-of-tree plugin canaries.

Only then write `RELEASE_COMPLETE`.

## 9. Claim ceiling
A successful release does not automatically establish production readiness, SLSA L3, independent security review, formal proof, external-adapter conformance, or untrusted-plugin sandbox security.
