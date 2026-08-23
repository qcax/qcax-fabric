from pathlib import Path
import argparse, json, os
from common import ReleaseError, load_json, require_commit, require_sha256, sha256_file, write_json
from verify_candidate import verify

def build_receipt(candidate: Path, artifact_id: str, artifact_digest: str, repository: str, run_id: str, run_attempt: str):
    candidate = Path(candidate)
    if not str(artifact_id).isdigit():
        raise ReleaseError("numeric artifact id required")
    digest = require_sha256(artifact_digest)
    if not str(run_id).isdigit() or not str(run_attempt).isdigit():
        raise ReleaseError("numeric workflow run identity required")
    verify(candidate)
    mf = load_json(candidate / "payload-manifest.json")
    source_commit = require_commit(mf.get("source_commit"))
    source_tree = require_commit(mf.get("source_tree"))
    receipt = {
        "schema": "qcax.release-receipt/2",
        "stage": "preflight",
        "repository": repository,
        "source_commit": source_commit,
        "source_tree": source_tree,
        "release_tag": mf.get("release_tag"),
        "package_set_digest": require_sha256(mf.get("package_set_digest_sha256")),
        "artifact": {
            "candidate_artifact_id": int(artifact_id),
            "candidate_artifact_digest": "sha256:" + digest,
            "payload_manifest_sha256": sha256_file(candidate / "payload-manifest.json"),
        },
        "workflow": {"run_id": int(run_id), "run_attempt": int(run_attempt)},
        "evidence": [
            {"kind": "candidate-verification", "status": "PASS"},
            {"kind": "container-identity", "status": "BOUND_AFTER_UPLOAD"},
        ],
    }
    return receipt

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    aid = os.environ.get("ARTIFACT_ID")
    adig = os.environ.get("ARTIFACT_DIGEST")
    repo = os.environ.get("GITHUB_REPOSITORY")
    run = os.environ.get("GITHUB_RUN_ID")
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    if not all((aid, adig, repo, run)):
        raise ReleaseError("ARTIFACT_ID, ARTIFACT_DIGEST, GITHUB_REPOSITORY and GITHUB_RUN_ID required")
    receipt = build_receipt(Path(a.candidate), aid, adig, repo, run, attempt)
    write_json(a.out, receipt)
    print(json.dumps({"status": "PASS", "artifact_id": int(aid), "out": a.out}, sort_keys=True))
