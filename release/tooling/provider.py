from __future__ import annotations
from pathlib import Path
import json, os, subprocess, tempfile, urllib.parse
from common import ReleaseError, sha256_file

REPO_RE = __import__("re").compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
TAG_RE = __import__("re").compile(r"^[A-Za-z0-9._-]+$")

def require_repo(repo: str) -> str:
    if not isinstance(repo, str) or not REPO_RE.fullmatch(repo):
        raise ReleaseError("repository must be owner/name")
    return repo

def require_tag(tag: str) -> str:
    if not isinstance(tag, str) or not TAG_RE.fullmatch(tag):
        raise ReleaseError("unsafe release tag")
    return tag

def run_checked(argv, *, cwd=None, env=None, timeout=120, json_output=False):
    p = subprocess.run(
        list(map(str, argv)),
        cwd=None if cwd is None else str(cwd),
        env={**os.environ, **(env or {})},
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if p.returncode:
        raise ReleaseError("command failed: " + " ".join(map(str, argv)) + " :: " + p.stderr.strip()[-1200:])
    if json_output:
        try:
            return json.loads(p.stdout)
        except Exception as exc:
            raise ReleaseError("invalid JSON from command: " + " ".join(map(str, argv))) from exc
    return p.stdout

def run_mutation(argv, *, cwd=None, env=None, timeout=120):
    try:
        p = subprocess.run(
            list(map(str, argv)),
            cwd=None if cwd is None else str(cwd),
            env={**os.environ, **(env or {})},
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "returncode": p.returncode,
            "stdout": p.stdout,
            "stderr": p.stderr,
            "error": None if p.returncode == 0 else p.stderr.strip()[-1200:],
        }
    except Exception as exc:
        return {"returncode": None, "stdout": "", "stderr": "", "error": f"{type(exc).__name__}: {exc}"}

def gh_json(args, *, timeout=120):
    return run_checked(["gh", *args], timeout=timeout, json_output=True)

def gh_text(args, *, timeout=120):
    return run_checked(["gh", *args], timeout=timeout)

def release_list(repo: str):
    require_repo(repo)
    return gh_json([
        "release", "list", "--repo", repo, "--limit", "100",
        "--json", "tagName,isDraft,isImmutable,isPrerelease,name,publishedAt"
    ])

def release_view(repo: str, tag: str):
    require_repo(repo); require_tag(tag)
    rows = [x for x in release_list(repo) if x.get("tagName") == tag]
    if len(rows) > 1:
        raise ReleaseError("duplicate release rows for tag")
    if not rows:
        return None
    return gh_json([
        "release", "view", tag, "--repo", repo,
        "--json", "databaseId,tagName,targetCommitish,isDraft,isImmutable,isPrerelease,name,publishedAt,assets"
    ])

def api_json(endpoint: str):
    return gh_json(["api", endpoint])

def tag_commit(repo: str, tag: str):
    require_repo(repo); require_tag(tag)
    endpoint = f"repos/{repo}/git/ref/tags/{urllib.parse.quote(tag, safe='')}"
    p = subprocess.run(["gh", "api", endpoint], capture_output=True, text=True, env=os.environ.copy(), timeout=60)
    if p.returncode:
        err = (p.stderr or "") + (p.stdout or "")
        if "404" in err or "Not Found" in err:
            return None
        raise ReleaseError("tag ref read failed: " + err.strip()[-1200:])
    try:
        ref = json.loads(p.stdout)
    except Exception as exc:
        raise ReleaseError("tag ref JSON invalid") from exc
    obj = ref.get("object") or {}
    typ, sha = obj.get("type"), obj.get("sha")
    for _ in range(5):
        if typ == "commit":
            return sha
        if typ != "tag" or not sha:
            raise ReleaseError("unsupported tag ref object")
        tag_obj = api_json(f"repos/{repo}/git/tags/{sha}")
        obj = tag_obj.get("object") or {}
        typ, sha = obj.get("type"), obj.get("sha")
    raise ReleaseError("annotated tag peel depth exceeded")

def local_hashes(root: Path):
    root = Path(root)
    return {p.name: sha256_file(p) for p in sorted(root.iterdir()) if p.is_file()}

def download_release_assets(repo: str, tag: str, dest: Path):
    require_repo(repo); require_tag(tag)
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    gh_text(["release", "download", tag, "--repo", repo, "--dir", str(dest)])
    return local_hashes(dest)

def release_snapshot(repo: str, tag: str, expected_names=None):
    rel = release_view(repo, tag)
    tcommit = tag_commit(repo, tag)
    hashes = {}
    if rel is not None and rel.get("assets"):
        with tempfile.TemporaryDirectory() as td:
            hashes = download_release_assets(repo, tag, Path(td))
    names = set(hashes)
    if expected_names is not None and rel is not None:
        listed = {x.get("name") for x in (rel.get("assets") or [])}
        if None in listed:
            raise ReleaseError("release asset without name")
        if listed != names:
            raise ReleaseError("release asset list/download set mismatch")
    return {"release": rel, "tag_commit": tcommit, "asset_hashes": hashes}

def workflow_run(repo: str, run_id: str):
    if not str(run_id).isdigit():
        raise ReleaseError("numeric workflow run id required")
    return api_json(f"repos/{require_repo(repo)}/actions/runs/{run_id}")

def run_artifacts(repo: str, run_id: str):
    d = api_json(f"repos/{require_repo(repo)}/actions/runs/{run_id}/artifacts?per_page=100")
    return d.get("artifacts") or []

def artifact(repo: str, artifact_id: str):
    if not str(artifact_id).isdigit():
        raise ReleaseError("numeric artifact id required")
    return api_json(f"repos/{require_repo(repo)}/actions/artifacts/{artifact_id}")

def download_run_artifact(repo: str, run_id: str, name: str, dest: Path):
    if not str(run_id).isdigit():
        raise ReleaseError("numeric workflow run id required")
    dest = Path(dest); dest.mkdir(parents=True, exist_ok=True)
    gh_text(["run", "download", str(run_id), "--repo", require_repo(repo), "--name", name, "--dir", str(dest)], timeout=180)

def verify_attestation(path: Path, repo: str, *, predicate_type=None, signer_workflow=None, source_ref=None):
    args = ["attestation", "verify", str(path), "--repo", require_repo(repo), "--format", "json"]
    if predicate_type:
        args += ["--predicate-type", predicate_type]
    if signer_workflow:
        args += ["--signer-workflow", signer_workflow]
    if source_ref:
        args += ["--source-ref", source_ref]
    return gh_json(args, timeout=120)

def verify_release_attestation(repo: str, tag: str):
    return gh_json(["release", "verify", require_tag(tag), "--repo", require_repo(repo), "--format", "json"], timeout=120)

def verify_release_asset(repo: str, tag: str, path: Path):
    return gh_json(["release", "verify-asset", require_tag(tag), str(path), "--repo", require_repo(repo), "--format", "json"], timeout=120)
