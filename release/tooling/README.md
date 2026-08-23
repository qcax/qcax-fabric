# Release tooling implementation contract

These modules are deliberately not implemented by the architecture seed. W5 must implement them with unit/mutation tests before workflows are enabled:
- `activate_contract.py`
- `build_candidate.py`
- `verify_candidate.py`
- `prepare_sbom_root.py`
- `finalize_payload.py`
- `verify_github_attestations.py`
- `record_preflight_receipt.py`
- `reconcile_preflight.py`
- `publish_github.py`
- `verify_github_release.py`
- `assert_release_event.py`
- `compare_replay.py`
- `record_replay_receipt.py`
- `pypi_precheck.py`
- `pypi_postverify.py`

Candidate member identity and Actions artifact-container identity are separate layers; `record_preflight_receipt.py` writes outside the candidate after upload so there is no self-referential digest. Provider operations must be split into pure classification and explicit mutation calls. Every mutation error/timeout is followed by provider re-read before any retry.
