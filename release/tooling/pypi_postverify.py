from pathlib import Path
import argparse, json, os, subprocess, sys, tempfile, urllib.error, urllib.request, venv

from common import ReleaseError, load_json, require_commit, sha256_file
from pypi_integrity import publisher_bindings, verify_pypi_file_identity
from verify_github_release import verify_release

ROOT = Path(__file__).resolve().parents[2]
BINDINGS = publisher_bindings()
PROJECTS = list(BINDINGS)


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "QCAX-W9-PyPI-Postverify/2"})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise ReleaseError(f"PyPI HTTP {exc.code}: {url}") from exc


def download(url, path):
    req = urllib.request.Request(url, headers={"User-Agent": "QCAX-W9-PyPI-Postverify/2"})
    with urllib.request.urlopen(req, timeout=60) as response:
        Path(path).write_bytes(response.read())


def live_index_install(projects, version):
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir = Path(temp_dir)
        envdir = temp_dir / "venv"
        venv.EnvBuilder(with_pip=True, clear=True).create(envdir)
        python = envdir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        specs = [f"{project}=={version}" for project in projects]
        proc = subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--index-url",
                "https://pypi.org/simple",
                *specs,
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if proc.returncode:
            raise ReleaseError("live-index install failed: " + proc.stderr[-2000:])
        code = (
            "import importlib.metadata as m,json; "
            "ds={d.metadata['Name'].lower():d.version for d in m.distributions()}; "
            "eps=list(m.entry_points(group='qcax.fabric.plugins')); "
            "print(json.dumps({'entry_points':len(eps),'versions':ds}))"
        )
        check = subprocess.run(
            [str(python), "-c", code],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if check.returncode:
            raise ReleaseError("live-index metadata canary failed: " + check.stderr[-1200:])
        data = json.loads(check.stdout)
        if any(data["versions"].get(project) != version for project in projects) or data["entry_points"] != 8:
            raise ReleaseError("live-index installed identity mismatch")
        return {"status": "PASS", "projects": len(projects), "entry_points": data["entry_points"]}


def postverify(tag, commit, repository):
    commit = require_commit(commit)
    if repository != "https://github.com/qcax/qcax-fabric":
        raise ReleaseError("canonical repository URL required")
    repo = repository.removeprefix("https://github.com/").rstrip("/")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir = Path(temp_dir)
        expected = temp_dir / "github-release"
        expected.mkdir()

        proc = subprocess.run(
            ["gh", "release", "download", tag, "--repo", repo, "--dir", str(expected)],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if proc.returncode:
            raise ReleaseError("GitHub release download failed: " + proc.stderr[-1200:])
        verify_release(expected, repo, tag, commit)

        lock = load_json(expected / "release-lock.json")
        entries = lock.get("entries") or []
        projects = [entry["distribution_name"] for entry in entries]
        if len(entries) != 11 or projects != PROJECTS:
            raise ReleaseError("release lock package set/order mismatch")
        version = entries[0]["distribution_version"]
        if any(entry.get("distribution_version") != version for entry in entries):
            raise ReleaseError("release lock coordinated version mismatch")

        downloaded = temp_dir / "pypi"
        downloaded.mkdir()
        exact_rows = []
        missing = []
        mismatch = []
        unexpected = []

        for entry in entries:
            project = entry["distribution_name"]
            data = fetch_json(f"https://pypi.org/pypi/{project}/{version}/json")
            urls = (data or {}).get("urls") or []
            by_name = {}
            for row in urls:
                name = row.get("filename")
                if not name:
                    continue
                if name in by_name:
                    mismatch.append({"project": project, "filename": name, "reason": "duplicate filename"})
                by_name[name] = row

            expected_names = {entry["wheel_filename"], entry["sdist_filename"]}
            unexpected.extend(
                {"project": project, "filename": name}
                for name in sorted(set(by_name) - expected_names)
            )

            for filename, hash_key in (
                (entry["wheel_filename"], "wheel_sha256"),
                (entry["sdist_filename"], "sdist_sha256"),
            ):
                expected_hash = entry[hash_key]
                row = by_name.get(filename)
                if row is None:
                    missing.append({"project": project, "filename": filename})
                    continue

                digest = (row.get("digests") or {}).get("sha256")
                if digest != expected_hash:
                    mismatch.append(
                        {
                            "project": project,
                            "filename": filename,
                            "reason": "index digest mismatch",
                            "observed": digest,
                            "expected": expected_hash,
                        }
                    )
                    continue

                path = downloaded / filename
                download(row["url"], path)
                downloaded_hash = sha256_file(path)
                if downloaded_hash != expected_hash:
                    mismatch.append(
                        {
                            "project": project,
                            "filename": filename,
                            "reason": "downloaded digest mismatch",
                            "observed": downloaded_hash,
                            "expected": expected_hash,
                        }
                    )
                    continue

                if not verify_pypi_file_identity(
                    project,
                    version,
                    filename,
                    repository,
                    BINDINGS[project],
                ):
                    mismatch.append(
                        {
                            "project": project,
                            "filename": filename,
                            "reason": "Trusted Publisher/PEP740 identity mismatch",
                            "expected_environment": BINDINGS[project]["environment"],
                        }
                    )
                    continue

                exact_rows.append(
                    {
                        "project": project,
                        "filename": filename,
                        "sha256": expected_hash,
                        "publisher": {
                            "kind": "GitHub",
                            "repository": repo,
                            "workflow": "pypi-publish.yml",
                            "environment": BINDINGS[project]["environment"],
                        },
                        "pep740": "PASS",
                    }
                )

        if mismatch or unexpected or missing:
            if mismatch or unexpected:
                state = "INCIDENT"
            elif exact_rows:
                state = "PARTIAL_PYPI_PUBLICATION"
            else:
                state = "PYPI_ALL_MISSING"
            summary = {
                "overall_state": state,
                "exact": len(exact_rows),
                "missing": missing,
                "mismatch": mismatch,
                "unexpected": unexpected,
            }
            raise ReleaseError("PyPI poststate not complete: " + json.dumps(summary, sort_keys=True))

        for relative in (
            "conformance/run_exact_wheel_canaries.py",
            "conformance/run_out_of_tree_canary.py",
        ):
            check = subprocess.run(
                [sys.executable, str(ROOT / relative), str(downloaded)],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=300,
            )
            if check.returncode:
                raise ReleaseError(
                    relative
                    + " failed on PyPI-downloaded wheels: "
                    + check.stderr[-1600:]
                    + " "
                    + check.stdout[-1600:]
                )

        live = live_index_install(projects, version)
        return {
            "status": "PASS",
            "overall_state": "PYPI_POSTVERIFY_PASS",
            "projects": len(projects),
            "files": len(exact_rows),
            "pep740_verified": len(exact_rows),
            "publisher_identities_verified": len(exact_rows),
            "live_index": live,
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--repository", required=True)
    args = parser.parse_args()
    print(json.dumps(postverify(args.tag, args.commit, args.repository), sort_keys=True))
