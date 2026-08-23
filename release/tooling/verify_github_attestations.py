from pathlib import Path
import argparse, json, os
from common import ReleaseError
from provider import require_repo, verify_attestation
from verify_candidate import verify

PROVENANCE = "https://slsa.dev/provenance/v1"
SPDX = "https://spdx.dev/Document/v2.3"

def verify_attestations(root: Path, repo: str):
    root = Path(root); repo = require_repo(repo)
    verify(root)
    signer = f"{repo}/.github/workflows/release-preflight.yml"
    rows = []
    files = sorted(p for p in root.iterdir() if p.is_file())
    for p in files:
        out = verify_attestation(p, repo, predicate_type=PROVENANCE, signer_workflow=signer, source_ref="refs/heads/main")
        if not out:
            raise ReleaseError("missing verified provenance attestation for " + p.name)
        rows.append({"name": p.name, "provenance": "PASS"})
        if p.suffix == ".whl":
            sb = verify_attestation(p, repo, predicate_type=SPDX, signer_workflow=signer, source_ref="refs/heads/main")
            if not sb:
                raise ReleaseError("missing verified SPDX SBOM attestation for " + p.name)
            rows[-1]["sbom"] = "PASS"
    return {"status": "PASS", "assets": len(files), "wheel_sbom_attestations": sum(1 for r in rows if r.get("sbom") == "PASS"), "rows": rows}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"))
    a = ap.parse_args()
    if not a.repo:
        raise ReleaseError("repository required")
    print(json.dumps(verify_attestations(Path(a.root), a.repo), sort_keys=True))
