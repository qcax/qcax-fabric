from pathlib import Path
import argparse, json
from common import ReleaseError, require_commit
from provider import local_hashes, release_snapshot, run_mutation
from verify_candidate import verify

def classify_release(snapshot, expected_commit, expected_hashes):
    rel = snapshot.get("release")
    tag_commit = snapshot.get("tag_commit")
    observed = snapshot.get("asset_hashes") or {}
    if rel is None:
        if tag_commit is not None:
            return {"state": "BLOCK_PROVIDER_MISMATCH", "reason": "tag exists without exact release", "missing": [], "mismatch": [], "unexpected": []}
        return {"state": "NO_RELEASE", "missing": sorted(expected_hashes), "mismatch": [], "unexpected": []}
    if rel.get("isDraft"):
        if tag_commit is not None:
            return {"state": "BLOCK_PROVIDER_MISMATCH", "reason": "tag exists while release is draft", "missing": [], "mismatch": [], "unexpected": []}
        if rel.get("targetCommitish") != expected_commit:
            return {"state": "BLOCK_PROVIDER_MISMATCH", "reason": "draft target mismatch", "missing": [], "mismatch": [], "unexpected": []}
    else:
        if tag_commit != expected_commit:
            return {"state": "BLOCK_PROVIDER_MISMATCH", "reason": "published tag commit mismatch", "missing": [], "mismatch": [], "unexpected": []}
        if rel.get("isImmutable") is not True:
            return {"state": "BLOCK_PROVIDER_MISMATCH", "reason": "published release is not immutable", "missing": [], "mismatch": [], "unexpected": []}
    unexpected = sorted(set(observed) - set(expected_hashes))
    missing = sorted(set(expected_hashes) - set(observed))
    mismatch = sorted(n for n in set(expected_hashes) & set(observed) if expected_hashes[n] != observed[n])
    if unexpected:
        return {"state": "BLOCK_ARTIFACT_SET", "missing": missing, "mismatch": mismatch, "unexpected": unexpected}
    if rel.get("isDraft"):
        if missing or mismatch:
            return {"state": "DRAFT_RECONCILE", "missing": missing, "mismatch": mismatch, "unexpected": []}
        return {"state": "DRAFT_EXACT", "missing": [], "mismatch": [], "unexpected": []}
    if missing or mismatch:
        return {"state": "BLOCK_PROVIDER_MISMATCH", "reason": "immutable release assets differ", "missing": missing, "mismatch": mismatch, "unexpected": []}
    return {"state": "PUBLISHED_EXACT", "missing": [], "mismatch": [], "unexpected": []}

def publish(root: Path, repo: str, tag: str, commit: str):
    root = Path(root); commit = require_commit(commit)
    verify(root)
    expected = local_hashes(root)

    def reread():
        snap = release_snapshot(repo, tag, expected_names=set(expected))
        return {"snapshot": snap, "classification": classify_release(snap, commit, expected)}

    state = reread()
    c = state["classification"]
    if c["state"] == "NO_RELEASE":
        notes = root / "RELEASE_NOTES.md"
        cmd = ["gh", "release", "create", tag, "--repo", repo, "--draft", "--prerelease", "--target", commit, "--title", tag]
        if notes.is_file():
            cmd += ["--notes-file", str(notes)]
        mutation = run_mutation(cmd)
        state = reread()
        c = state["classification"]
        if c["state"] not in {"DRAFT_RECONCILE", "DRAFT_EXACT"}:
            raise ReleaseError("draft creation did not reconcile: " + json.dumps({"mutation": mutation, "classification": c}, sort_keys=True))
    if c["state"] == "PUBLISHED_EXACT":
        return {"status": "PASS", "state": "PUBLISHED_EXACT_NO_MUTATION", "assets": len(expected)}
    if c["state"].startswith("BLOCK_"):
        raise ReleaseError("provider release state blocked: " + json.dumps(c, sort_keys=True))
    if c["state"] not in {"DRAFT_RECONCILE", "DRAFT_EXACT"}:
        raise ReleaseError("unexpected provider state " + c["state"])

    for name in list(c.get("mismatch") or []):
        mutation = run_mutation(["gh", "release", "delete-asset", tag, name, "--repo", repo, "--yes"])
        state = reread()
        c2 = state["classification"]
        if name not in c2.get("missing", []):
            raise ReleaseError("draft asset deletion did not reconcile: " + json.dumps({"name": name, "mutation": mutation, "classification": c2}, sort_keys=True))
        c = c2

    for name in sorted(set(c.get("missing") or [])):
        mutation = run_mutation(["gh", "release", "upload", tag, str(root / name), "--repo", repo])
        state = reread()
        c2 = state["classification"]
        if name in c2.get("missing", []) or name in c2.get("mismatch", []):
            raise ReleaseError("draft asset upload did not reconcile: " + json.dumps({"name": name, "mutation": mutation, "classification": c2}, sort_keys=True))
        c = c2
    if c["state"] != "DRAFT_EXACT":
        state = reread(); c = state["classification"]
    if c["state"] != "DRAFT_EXACT":
        raise ReleaseError("draft never reached exact asset state: " + json.dumps(c, sort_keys=True))

    mutation = run_mutation(["gh", "release", "edit", tag, "--repo", repo, "--draft=false", "--prerelease"])
    state = reread(); c = state["classification"]
    if c["state"] != "PUBLISHED_EXACT":
        raise ReleaseError("publish did not reconcile to immutable exact release: " + json.dumps({"mutation": mutation, "classification": c}, sort_keys=True))
    return {"status": "PASS", "state": "PUBLISHED_EXACT", "assets": len(expected)}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--commit", required=True)
    a = ap.parse_args()
    print(json.dumps(publish(Path(a.root), a.repo, a.tag, a.commit), sort_keys=True))
