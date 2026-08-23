from pathlib import Path
import argparse, json, tempfile
from common import ReleaseError, require_commit
from provider import local_hashes, release_view, tag_commit, download_release_assets, verify_release_attestation, verify_release_asset
from verify_candidate import verify

def verify_release(root: Path, repo: str, tag: str, commit: str):
    root = Path(root); commit = require_commit(commit)
    verify(root)
    rel = release_view(repo, tag)
    if rel is None:
        raise ReleaseError("GitHub release absent")
    if rel.get("isDraft") is not False or rel.get("isImmutable") is not True:
        raise ReleaseError("GitHub release is not published immutable")
    if rel.get("tagName") != tag:
        raise ReleaseError("release tag mismatch")
    if tag_commit(repo, tag) != commit:
        raise ReleaseError("release tag commit mismatch")
    expected = local_hashes(root)
    with tempfile.TemporaryDirectory() as td:
        observed = download_release_assets(repo, tag, Path(td))
        if observed != expected:
            raise ReleaseError("downloaded immutable release asset set/hash mismatch")
    verified_release = verify_release_attestation(repo, tag)
    if not verified_release:
        raise ReleaseError("release attestation verification returned no result")
    for p in sorted(root.iterdir()):
        if p.is_file():
            out = verify_release_asset(repo, tag, p)
            if not out:
                raise ReleaseError("release asset attestation verification returned no result for " + p.name)
    return {"status": "PASS", "tag": tag, "commit": commit, "assets": len(expected), "immutable": True}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--commit", required=True)
    a = ap.parse_args()
    print(json.dumps(verify_release(Path(a.root), a.repo, a.tag, a.commit), sort_keys=True))
