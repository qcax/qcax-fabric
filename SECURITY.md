# Security Policy

## Supported versions
The shadow pilot is pre-1.0. Security fixes target the newest tagged release unless a maintainer explicitly states otherwise.

## Reporting
Before repository publication, report privately to the repository owner through the private channel named in the future GitHub Security policy. Do not publish exploit details before a fix/release decision.

## Security boundaries
- Capability plugins never grant external mutation authority.
- Default core executes no external network calls.
- Sandboxes/providers are optional adapters and require integration testing.
- Artifact attestations are provenance evidence, not proof that code is secure.
- Secrets must never be committed; future GitHub setup should enable secret scanning/push protection when available.
