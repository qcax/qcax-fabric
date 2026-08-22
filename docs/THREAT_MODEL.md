# Threat model

Primary threats: plugin code execution before admission; forged or ambiguous artifact identity; reserved-capability takeover; in-process permission laundering; event-contract drift; guard bypass; rollback residue; dependency cycles; provider last-write-wins; stale generation promotion; poisoned memory/source ancestry; GitHub Actions supply-chain compromise; secret exposure on untrusted PRs; dependency confusion; release/tag mutation; attestation/security conflation.

Alpha boundary: trusted in-process plugins are not sandboxed. Untrusted plugin security isolation is NOT established. Future sandboxed-process/remote execution must bind IPC identity, capability mediation, time/resource budgets, cancellation, crash recovery, provenance and result canonicalization before promotion.
