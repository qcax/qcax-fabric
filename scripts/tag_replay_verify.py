from pathlib import Path
import argparse
import json
import os
import re
import tempfile
import sys

from release_common import EXPECTED_RELEASE, ROOT, norm_dist, run, sha256_file, tar_content_manifest
from release_provider import run_gh


EXACT = {
    "release-lock.json",
    "qcax-fabric-spec-v0.1.0-alpha.1.zip",
    "qcax-fabric-conformance-v0.1.0-alpha.1.zip",
    "RELEASE_NOTES-v0.1.0-alpha.1.md",
}


def sbom_fingerprint(path: Path, expected: set[str]) -> dict:
    doc = json.loads(path.read_text(encoding="utf-8"))
    if doc.get("spdxVersion") != "SPDX-2.3":
        raise RuntimeError("bad SPDX version")
    rows = {}
    for pkg in doc.get("packages", []):
        name = pkg.get("name")
        if not name:
            continue
        key = norm_dist(name)
        if key in expected:
            rows[key] = {
                "name": key,
                "versionInfo": str(pkg.get("versionInfo", "")),
                "licenseConcluded": pkg.get("licenseConcluded"),
                "licenseDeclared": pkg.get("licenseDeclared"),
                "filesAnalyzed": pkg.get("filesAnalyzed"),
            }
    if set(rows) != expected:
        raise RuntimeError(f"SBOM expected distribution mismatch: {sorted(expected-set(rows))}")
    return rows


def provenance_core(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "schema": data.get("schema"),
        "release": data.get("release"),
        "repository": data.get("repository"),
        "source_commit": data.get("source_commit"),
        "source_tree": data.get("source_tree"),
        "package_identities": data.get("package_identities"),
        "components": [
            x
            for x in data.get("components", [])
            if x.get("name") not in {"qcax-release-provenance.json", "sbom.spdx.json", "payload-manifest.json", "SHA256SUMS"}
            and not str(x.get("name", "")).endswith(".tar.gz")
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("candidate")
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", "qcax/qcax-fabric"))
    ap.add_argument("--tag", default=os.environ.get("GITHUB_REF_NAME", EXPECTED_RELEASE))
    ap.add_argument("--commit", default=os.environ.get("GITHUB_SHA", ""))
    ns = ap.parse_args()
    candidate = Path(ns.candidate).resolve()
    if ns.tag != EXPECTED_RELEASE or not re.fullmatch(r"[0-9a-f]{40}", ns.commit):
        raise RuntimeError("exact tag replay identity required")

    lock = json.loads((candidate / "release-lock.json").read_text(encoding="utf-8"))
    expected_dists = {norm_dist(e["distribution_name"]) for e in lock["entries"]}
    with tempfile.TemporaryDirectory() as td_raw:
        published = Path(td_raw) / "published"
        published.mkdir()
        run_gh(["release", "download", ns.tag, "--repo", ns.repo, "--dir", str(published)])
        if len([p for p in published.iterdir() if p.is_file()]) != 30:
            raise RuntimeError("published release asset count mismatch")

        run([sys.executable, str(ROOT / "scripts/verify_release_payload.py"), str(published), "--tag", ns.tag, "--commit", ns.commit], cwd=ROOT)

        exact_rows = []
        for name in sorted(EXACT):
            a, b = candidate / name, published / name
            same = a.read_bytes() == b.read_bytes()
            exact_rows.append({"name": name, "exact": same})
            if not same:
                raise RuntimeError(f"exact replay mismatch: {name}")
        for wheel in sorted(candidate.glob("*.whl")):
            other = published / wheel.name
            if not other.is_file() or wheel.read_bytes() != other.read_bytes():
                raise RuntimeError(f"wheel replay mismatch: {wheel.name}")
            exact_rows.append({"name": wheel.name, "exact": True})

        sdist_rows = []
        for sdist in sorted(candidate.glob("*.tar.gz")):
            other = published / sdist.name
            if not other.is_file():
                raise RuntimeError(f"published sdist missing: {sdist.name}")
            a = tar_content_manifest(sdist)
            b = tar_content_manifest(other)
            same = a == b
            sdist_rows.append({"name": sdist.name, "normalized_content_equal": same})
            if not same:
                raise RuntimeError(f"sdist normalized-content replay mismatch: {sdist.name}")

        if sbom_fingerprint(candidate / "sbom.spdx.json", expected_dists) != sbom_fingerprint(
            published / "sbom.spdx.json", expected_dists
        ):
            raise RuntimeError("SBOM semantic replay mismatch")
        if provenance_core(candidate / "qcax-release-provenance.json") != provenance_core(
            published / "qcax-release-provenance.json"
        ):
            raise RuntimeError("provenance semantic replay mismatch")

    print(
        json.dumps(
            {
                "status": "PASS",
                "exact_assets": len(exact_rows),
                "sdist_semantic_assets": len(sdist_rows),
                "sbom_semantic": "PASS",
                "provenance_semantic": "PASS",
                "release": ns.tag,
                "commit": ns.commit,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
