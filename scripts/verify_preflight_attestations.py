from __future__ import annotations

from pathlib import Path
import argparse
import json
import re

from release_provider import EXPECTED_ASSET_COUNT, EXPECTED_TAG, ProviderError, local_assets, run_gh

PROVENANCE = "https://slsa.dev/provenance/v1"
SPDX = "https://spdx.dev/Document/v2.3"


def verify_one(path: Path, *, repo: str, commit: str, predicate: str) -> list[dict]:
    args = [
        "attestation", "verify", str(path),
        "--repo", repo,
        "--signer-workflow", f"{repo}/.github/workflows/release-build.yml",
        "--source-digest", commit,
        "--source-ref", "refs/heads/main",
        "--predicate-type", predicate,
        "--format", "json",
        "--deny-self-hosted-runners",
    ]
    proc = run_gh(args, timeout=180)
    try:
        data = json.loads(proc.stdout)
    except Exception as exc:
        raise ProviderError(f"attestation verification did not return JSON for {path.name}: {proc.stdout!r}") from exc
    if not isinstance(data, list) or not data:
        raise ProviderError(f"no verified {predicate} attestation for {path.name}")
    digest = __import__("hashlib").sha256(path.read_bytes()).hexdigest()
    matched = False
    for row in data:
        statement = (((row or {}).get("verificationResult") or {}).get("statement") or {})
        if statement.get("predicateType") != predicate:
            continue
        for subject in statement.get("subject", []):
            d = (subject.get("digest") or {}).get("sha256")
            if d == digest:
                matched = True
                break
    if not matched:
        raise ProviderError(f"verified attestation output did not bind exact digest for {path.name}")
    return data


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("directory")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--tag", default=EXPECTED_TAG)
    ap.add_argument("--commit", required=True)
    ns = ap.parse_args()
    if ns.tag != EXPECTED_TAG or not re.fullmatch(r"[0-9a-f]{40}", ns.commit):
        raise ProviderError("exact alpha1 tag and 40-hex commit required")

    root = Path(ns.directory).resolve()
    assets = local_assets(root)
    if len(assets) != EXPECTED_ASSET_COUNT:
        raise ProviderError(f"expected {EXPECTED_ASSET_COUNT} assets, got {len(assets)}")
    wheels = [x for x in assets.values() if x.name.endswith(".whl")]
    if len(wheels) != 11:
        raise ProviderError(f"expected 11 wheels, got {len(wheels)}")

    provenance_verified = 0
    for item in assets.values():
        verify_one(item.path, repo=ns.repo, commit=ns.commit, predicate=PROVENANCE)
        provenance_verified += 1
    sbom_verified = 0
    for item in wheels:
        verify_one(item.path, repo=ns.repo, commit=ns.commit, predicate=SPDX)
        sbom_verified += 1

    receipt = {
        "schema": "qcax.preflight-attestation-receipt/1",
        "status": "PASS",
        "release": ns.tag,
        "repository": ns.repo,
        "source_commit": ns.commit,
        "source_ref": "refs/heads/main",
        "signer_workflow": f"{ns.repo}/.github/workflows/release-build.yml",
        "provenance_subjects_verified": provenance_verified,
        "sbom_wheel_subjects_verified": sbom_verified,
        "provenance_predicate": PROVENANCE,
        "sbom_predicate": SPDX,
    }
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
