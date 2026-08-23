from pathlib import Path
import json, subprocess, urllib.error, urllib.parse, urllib.request

from common import ReleaseError, load_json

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_REPOSITORY = "qcax/qcax-fabric"
EXPECTED_WORKFLOW = "pypi-publish.yml"
INTEGRITY_ACCEPT = "application/vnd.pypi.integrity.v1+json"


def publisher_bindings():
    policy = load_json(ROOT / "release/policy/pypi-publication-policy.json")
    if policy.get("schema") != "qcax.pypi-publication-policy/3":
        raise ReleaseError("PyPI publication policy schema mismatch")
    if policy.get("workflow") != ".github/workflows/" + EXPECTED_WORKFLOW:
        raise ReleaseError("PyPI publication workflow mismatch")
    if policy.get("environment_model") != "per-project":
        raise ReleaseError("PyPI environment model mismatch")

    contract = load_json(ROOT / "release/policy/release-contract.json")
    expected_projects = [
        x["name"] for x in contract["package_set"]["packages"] if x.get("publish")
    ]
    rows = policy.get("trusted_publishers") or []
    if len(rows) != len(expected_projects):
        raise ReleaseError("PyPI Trusted Publisher binding count mismatch")

    by_name = {}
    environments = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ReleaseError("PyPI Trusted Publisher binding row must be object")
        name = row.get("name")
        environment = row.get("environment")
        if name in by_name or name not in expected_projects:
            raise ReleaseError("PyPI Trusted Publisher project identity mismatch")
        if not isinstance(environment, str) or not environment.startswith("pypi"):
            raise ReleaseError("PyPI Trusted Publisher environment invalid")
        if environment in environments:
            raise ReleaseError("PyPI Trusted Publisher environments must be unique")
        by_name[name] = {
            "name": name,
            "environment": environment,
            "workflow": EXPECTED_WORKFLOW,
            "repository": EXPECTED_REPOSITORY,
        }
        environments.add(environment)

    if list(by_name) != expected_projects:
        raise ReleaseError("PyPI Trusted Publisher binding order/set mismatch")
    if by_name["qcax-fabric-contracts"]["environment"] != "pypi":
        raise ReleaseError("contracts publisher environment drift")
    return by_name


def integrity_url(project, version, filename):
    parts = [urllib.parse.quote(x, safe="") for x in (project, version, filename)]
    return f"https://pypi.org/integrity/{parts[0]}/{parts[1]}/{parts[2]}/provenance"


def fetch_integrity(project, version, filename):
    url = integrity_url(project, version, filename)
    req = urllib.request.Request(
        url,
        headers={
            "Accept": INTEGRITY_ACCEPT,
            "User-Agent": "QCAX-W9-PyPI-Integrity/1",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            if response.status != 200:
                raise ReleaseError(f"PyPI Integrity HTTP {response.status}: {filename}")
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ReleaseError(f"PyPI Integrity HTTP {exc.code}: {filename}") from exc


def publisher_identity_matches(provenance, repository, workflow, environment):
    if not isinstance(provenance, dict) or provenance.get("version") != 1:
        return False
    bundles = provenance.get("attestation_bundles")
    if not isinstance(bundles, list) or len(bundles) != 1:
        return False
    publisher = bundles[0].get("publisher")
    if not isinstance(publisher, dict):
        return False
    return (
        publisher.get("kind") == "GitHub"
        and publisher.get("repository") == repository
        and publisher.get("workflow") == workflow
        and publisher.get("environment") == environment
    )


def verify_pypi_file_identity(project, version, filename, repository_url, binding):
    provenance = fetch_integrity(project, version, filename)
    if not publisher_identity_matches(
        provenance,
        binding["repository"],
        binding["workflow"],
        binding["environment"],
    ):
        return False

    proc = subprocess.run(
        [
            "pypi-attestations",
            "verify",
            "pypi",
            "--repository",
            repository_url,
            "pypi:" + filename,
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    return proc.returncode == 0
