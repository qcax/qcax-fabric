# PyPI Trusted Publisher Setup — QCAX Fabric

Register the same top-level workflow `.github/workflows/pypi-publish.yml` and environment `pypi` for each intended PyPI project. Current PyPI Trusted Publishing supports one publisher identity mapped to many projects.

Projects (11):
- `qcax-fabric-contracts`
- `qcax-fabric-sdk`
- `qcax-fabric-host`
- `qcax-fabric-plugin-authorization`
- `qcax-fabric-plugin-canonical-identity`
- `qcax-fabric-plugin-memory`
- `qcax-fabric-plugin-prompt-hardener`
- `qcax-fabric-plugin-provenance`
- `qcax-fabric-plugin-source-admission`
- `qcax-fabric-plugin-truth-policy`
- `qcax-fabric-plugin-hello-example`

Security configuration:
1. Repository must be the exact `qcax/qcax-fabric`.
2. Workflow must be the top-level `pypi-publish.yml`. Do not register a reusable workflow; current PyPI documentation states reusable workflows cannot currently serve as the Trusted Publisher workflow.
3. Environment must be `pypi`; require a trusted reviewer and prevent self-review where GitHub plan/provider settings permit.
4. The OIDC publishing job gets `id-token: write` only plus the minimum `actions: read` required to retrieve the prechecked artifact.
5. No long-lived PyPI API token is stored.
6. Register pending publishers carefully: a pending publisher does not reserve a project name until first publication.
7. Before first production upload, verify ownership/availability for all project names and record the resulting mappings in the release evidence.
8. Postpublication verification must use the PyPI Integrity API / `pypi-attestations verify pypi` and exact candidate hashes.

Multi-project transaction note:
Trusted Publisher identity may span these projects, but PyPI uploads files one at a time. The QCAX workflow therefore prechecks all names/files, constructs an exact missing-only subset, does not depend on upload order, then reconciles partial exact publication rather than assuming rollback.
