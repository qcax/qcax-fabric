# QCAX Fabric v0.1.0-alpha.1

First public alpha of the QCAX Fabric plugin-oriented agent/workflow harness reference architecture.

## Included
- tiny generic host trusted-computing base
- language-neutral contracts and Python SDK
- 8 implemented plugin packages
- verifier-issued InstallationReceipt / AdmissionTicket path
- exact BootLock and installed-image admission model
- deterministic standard wheel builds
- standard backend sdists with normalized-content and installed-image parity checks
- exact release lock generated from the published wheels
- SPDX 2.3 SBOM covering all 11 released distributions
- Linux, macOS and Windows CI
- conformance, mutation, dependency-review and CodeQL gates

## Alpha boundaries
- DURABLE events remain reserved but unsupported
- untrusted process isolation remains a later gate
- PyPI publication remains held
- external-adapter conformance is not claimed
- independent security review is not claimed
- production readiness is not claimed
