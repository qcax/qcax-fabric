# PyPI Trusted Publisher Setup — QCAX Fabric

QCAX Fabric uses one top-level trusted workflow, `.github/workflows/pypi-publish.yml`, and one distinct GitHub OIDC environment per PyPI project.

Why: PyPI pending GitHub publishers are uniquely identified by repository owner + repository + workflow filename + environment. The project name is not part of that pending-publisher uniqueness tuple. Distinct environments therefore allow all eleven not-yet-created projects to have independent pending publishers while keeping one audited publishing workflow.

## Exact pending/normal publisher bindings

| PyPI project | GitHub environment |
| --- | --- |
| `qcax-fabric-contracts` | `pypi` |
| `qcax-fabric-sdk` | `pypi-sdk` |
| `qcax-fabric-host` | `pypi-host` |
| `qcax-fabric-plugin-authorization` | `pypi-plugin-authorization` |
| `qcax-fabric-plugin-canonical-identity` | `pypi-plugin-canonical-identity` |
| `qcax-fabric-plugin-memory` | `pypi-plugin-memory` |
| `qcax-fabric-plugin-prompt-hardener` | `pypi-plugin-prompt-hardener` |
| `qcax-fabric-plugin-provenance` | `pypi-plugin-provenance` |
| `qcax-fabric-plugin-source-admission` | `pypi-plugin-source-admission` |
| `qcax-fabric-plugin-truth-policy` | `pypi-plugin-truth-policy` |
| `qcax-fabric-plugin-hello-example` | `pypi-plugin-hello-example` |

For every row:

- Owner: `qcax`
- Repository: `qcax-fabric`
- Workflow: `pypi-publish.yml`
- Environment: the exact environment shown above

`qcax-fabric-contracts` is intentionally retained at environment `pypi` because that pending publisher was created first.

## Security configuration

1. Repository must be exactly `qcax/qcax-fabric`.
2. Workflow must be the top-level `pypi-publish.yml`. Do not register a reusable workflow; PyPI documents reusable workflows as unsupported for the Trusted Publisher workflow.
3. Create the exact eleven GitHub environments above. Require a trusted reviewer and prevent self-review where GitHub plan/provider settings permit.
4. The OIDC publishing matrix job gets `id-token: write` only at job scope, plus the minimum `actions: read` needed to retrieve the prechecked artifact.
5. No long-lived PyPI API token is stored.
6. Each matrix job receives exactly one project/environment pair and publishes only that project's prechecked directory.
7. Pending publishers do not reserve project names before first publication.
8. Before first production upload, directly verify every exact project/repository/workflow/environment mapping and record the results in the provider-configuration receipt.
9. Postpublication verification must require exact candidate hashes, exact PyPI Integrity API publisher kind/repository/workflow/environment, and cryptographic `pypi-attestations verify pypi` verification for every wheel and sdist.

## Multi-project transaction

PyPI publication across eleven projects is not atomic. The QCAX precheck constructs a missing-only per-project matrix. Matrix execution order is not a correctness assumption.

After any publication attempt, including partial failure or cancellation, postverification re-reads PyPI and classifies the actual state. Exact already-published files may be retained only when their hash and full Trusted Publisher identity are exact. Wrong hashes, wrong publisher identities, unexpected files, or ambiguous state are incidents and are never handled by blind overwrite or skip-existing behavior.
