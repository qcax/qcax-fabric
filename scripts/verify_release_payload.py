from __future__ import annotations

from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import os
import re
import zipfile

from release_common import (
    EXPECTED_RELEASE,
    manifest_digest,
    norm_dist,
    safe_member_name,
    sha256_file,
    tar_content_manifest,
)

CONTROL = {
    "release-lock.json",
    "sbom.spdx.json",
    "qcax-fabric-spec-v0.1.0-alpha.1.zip",
    "qcax-fabric-conformance-v0.1.0-alpha.1.zip",
    "RELEASE_NOTES-v0.1.0-alpha.1.md",
    "qcax-release-provenance.json",
    "payload-manifest.json",
    "SHA256SUMS",
}
SPEC_FILES = {
    "artifact-envelope-v1alpha1.schema.json",
    "boot-lock-v1alpha1.schema.json",
    "installation-receipt-v1alpha1.schema.json",
    "plugin-descriptor-v1alpha1.schema.json",
    "release-lock-v1alpha1.schema.json",
    "MANIFEST.json",
}
CONF_FILES = {
    "metadata.json",
    "contract-conformance.json",
    "wheel-repro.json",
    "sdist-repro.json",
    "sdist-installed-image-parity.json",
}


def read_zip_json(z: zipfile.ZipFile, name: str) -> dict:
    return json.loads(z.read(name).decode("utf-8"))


def safe_zip_names(path: Path) -> set[str]:
    with zipfile.ZipFile(path) as z:
        names = [safe_member_name(i.filename) for i in z.infolist()]
    if len(names) != len(set(names)):
        raise RuntimeError(f"{path}: duplicate zip members")
    folded = {}
    nfc = {}
    import unicodedata
    for n in names:
        folded.setdefault(n.casefold(), []).append(n)
        nfc.setdefault(unicodedata.normalize("NFC", n), []).append(n)
    if any(len(set(v)) > 1 for v in folded.values()) or any(len(set(v)) > 1 for v in nfc.values()):
        raise RuntimeError(f"{path}: archive path collision")
    return set(names)


