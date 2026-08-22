# Changelog

## 0.1.0-alpha.1
- Separate plugin descriptor from observed artifact identity to avoid self-referential digests.
- Tiny generic host TCB; all QCAX systems above it plugin-shaped.
- SYSTEM_PINNED providers bound by BootLock exact artifact identities.
- Trusted-in-process alpha execution model; untrusted process isolation remains a later gate.
- Language-neutral JSON Schema contracts and RFC 8785-compatible restricted canonical receipt profile.
- Independent Python distributions for contracts, SDK, host, pinned providers, Prompt Hardener and Memory.
- Verifier-issued InstallationReceipt/AdmissionTicket path and strict schema/SemVer/BootLock/event-receipt gates.
- GitHub protected bootstrap CI exercised across configured Linux, macOS and Windows jobs.
- Release candidate adds 11 wheels + 11 sdists, exact release-lock, SPDX 2.3 SBOM, schema/conformance bundles, provenance/manifest/checksums, prepublication attestations, immutable one-time publish guards, post-release verification, and tag replay.
- PyPI, external adapter conformance, independent security review and production readiness remain separately gated.
