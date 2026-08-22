from __future__ import annotations

import json
import os
import re
import sys
import time

from release_provider import EXPECTED_TAG, ProviderError, get_release, repo_main_sha, resolve_tag_commit


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: wait_for_immutable_release.py TAG COMMIT")
    tag, commit = sys.argv[1], sys.argv[2]
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not repo:
        raise ProviderError("GITHUB_REPOSITORY is required")
    if tag != EXPECTED_TAG or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ProviderError("exact alpha1 tag and 40-hex commit required")

    last = None
    for index in range(60):
        release = get_release(repo, tag)
        tag_commit = resolve_tag_commit(repo, tag)
        last = {"release": release, "tag_commit": tag_commit}
        if tag_commit is not None and tag_commit != commit:
            raise ProviderError(f"protected tag points to wrong commit: {tag_commit} != {commit}")
        if release is not None:
            if release.get("tag_name") != tag:
                raise ProviderError("release tag identity mismatch")
            target = release.get("target_commitish")
            if isinstance(target, str) and re.fullmatch(r"[0-9a-f]{40}", target) and target != commit:
                raise ProviderError(f"release target mismatch: {target} != {commit}")
            if not release.get("draft") and release.get("immutable") and tag_commit == commit:
                print(json.dumps({
                    "status": "PASS",
                    "release": tag,
                    "source_commit": commit,
                    "release_id": release.get("id"),
                    "immutable": True,
                    "prerelease": bool(release.get("prerelease")),
                    "wait_iterations": index + 1,
                }, sort_keys=True))
                return 0
            if not release.get("draft") and not release.get("immutable"):
                raise ProviderError("release is published but not immutable")
        if index < 59:
            time.sleep(3)
    raise ProviderError(f"timed out waiting for immutable release: {last!r}")


if __name__ == "__main__":
    raise SystemExit(main())
