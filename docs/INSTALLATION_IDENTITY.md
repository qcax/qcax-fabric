# Installation trust chain — R4.5

QCAX separates **transport identity** from **runtime installed-image identity**.

1. A release wheel is identified by its SHA-256 and release provenance/attestations.
2. Before a trusted plugin is admitted, the install process verifies every hashed `RECORD` entry against installed files.
3. `InstalledImageIdentity` is the canonical digest of the hashed `RECORD` declarations after those files verify.
4. The verifier emits the normative `InstallationReceipt` and seals it into an opaque `AdmissionTicket` bound to the exact `PluginEnvelope`.
5. `PluginHost.preflight()` and `PluginHost.add()` require that verifier-issued AdmissionTicket; raw caller-constructed PluginEnvelope objects are rejected.
6. BootLock pins the exact InstalledImageIdentity for installed `SYSTEM_PINNED` and explicitly trusted in-process third-party/adapter providers.
7. Runtime can recompute InstalledImageIdentity from installed `RECORD` without assuming pip preserved the original wheel archive.

Installed-image canonicalization excludes installer-generated `.dist-info/INSTALLER`, `.dist-info/REQUESTED`, and `.dist-info/direct_url.json` entries because their bytes may depend on installer or source path. Unknown additional hashed RECORD entries are not excluded and therefore change the identity fail-closed. Bytecode/unhashed RECORD rows are not identity inputs.

A wheel SHA and an InstalledImageIdentity are not interchangeable. A normal `pip install` is not, by itself, an authority or provenance proof. Release lock manifests carry both identities. Private unit-test helpers may synthesize tickets only inside the test suite; the public SDK exports no development-ticket issuer. Release/runtime admission requires an `INSTALLED_IMAGE` ticket generated from verified RECORD bytes.
