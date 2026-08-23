# Release skill

Use only for QCAX Fabric release engineering.

Required sequence:
1. Rebase ACTIVE_CUT against live provider/source state.
2. Read `release/policy/release-contract.json`.
3. If release identity is HOLD, stop before publication.
4. Run full assurance and failed-first release mutations.
5. Build exact candidate once; record source/run/artifact identities.
6. Publish GitHub immutable release through the governed workflow only.
7. Require release replay PASS.
8. Publish PyPI only through the registered Trusted Publisher workflow/environment.
9. Verify every public file digest and provenance.
10. Apply claim ceiling.
