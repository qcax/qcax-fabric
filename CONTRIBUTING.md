# Contributing

1. Open an issue for behavior-changing proposals.
2. Preserve the non-pluggable TruthKernel and public protocol invariants.
3. Add or update tests and a predicted-effect record for material harness changes.
4. Do not modify held-out evaluators in the same change that proposes a candidate improvement.
5. Run `python scripts/run_all.py`.
6. Record source/version changes for externally borrowed mechanisms.
7. Pull requests must state rollback/reopen conditions and any public-schema compatibility impact.
