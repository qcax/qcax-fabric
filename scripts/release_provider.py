from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import quote
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time

EXPECTED_TAG = "v0.1.0-alpha.1"
EXPECTED_ASSET_COUNT = 30
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class ProviderError(RuntimeError):
    pass


class GhCommandError(ProviderError):
    def __init__(self, args: list[str], returncode: int, stdout: str, stderr: str):
        super().__init__(
            "gh command failed: "
            + json.dumps(args)
            + f"\nreturncode={returncode}\nstdout:\n{stdout}\nstderr:\n{stderr}"
        )
        self.args_list = list(args)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@dataclass(frozen=True)
class LocalAsset:
    name: str
    bytes: int
    sha256: str
    path: Path


@dataclass(frozen=True)
class AssetDiff:
    exact: tuple[str, ...]
    missing: tuple[str, ...]
    mismatched: tuple[str, ...]
    unexpected: tuple[str, ...]
    unknown_digest: tuple[str, ...]

    @property
    def is_exact(self) -> bool:
        return not (self.missing or self.mismatched or self.unexpected or self.unknown_digest)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _command_env() -> dict[str, str]:
    env = os.environ.copy()
    env["GH_PROMPT_DISABLED"] = "1"
    env["PAGER"] = "cat"
    return env


def run_gh(
    args: list[str],
    *,
    check: bool = True,
    timeout: int = 120,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        ["gh", *args],
        text=True,
        input=input_text,
        capture_output=True,
        env=_command_env(),
        timeout=timeout,
    )
    if check and proc.returncode:
        raise GhCommandError(args, proc.returncode, proc.stdout, proc.stderr)
    return proc


def gh_json(args: list[str], *, timeout: int = 120) -> Any:
    proc = run_gh(args, timeout=timeout)
    text = proc.stdout.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception as exc:
        raise ProviderError(f"expected JSON from gh {args!r}: {text!r}") from exc


def api(repo: str, suffix: str, *, method: str = "GET", check: bool = True) -> Any:
    endpoint = f"repos/{repo}/{suffix.lstrip('/')}"
    args = ["api", "-X", method, endpoint]
    proc = run_gh(args, check=check)
    if proc.returncode:
        return None
    text = proc.stdout.strip()
    return json.loads(text) if text else None


def repo_main_sha(repo: str) -> str:
    data = api(repo, "branches/main")
    try:
        sha = data["commit"]["sha"]
    except Exception as exc:
        raise ProviderError(f"unable to read main SHA: {data!r}") from exc
    if not FULL_SHA_RE.fullmatch(sha):
        raise ProviderError(f"invalid main SHA {sha!r}")
    return sha


def _find_release_from_list(repo: str, tag: str) -> dict[str, Any] | None:
    data = api(repo, "releases?per_page=100")
    if not isinstance(data, list):
        raise ProviderError(f"unexpected releases payload: {data!r}")
    matches = [x for x in data if x.get("tag_name") == tag]
    if len(matches) > 1:
        raise ProviderError(f"multiple releases found for {tag!r}")
    return matches[0] if matches else None


