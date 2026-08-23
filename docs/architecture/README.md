# Architecture

The clean-slate repository separates:
- specifications/contracts;
- SDK and tiny trusted host;
- plugins/adapters/profiles;
- release policy/provider tooling;
- tests/conformance;
- generated evidence;
- historical evidence.

Runtime code must not import from `history/`, `release/generated/`, `conformance/generated/`, or GitHub workflow/configuration surfaces.
