from __future__ import annotations

from pathlib import Path
import argparse
import json
import os
import platform
import shutil
import sys
import tempfile

from contract_conformance_lib import run_contract_conformance
from release_common import (
    EXPECTED_RELEASE,
    ROOT,
    deterministic_zip,
    json_bytes,
    package_identities,
    run,
    sha256_file,
)


def parse_json_stdout(text: str, label: str) -> dict:
    try:
        return json.loads(text.strip().splitlines()[-1])
    except Exception as exc:
        raise RuntimeError(f"{label}: expected JSON on final stdout line: {text!r}") from exc


def sanitize_sdist_receipt(receipt: dict) -> dict:
    rows = []
    for row in receipt["sdists"]:
        rows.append(
            {
                "distribution_name": row["distribution_name"],
                "distribution_version": row["distribution_version"],
                "sdist_filename": row["sdist_filename"],
                "normalized_content_equal": row["normalized_content_equal"],
                "normalized_content_sha256": row["normalized_content_sha256"],
                "normalized_members": row["normalized_members"],
            }
        )
    return {
        "status": receipt["status"],
        "builder": receipt["builder"],
        "distributions": receipt["distributions"],
        "normalized_content_twins": receipt["normalized_content_twins"],
        "sdists": sorted(rows, key=lambda x: x["distribution_name"]),
    }


def build_spec_bundle(out: Path, tag: str, commit: str) -> Path:
    schema_paths = sorted((ROOT / "spec").glob("*.schema.json"))
    if len(schema_paths) != 5:
        raise RuntimeError(f"expected exactly five public schemas, got {[p.name for p in schema_paths]}")
    records = [
        {"path": p.name, "bytes": p.stat().st_size, "sha256": sha256_file(p)}
        for p in schema_paths
    ]
    manifest = {
        "schema": "qcax.spec-bundle/1",
        "release": tag,
        "source_commit": commit,
        "files": records,
    }
    members = {p.name: p.read_bytes() for p in schema_paths}
    members["MANIFEST.json"] = json_bytes(manifest)
    target = out / "qcax-fabric-spec-v0.1.0-alpha.1.zip"
    deterministic_zip(target, members)
    return target


