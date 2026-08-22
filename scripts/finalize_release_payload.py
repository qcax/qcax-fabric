from __future__ import annotations

from pathlib import Path
import argparse
import json
import os

from release_common import EXPECTED_RELEASE, json_bytes, sha256_file

PRIMARY_CONTROL = {
    "release-lock.json",
    "sbom.spdx.json",
    "qcax-fabric-spec-v0.1.0-alpha.1.zip",
    "qcax-fabric-conformance-v0.1.0-alpha.1.zip",
    "RELEASE_NOTES-v0.1.0-alpha.1.md",
    "qcax-release-provenance.json",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("directory")
    ap.add_argument("--tag", default=os.environ.get("QCAX_RELEASE_TAG", EXPECTED_RELEASE))
    ap.add_argument("--commit", default=os.environ.get("QCAX_EXPECTED_COMMIT", ""))
    ns = ap.parse_args()
    root = Path(ns.directory).resolve()
    if ns.tag != EXPECTED_RELEASE:
        raise RuntimeError("unexpected release tag")
    if not ns.commit or len(ns.commit) != 40:
        raise RuntimeError("exact source commit required")

    wheels = sorted(root.glob("*.whl"))
    sdists = sorted(root.glob("*.tar.gz"))
    controls = {p.name for p in root.iterdir() if p.is_file()} - {p.name for p in wheels + sdists}
    if len(wheels) != 11 or len(sdists) != 11 or controls != PRIMARY_CONTROL:
        raise RuntimeError(
            f"pre-finalization inventory mismatch: wheels={len(wheels)} sdists={len(sdists)} controls={sorted(controls)}"
        )

    primary = sorted(wheels + sdists + [root / x for x in PRIMARY_CONTROL], key=lambda p: p.name)
    if len(primary) != 28:
        raise RuntimeError(f"expected 28 primary assets, got {len(primary)}")

    manifest = {
        "schema": "qcax.release-payload-manifest/1",
        "release": ns.tag,
        "source_commit": ns.commit,
        "assets": [
            {"name": p.name, "bytes": p.stat().st_size, "sha256": sha256_file(p)}
            for p in primary
        ],
    }
    manifest_path = root / "payload-manifest.json"
    manifest_path.write_bytes(json_bytes(manifest))

    checksummed = sorted(primary + [manifest_path], key=lambda p: p.name)
    sums = "".join(f"{sha256_file(p)}  {p.name}\n" for p in checksummed)
    (root / "SHA256SUMS").write_text(sums, encoding="utf-8")

    files = sorted(p for p in root.iterdir() if p.is_file())
    if len(files) != 30:
        raise RuntimeError(f"expected 30 uploaded assets, got {len(files)}")
    print(json.dumps({"status": "PASS", "assets": 30, "primary": 28, "release": ns.tag}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
