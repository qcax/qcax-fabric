# ADR-0001: Tiny TCB and plugin-shaped QCAX systems
Status: accepted for pre-publication alpha architecture.
Decision: all high-level QCAX systems are plugins; only generic loader/admission/lifecycle/effects/events/BootLock mechanics remain in host TCB.
Reason: maximises composability and replacement without allowing plugin installation to acquire authority.
Rejected: direct Cordis as load-bearing host (preview instability); fully privileged-free host (violates QCAX authority boundary); monolith (couples systems and defeats plugin experiment).