def build_conformance_bundle(
    out: Path,
    tag: str,
    commit: str,
    wheel_receipt: dict,
    sdist_receipt: dict,
    parity_receipt: dict,
) -> Path:
    contract = run_contract_conformance(ROOT)
    if contract.get("status") != "PASS":
        raise RuntimeError("contract conformance failed: " + json.dumps(contract, sort_keys=True))
    wheel_receipt = dict(wheel_receipt)
    wheel_receipt.pop("output_dir", None)
    sdist_receipt = sanitize_sdist_receipt(sdist_receipt)
    metadata = {
        "schema": "qcax.conformance-bundle/1",
        "release": tag,
        "source_commit": commit,
        "runner": "scripts/contract_conformance_lib.py + standard package release checks",
        "receipts": [
            "contract-conformance.json",
            "wheel-repro.json",
            "sdist-repro.json",
            "sdist-installed-image-parity.json",
        ],
    }
    members = {
        "metadata.json": json_bytes(metadata),
        "contract-conformance.json": json_bytes(contract),
        "wheel-repro.json": json_bytes(wheel_receipt),
        "sdist-repro.json": json_bytes(sdist_receipt),
        "sdist-installed-image-parity.json": json_bytes(parity_receipt),
    }
    target = out / "qcax-fabric-conformance-v0.1.0-alpha.1.zip"
    deterministic_zip(target, members)
    return target


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--tag", default=os.environ.get("QCAX_RELEASE_TAG", EXPECTED_RELEASE))
    ap.add_argument("--commit", default=os.environ.get("QCAX_EXPECTED_COMMIT", ""))
    ns = ap.parse_args()

    if ns.tag != EXPECTED_RELEASE:
        raise RuntimeError(f"unexpected release identity {ns.tag!r}")
    commit = ns.commit or run(["git", "rev-parse", "HEAD"], cwd=ROOT)
    if not re_full_sha(commit):
        raise RuntimeError(f"expected 40-hex commit, got {commit!r}")
    actual = run(["git", "rev-parse", "HEAD"], cwd=ROOT)
    if actual != commit:
        raise RuntimeError(f"checkout SHA {actual} != expected {commit}")
    source_tree = run(["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT)

    out = Path(ns.out).resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    with tempfile.TemporaryDirectory() as td_raw:
        td = Path(td_raw)
        wheel_dir = td / "wheels"
        sdist_dir = td / "sdists"

        wheel_receipt = parse_json_stdout(
            run([sys.executable, str(ROOT / "scripts/run_standard_build_repro.py"), str(wheel_dir)], cwd=ROOT),
            "wheel reproducibility",
        )
        if wheel_receipt.get("status") != "PASS" or wheel_receipt.get("distributions") != 11:
            raise RuntimeError("wheel reproducibility gate failed")

        lock_path = out / "release-lock.json"
        lock_receipt = parse_json_stdout(
            run(
                [
                    sys.executable,
                    str(ROOT / "scripts/generate_release_lock.py"),
                    str(wheel_dir),
                    str(lock_path),
                    ns.tag,
                ],
                cwd=ROOT,
            ),
            "release lock",
        )
        if lock_receipt.get("status") != "PASS" or lock_receipt.get("entries") != 11:
            raise RuntimeError("release-lock gate failed")

        sdist_receipt = parse_json_stdout(
            run([sys.executable, str(ROOT / "scripts/run_standard_sdist_repro.py"), str(sdist_dir)], cwd=ROOT),
            "sdist reproducibility",
        )
        if sdist_receipt.get("status") != "PASS" or sdist_receipt.get("distributions") != 11:
            raise RuntimeError("sdist gate failed")

        parity_receipt = parse_json_stdout(
            run(
                [
                    sys.executable,
                    str(ROOT / "scripts/verify_sdist_parity.py"),
                    str(sdist_dir),
                    str(lock_path),
                ],
                cwd=ROOT,
            ),
            "sdist installed-image parity",
        )
        if parity_receipt.get("status") != "PASS" or parity_receipt.get("matches") != 11:
            raise RuntimeError("sdist installed-image parity failed")

        wheels = sorted(wheel_dir.glob("*.whl"))
        sdists = sorted(sdist_dir.glob("*.tar.gz"))
        if len(wheels) != 11 or len(sdists) != 11:
            raise RuntimeError("package artifact count mismatch")
        for p in wheels + sdists:
            shutil.copy2(p, out / p.name)

        build_spec_bundle(out, ns.tag, commit)
        build_conformance_bundle(out, ns.tag, commit, wheel_receipt, sdist_receipt, parity_receipt)

    notes_src = ROOT / "release/RELEASE_NOTES-v0.1.0-alpha.1.md"
    notes_dst = out / notes_src.name
    shutil.copy2(notes_src, notes_dst)

    component_paths = sorted(
        [p for p in out.iterdir() if p.is_file() and p.name != "qcax-release-provenance.json"],
        key=lambda p: p.name,
    )
    provenance = {
        "schema": "qcax.release-provenance/1",
        "release": ns.tag,
        "repository": os.environ.get("GITHUB_REPOSITORY", "qcax/qcax-fabric"),
        "source_commit": commit,
        "source_tree": source_tree,
        "event": os.environ.get("GITHUB_EVENT_NAME", "local"),
        "workflow": os.environ.get("GITHUB_WORKFLOW", "local"),
        "run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", ""),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "package_identities": package_identities(),
        "components": [
            {"name": p.name, "bytes": p.stat().st_size, "sha256": sha256_file(p)}
            for p in component_paths
        ],
    }
    (out / "qcax-release-provenance.json").write_bytes(json_bytes(provenance))

    count = len([p for p in out.iterdir() if p.is_file()])
    if count != 27:
        raise RuntimeError(f"expected 27 pre-SBOM primary files, got {count}: {sorted(p.name for p in out.iterdir())}")
    print(
        json.dumps(
            {
                "status": "PASS",
                "release": ns.tag,
                "source_commit": commit,
                "source_tree": source_tree,
                "files": count,
                "wheels": 11,
                "sdists": 11,
            },
            sort_keys=True,
        )
    )
    return 0


def re_full_sha(value: str) -> bool:
    import re
    return bool(re.fullmatch(r"[0-9a-f]{40}", value))


if __name__ == "__main__":
    raise SystemExit(main())
