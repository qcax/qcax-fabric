from pathlib import Path
import argparse, json, os
from common import ReleaseError, load_json, require_commit, require_sha256, sha256_file, write_json

def build_receipt(candidate: Path, comparison: Path, repository: str, run_id: str, run_attempt: str):
    candidate = Path(candidate); comparison = Path(comparison)
    comp = load_json(comparison)
    if comp.get("status") != "PASS":
        raise ReleaseError("replay comparison is not PASS")
    mf = load_json(candidate / "payload-manifest.json")
    if not str(run_id).isdigit() or not str(run_attempt).isdigit():
        raise ReleaseError("numeric replay workflow identity required")
    receipt = {
        "schema": "qcax.release-receipt/2",
        "stage": "replay",
        "repository": repository,
        "source_commit": require_commit(mf.get("source_commit")),
        "source_tree": require_commit(mf.get("source_tree")),
        "release_tag": mf.get("release_tag"),
        "package_set_digest": require_sha256(mf.get("package_set_digest_sha256")),
        "workflow": {"run_id": int(run_id), "run_attempt": int(run_attempt)},
        "artifact": {"replay_comparison_sha256": sha256_file(comparison)},
        "evidence": [{"kind": "class-aware-replay-equivalence", "status": "PASS", "assets": comp.get("assets")}],
        "overall_state": "REPLAY_PASS",
    }
    return receipt

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--comparison", required=True)
    ap.add_argument("--out", default="replay-receipt.json")
    a = ap.parse_args()
    repo = os.environ.get("GITHUB_REPOSITORY")
    run = os.environ.get("GITHUB_RUN_ID")
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    if not all((repo, run)):
        raise ReleaseError("GITHUB_REPOSITORY and GITHUB_RUN_ID required")
    receipt = build_receipt(Path(a.candidate), Path(a.comparison), repo, run, attempt)
    write_json(a.out, receipt)
    print(json.dumps({"status": "PASS", "out": a.out}, sort_keys=True))
