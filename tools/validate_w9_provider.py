#!/usr/bin/env python3
from pathlib import Path
import json, sys

ROOT = Path(__file__).resolve().parents[1]
errors = []
checks = 0


def ck(condition, message):
    global checks
    checks += 1
    if not condition:
        errors.append(message)


required = [
    "release/tooling/provider.py",
    "release/tooling/verify_github_attestations.py",
    "release/tooling/record_preflight_receipt.py",
    "release/tooling/reconcile_preflight.py",
    "release/tooling/publish_github.py",
    "release/tooling/verify_github_release.py",
    "release/tooling/assert_release_event.py",
    "release/tooling/record_replay_receipt.py",
    "release/tooling/pypi_integrity.py",
    "release/tooling/pypi_precheck.py",
    "release/tooling/pypi_postverify.py",
    "tests/release/test_w9_provider_mutations.py",
    "tests/semantics/test_w9_provider.py",
]
for relative in required:
    path = ROOT / relative
    ck(path.is_file(), "missing W9 interface " + relative)
    if path.is_file() and path.suffix == ".py":
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except Exception as exc:
            ck(False, f"{relative} compile: {exc}")

stub_phrases = (" is W9", "requires successful W9 replay", "exists only after W9 publication")
for relative in required[:11]:
    path = ROOT / relative
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    ck(not any(phrase in text for phrase in stub_phrases), relative + " still contains W9 stub")

replay = (ROOT / ".github/workflows/release-replay.yml").read_text(encoding="utf-8")
ck("gh release download" in replay, "replay workflow does not download immutable release assets")
ck("--published published-assets" in replay, "replay workflow does not pass provider-neutral published asset directory")
ck("finalize_payload.py replay-assets --replay" not in replay, "replay workflow passes unsupported --replay flag to finalizer")
ck("QCAX_EXPECTED_COMMIT: ${{ github.sha }}" in replay and "QCAX_RELEASE_TAG: ${{ github.event.release.tag_name }}" in replay, "replay candidate is not explicitly bound to event commit/tag")
ck("qcax-replay-receipt-${{ github.event.release.tag_name }}" in replay, "replay receipt is not uploaded with tag-bound name")

policy = json.loads((ROOT / "release/policy/pypi-publication-policy.json").read_text(encoding="utf-8"))
expected_projects = [
    "qcax-fabric-contracts",
    "qcax-fabric-sdk",
    "qcax-fabric-host",
    "qcax-fabric-plugin-authorization",
    "qcax-fabric-plugin-canonical-identity",
    "qcax-fabric-plugin-memory",
    "qcax-fabric-plugin-prompt-hardener",
    "qcax-fabric-plugin-provenance",
    "qcax-fabric-plugin-source-admission",
    "qcax-fabric-plugin-truth-policy",
    "qcax-fabric-plugin-hello-example",
]
expected_environments = [
    "pypi",
    "pypi-sdk",
    "pypi-host",
    "pypi-plugin-authorization",
    "pypi-plugin-canonical-identity",
    "pypi-plugin-memory",
    "pypi-plugin-prompt-hardener",
    "pypi-plugin-provenance",
    "pypi-plugin-source-admission",
    "pypi-plugin-truth-policy",
    "pypi-plugin-hello-example",
]
ck(policy.get("schema") == "qcax.pypi-publication-policy/3", "PyPI policy schema is not v3")
ck(policy.get("environment_model") == "per-project", "PyPI policy is not per-project environment model")
ck(policy.get("workflow") == ".github/workflows/pypi-publish.yml", "PyPI workflow identity drift")
ck(policy.get("projects") == expected_projects, "PyPI project set/order drift")
rows = policy.get("trusted_publishers") or []
ck(len(rows) == 11, "PyPI Trusted Publisher binding count is not 11")
ck([row.get("name") for row in rows] == expected_projects, "PyPI Trusted Publisher project order drift")
ck([row.get("environment") for row in rows] == expected_environments, "PyPI Trusted Publisher environment map drift")
ck(len({row.get("environment") for row in rows}) == 11, "PyPI Trusted Publisher environments are not unique")

pypi = (ROOT / ".github/workflows/pypi-publish.yml").read_text(encoding="utf-8")
ck(pypi.count("requirements/release-verify.txt") >= 2, "PyPI precheck/postverify do not both install verifier environment")
ck("GH_TOKEN: ${{ github.token }}" in pypi, "PyPI workflow missing GitHub read token for release/replay verification")
ck("publish_matrix: ${{ steps.plan.outputs.publish_matrix }}" in pypi, "PyPI precheck does not export publish matrix")
ck("matrix: ${{ fromJSON(needs.precheck.outputs.publish_matrix) }}" in pypi, "PyPI publish job does not consume exact dynamic matrix")
ck("environment: ${{ matrix.environment }}" in pypi, "PyPI publish job is not bound to matrix environment")
ck("packages-dir: staged/${{ matrix.project }}/" in pypi, "PyPI publish job is not project-directory scoped")
ck("fail-fast: false" in pypi, "PyPI matrix does not preserve independent project outcomes")
ck("id-token: write" in pypi, "PyPI publish job missing OIDC permission")
ck("path: pypi-missing/" in pypi, "PyPI precheck artifact is not per-project tree")
ck("always() && needs.precheck.result == 'success'" in pypi, "PyPI postverify does not run after partial publish failure/cancel")
publish_section = pypi[pypi.index("  publish:"):pypi.index("  postverify:")]
ck("checkout@" not in publish_section, "OIDC publish job checks out source")
ck("python " not in publish_section, "OIDC publish job executes repository Python")

