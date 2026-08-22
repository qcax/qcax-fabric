# Namespace policy

- `org.qcax.*` plugin IDs are reserved for first-party QCAX distributions.
- `qcax.*` capability/event namespaces are reserved for published QCAX contracts.
- Third-party public plugins should use an ownership-scoped reverse namespace such as `io.github.<owner>.*` or another domain the publisher can demonstrate control over.
- Registration/discovery never treats namespace appearance as authority. Identity still requires exact artifact evidence and the applicable trust/admission policy.
- Names are case-sensitive in the normative descriptor; distribution-name normalization follows the host ecosystem separately.
