from pathlib import Path
import json
import shutil
import sys
import tempfile

from release_common import (
    PACKAGE_DIRS,
    base_env,
    manifest_digest,
    package_identity,
    run,
    sha256_file,
    tar_content_manifest,
)


def build_one(src: Path, work: Path, out: Path) -> Path:
    shutil.copytree(src, work)
    out.mkdir(parents=True, exist_ok=True)
    run(
        [
            sys.executable,
            "-m",
            "build",
            "--sdist",
            "--no-isolation",
            "--outdir",
            str(out),
            str(work),
        ],
        env=base_env(),
    )
    items = list(out.glob("*.tar.gz"))
    if len(items) != 1:
        raise RuntimeError(f"{src}: expected one sdist, got {len(items)}")
    return items[0]


def main() -> int:
    outdir = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else None
    rows = []
    with tempfile.TemporaryDirectory() as td_raw:
        td = Path(td_raw)
        for idx, src in enumerate(PACKAGE_DIRS):
            a = build_one(src, td / f"a-src-{idx:02d}", td / f"a-out-{idx:02d}")
            b = build_one(src, td / f"b-src-{idx:02d}", td / f"b-out-{idx:02d}")
            ma = tar_content_manifest(a)
            mb = tar_content_manifest(b)
            name, version = package_identity(src)
            logical_equal = ma == mb
            row = {
                "distribution_name": name,
                "distribution_version": version,
                "sdist_filename": a.name,
                "sha256": sha256_file(a),
                "bytes": a.stat().st_size,
                "raw_twin_equal": a.read_bytes() == b.read_bytes(),
                "normalized_content_equal": logical_equal,
                "normalized_content_sha256": manifest_digest(ma),
                "normalized_members": len(ma),
            }
            rows.append(row)
            if not logical_equal:
                raise RuntimeError(f"{src}: normalized sdist contents differ across clean builds")
            if outdir is not None:
                outdir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(a, outdir / a.name)
    result = {
        "status": "PASS",
        "builder": "python-build-setuptools-no-isolation",
        "distributions": len(rows),
        "normalized_content_twins": sum(1 for r in rows if r["normalized_content_equal"]),
        "raw_byte_twins": sum(1 for r in rows if r["raw_twin_equal"]),
        "sdists": sorted(rows, key=lambda x: x["distribution_name"]),
        "output_dir": str(outdir) if outdir else None,
    }
    if result["distributions"] != 11 or result["normalized_content_twins"] != 11:
        raise RuntimeError(json.dumps(result, sort_keys=True))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
