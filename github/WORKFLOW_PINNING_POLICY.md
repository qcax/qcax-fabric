# Workflow action pinning
Every enabled GitHub Action reference must be a full-length immutable commit SHA. Human-readable release/tag names may be retained in comments. The staging tree intentionally does not invent SHAs; R5 must resolve and record them from the official repositories immediately before enabling workflows, then rerun the late-source/security check.
