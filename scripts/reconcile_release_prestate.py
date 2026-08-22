from __future__ import annotations

from pathlib import Path
import argparse
import json
import re
import shutil

from release_provider import (
    EXPECTED_ASSET_COUNT,
    EXPECTED_TAG,
    ProviderError,
    classify_provider_state,
    compare_asset_sets,
    get_release,
    get_release_assets,
    hydrate_unknown_asset_digests,
    local_assets,
    repo_main_sha,
    resolve_tag_commit,
    run_gh,
)


def run_metadata(repo: str, run_id: str) -> dict:
    if not re.fullmatch(r"[0-9]+", run_id):
        raise ProviderError(f"invalid preflight run id {run_id!r}")
    proc = run_gh([
        "run", "view", run_id, "-R", repo,
        "--json", "status,conclusion,headSha,event,workflowName,attempt,databaseId,url"
    ])
    try:
        return json.loads(proc.stdout)
    except Exception as exc:
        raise ProviderError(f"invalid workflow-run JSON: {proc.stdout!r}") from exc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--download", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--tag", default=EXPECTED_TAG)
    ap.add_argument("--commit", required=True)
    ap.add_argument("--run-id", required=True)
    ns = ap.parse_args()

    if ns.tag != EXPECTED_TAG:
        raise ProviderError(f"unexpected release tag {ns.tag!r}")
    if not re.fullmatch(r"[0-9a-f]{40}", ns.commit):
        raise ProviderError("exact 40-hex commit required")

    main_sha = repo_main_sha(ns.repo)
    if main_sha != ns.commit:
        raise ProviderError(f"main moved before publish: {main_sha} != {ns.commit}")

    meta = run_metadata(ns.repo, ns.run_id)
    if meta.get("status") != "completed" or meta.get("conclusion") != "success":
        raise ProviderError(f"preflight run is not a completed success: {meta!r}")
    if meta.get("headSha") != ns.commit:
        raise ProviderError(f"preflight head SHA mismatch: {meta.get('headSha')} != {ns.commit}")
    if meta.get("event") != "workflow_dispatch":
        raise ProviderError(f"preflight event mismatch: {meta.get('event')!r}")
    if meta.get("workflowName") != "release-build":
        raise ProviderError(f"preflight workflow mismatch: {meta.get('workflowName')!r}")

    target = Path(ns.download).resolve()
    if target.exists():
        if any(target.iterdir()):
            raise ProviderError(f"download target must be empty: {target}")
        shutil.rmtree(target)
    target.mkdir(parents=True)
    artifact_name = "release-candidate-v0.1.0-alpha.1"
    try:
        run_gh([
            "run", "download", ns.run_id, "-R", ns.repo,
            "-n", artifact_name, "-D", str(target)
        ], timeout=240)
    except Exception:
        # Unknown result is reconciled by inspecting the local post-state, never blind retry.
        if not target.exists() or len([p for p in target.iterdir() if p.is_file()]) != EXPECTED_ASSET_COUNT:
            raise

    local = local_assets(target)
    if len(local) != EXPECTED_ASSET_COUNT:
        raise ProviderError(f"preflight artifact must contain exactly {EXPECTED_ASSET_COUNT} files, got {len(local)}")
    if "payload-manifest.json" not in local or "SHA256SUMS" not in local:
        raise ProviderError("preflight artifact is missing release control files")

    release = get_release(ns.repo, ns.tag)
    tag_commit = resolve_tag_commit(ns.repo, ns.tag)
    remote = get_release_assets(ns.repo, release)
    if remote and any(not x.get("digest") for x in remote):
        remote = hydrate_unknown_asset_digests(ns.repo, ns.tag, remote)
    diff = compare_asset_sets(local, remote) if release is not None else None
    state = classify_provider_state(
        main_sha=main_sha,
        expected_commit=ns.commit,
        release=release,
        tag_commit=tag_commit,
        asset_diff=diff,
        tag=ns.tag,
    )
    if state.startswith("BLOCK_") or state == "HOLD_MAIN_MOVED":
        raise ProviderError(f"provider prestate is not publish-recoverable: {state}")

    print(json.dumps({
        "status": "PASS",
        "preflight_run_id": int(ns.run_id),
        "preflight_attempt": meta.get("attempt"),
        "preflight_url": meta.get("url"),
        "source_commit": ns.commit,
        "downloaded_assets": len(local),
        "provider_state": state,
        "tag_commit": tag_commit,
        "release_id": release.get("id") if release else None,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
