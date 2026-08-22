from __future__ import annotations

from pathlib import Path
import argparse
import json
import re
import time

from release_provider import (
    EXPECTED_ASSET_COUNT,
    EXPECTED_TAG,
    ProviderError,
    classify_provider_state,
    compare_asset_sets,
    create_draft,
    delete_draft_asset,
    get_release,
    get_release_assets,
    hydrate_unknown_asset_digests,
    local_assets,
    publish_draft,
    repo_main_sha,
    remote_asset_map,
    resolve_tag_commit,
    upload_asset,
)

TITLE = "QCAX Fabric v0.1.0-alpha.1"


def fresh_provider(repo: str, tag: str, expected_commit: str, local: dict):
    main_sha = repo_main_sha(repo)
    release = get_release(repo, tag)
    tag_commit = resolve_tag_commit(repo, tag)
    remote = get_release_assets(repo, release)
    if remote and any(not x.get("digest") for x in remote):
        remote = hydrate_unknown_asset_digests(repo, tag, remote)
    diff = compare_asset_sets(local, remote) if release is not None else None
    state = classify_provider_state(
        main_sha=main_sha,
        expected_commit=expected_commit,
        release=release,
        tag_commit=tag_commit,
        asset_diff=diff,
        tag=tag,
    )
    return main_sha, release, tag_commit, remote, diff, state


