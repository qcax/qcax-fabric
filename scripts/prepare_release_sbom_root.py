from pathlib import Path, PurePosixPath
import shutil
import stat
import sys
import zipfile

from release_common import safe_member_name


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: prepare_release_sbom_root.py WHEELDIR OUTDIR")
    src = Path(sys.argv[1]).resolve()
    dst = Path(sys.argv[2]).resolve()
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    wheels = sorted(src.glob("*.whl"))
    if len(wheels) != 11:
        raise RuntimeError(f"expected 11 wheels, got {len(wheels)}")
    for wheel in wheels:
        out = dst / wheel.stem
        out.mkdir()
        with zipfile.ZipFile(wheel) as z:
            seen = set()
            for info in z.infolist():
                name = safe_member_name(info.filename)
                if name in seen:
                    raise RuntimeError(f"{wheel}: duplicate member {name}")
                seen.add(name)
                mode = (info.external_attr >> 16) & 0o170000
                if mode == stat.S_IFLNK:
                    raise RuntimeError(f"{wheel}: symlink member forbidden: {name}")
                target = out.joinpath(*PurePosixPath(name).parts)
                target_resolved = target.resolve()
                if out.resolve() not in target_resolved.parents and target_resolved != out.resolve():
                    raise RuntimeError(f"{wheel}: extraction escaped root: {name}")
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(info) as rf, target.open("wb") as wf:
                        shutil.copyfileobj(rf, wf)
    print(f"prepared {len(wheels)} wheels for SBOM scan")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
