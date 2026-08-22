# CI plan

Workflows are templates until R5 resolves and pins each action to an exact full commit SHA.

- `ci.yml`: Linux Python 3.11–3.14; Windows/macOS representative versions; unit + static repository validator.
- `conformance.yml`: independent wheel builds, clean venv install, metadata-only plugin discovery, public ABI fixtures, import-boundary lint, semantic mutations, deterministic receipt vectors.
- `dependency-review.yml`: block newly introduced dependencies violating configured severity/licence policy.
- CodeQL: prefer GitHub default setup initially; move to advanced workflow only when custom build/query requirements justify it.
- `scorecard.yml`: OpenSSF Scorecard after repository is public.
- `release.yml`: exact tag/commit build, wheel+sdist+schema bundle+SBOM, attestations, immutable GitHub release, optional PyPI Trusted Publisher.

Never use `pull_request_target` to execute fork-controlled code. Release/environment workflows receive the narrowest token permissions possible.
