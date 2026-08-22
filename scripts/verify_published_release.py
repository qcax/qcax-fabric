from __future__ import annotations

from pathlib import Path
import argparse
import json
import re
import subprocess
import sys
import tempfile

from release_provider import (
    EXPECTED_ASSET_COUNT,
    EXPECTED_TAG,
    ProviderError,
    compare_asset_sets,
    download_all_release_assets,
    get_release,
    get_release_assets,
    hydrate_unknown_asset_digests,
    local_assets,
    resolve_tag_commit,
    run_gh,
)

ROOT = Path(__file__).resolve().parents[1]


def run_python(script: str, args: list[str]) -> dict:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), *args],
        cwd="/",
        text=True,
        capture_output=True,
        env=__import__("os").environ.copy(),
    )
    if proc.returncode:
        raise ProviderError(f"{script} failed\n{proc.stdout}\n{proc.stderr}")
    line = proc.stdout.strip().splitlines()[-1]
    try:
        return json.loads(line)
    except Exception as exc:
        raise ProviderError(f"{script} did not return JSON: {proc.stdout!r}") from exc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("directory")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--tag", default=EXPECTED_TAG)
    ap.add_argument("--commit", required=True)
    ns = ap.parse_args()
    if ns.tag != EXPECTED_TAG or not re.fullmatch(r"[0-9a-f]{40}", ns.commit):
        raise ProviderError("exact alpha1 tag and 40-hex commit required")

    local = local_assets(Path(ns.directory).resolve())
    if len(local) != EXPECTED_ASSET_COUNT:
        raise ProviderError(f"expected {EXPECTED_ASSET_COUNT} local assets, got {len(local)}")
    release = get_release(ns.repo, ns.tag)
    tag_commit = resolve_tag_commit(ns.repo, ns.tag)
    if not release or release.get("draft") or not release.get("immutable"):
        raise ProviderError(f"release is not published immutable: {release!r}")
    if not release.get("prerelease"):
        raise ProviderError("release is not a prerelease")
    if tag_commit != ns.commit:
        raise ProviderError(f"tag commit mismatch: {tag_commit} != {ns.commit}")
    remote = get_release_assets(ns.repo, release)
    if any(not x.get("digest") for x in remote):
        remote = hydrate_unknown_asset_digests(ns.repo, ns.tag, remote)
    diff = compare_asset_sets(local, remote)
    if not diff.is_exact:
        raise ProviderError(f"published asset metadata mismatch: {diff}")

    release_verify = run_gh(["release", "verify", ns.tag, "-R", ns.repo, "--format", "json"], timeout=180)
    try:
        release_attestation = json.loads(release_verify.stdout)
    except Exception as exc:
        raise ProviderError("release verify did not return JSON") from exc
    if not release_attestation:
        raise ProviderError("release attestation verification returned no result")

    verified_assets = 0
    for item in local.values():
        proc = run_gh([
            "release", "verify-asset", ns.tag, str(item.path), "-R", ns.repo, "--format", "json"
        ], timeout=180)
        try:
            data = json.loads(proc.stdout)
        except Exception as exc:
            raise ProviderError(f"release asset verification did not return JSON for {item.name}") from exc
        if not data:
            raise ProviderError(f"release asset attestation verification empty for {item.name}")
        verified_assets += 1

    with tempfile.TemporaryDirectory() as td:
        downloaded = Path(td) / "published-assets"
        download_all_release_assets(ns.repo, ns.tag, downloaded)
        fresh = local_assets(downloaded)
        if len(fresh) != EXPECTED_ASSET_COUNT:
            raise ProviderError(f"published download count mismatch: {len(fresh)}")
        for name, item in local.items():
            other = fresh.get(name)
            if other is None or other.bytes != item.bytes or other.sha256 != item.sha256:
                raise ProviderError(f"downloaded release asset mismatch: {name}")
        payload = run_python("verify_release_payload.py", [str(downloaded), "--tag", ns.tag, "--commit", ns.commit])
        canary = run_python("run_secure_installed_canary.py", [str(downloaded)])
        oot = run_python("run_out_of_tree_canary.py", [str(downloaded)])
        if payload.get("status") != "PASS" or canary.get("status") != "PASS" or oot.get("status") != "PASS":
            raise ProviderError("clean downloaded-release verification failed")

    print(json.dumps({
        "status": "PASS",
        "release": ns.tag,
        "source_commit": ns.commit,
        "immutable": True,
        "prerelease": True,
        "release_attestation_verified": True,
        "release_assets_verified": verified_assets,
        "clean_downloaded_assets": EXPECTED_ASSET_COUNT,
        "payload_verify": "PASS",
        "secure_canary": "PASS",
        "out_of_tree_canary": "PASS",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
