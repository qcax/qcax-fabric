# Security Policy

## Supported state

QCAX Fabric is pre-1.0. Do not infer a published release from version strings present in source. Security fixes target the current maintained source and, when applicable, the newest immutable tagged release.

## Reporting

Use GitHub private vulnerability reporting / security-advisory facilities for this repository. Do not publish exploit details before a fix and disclosure decision.

## Security boundaries

- Capability plugins do not grant external mutation authority by themselves.
- Authority-sensitive providers are fail-closed and must satisfy BootLock/SYSTEM_PINNED controls.
- Provider mutation outcomes require provider-state reread before retry or promotion.
- Artifact hashes and attestations are provenance/identity evidence, not proof that code is secure or semantically correct.
- Secrets must not be committed; repository secret scanning and push protection should remain enabled where available.
- Production readiness, independent security review, external-adapter conformance, and formal verification are not implied by passing repository CI.
