from pathlib import Path
import io
import json
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from release_common import deterministic_zip, safe_member_name, tar_content_manifest
from release_provider import (
    AssetDiff,
    LocalAsset,
    ProviderError,
    classify_provider_state,
    compare_asset_sets,
    create_draft,
    delete_draft_asset,
)
from tag_replay_verify import provenance_core, sbom_fingerprint

COMMIT = "a" * 40
TAG = "v0.1.0-alpha.1"


def diff(*, exact=(), missing=(), mismatched=(), unexpected=(), unknown=()):
    return AssetDiff(tuple(exact), tuple(missing), tuple(mismatched), tuple(unexpected), tuple(unknown))


def release(*, draft=True, immutable=False, target=COMMIT, tag=TAG):
    return {
        "id": 1,
        "tag_name": tag,
        "draft": draft,
        "immutable": immutable,
        "target_commitish": target,
        "prerelease": True,
    }


class ReleaseCommonTests(unittest.TestCase):
    def _sdist(self, path: Path, payload: bytes, mtime: int) -> None:
        with tarfile.open(path, "w:gz") as tf:
            root = tarfile.TarInfo("example-0.1.0/")
            root.type = tarfile.DIRTYPE
            root.mtime = mtime
            tf.addfile(root)
            info = tarfile.TarInfo("example-0.1.0/a.txt")
            info.size = len(payload)
            info.mtime = mtime
            tf.addfile(info, io.BytesIO(payload))

    def test_sdist_manifest_ignores_container_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            a, b = td / "a.tar.gz", td / "b.tar.gz"
            self._sdist(a, b"same\n", 1)
            self._sdist(b, b"same\n", 999999)
            self.assertEqual(tar_content_manifest(a), tar_content_manifest(b))

    def test_sdist_manifest_detects_payload_change(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            a, b = td / "a.tar.gz", td / "b.tar.gz"
            self._sdist(a, b"A", 1)
            self._sdist(b, b"B", 1)
            self.assertNotEqual(tar_content_manifest(a), tar_content_manifest(b))

    def test_unsafe_archive_path_rejected(self):
        for bad in ("../escape", "/absolute", "a\\b"):
            with self.subTest(bad=bad), self.assertRaises(RuntimeError):
                safe_member_name(bad)

    def test_deterministic_zip_twins(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            a, b = td / "a.zip", td / "b.zip"
            members = {"b.txt": b"B", "a.txt": b"A"}
            deterministic_zip(a, members)
            deterministic_zip(b, dict(reversed(list(members.items()))))
            self.assertEqual(a.read_bytes(), b.read_bytes())


class ReleaseProviderStateTests(unittest.TestCase):
    def test_main_drift_holds_before_provider_mutation(self):
        self.assertEqual(
            classify_provider_state(
                main_sha="b" * 40,
                expected_commit=COMMIT,
                release=None,
                tag_commit=None,
                asset_diff=None,
            ),
            "HOLD_MAIN_MOVED",
        )

    def test_wrong_tag_blocks(self):
        self.assertEqual(
            classify_provider_state(
                main_sha=COMMIT,
                expected_commit=COMMIT,
                release=None,
                tag_commit="b" * 40,
                asset_diff=None,
            ),
            "BLOCK_WRONG_TAG",
        )

    def test_absent_release_creates_exact_draft(self):
        self.assertEqual(
            classify_provider_state(
                main_sha=COMMIT,
                expected_commit=COMMIT,
                release=None,
                tag_commit=None,
                asset_diff=None,
            ),
            "CREATE_EXACT_DRAFT",
        )

    def test_draft_asset_states_are_fail_closed(self):
        cases = [
            (None, "DRAFT_EXACT"),
            (diff(exact=("a",)), "DRAFT_ASSETS_EXACT"),
            (diff(missing=("a",)), "DRAFT_RECONCILE_ASSETS"),
            (diff(mismatched=("a",)), "DRAFT_RECONCILE_ASSETS"),
            (diff(unknown=("a",)), "DRAFT_RECONCILE_ASSETS"),
            (diff(unexpected=("x",)), "BLOCK_DRAFT_UNEXPECTED_ASSETS"),
        ]
        for asset_diff, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(
                    classify_provider_state(
                        main_sha=COMMIT,
                        expected_commit=COMMIT,
                        release=release(),
                        tag_commit=None,
                        asset_diff=asset_diff,
                    ),
                    expected,
                )

    def test_published_exact_immutable_is_verify_only(self):
        self.assertEqual(
            classify_provider_state(
                main_sha=COMMIT,
                expected_commit=COMMIT,
                release=release(draft=False, immutable=True),
                tag_commit=COMMIT,
                asset_diff=diff(exact=("all",)),
            ),
            "VERIFY_ONLY",
        )

    def test_published_mutable_or_mismatched_is_blocked(self):
        mutable = classify_provider_state(
            main_sha=COMMIT,
            expected_commit=COMMIT,
            release=release(draft=False, immutable=False),
            tag_commit=COMMIT,
            asset_diff=diff(exact=("all",)),
        )
        mismatched = classify_provider_state(
            main_sha=COMMIT,
            expected_commit=COMMIT,
            release=release(draft=False, immutable=True),
            tag_commit=COMMIT,
            asset_diff=diff(mismatched=("a",)),
        )
        self.assertEqual(mutable, "BLOCK_PUBLISHED_MUTABLE")
        self.assertEqual(mismatched, "BLOCK_PUBLISHED_IMMUTABLE_MISMATCH")

    def test_create_draft_binds_exact_commit_and_verify_tag_only_when_existing(self):
        notes = Path("notes.md")
        with mock.patch("release_provider.resolve_tag_commit", return_value=None), mock.patch(
            "release_provider.run_gh"
        ) as run_gh:
            create_draft("qcax/qcax-fabric", TAG, COMMIT, notes, "title")
            args = run_gh.call_args.args[0]
            self.assertIn("--target", args)
            self.assertEqual(args[args.index("--target") + 1], COMMIT)
            self.assertNotIn("--verify-tag", args)
        with mock.patch("release_provider.resolve_tag_commit", return_value=COMMIT), mock.patch(
            "release_provider.run_gh"
        ) as run_gh:
            create_draft("qcax/qcax-fabric", TAG, COMMIT, notes, "title")
            self.assertIn("--verify-tag", run_gh.call_args.args[0])

    def test_create_draft_refuses_wrong_existing_tag(self):
        with mock.patch("release_provider.resolve_tag_commit", return_value="b" * 40):
            with self.assertRaises(ProviderError):
                create_draft("qcax/qcax-fabric", TAG, COMMIT, Path("notes.md"), "title")

    def test_delete_asset_refuses_non_draft(self):
        with self.assertRaises(ProviderError):
            delete_draft_asset("qcax/qcax-fabric", release(draft=False, immutable=True), {"id": 7})


class AssetDiffTests(unittest.TestCase):
    def test_compare_asset_sets_detects_exact_missing_mismatch_unexpected_unknown(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)

            def local(name, data):
                p = td / name
                p.write_bytes(data)
                import hashlib
                return LocalAsset(name, len(data), hashlib.sha256(data).hexdigest(), p)

            loc = {n.name: n for n in [local("exact", b"1"), local("missing", b"2"), local("bad", b"3"), local("unknown", b"4")]}
            remote = [
                {"name": "exact", "size": 1, "digest": "sha256:" + loc["exact"].sha256},
                {"name": "bad", "size": 1, "digest": "sha256:" + ("0" * 64)},
                {"name": "unknown", "size": 1},
                {"name": "extra", "size": 1, "digest": "sha256:" + ("1" * 64)},
            ]
            d = compare_asset_sets(loc, remote)
            self.assertEqual(d.exact, ("exact",))
            self.assertEqual(d.missing, ("missing",))
            self.assertEqual(d.mismatched, ("bad",))
            self.assertEqual(d.unexpected, ("extra",))
            self.assertEqual(d.unknown_digest, ("unknown",))


class ReplayEquivalenceTests(unittest.TestCase):
    def test_sbom_fingerprint_ignores_document_namespace_but_detects_package_version(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            a, b = td / "a.json", td / "b.json"
            base = {
                "spdxVersion": "SPDX-2.3",
                "documentNamespace": "urn:a",
                "packages": [{"name": "qcax-fabric-host", "versionInfo": "0.1.0a1", "licenseDeclared": "Apache-2.0", "licenseConcluded": "Apache-2.0", "filesAnalyzed": True}],
            }
            a.write_text(json.dumps(base), encoding="utf-8")
            changed = json.loads(json.dumps(base)); changed["documentNamespace"] = "urn:b"
            b.write_text(json.dumps(changed), encoding="utf-8")
            expected = {"qcax-fabric-host"}
            self.assertEqual(sbom_fingerprint(a, expected), sbom_fingerprint(b, expected))
            changed["packages"][0]["versionInfo"] = "9.9.9"
            b.write_text(json.dumps(changed), encoding="utf-8")
            self.assertNotEqual(sbom_fingerprint(a, expected), sbom_fingerprint(b, expected))

    def test_provenance_core_ignores_run_and_sdist_raw_hash_but_binds_source_and_wheels(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            a, b = td / "a.json", td / "b.json"
            base = {
                "schema": "qcax.release-provenance/1",
                "release": TAG,
                "repository": "qcax/qcax-fabric",
                "source_commit": COMMIT,
                "source_tree": "c" * 40,
                "run_id": "1",
                "run_attempt": "1",
                "package_identities": [{"name": "x", "version": "1"}],
                "components": [
                    {"name": "x.whl", "sha256": "1" * 64, "bytes": 10},
                    {"name": "x.tar.gz", "sha256": "2" * 64, "bytes": 20},
                ],
            }
            a.write_text(json.dumps(base), encoding="utf-8")
            changed = json.loads(json.dumps(base)); changed["run_id"] = "999"; changed["components"][1]["sha256"] = "3" * 64
            b.write_text(json.dumps(changed), encoding="utf-8")
            self.assertEqual(provenance_core(a), provenance_core(b))
            changed["source_commit"] = "b" * 40
            b.write_text(json.dumps(changed), encoding="utf-8")
            self.assertNotEqual(provenance_core(a), provenance_core(b))


class ReleaseWorkflowPermissionTests(unittest.TestCase):
    def test_publish_job_can_read_preflight_run_and_artifact(self):
        enabled = (ROOT / ".github/workflows/release-build.yml").read_text(encoding="utf-8")
        reviewed = (ROOT / "github/workflows-ready/release-build.yml").read_text(encoding="utf-8")
        self.assertEqual(enabled, reviewed)
        publish = enabled.split("\n  publish:\n", 1)[1].split("\n  tag-replay:\n", 1)[0]
        self.assertIn("    permissions:\n      actions: read\n      contents: write\n      attestations: read\n", publish)
        self.assertIn("python scripts/reconcile_release_prestate.py", publish)
        self.assertIn("gh run view", (ROOT / "scripts/reconcile_release_prestate.py").read_text(encoding="utf-8"))
        self.assertIn("gh run download", (ROOT / "scripts/reconcile_release_prestate.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