def require_publish_recoverable(state: str) -> None:
    if state.startswith("BLOCK_") or state == "HOLD_MAIN_MOVED":
        raise ProviderError(f"release provider state is blocked: {state}")


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
    local = local_assets(root)
    if len(local) != EXPECTED_ASSET_COUNT:
        raise ProviderError(f"expected {EXPECTED_ASSET_COUNT} local assets, got {len(local)}")
    notes = root / "RELEASE_NOTES-v0.1.0-alpha.1.md"
    if not notes.is_file():
        raise ProviderError("release notes asset missing")

    main_sha, release, tag_commit, remote, diff, state = fresh_provider(ns.repo, ns.tag, ns.commit, local)
    require_publish_recoverable(state)
    if state == "VERIFY_ONLY":
        print(json.dumps({
            "status": "PASS",
            "mode": "VERIFY_ONLY",
            "release": ns.tag,
            "source_commit": ns.commit,
            "release_id": release.get("id"),
            "immutable": True,
            "assets": len(remote),
        }, sort_keys=True))
        return 0

    if release is None:
        try:
            create_draft(ns.repo, ns.tag, ns.commit, notes, TITLE)
        except Exception:
            # Unknown mutation result: reconcile first, never blind retry.
            main_sha, release, tag_commit, remote, diff, state = fresh_provider(ns.repo, ns.tag, ns.commit, local)
            require_publish_recoverable(state)
            if release is None:
                # Provider says the create did not land. One retry after reconciliation is allowed.
                create_draft(ns.repo, ns.tag, ns.commit, notes, TITLE)
        main_sha, release, tag_commit, remote, diff, state = fresh_provider(ns.repo, ns.tag, ns.commit, local)
        require_publish_recoverable(state)
        if release is None or not release.get("draft"):
            if state == "VERIFY_ONLY":
                print(json.dumps({"status":"PASS","mode":"VERIFY_ONLY","release":ns.tag,"source_commit":ns.commit}, sort_keys=True))
                return 0
            raise ProviderError(f"draft creation did not produce exact draft: {state}")

    # Exact draft only from this point. Unexpected assets are not auto-deleted.
    main_sha, release, tag_commit, remote, diff, state = fresh_provider(ns.repo, ns.tag, ns.commit, local)
    require_publish_recoverable(state)
    if state == "VERIFY_ONLY":
        print(json.dumps({"status":"PASS","mode":"VERIFY_ONLY","release":ns.tag,"source_commit":ns.commit}, sort_keys=True))
        return 0
    if not release or not release.get("draft"):
        raise ProviderError(f"expected exact draft, got {state}")
    if diff and diff.unexpected:
        raise ProviderError(f"unexpected draft assets require explicit reconciliation: {diff.unexpected}")

    # Reconcile only missing/mismatched exact-name assets. A timeout is always followed by a GET.
    for name in sorted(local):
        main_sha, release, tag_commit, remote, diff, state = fresh_provider(ns.repo, ns.tag, ns.commit, local)
        require_publish_recoverable(state)
        if state == "VERIFY_ONLY":
            print(json.dumps({"status":"PASS","mode":"VERIFY_ONLY","release":ns.tag,"source_commit":ns.commit}, sort_keys=True))
            return 0
        if not release or not release.get("draft"):
            raise ProviderError(f"release stopped being a draft during asset reconciliation: {state}")
        if diff and diff.unexpected:
            raise ProviderError(f"unexpected draft assets: {diff.unexpected}")
        if diff and name in diff.exact:
            continue
        rmap = remote_asset_map(remote)
        if name in rmap:
            try:
                delete_draft_asset(ns.repo, release, rmap[name])
            except Exception:
                # Re-read. If the asset is gone, continue; if still present, retry deletion once.
                release2 = get_release(ns.repo, ns.tag)
                remote2 = get_release_assets(ns.repo, release2)
                rmap2 = remote_asset_map(remote2)
                if name in rmap2:
                    if not release2 or not release2.get("draft"):
                        raise
                    delete_draft_asset(ns.repo, release2, rmap2[name])
        try:
            upload_asset(ns.repo, ns.tag, local[name].path)
        except Exception:
            # Unknown upload result: accept exact post-state; retry only if absent/mismatched after GET.
            release2 = get_release(ns.repo, ns.tag)
            remote2 = get_release_assets(ns.repo, release2)
            if remote2 and any(not x.get("digest") for x in remote2):
                remote2 = hydrate_unknown_asset_digests(ns.repo, ns.tag, remote2)
            diff2 = compare_asset_sets(local, remote2)
            if name not in diff2.exact:
                rmap2 = remote_asset_map(remote2)
                if name in rmap2:
                    if not release2 or not release2.get("draft"):
                        raise ProviderError("cannot repair asset after draft became immutable/published")
                    delete_draft_asset(ns.repo, release2, rmap2[name])
                upload_asset(ns.repo, ns.tag, local[name].path)

    main_sha, release, tag_commit, remote, diff, state = fresh_provider(ns.repo, ns.tag, ns.commit, local)
    require_publish_recoverable(state)
    if state == "VERIFY_ONLY":
        print(json.dumps({"status":"PASS","mode":"VERIFY_ONLY","release":ns.tag,"source_commit":ns.commit}, sort_keys=True))
        return 0
    if state != "DRAFT_ASSETS_EXACT" or not diff or not diff.is_exact:
        raise ProviderError(f"draft payload is not exact before publish: state={state} diff={diff}")
    if repo_main_sha(ns.repo) != ns.commit:
        raise ProviderError("main moved after asset upload and before publish")
    if resolve_tag_commit(ns.repo, ns.tag) not in {None, ns.commit}:
        raise ProviderError("tag moved before publish")

    try:
        publish_draft(ns.repo, ns.tag)
    except Exception:
        # Unknown publish result: GET first.
        main_sha, release, tag_commit, remote, diff, state = fresh_provider(ns.repo, ns.tag, ns.commit, local)
        if state != "VERIFY_ONLY":
            if not release or not release.get("draft") or not diff or not diff.is_exact:
                raise ProviderError(f"publish failed into non-recoverable state: {state}")
            if repo_main_sha(ns.repo) != ns.commit:
                raise ProviderError("main moved before publish retry")
            publish_draft(ns.repo, ns.tag)

    # Immutable state can take a short time to surface. Never mutate after publication.
    last = None
    for _ in range(20):
        main_sha, release, tag_commit, remote, diff, state = fresh_provider(ns.repo, ns.tag, ns.commit, local)
        last = (release, tag_commit, diff, state)
        if state == "VERIFY_ONLY":
            if not release.get("prerelease"):
                raise ProviderError("published release is not marked prerelease")
            print(json.dumps({
                "status": "PASS",
                "mode": "PUBLISHED_ONCE",
                "release": ns.tag,
                "source_commit": ns.commit,
                "tag_commit": tag_commit,
                "release_id": release.get("id"),
                "release_url": release.get("html_url"),
                "immutable": True,
                "prerelease": True,
                "assets": len(remote),
            }, sort_keys=True))
            return 0
        if release is not None and not release.get("draft") and not release.get("immutable"):
            time.sleep(2)
            continue
        if state.startswith("BLOCK_"):
            raise ProviderError(f"post-publish state blocked: {state}")
        time.sleep(2)
    raise ProviderError(f"immutable post-state was not observed after publish: {last!r}")


if __name__ == "__main__":
    raise SystemExit(main())
