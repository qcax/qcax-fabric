from pathlib import Path
import json, os, subprocess
from common import ReleaseError, load_json, require_commit
from provider import release_view, tag_commit

ROOT = Path(__file__).resolve().parents[2]

def classify_event(event, expected_tag):
    rel = event.get("release") or {}
    errors = []
    if event.get("action") != "published":
        errors.append("release event action is not published")
    if rel.get("tag_name") != expected_tag:
        errors.append("event release tag mismatch")
    if rel.get("draft") is not False:
        errors.append("event release is draft")
    return errors

def main():
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    repo = os.environ.get("GITHUB_REPOSITORY")
    sha = os.environ.get("GITHUB_SHA")
    if not event_path or not repo or not sha:
        raise ReleaseError("release event environment incomplete")
    sha = require_commit(sha)
    event = load_json(event_path)
    contract = load_json(ROOT / "release/policy/release-contract.json")
    ident = contract.get("release_identity") or {}
    if ident.get("status") != "ACTIVE":
        raise ReleaseError("release identity not ACTIVE")
    tag = ident.get("selected_tag")
    errors = classify_event(event, tag)
    if errors:
        raise ReleaseError("; ".join(errors))
    rel = release_view(repo, tag)
    if rel is None or rel.get("isDraft") is not False or rel.get("isImmutable") is not True:
        raise ReleaseError("provider release readback is not published immutable")
    if tag_commit(repo, tag) != sha:
        raise ReleaseError("provider tag commit differs from release-event SHA")
    p = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT), capture_output=True, text=True, timeout=30)
    if p.returncode or p.stdout.strip() != sha:
        raise ReleaseError("checked-out tag commit differs from release-event SHA")
    print(json.dumps({"status": "PASS", "repository": repo, "tag": tag, "commit": sha, "immutable": True}, sort_keys=True))

if __name__ == "__main__":
    main()
