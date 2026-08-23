# Contributing

1. Open an issue for behaviour-changing proposals or public-contract changes.
2. Preserve the tiny host TCB, BootLock/SYSTEM_PINNED authority boundaries, exact identity rules, and fail-closed external-mutation gates.
3. Add or update semantic tests and mutation tests for material invariant changes.
4. Run `python tools/validate_repo.py` and `python -m unittest discover -s tests/semantics -p "test_*.py"` before submitting a pull request.
5. Release changes must also satisfy the applicable `release/policy/` contract and PR conformance checks.
6. Record compatibility, rollback/reopen conditions, external source/version changes, and any public-schema impact.
7. Do not represent internal self-review as independent review or source identity as semantic correctness.
