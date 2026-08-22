# Branch and pull-request policy

Use trunk-based development on `main` with short-lived topic branches. Do not create a long-lived `develop` branch. Every non-emergency change reaches `main` through a pull request after bootstrap rulesets are active.

Solo-maintainer bootstrap: require a PR record, required CI checks, and resolved conversations, but zero approving reviews. A maintainer cannot supply independent review of their own change; do not create a permanently blocked rule. Once a second eligible maintainer exists, require at least one approval and code-owner review for host TCB, contracts/schemas, BootLock, security policy and release workflow changes.

Breaking public ABI changes require an RFC/ADR, migration notes, conformance-vector update, mutation delta and explicit prerelease version impact. Emergency bypasses must produce an issue/receipt and a post-merge retrospective check.
