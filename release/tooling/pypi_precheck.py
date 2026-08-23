from pathlib import Path
import argparse, json, shutil, subprocess, tempfile, urllib.error, urllib.request

from common import ReleaseError, load_json, require_commit
from provider import download_run_artifact, workflow_run
from pypi_integrity import publisher_bindings, verify_pypi_file_identity
from verify_github_release import verify_release

ROOT = Path(__file__).resolve().parents[2]
BINDINGS = publisher_bindings()
PROJECTS = list(BINDINGS)


def classify_files(intended, observed):
    exact = []
    missing = []
    mismatch = []
    for name, expected in intended.items():
        got = observed.get(name)
        if got is None:
            missing.append(name)
        elif got.get("sha256") != expected.get("sha256") or got.get("trusted_publisher") is not True:
            mismatch.append(name)
        else:
            exact.append(name)
    unexpected = [name for name in observed if name not in intended]
    state = (
        "INCIDENT"
        if mismatch or unexpected
        else (
            "PYPI_EXACT"
            if not missing
            else ("PARTIAL_PYPI_PUBLICATION" if exact else "PYPI_ALL_MISSING")
        )
    )
    return {
        "state": state,
        "exact": sorted(exact),
        "missing": sorted(missing),
        "mismatch": sorted(mismatch),
        "unexpected": sorted(unexpected),
    }


def publish_matrix_for_missing(missing, project_for):
    missing_projects = []
    seen = set()
    for project in PROJECTS:
        if any(project_for.get(name) == project for name in missing):
            if project in seen:
                raise ReleaseError("duplicate project in PyPI publish matrix")
            seen.add(project)
            binding = BINDINGS[project]
            missing_projects.append(
                {
                    "project": project,
                    "environment": binding["environment"],
                }
            )
    if any(project_for.get(name) not in seen for name in missing):
        raise ReleaseError("missing PyPI file is not bound to a publish project")
    return {"include": missing_projects}


def validate_provider_receipt(path: Path, repo: str, commit: str):
    path = Path(path)
    if not path.is_file():
        raise ReleaseError("current W9 provider-configuration receipt required before PyPI precheck")
    data = load_json(path)
    if data.get("schema") != "qcax.provider-configuration-receipt/1" or data.get("overall") != "PASS":
        raise ReleaseError("provider-configuration receipt is not PASS")
    if data.get("repository") != repo or data.get("observed_commit") != commit:
        raise ReleaseError("provider-configuration receipt source binding mismatch")
    if not isinstance(data.get("observed_utc"), str) or not data.get("observed_utc"):
        raise ReleaseError("provider-configuration receipt observation timestamp required")

    github = data.get("github") or {}
    required_github = (
        "actions_sha_pinning_required",
        "immutable_releases",
        "main_ruleset_required_checks_verified",
        "github_release_environment_verified",
        "pypi_environments_verified",
    )
    if any(github.get(key) is not True for key in required_github):
        raise ReleaseError("all GitHub provider-configuration gates must be directly verified")

    pypi = data.get("pypi") or {}
    if pypi.get("workflow") != ".github/workflows/pypi-publish.yml":
        raise ReleaseError("PyPI publisher workflow mismatch")
    if pypi.get("environment_model") != "per-project":
        raise ReleaseError("PyPI publisher environment model mismatch")

    rows = pypi.get("projects") or []
    by_name = {row.get("name"): row for row in rows if isinstance(row, dict)}
    if len(rows) != len(PROJECTS) or len(by_name) != len(PROJECTS) or set(by_name) != set(PROJECTS):
        raise ReleaseError("all eleven exact Trusted Publisher bindings must be directly verified")

    for project in PROJECTS:
        row = by_name[project]
        if (
            row.get("environment") != BINDINGS[project]["environment"]
            or row.get("workflow") != "pypi-publish.yml"
            or row.get("repository") != repo
            or row.get("trusted_publisher_verified") is not True
        ):
            raise ReleaseError("Trusted Publisher binding mismatch for " + project)
    return data


def pypi_json(project):
    url = f"https://pypi.org/pypi/{project}/json"
    req = urllib.request.Request(url, headers={"User-Agent": "QCAX-W9-PyPI-Precheck/2"})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return 404, None
        raise ReleaseError(f"PyPI HTTP {exc.code} for {project}") from exc


def observed_project(project, version, intended_names, repository_url):
    status, data = pypi_json(project)
    if status == 404:
        return {}
    files = (data.get("releases") or {}).get(version) or []
    rows = {}
    for file_row in files:
        name = file_row.get("filename")
        if not name:
            continue
        if name in rows:
            rows[name] = {"sha256": "DUPLICATE", "trusted_publisher": False}
            continue
        digest = ((file_row.get("digests") or {}).get("sha256"))
        trusted = False
        if name in intended_names:
            trusted = verify_pypi_file_identity(
                project,
                version,
                name,
                repository_url,
                BINDINGS[project],
            )
        rows[name] = {"sha256": digest, "trusted_publisher": trusted}
    return rows


