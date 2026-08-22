# Plugin author guide — v1alpha1

1. Create an independent Python distribution or another ecosystem package.
2. Ship a static `qcax-plugin.json` descriptor as package data.
3. For Python, register exactly one or more entry points in group `qcax.fabric.plugins`.
4. Depend on `qcax-fabric-sdk` and `qcax-fabric-contracts`, not `qcax-fabric-host`.
5. Declare every provided/required capability and its contract SemVer.
6. Declare events and modes. `DURABLE` is reserved in the wire schema but unsupported by the alpha1 host; use only `EPHEMERAL` until the event-store seam lands.
7. Register every reversible side effect with a disposer.
8. Do not claim sandboxing merely because permissions are declared.
9. Pass the conformance suite from a clean installed wheel before requesting inclusion.
10. First-party/system-pinned upgrades use a new BootLock generation and canary/rollback receipt.
