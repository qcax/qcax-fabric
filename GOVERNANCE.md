# Governance

QCAX Fabric treats the tiny trusted host, BootLock/SYSTEM_PINNED authority binding, canonical identity/provenance rules, external-mutation authorization, release-state reconciliation, and claim ceilings as protected architecture boundaries.

Normal changes require review and deterministic tests. Material changes to those protected boundaries require an explicit proposal, threat/failure analysis, compatibility statement, migration/rollback plan, semantic and mutation coverage, and a protocol/schema version change when compatibility requires it.

Application profiles and adapters may compose the fabric but may not silently change the host TCB or inherit execution/assurance credit from another target.
