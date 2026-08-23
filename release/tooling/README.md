# Release tooling implementation contract

Current state after alpha1 identity activation:

Implemented provider-neutral / activation tooling:
- `activate_contract.py`
- `build_candidate.py`
- `verify_candidate.py`
- `prepare_sbom_root.py`
- `finalize_payload.py`
- `compare_replay.py`

W9 provider-facing tooling implemented by the W9 branch/PR must remain fail-closed and testable without live irreversible publication:
- `provider.py`
- `verify_github_attestations.py`
- `record_preflight_receipt.py`
- `reconcile_preflight.py`
- `publish_github.py`
- `verify_github_release.py`
- `assert_release_event.py`
- `record_replay_receipt.py`
- `pypi_precheck.py`
- `pypi_postverify.py`

Candidate member identity and Actions artifact-container identity are separate layers. `record_preflight_receipt.py` writes outside the candidate after upload so there is no self-referential digest.

Provider operations must split pure classification from explicit mutation calls. Any mutation error, timeout, or ambiguous result requires provider reread before any retry. GitHub draft publication may reconcile exact expected-name assets, but unexpected assets block. PyPI publication is non-atomic across eleven projects and therefore uses exact precheck + missing-only publication + explicit partial-state reconciliation.

Implementation passing tests does not establish provider configuration, publication readiness, production readiness, or independent security review. Release-preflight, GitHub publication and PyPI publication remain separately authorized operations.
