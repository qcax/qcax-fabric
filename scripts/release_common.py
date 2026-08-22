from __future__ import annotations

from email.parser import Parser
from pathlib import Path, PurePosixPath
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import tomllib
import unicodedata
import zipfile

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_RELEASE = "v0.1.0-alpha.1"
SOURCE_DATE_EPOCH = "1787356800"
PACKAGE_DIRS = [
    ROOT / "packages/contracts",
    ROOT / "packages/sdk",
    ROOT / "packages/host",
] + sorted(p for p in (ROOT / "packages/plugins").iterdir() if p.is_dir())


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def norm_dist(name: str) -> str:
    import re
    return re.sub(r"[-_.]+", "-", name).lower()


def base_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    env["SOURCE_DATE_EPOCH"] = SOURCE_DATE_EPOCH
    return env


def run(cmd: list[str], *, cwd: str | Path = "/", env: dict[str, str] | None = None) -> str:
    r = subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env or base_env(),
        text=True,
        capture_output=True,
    )
    if r.returncode:
        raise RuntimeError(
            "command failed\n"
            + json.dumps(cmd)
            + "\nstdout:\n"
            + r.stdout
            + "\nstderr:\n"
            + r.stderr
        )
    return r.stdout.strip()


def package_identity(package_dir: Path) -> tuple[str, str]:
    data = tomllib.loads((package_dir / "pyproject.toml").read_text(encoding="utf-8"))
    project = data["project"]
    return project["name"], project["version"]


def package_identities() -> list[dict[str, str]]:
    rows = []
    for p in PACKAGE_DIRS:
        name, version = package_identity(p)
        rows.append({"path": p.relative_to(ROOT).as_posix(), "name": name, "version": version})
    return sorted(rows, key=lambda x: norm_dist(x["name"]))


def wheel_metadata(wheel: Path) -> tuple[str, str]:
    with zipfile.ZipFile(wheel) as z:
        names = [n for n in z.namelist() if n.endswith(".dist-info/METADATA")]
        if len(names) != 1:
            raise RuntimeError(f"{wheel}: expected one METADATA file, got {len(names)}")
        msg = Parser().parsestr(z.read(names[0]).decode("utf-8"))
    return msg["Name"], msg["Version"]


def safe_member_name(name: str) -> str:
    p = PurePosixPath(name)
    if p.is_absolute() or ".." in p.parts or "\\" in name:
        raise RuntimeError(f"unsafe archive path: {name!r}")
    return p.as_posix()


def _collision_guard(names: list[str]) -> None:
    cf: dict[str, list[str]] = {}
    nf: dict[str, list[str]] = {}
    for n in names:
        cf.setdefault(n.casefold(), []).append(n)
        nf.setdefault(unicodedata.normalize("NFC", n), []).append(n)
    bad_cf = [v for v in cf.values() if len(set(v)) > 1]
    bad_nf = [v for v in nf.values() if len(set(v)) > 1]
    if bad_cf:
        raise RuntimeError(f"casefold path collision: {bad_cf}")
    if bad_nf:
        raise RuntimeError(f"Unicode NFC path collision: {bad_nf}")


def tar_content_manifest(sdist: Path) -> list[dict[str, object]]:
    rows = []
    names: list[str] = []
    with tarfile.open(sdist, "r:gz") as tf:
        members = tf.getmembers()
        roots = {PurePosixPath(m.name).parts[0] for m in members if PurePosixPath(m.name).parts}
        if len(roots) != 1:
            raise RuntimeError(f"{sdist}: expected one sdist root directory, got {sorted(roots)}")
        root = next(iter(roots))
        for m in members:
            safe_member_name(m.name)
            p = PurePosixPath(m.name)
            rel = PurePosixPath(*p.parts[1:]).as_posix() if len(p.parts) > 1 else ""
            if not rel or m.isdir():
                continue
            if not m.isfile():
                raise RuntimeError(f"{sdist}: non-regular member forbidden: {m.name} type={m.type!r}")
            rel = safe_member_name(rel)
            f = tf.extractfile(m)
            if f is None:
                raise RuntimeError(f"{sdist}: unable to read {m.name}")
            data = f.read()
            names.append(rel)
            rows.append({"path": rel, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    _collision_guard(names)
    if len(names) != len(set(names)):
        raise RuntimeError(f"{sdist}: duplicate member path")
    return sorted(rows, key=lambda x: x["path"])


def manifest_digest(rows: list[dict[str, object]]) -> str:
    raw = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def zip_inventory(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as z:
        names = [safe_member_name(n) for n in z.namelist()]
    _collision_guard(names)
    if len(names) != len(set(names)):
        raise RuntimeError(f"{path}: duplicate zip member path")
    return sorted(names)


def deterministic_zip(out: Path, members: dict[str, bytes]) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, data in sorted(members.items()):
            name = safe_member_name(name)
            info = zipfile.ZipInfo(name, date_time=(2026, 8, 22, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100644 & 0xFFFF) << 16
            z.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def json_bytes(obj: object) -> bytes:
    return (json.dumps(obj, indent=2, sort_keys=True) + "\n").encode("utf-8")
