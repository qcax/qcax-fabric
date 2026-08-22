from pathlib import Path
import json
import os
import re
import sys
import tempfile

from release_common import base_env, norm_dist, run, wheel_metadata


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: verify_sdist_parity.py SDISTDIR RELEASE_LOCK")
    sdistdir = Path(sys.argv[1]).resolve()
    lock_path = Path(sys.argv[2]).resolve()
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    entries = {norm_dist(x["distribution_name"]): x for x in lock["entries"]}
    sdists = sorted(sdistdir.glob("*.tar.gz"))
    if len(sdists) != 11 or len(entries) != 11:
        raise RuntimeError(f"expected 11 sdists and 11 lock entries, got {len(sdists)} and {len(entries)}")

    root = Path(__file__).resolve().parents[1]
    rows = []
    with tempfile.TemporaryDirectory() as td_raw:
        td = Path(td_raw)
        wheel_dir = td / "derived-wheels"
        wheel_dir.mkdir()
        derived = {}
        for sdist in sdists:
            run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "wheel",
                    "--no-deps",
                    "--no-build-isolation",
                    "-w",
                    str(wheel_dir),
                    str(sdist),
                ],
                env=base_env(),
            )
        wheels = sorted(wheel_dir.glob("*.whl"))
        if len(wheels) != 11:
            raise RuntimeError(f"expected 11 sdist-derived wheels, got {len(wheels)}")
        for wheel in wheels:
            name, version = wheel_metadata(wheel)
            key = norm_dist(name)
            if key in derived:
                raise RuntimeError(f"duplicate derived distribution {name}")
            derived[key] = (wheel, version)

        venv = td / "venv"
        run([sys.executable, "-m", "venv", str(venv)], env=base_env())
        py = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        ordered_keys = []
        for token in ("contracts", "sdk", "host"):
            ordered_keys += [k for k in derived if k == f"qcax-fabric-{token}"]
        ordered_keys += sorted(k for k in derived if k not in ordered_keys)
        for key in ordered_keys:
            run([str(py), "-m", "pip", "install", "--no-index", "--no-deps", str(derived[key][0])], env=base_env())
        run([str(py), "-m", "pip", "check"], env=base_env())

        for key in sorted(entries):
            if key not in derived:
                raise RuntimeError(f"missing sdist-derived wheel for {key}")
            wheel, version = derived[key]
            observed = json.loads(
                run([str(py), str(root / "scripts/verify_installed_wheel.py"), str(wheel), str(venv)], env=base_env())
            )
            expected = entries[key]
            row = {
                "distribution_name": observed["distribution_name"],
                "distribution_version": observed["distribution_version"],
                "installed_image_sha256": observed["installed_image_sha256"],
                "expected_installed_image_sha256": expected["installed_image_sha256"],
                "plugin_ids": observed["plugin_ids"],
                "expected_plugin_ids": expected["plugin_ids"],
                "match": (
                    norm_dist(observed["distribution_name"]) == key
                    and observed["distribution_version"] == expected["distribution_version"]
                    and observed["installed_image_sha256"] == expected["installed_image_sha256"]
                    and observed["plugin_ids"] == expected["plugin_ids"]
                ),
            }
            rows.append(row)
        bad = [r for r in rows if not r["match"]]
        result = {
            "status": "PASS" if not bad else "FAIL",
            "distributions": len(rows),
            "matches": len(rows) - len(bad),
            "mismatches": bad,
            "rows": rows,
        }
        print(json.dumps(result, sort_keys=True))
        return 0 if not bad and len(rows) == 11 else 1


if __name__ == "__main__":
    raise SystemExit(main())