def parse_sums(path: Path) -> dict[str, str]:
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.fullmatch(r"([0-9a-f]{64})  ([^\r\n]+)", line)
        if not m:
            raise RuntimeError(f"bad SHA256SUMS line: {line!r}")
        digest, name = m.groups()
        safe_member_name(name)
        if name in rows:
            raise RuntimeError(f"duplicate checksum name {name}")
        rows[name] = digest
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("directory")
    ap.add_argument("--tag", default=os.environ.get("QCAX_RELEASE_TAG", EXPECTED_RELEASE))
    ap.add_argument("--commit", default=os.environ.get("QCAX_EXPECTED_COMMIT", ""))
    ns = ap.parse_args()
    root = Path(ns.directory).resolve()
    if ns.tag != EXPECTED_RELEASE:
        raise RuntimeError(f"unexpected release tag {ns.tag}")
    if not re.fullmatch(r"[0-9a-f]{40}", ns.commit):
        raise RuntimeError("exact 40-hex expected commit required")

    files = sorted(p for p in root.iterdir() if p.is_file())
    wheels = sorted(root.glob("*.whl"))
    sdists = sorted(root.glob("*.tar.gz"))
    names = {p.name for p in files}
    if len(files) != 30 or len(wheels) != 11 or len(sdists) != 11:
        raise RuntimeError(f"release inventory count mismatch: files={len(files)} wheels={len(wheels)} sdists={len(sdists)}")
    if names - {p.name for p in wheels + sdists} != CONTROL:
        raise RuntimeError(f"control asset set mismatch: {sorted(names - {p.name for p in wheels + sdists})}")

    manifest = json.loads((root / "payload-manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != "qcax.release-payload-manifest/1" or manifest.get("release") != ns.tag:
        raise RuntimeError("payload manifest identity mismatch")
    if manifest.get("source_commit") != ns.commit:
        raise RuntimeError("payload manifest source commit mismatch")
    mrows = manifest.get("assets", [])
    manifest_names = {r["name"] for r in mrows}
    expected_primary_names = names - {"payload-manifest.json", "SHA256SUMS"}
    if len(mrows) != 28 or len(manifest_names) != 28 or manifest_names != expected_primary_names:
        raise RuntimeError(
            f"payload manifest primary set mismatch: manifest={sorted(manifest_names)} expected={sorted(expected_primary_names)}"
        )
    for row in mrows:
        p = root / safe_member_name(row["name"])
        if not p.is_file():
            raise RuntimeError(f"manifest asset missing: {row['name']}")
        if p.stat().st_size != row["bytes"] or sha256_file(p) != row["sha256"]:
            raise RuntimeError(f"manifest digest mismatch: {row['name']}")

    sums = parse_sums(root / "SHA256SUMS")
    if len(sums) != 29 or "SHA256SUMS" in sums or set(sums) != names - {"SHA256SUMS"}:
        raise RuntimeError("SHA256SUMS must cover exactly the other 29 uploaded assets")
    for name, digest in sums.items():
        p = root / name
        if not p.is_file() or sha256_file(p) != digest:
            raise RuntimeError(f"SHA256SUMS mismatch: {name}")

    lock = json.loads((root / "release-lock.json").read_text(encoding="utf-8"))
    if lock.get("schema") != "qcax.release-lock/v1alpha1" or lock.get("release") != ns.tag:
        raise RuntimeError("release-lock identity mismatch")
    entries = lock.get("entries", [])
    if len(entries) != 11:
        raise RuntimeError("release-lock entry count")
    expected_dists = {}
    for e in entries:
        key = norm_dist(e["distribution_name"])
        if key in expected_dists:
            raise RuntimeError(f"duplicate release-lock distribution {key}")
        expected_dists[key] = e
        wheel = root / e["wheel_filename"]
        if not wheel.is_file() or sha256_file(wheel) != e["wheel_sha256"]:
            raise RuntimeError(f"release-lock wheel mismatch: {e['wheel_filename']}")

    sbom = json.loads((root / "sbom.spdx.json").read_text(encoding="utf-8"))
    if sbom.get("spdxVersion") != "SPDX-2.3":
        raise RuntimeError("unexpected SPDX version")
    observed = {}
    for pkg in sbom.get("packages", []):
        name = pkg.get("name")
        if name:
            observed.setdefault(norm_dist(name), set()).add(str(pkg.get("versionInfo", "")))
    missing = sorted(set(expected_dists) - set(observed))
    if missing:
        raise RuntimeError(f"SBOM missing release distributions: {missing}")
    for key, e in expected_dists.items():
        versions = observed[key]
        if e["distribution_version"] not in versions:
            raise RuntimeError(f"SBOM version mismatch for {key}: {versions}")

    spec_path = root / "qcax-fabric-spec-v0.1.0-alpha.1.zip"
    if safe_zip_names(spec_path) != SPEC_FILES:
        raise RuntimeError("spec bundle inventory mismatch")
    with zipfile.ZipFile(spec_path) as z:
        sm = read_zip_json(z, "MANIFEST.json")
        if sm.get("release") != ns.tag or sm.get("source_commit") != ns.commit or len(sm.get("files", [])) != 5:
            raise RuntimeError("spec bundle manifest identity mismatch")
        for row in sm["files"]:
            data = z.read(row["path"])
            if len(data) != row["bytes"] or hashlib.sha256(data).hexdigest() != row["sha256"]:
                raise RuntimeError(f"spec bundle digest mismatch: {row['path']}")

    conf_path = root / "qcax-fabric-conformance-v0.1.0-alpha.1.zip"
    if safe_zip_names(conf_path) != CONF_FILES:
        raise RuntimeError("conformance bundle inventory mismatch")
    with zipfile.ZipFile(conf_path) as z:
        meta = read_zip_json(z, "metadata.json")
        contract = read_zip_json(z, "contract-conformance.json")
        wheel_r = read_zip_json(z, "wheel-repro.json")
        sdist_r = read_zip_json(z, "sdist-repro.json")
        parity_r = read_zip_json(z, "sdist-installed-image-parity.json")
        if meta.get("release") != ns.tag or meta.get("source_commit") != ns.commit:
            raise RuntimeError("conformance metadata identity mismatch")
        if contract.get("status") != "PASS" or contract.get("checks", 0) < 80:
            raise RuntimeError("contract conformance failed")
        if wheel_r.get("status") != "PASS" or wheel_r.get("distributions") != 11 or wheel_r.get("byte_identical_twins") != 11:
            raise RuntimeError("wheel reproducibility receipt failed")
        if sdist_r.get("status") != "PASS" or sdist_r.get("distributions") != 11 or sdist_r.get("normalized_content_twins") != 11:
            raise RuntimeError("sdist normalized-content receipt failed")
        if parity_r.get("status") != "PASS" or parity_r.get("distributions") != 11 or parity_r.get("matches") != 11:
            raise RuntimeError("sdist installed-image parity receipt failed")

        wheel_rows = wheel_r.get("wheels", {})
        if set(wheel_rows) != {p.name for p in wheels}:
            raise RuntimeError("wheel reproducibility receipt inventory mismatch")
        for wheel in wheels:
            row = wheel_rows[wheel.name]
            if row.get("sha256") != sha256_file(wheel) or row.get("bytes") != wheel.stat().st_size:
                raise RuntimeError(f"wheel reproducibility receipt mismatch: {wheel.name}")

        sdist_rows = {r["sdist_filename"]: r for r in sdist_r.get("sdists", [])}
        if set(sdist_rows) != {p.name for p in sdists}:
            raise RuntimeError("sdist reproducibility receipt inventory mismatch")
        for sdist in sdists:
            row = sdist_rows[sdist.name]
            normalized = tar_content_manifest(sdist)
            if (
                row.get("normalized_content_equal") is not True
                or row.get("normalized_members") != len(normalized)
                or row.get("normalized_content_sha256") != manifest_digest(normalized)
            ):
                raise RuntimeError(f"sdist normalized-content receipt mismatch: {sdist.name}")

        parity_rows = {norm_dist(r["distribution_name"]): r for r in parity_r.get("rows", [])}
        if set(parity_rows) != set(expected_dists):
            raise RuntimeError("sdist InstalledImage parity receipt inventory mismatch")
        for key, expected in expected_dists.items():
            row = parity_rows[key]
            if (
                row.get("match") is not True
                or row.get("distribution_version") != expected["distribution_version"]
                or row.get("installed_image_sha256") != expected["installed_image_sha256"]
                or row.get("expected_installed_image_sha256") != expected["installed_image_sha256"]
                or row.get("plugin_ids") != expected["plugin_ids"]
                or row.get("expected_plugin_ids") != expected["plugin_ids"]
            ):
                raise RuntimeError(f"sdist InstalledImage parity receipt mismatch: {key}")

    provenance = json.loads((root / "qcax-release-provenance.json").read_text(encoding="utf-8"))
    if provenance.get("release") != ns.tag or provenance.get("source_commit") != ns.commit:
        raise RuntimeError("provenance source identity mismatch")
    if provenance.get("repository") != os.environ.get("GITHUB_REPOSITORY", "qcax/qcax-fabric"):
        raise RuntimeError("provenance repository mismatch")
    if len(provenance.get("package_identities", [])) != 11:
        raise RuntimeError("provenance package identity count")
    component_rows = provenance.get("components", [])
    component_names = {r.get("name") for r in component_rows}
    expected_component_names = names - {
        "qcax-release-provenance.json", "sbom.spdx.json", "payload-manifest.json", "SHA256SUMS"
    }
    if len(component_rows) != 26 or len(component_names) != 26 or component_names != expected_component_names:
        raise RuntimeError("provenance component inventory mismatch")
    for row in component_rows:
        p = root / safe_member_name(row["name"])
        if p.stat().st_size != row.get("bytes") or sha256_file(p) != row.get("sha256"):
            raise RuntimeError(f"provenance component mismatch: {row['name']}")
    notes = (root / "RELEASE_NOTES-v0.1.0-alpha.1.md").read_text(encoding="utf-8")
    if "production readiness is not claimed" not in notes or "PyPI publication remains held" not in notes:
        raise RuntimeError("release notes claim-boundary text missing")

    print(json.dumps({"status": "PASS", "assets": 30, "wheels": 11, "sdists": 11, "release": ns.tag}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
