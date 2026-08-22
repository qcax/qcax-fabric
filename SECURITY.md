# Security Policy

## Supported versions
QCAX Fabric is pre-1.0. Security fixes target the newest tagged release unless a maintainer explicitly states otherwise.

## Reporting
Use GitHub's private vulnerability reporting / security-advisory flow for this repository. Do not publish exploit details before a fix and disclosure decision.

## Security boundaries
- Capability plugins never grant external mutation authority.
- Default core executes no external network calls.
- Sandboxes/providers are optional adapters and require integration testing.
- Artifact attestations are provenance evidence, not proof that code is secure.
- Secrets must never be committed; repository secret scanning and push protection should remain enabled where available.
