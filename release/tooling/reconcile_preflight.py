from pathlib import Path
import argparse, json, shutil, tempfile
from common import ReleaseError, load_json, require_commit, require_sha256, sha256_file
from provider import artifact, download_run_artifact, run_artifacts, workflow_run
from verify_candidate import verify

def classify_preflight(run, candidate_artifact, receipt, expected):
    errors = []
    if run.get("status") != "completed" or run.get("conclusion") != "success":
        errors.append("preflight run not successful")
    if run.get("head_sha") != expected["commit"]:
        errors.append("preflight head SHA mismatch")
    if run.get("event") != "workflow_dispatch":
        errors.append("preflight event mismatch")
    if candidate_artifact.get("id") != int(expected["artifact_id"]):
        errors.append("candidate artifact id mismatch")
    if candidate_artifact.get("expired") is True:
        errors.append("candidate artifact expired")
    if candidate_artifact.get("digest") != "sha256:" + expected["artifact_digest"]:
        errors.append("candidate artifact digest mismatch")
    wr = candidate_artifact.get("workflow_run") or {}
    if wr.get("id") != int(expected["run_id"]):
        errors.append("candidate artifact run binding mismatch")
    if receipt.get("stage") != "preflight":
        errors.append("receipt stage mismatch")
    if receipt.get("repository") != expected["repo"]:
        errors.append("receipt repository mismatch")
    if receipt.get("source_commit") != expected["commit"]:
        errors.append("receipt commit mismatch")
    if receipt.get("release_tag") != expected["tag"]:
        errors.append("receipt tag mismatch")
    art = receipt.get("artifact") or {}
    if art.get("candidate_artifact_id") != int(expected["artifact_id"]):
        errors.append("receipt artifact id mismatch")
    if art.get("candidate_artifact_digest") != "sha256:" + expected["artifact_digest"]:
        errors.append("receipt artifact digest mismatch")
    return {"status": "PASS" if not errors else "FAIL", "errors": errors}

def reconcile(repo, run_id, artifact_id, artifact_digest, receipt_name, commit, tag, download):
    commit = require_commit(commit)
    digest = require_sha256(artifact_digest)
    run = workflow_run(repo, run_id)
    ca = artifact(repo, artifact_id)
    arts = run_artifacts(repo, run_id)
    receipt_rows = [x for x in arts if x.get("name") == receipt_name]
    if len(receipt_rows) != 1 or receipt_rows[0].get("expired") is True:
        raise ReleaseError("exact live preflight receipt artifact required")
    if ca.get("name") != f"qcax-release-candidate-{tag}":
        raise ReleaseError("candidate artifact name mismatch")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        receipt_dir = td / "receipt"
        download_run_artifact(repo, run_id, receipt_name, receipt_dir)
        files = [p for p in receipt_dir.rglob("*") if p.is_file()]
        if len(files) != 1 or files[0].name != "preflight-receipt.json":
            raise ReleaseError("receipt artifact content mismatch")
        receipt = load_json(files[0])
        expected = {"repo": repo, "run_id": str(run_id), "artifact_id": str(artifact_id), "artifact_digest": digest, "commit": commit, "tag": tag}
        verdict = classify_preflight(run, ca, receipt, expected)
        if verdict["status"] != "PASS":
            raise ReleaseError("preflight reconciliation failed: " + "; ".join(verdict["errors"]))
        out = Path(download)
        if out.exists():
            shutil.rmtree(out)
        download_run_artifact(repo, run_id, ca["name"], out)
        verify(out)
        mf = load_json(out / "payload-manifest.json")
        if mf.get("source_commit") != commit or mf.get("release_tag") != tag:
            raise ReleaseError("downloaded candidate source/tag mismatch")
        if (receipt.get("artifact") or {}).get("payload_manifest_sha256") != sha256_file(out / "payload-manifest.json"):
            raise ReleaseError("receipt payload-manifest binding mismatch")
    return {"status": "PASS", "run_id": int(run_id), "artifact_id": int(artifact_id), "download": str(download)}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--artifact-id", required=True)
    ap.add_argument("--artifact-digest", required=True)
    ap.add_argument("--receipt-artifact-name", required=True)
    ap.add_argument("--commit", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--download", required=True)
    ap.add_argument("--repo", default=__import__("os").environ.get("GITHUB_REPOSITORY"))
    a = ap.parse_args()
    if not a.repo:
        raise ReleaseError("repository required")
    print(json.dumps(reconcile(a.repo, a.run_id, a.artifact_id, a.artifact_digest, a.receipt_artifact_name, a.commit, a.tag, a.download), sort_keys=True))
