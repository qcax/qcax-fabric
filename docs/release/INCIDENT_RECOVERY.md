# Release Incident Recovery

## General
Freeze further publication. Preserve logs, provider responses, candidate artifacts, attestations, hashes, run IDs and timestamps. Do not mutate evidence to make the state resemble the intended state.

## Ambiguous GitHub mutation
Re-read release, tag and assets before retrying. If the exact intended state exists, continue verification. If absent and still safely draft/recoverable, one bounded action may be retried. Never clobber or modify an immutable release.

## Wrong GitHub tag or immutable asset
Classify as provider integrity incident. No automated repair. Preserve release attestation and all downloaded evidence.

## Partial exact PyPI publication
This is expected to be possible because files/projects publish independently and upload order is not a correctness guarantee. Re-read Simple and Integrity APIs. Accept already-published files only when exact digest and publisher provenance match. Continue only missing files.

## Wrong PyPI file/hash/provenance
Stop. Never overwrite or skip. Determine blast radius across all coordinated projects. If the release is broken/incompatible/security-sensitive, use PyPI whole-release yanking where appropriate. Deletion is not a transactional rollback and should not be treated as one.

## Compromised publisher/workflow
Disable/revoke Trusted Publisher mappings, protect the GitHub environment/workflow, rotate any remaining static credentials, audit repository/admin membership and workflow history, and perform a new clean release identity after remediation. Never reuse an immutable/public package identity merely to hide the incident.
