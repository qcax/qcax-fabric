# Workflows ready for R5

These files are intentionally **not** under `.github/workflows/`. Before enablement, re-resolve every `uses:` dependency to a current full commit SHA, compare to `ACTION_PIN_LEDGER.json`, confirm runner support, then copy only the workflows whose settings/environment prerequisites exist. `pypi-publish.yml` is hard-disabled until exact PyPI Trusted Publisher and protected environment evidence exists.
