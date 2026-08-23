#!/usr/bin/env python3
from pathlib import Path
import json, os, shutil, subprocess, sys, tempfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
ENV = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}


def run(root):
    return subprocess.run(
        [sys.executable, str(root / "tools/validate_w9_provider.py")],
        cwd=str(root),
        env=ENV,
        capture_output=True,
        text=True,
        timeout=60,
    )


def main():
    with tempfile.TemporaryDirectory() as temp_dir:
        repo = Path(temp_dir) / "r"
        shutil.copytree(ROOT, repo)
        cases = []

        def mutate(mid, relative, old, new):
            path = repo / relative
            before = path.read_bytes()
            try:
                source = path.read_text(encoding="utf-8")
                if old not in source:
                    raise RuntimeError(mid + " anchor missing")
                path.write_text(source.replace(old, new, 1), encoding="utf-8")
                proc = run(repo)
                cases.append({"id": mid, "killed": proc.returncode != 0})
            finally:
                path.write_bytes(before)

        mutate("W9_REMOVE_REPLAY_DOWNLOAD", ".github/workflows/release-replay.yml", "gh release download", "echo disabled-release-download")
        mutate("W9_DROP_PUBLISHED_ARG", ".github/workflows/release-replay.yml", "--published published-assets", "--published-disabled published-assets")
        mutate("W9_ADD_UNSUPPORTED_FINALIZE_FLAG", ".github/workflows/release-replay.yml", "finalize_payload.py replay-assets", "finalize_payload.py replay-assets --replay")
        mutate("W9_DROP_REPLAY_SOURCE_BINDING", ".github/workflows/release-replay.yml", "QCAX_EXPECTED_COMMIT: ${{ github.sha }}", "QCAX_EXPECTED_COMMIT_DISABLED: ${{ github.sha }}")
        mutate("W9_UNPIN_PYPI_ATTEST", "requirements/release-verify.txt", "pypi-attestations==0.0.30", "pypi-attestations>=0")
        mutate("W9_PROMOTE_TEMPLATE", "history/evidence/W9_PROVIDER_CONFIGURATION_TEMPLATE.json", '"overall": "HOLD"', '"overall": "PASS"')
        mutate("W9_FAKE_OBSERVED_COMMIT", "history/evidence/W9_PROVIDER_CONFIGURATION_TEMPLATE.json", '"observed_commit": null', '"observed_commit": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"')
        mutate("W9_REMOVE_REREAD", "release/tooling/publish_github.py", "state = reread()", 'state = {"classification":{"state":"DRAFT_EXACT"}}')
        mutate("W9_REMOVE_MUTATION_FAMILY", "conformance/run_mutations.py", " 'tests/release/test_w9_provider_mutations.py',\n", "")
        mutate("W9_REMOVE_RUNALL_FAMILY", "tools/run_all.py", " [sys.executable,str(ROOT/'tests/release/test_w9_provider_mutations.py')],\n", "")
        mutate("W9_SYNTAX_BREAK", "release/tooling/pypi_postverify.py", "def postverify(tag, commit, repository):", "def postverify(tag, commit, repository)")
        mutate("W9_SHARED_PENDING_IDENTITY_REGRESSION", "release/policy/pypi-publication-policy.json", '"environment": "pypi-sdk"', '"environment": "pypi"')
        mutate("W9_TEMPLATE_ENVIRONMENT_DRIFT", "history/evidence/W9_PROVIDER_CONFIGURATION_TEMPLATE.json", '"environment": "pypi-sdk"', '"environment": "pypi-sdk-wrong"')
        mutate("W9_DROP_DYNAMIC_ENVIRONMENT", ".github/workflows/pypi-publish.yml", "environment: ${{ matrix.environment }}", "environment: pypi")
        mutate("W9_BROADEN_PROJECT_DIRECTORY", ".github/workflows/pypi-publish.yml", "packages-dir: staged/${{ matrix.project }}/", "packages-dir: staged/")
        mutate("W9_DROP_INTEGRITY_ENVIRONMENT_BINDING", "release/tooling/pypi_integrity.py", 'publisher.get("environment") == environment', 'publisher.get("environment") == "pypi"')
        mutate("W9_DROP_INTEGRITY_WORKFLOW_BINDING", "release/tooling/pypi_integrity.py", 'publisher.get("workflow") == workflow', 'publisher.get("workflow") == "anything.yml"')
        mutate("W9_DROP_ALL_ENVIRONMENTS_RECEIPT_GATE", "release/tooling/pypi_precheck.py", '"pypi_environments_verified",', '"pypi_environment_verified",')
        mutate("W9_DROP_POSTFAIL_RECONCILIATION", ".github/workflows/pypi-publish.yml", "always() && needs.precheck.result == 'success'", "needs.publish.result == 'success'")

        clean = run(repo)
        survivors = [case["id"] for case in cases if not case["killed"]]
        result = {
            "status": "PASS" if not survivors and clean.returncode == 0 else "FAIL",
            "mutations": len(cases),
            "killed": sum(case["killed"] for case in cases),
            "survivors": survivors,
            "post_restore_validator_returncode": clean.returncode,
        }
        print(json.dumps(result, sort_keys=True))
        if result["status"] != "PASS":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