def get_release(repo: str, tag: str) -> dict[str, Any] | None:
    # releases list includes drafts for an authenticated writer, unlike latest/public-only paths.
    release = _find_release_from_list(repo, tag)
    if release is None:
        return None
    # Refresh with the release-specific endpoint when possible.
    rid = release.get("id")
    if rid is not None:
        refreshed = api(repo, f"releases/{rid}", check=False)
        if isinstance(refreshed, dict):
            release = refreshed
    if "immutable" not in release:
        # gh release view exposes isImmutable on current GitHub CLI.
        proc = run_gh(
            [
                "release",
                "view",
                tag,
                "-R",
                repo,
                "--json",
                "isImmutable,isDraft,isPrerelease,tagName,targetCommitish,databaseId,url",
            ],
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            view = json.loads(proc.stdout)
            release["immutable"] = bool(view.get("isImmutable"))
            release["draft"] = bool(view.get("isDraft"))
            release["prerelease"] = bool(view.get("isPrerelease"))
            release["target_commitish"] = view.get("targetCommitish") or release.get("target_commitish")
            release["html_url"] = view.get("url") or release.get("html_url")
    return release


def get_release_assets(repo: str, release: dict[str, Any] | None) -> list[dict[str, Any]]:
    if release is None:
        return []
    rid = release.get("id")
    if not isinstance(rid, int):
        raise ProviderError(f"release id missing: {release!r}")
    data = api(repo, f"releases/{rid}/assets?per_page=100")
    if not isinstance(data, list):
        raise ProviderError(f"unexpected release assets payload: {data!r}")
    return data


def get_tag_ref(repo: str, tag: str) -> dict[str, Any] | None:
    suffix = f"git/ref/tags/{quote(tag, safe='')}"
    return api(repo, suffix, check=False)


def resolve_tag_commit(repo: str, tag: str, *, max_depth: int = 4) -> str | None:
    ref = get_tag_ref(repo, tag)
    if not ref:
        return None
    obj = ref.get("object") or {}
    typ = obj.get("type")
    sha = obj.get("sha")
    for _ in range(max_depth):
        if typ == "commit":
            if not FULL_SHA_RE.fullmatch(str(sha)):
                raise ProviderError(f"invalid tag commit SHA {sha!r}")
            return str(sha)
        if typ != "tag" or not FULL_SHA_RE.fullmatch(str(sha)):
            raise ProviderError(f"unexpected tag ref object {obj!r}")
        annotated = api(repo, f"git/tags/{sha}")
        obj = annotated.get("object") or {}
        typ = obj.get("type")
        sha = obj.get("sha")
    raise ProviderError(f"annotated tag chain too deep for {tag!r}")


def local_assets(root: Path) -> dict[str, LocalAsset]:
    root = root.resolve()
    rows: dict[str, LocalAsset] = {}
    for p in sorted(root.iterdir()):
        if not p.is_file():
            continue
        if p.name in rows:
            raise ProviderError(f"duplicate local asset name {p.name}")
        rows[p.name] = LocalAsset(p.name, p.stat().st_size, sha256_file(p), p)
    return rows


def _remote_digest(asset: dict[str, Any]) -> str | None:
    value = asset.get("digest")
    if not value:
        return None
    if not isinstance(value, str) or not value.startswith("sha256:"):
        raise ProviderError(f"unsupported remote asset digest {value!r}")
    digest = value.split(":", 1)[1]
    if not SHA256_RE.fullmatch(digest):
        raise ProviderError(f"invalid remote asset digest {value!r}")
    return digest


def remote_asset_map(assets: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in assets:
        name = row.get("name")
        if not isinstance(name, str) or not name:
            raise ProviderError(f"remote asset without valid name: {row!r}")
        if name in out:
            raise ProviderError(f"duplicate remote asset name {name!r}")
        out[name] = row
    return out


def compare_asset_sets(local: dict[str, LocalAsset], remote: list[dict[str, Any]]) -> AssetDiff:
    rmap = remote_asset_map(remote)
    exact: list[str] = []
    missing: list[str] = []
    mismatched: list[str] = []
    unexpected = sorted(set(rmap) - set(local))
    unknown: list[str] = []
    for name, item in sorted(local.items()):
        row = rmap.get(name)
        if row is None:
            missing.append(name)
            continue
        digest = _remote_digest(row)
        if digest is None:
            unknown.append(name)
            continue
        if int(row.get("size", -1)) != item.bytes or digest != item.sha256:
            mismatched.append(name)
        else:
            exact.append(name)
    return AssetDiff(tuple(exact), tuple(missing), tuple(mismatched), tuple(unexpected), tuple(unknown))


def hydrate_unknown_asset_digests(
    repo: str,
    tag: str,
    remote: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = [dict(x) for x in remote]
    for row in rows:
        if _remote_digest(row) is not None:
            continue
        name = row.get("name")
        with tempfile.TemporaryDirectory() as td:
            run_gh(["release", "download", tag, "-R", repo, "-p", str(name), "-D", td])
            p = Path(td) / str(name)
            if not p.is_file():
                raise ProviderError(f"downloaded asset missing: {name}")
            row["digest"] = "sha256:" + sha256_file(p)
            row["size"] = p.stat().st_size
    return rows


def is_release_exact(
    release: dict[str, Any] | None,
    *,
    tag: str,
    expected_commit: str,
    tag_commit: str | None,
) -> bool:
    if release is None or release.get("tag_name") != tag:
        return False
    target = release.get("target_commitish")
    if isinstance(target, str) and FULL_SHA_RE.fullmatch(target) and target != expected_commit:
        return False
    # Exact tag binding is the strongest condition once the tag exists.
    if tag_commit is not None:
        return tag_commit == expected_commit
    return target == expected_commit


def classify_provider_state(
    *,
    main_sha: str,
    expected_commit: str,
    release: dict[str, Any] | None,
    tag_commit: str | None,
    asset_diff: AssetDiff | None,
    tag: str = EXPECTED_TAG,
) -> str:
    if main_sha != expected_commit:
        return "HOLD_MAIN_MOVED"
    if tag_commit is not None and tag_commit != expected_commit:
        return "BLOCK_WRONG_TAG"
    if release is None:
        return "CREATE_EXACT_DRAFT"
    if release.get("tag_name") != tag:
        return "BLOCK_WRONG_RELEASE"
    if not is_release_exact(release, tag=tag, expected_commit=expected_commit, tag_commit=tag_commit):
        return "BLOCK_WRONG_RELEASE_TARGET"
    draft = bool(release.get("draft"))
    immutable = bool(release.get("immutable"))
    if not draft:
        if immutable and tag_commit == expected_commit and asset_diff and asset_diff.is_exact:
            return "VERIFY_ONLY"
        if immutable:
            return "BLOCK_PUBLISHED_IMMUTABLE_MISMATCH"
        return "BLOCK_PUBLISHED_MUTABLE"
    if asset_diff is None:
        return "DRAFT_EXACT"
    if asset_diff.unexpected:
        return "BLOCK_DRAFT_UNEXPECTED_ASSETS"
    if asset_diff.is_exact:
        return "DRAFT_ASSETS_EXACT"
    return "DRAFT_RECONCILE_ASSETS"


def create_draft(repo: str, tag: str, commit: str, notes_file: Path, title: str) -> None:
    if not FULL_SHA_RE.fullmatch(commit):
        raise ProviderError(f"invalid commit {commit!r}")
    args = [
        "release",
        "create",
        tag,
        "-R",
        repo,
        "--draft",
        "--prerelease",
        "--latest=false",
        "--title",
        title,
        "--notes-file",
        str(notes_file),
        "--target",
        commit,
    ]
    existing_tag = resolve_tag_commit(repo, tag)
    if existing_tag is not None:
        if existing_tag != commit:
            raise ProviderError(f"cannot create draft: existing tag {tag} points to {existing_tag}")
        args.append("--verify-tag")
    run_gh(args)


def upload_asset(repo: str, tag: str, path: Path) -> None:
    run_gh(["release", "upload", tag, str(path), "-R", repo])


def delete_draft_asset(repo: str, release: dict[str, Any], asset: dict[str, Any]) -> None:
    if not release.get("draft"):
        raise ProviderError("refusing to delete asset from non-draft release")
    aid = asset.get("id")
    if not isinstance(aid, int):
        raise ProviderError(f"asset id missing: {asset!r}")
    api(repo, f"releases/assets/{aid}", method="DELETE")


def publish_draft(repo: str, tag: str) -> None:
    run_gh(["release", "edit", tag, "-R", repo, "--draft=false", "--prerelease", "--latest=false"])


def download_all_release_assets(repo: str, tag: str, destination: Path) -> None:
    destination = destination.resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ProviderError(f"download destination is not empty: {destination}")
    destination.mkdir(parents=True, exist_ok=True)
    run_gh(["release", "download", tag, "-R", repo, "-D", str(destination)])


def wait_for_state(
    read: Callable[[], Any],
    accept: Callable[[Any], bool],
    *,
    attempts: int = 20,
    delay_seconds: float = 3.0,
    description: str = "provider state",
) -> Any:
    last = None
    for index in range(attempts):
        last = read()
        if accept(last):
            return last
        if index + 1 < attempts:
            time.sleep(delay_seconds)
    raise ProviderError(f"timed out waiting for {description}; last={last!r}")


def parse_sha256sums(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.fullmatch(r"([0-9a-f]{64})  ([^\r\n]+)", line)
        if not m:
            raise ProviderError(f"invalid SHA256SUMS line: {line!r}")
        digest, name = m.groups()
        if name in out:
            raise ProviderError(f"duplicate SHA256SUMS entry {name}")
        out[name] = digest
    return out


def spdx_semantic_signature(doc: dict[str, Any]) -> dict[str, Any]:
    if doc.get("spdxVersion") != "SPDX-2.3":
        raise ProviderError(f"unsupported SPDX version {doc.get('spdxVersion')!r}")
    id_to_label: dict[str, str] = {}
    packages = []
    for pkg in doc.get("packages", []):
        spdxid = str(pkg.get("SPDXID", ""))
        label = f"{pkg.get('name','')}@{pkg.get('versionInfo','')}"
        if spdxid:
            id_to_label[spdxid] = label
        packages.append(
            {
                "name": str(pkg.get("name", "")),
                "versionInfo": str(pkg.get("versionInfo", "")),
                "downloadLocation": str(pkg.get("downloadLocation", "")),
                "filesAnalyzed": bool(pkg.get("filesAnalyzed", False)),
                "licenseConcluded": str(pkg.get("licenseConcluded", "")),
                "licenseDeclared": str(pkg.get("licenseDeclared", "")),
                "supplier": str(pkg.get("supplier", "")),
                "checksums": sorted(
                    (str(x.get("algorithm", "")), str(x.get("checksumValue", "")))
                    for x in pkg.get("checksums", [])
                ),
                "externalRefs": sorted(
                    (
                        str(x.get("referenceCategory", "")),
                        str(x.get("referenceType", "")),
                        str(x.get("referenceLocator", "")),
                    )
                    for x in pkg.get("externalRefs", [])
                ),
            }
        )
    relationships = []
    for rel in doc.get("relationships", []):
        left = str(rel.get("spdxElementId", ""))
        right = str(rel.get("relatedSpdxElement", ""))
        relationships.append(
            (
                id_to_label.get(left, "DOCUMENT_OR_ROOT" if left.startswith("SPDXRef-DOCUMENT") else left),
                str(rel.get("relationshipType", "")),
                id_to_label.get(right, "DOCUMENT_OR_ROOT" if right.startswith("SPDXRef-DOCUMENT") else right),
            )
        )
    return {
        "packages": sorted(packages, key=lambda x: json.dumps(x, sort_keys=True)),
        "relationships": sorted(relationships),
    }


def provenance_semantic_signature(doc: dict[str, Any]) -> dict[str, Any]:
    component_exact = []
    component_semantic = []
    for row in doc.get("components", []):
        name = str(row.get("name", ""))
        if name.endswith(".tar.gz"):
            component_semantic.append(name)
        else:
            component_exact.append(
                (name, int(row.get("bytes", -1)), str(row.get("sha256", "")))
            )
    return {
        "schema": doc.get("schema"),
        "release": doc.get("release"),
        "repository": doc.get("repository"),
        "source_commit": doc.get("source_commit"),
        "source_tree": doc.get("source_tree"),
        "package_identities": sorted(
            doc.get("package_identities", []), key=lambda x: (x.get("name", ""), x.get("path", ""))
        ),
        "exact_components": sorted(component_exact),
        "sdist_component_names": sorted(component_semantic),
    }
