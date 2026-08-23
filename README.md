# QCAX Fabric

QCAX Fabric is a pre-1.0, plugin-oriented agent/workflow harness reference architecture built around a small trusted host, explicit authority boundaries, exact artifact identity, deterministic release evidence, and fail-closed external-mutation gates.

## Current implementation

The clean-slate alpha candidate contains 11 Python distributions: contracts, SDK, host, and 8 plugin packages. Authority-sensitive providers use the same plugin contract but are bound through BootLock/SYSTEM_PINNED controls.

This repository state is a **release candidate source tree**, not evidence that a GitHub Release or PyPI publication has occurred. Production readiness, independent security review, formal verification, external-adapter conformance, and higher SLSA levels remain separate gates.

## Verify the repository

```bash
python tools/validate_repo.py
python -m unittest discover -s tests/semantics -p "test_*.py"
python conformance/run_mutations.py
```

Release-candidate and installed-wheel checks are exercised by the PR conformance workflow.

## Start here

- `docs/architecture/README.md` — architecture boundary
- `release/policy/release-contract.json` — release contract
- `docs/release/OPERATOR_RUNBOOK.md` — release operations
- `AGENTS.md` — agent-facing repository instructions
- `SECURITY.md` — security reporting and boundaries
- `CONTRIBUTING.md` — contribution requirements

## License

Apache-2.0. See `LICENSE` and the package-level notices.