req = (ROOT / "requirements/release-verify.txt").read_text(encoding="utf-8")
ck("pypi-attestations==0.0.30" in req, "pypi-attestations is not exact pinned admitted verifier")

template = json.loads((ROOT / "history/evidence/W9_PROVIDER_CONFIGURATION_TEMPLATE.json").read_text(encoding="utf-8"))
ck(template.get("overall") == "HOLD", "provider configuration template must fail closed")
ck(template.get("observed_commit") is None, "provider configuration template must not masquerade as current evidence")
ck(template.get("observed_utc") is None, "provider configuration template must not carry a fake observation timestamp")
github = template.get("github") or {}
ck("pypi_environments_verified" in github, "provider template missing plural PyPI environments gate")
ck("pypi_environment_verified" not in github, "provider template retains obsolete singular PyPI environment gate")
tpypi = template.get("pypi") or {}
ck(tpypi.get("environment_model") == "per-project", "provider template PyPI model drift")
trows = tpypi.get("projects") or []
ck([row.get("name") for row in trows] == expected_projects, "provider template project map drift")
ck([row.get("environment") for row in trows] == expected_environments, "provider template environment map drift")
ck(all(row.get("repository") == "qcax/qcax-fabric" for row in trows), "provider template repository binding drift")
ck(all(row.get("workflow") == "pypi-publish.yml" for row in trows), "provider template workflow binding drift")
ck(all(row.get("trusted_publisher_verified") is None for row in trows), "provider template contains unearned Trusted Publisher proof")

integrity = (ROOT / "release/tooling/pypi_integrity.py").read_text(encoding="utf-8")
for token, message in (
    ('publisher.get("kind") == "GitHub"', "Integrity verifier does not bind publisher kind"),
    ('publisher.get("repository") == repository', "Integrity verifier does not bind repository"),
    ('publisher.get("workflow") == workflow', "Integrity verifier does not bind workflow"),
    ('publisher.get("environment") == environment', "Integrity verifier does not bind environment"),
    ('application/vnd.pypi.integrity.v1+json', "Integrity verifier does not request stable media type"),
    ('pypi-attestations', "Integrity verifier lacks cryptographic verifier"),
):
    ck(token in integrity, message)

precheck = (ROOT / "release/tooling/pypi_precheck.py").read_text(encoding="utf-8")
ck("pypi_environments_verified" in precheck, "precheck does not require all PyPI environments verified")
ck("publish_matrix_for_missing" in precheck, "precheck lacks project/environment matrix construction")
ck("project_dir = out / project" in precheck, "precheck does not stage project-specific directories")
ck('row.get("environment") != BINDINGS[project]["environment"]' in precheck, "provider receipt validation does not bind exact project environment")
ck('row.get("workflow") != "pypi-publish.yml"' in precheck, "provider receipt validation does not bind workflow")
ck('row.get("repository") != repo' in precheck, "provider receipt validation does not bind repository")

postverify = (ROOT / "release/tooling/pypi_postverify.py").read_text(encoding="utf-8")
ck("verify_pypi_file_identity" in postverify, "postverify does not use exact Integrity/PEP740 verifier")
ck('"PARTIAL_PYPI_PUBLICATION"' in postverify, "postverify does not preserve partial publication state")
ck('"INCIDENT"' in postverify, "postverify does not preserve incident state")
ck("unexpected" in postverify and "mismatch" in postverify and "missing" in postverify, "postverify does not reconcile full target-version state")

mut = (ROOT / "conformance/run_mutations.py").read_text(encoding="utf-8")
runall = (ROOT / "tools/run_all.py").read_text(encoding="utf-8")
ck("test_w9_provider_mutations.py" in mut, "W9 mutation family missing from conformance aggregate")
ck("test_w9_provider_mutations.py" in runall, "W9 mutation family missing from full assurance aggregate")

pub = (ROOT / "release/tooling/publish_github.py").read_text(encoding="utf-8")
ck(pub.count("reread()") >= 7 and pub.count("run_mutation(") >= 4, "GitHub publisher lacks complete mutation/reread coverage")

for relative in (
    "release/tooling/provider.py",
    "release/tooling/publish_github.py",
    "release/tooling/pypi_integrity.py",
    "release/tooling/pypi_precheck.py",
    "release/tooling/pypi_postverify.py",
):
    text = (ROOT / relative).read_text(encoding="utf-8")
    for bad in ("gh ruleset", "gh secret", "gh variable", "/environments/", "branch-protection"):
        ck(bad not in text, f"{relative} contains forbidden provider-configuration mutation surface {bad}")

print(json.dumps({"status": "PASS" if not errors else "FAIL", "checks": checks, "errors": errors}, sort_keys=True))
sys.exit(1 if errors else 0)