def verify_replay(repo, tag, commit, replay_run_id, dest):
    run = workflow_run(repo, replay_run_id)
    if (
        run.get("status") != "completed"
        or run.get("conclusion") != "success"
        or run.get("event") != "release"
        or run.get("head_sha") != commit
    ):
        raise ReleaseError("replay workflow run identity/status mismatch")
    name = f"qcax-replay-receipt-{tag}"
    download_run_artifact(repo, replay_run_id, name, dest)
    files = [path for path in Path(dest).rglob("*") if path.is_file()]
    if len(files) != 1 or files[0].name != "replay-receipt.json":
        raise ReleaseError("replay receipt artifact content mismatch")
    receipt = load_json(files[0])
    if (
        receipt.get("stage") != "replay"
        or receipt.get("overall_state") != "REPLAY_PASS"
        or receipt.get("source_commit") != commit
        or receipt.get("release_tag") != tag
    ):
        raise ReleaseError("replay receipt binding mismatch")
    return receipt


def precheck(repo, tag, commit, replay_run_id, confirmation, missing_out, github_output, provider_receipt):
    commit = require_commit(commit)
    if confirmation != "PYPI-" + tag:
        raise ReleaseError("explicit PyPI confirmation mismatch")

    contract = load_json(ROOT / "release/policy/release-contract.json")
    identity = contract.get("release_identity") or {}
    if identity.get("status") != "ACTIVE" or identity.get("selected_tag") != tag:
        raise ReleaseError("release identity not activated for requested tag")
    version = identity.get("selected_version")

    validate_provider_receipt(provider_receipt, repo, commit)
    repository_url = "https://github.com/" + repo

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir = Path(temp_dir)
        assets = temp_dir / "release-assets"
        assets.mkdir()
        proc = subprocess.run(
            ["gh", "release", "download", tag, "--repo", repo, "--dir", str(assets)],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if proc.returncode:
            raise ReleaseError("GitHub release download failed: " + proc.stderr[-1200:])

        verify_release(assets, repo, tag, commit)
        verify_replay(repo, tag, commit, replay_run_id, temp_dir / "replay-receipt")

        lock = load_json(assets / "release-lock.json")
        intended = {}
        project_for = {}
        for entry in lock.get("entries") or []:
            for key, hash_key in (
                ("wheel_filename", "wheel_sha256"),
                ("sdist_filename", "sdist_sha256"),
            ):
                name = entry[key]
                intended[name] = {"sha256": entry[hash_key]}
                project_for[name] = entry["distribution_name"]

        if set(project_for.values()) != set(PROJECTS):
            raise ReleaseError("release lock project set does not match PyPI publisher bindings")

        observed = {}
        for project in PROJECTS:
            names = {name for name, owner in project_for.items() if owner == project}
            observed.update(observed_project(project, version, names, repository_url))

        result = classify_files(intended, observed)
        if result["state"] == "INCIDENT":
            raise ReleaseError("PyPI precheck incident: " + json.dumps(result, sort_keys=True))

        out = Path(missing_out)
        if out.exists():
            shutil.rmtree(out)
        out.mkdir(parents=True)

        for name in result["missing"]:
            project = project_for[name]
            project_dir = out / project
            project_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(assets / name, project_dir / name)

        matrix = publish_matrix_for_missing(result["missing"], project_for)
        publish_required = bool(result["missing"])
        if github_output:
            with Path(github_output).open("a", encoding="utf-8") as output:
                output.write("publish_required=" + ("true" if publish_required else "false") + "\n")
                output.write("publish_matrix=" + json.dumps(matrix, separators=(",", ":"), sort_keys=True) + "\n")

        result.update(
            {
                "status": "PASS",
                "publish_required": publish_required,
                "missing_count": len(result["missing"]),
                "publish_matrix": matrix,
            }
        )
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--replay-run-id", required=True)
    parser.add_argument("--confirmation", required=True)
    parser.add_argument("--missing-out", required=True)
    parser.add_argument("--github-output")
    parser.add_argument("--provider-receipt", default="history/evidence/W9_PROVIDER_CONFIGURATION.json")
    args = parser.parse_args()
    print(
        json.dumps(
            precheck(
                args.repo,
                args.tag,
                args.commit,
                args.replay_run_id,
                args.confirmation,
                args.missing_out,
                args.github_output,
                Path(args.provider_receipt),
            ),
            sort_keys=True,
        )
    )
