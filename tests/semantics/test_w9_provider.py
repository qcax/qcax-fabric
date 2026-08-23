from pathlib import Path
import json, sys, tempfile, unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "release/tooling"))

from common import ReleaseError
from publish_github import classify_release
from pypi_integrity import publisher_bindings, publisher_identity_matches
from pypi_precheck import classify_files, publish_matrix_for_missing, validate_provider_receipt


class W9ProviderSemantics(unittest.TestCase):
    def test_release_no_provider_state(self):
        expected = {"a.whl": "1" * 64}
        got = classify_release({"release": None, "tag_commit": None, "asset_hashes": {}}, "a" * 40, expected)
        self.assertEqual(got["state"], "NO_RELEASE")

    def test_tag_without_release_blocks(self):
        expected = {"a.whl": "1" * 64}
        got = classify_release({"release": None, "tag_commit": "a" * 40, "asset_hashes": {}}, "a" * 40, expected)
        self.assertEqual(got["state"], "BLOCK_PROVIDER_MISMATCH")

    def test_draft_exact(self):
        expected = {"a.whl": "1" * 64}
        release = {"isDraft": True, "targetCommitish": "a" * 40}
        got = classify_release({"release": release, "tag_commit": None, "asset_hashes": dict(expected)}, "a" * 40, expected)
        self.assertEqual(got["state"], "DRAFT_EXACT")

    def test_draft_unexpected_blocks(self):
        expected = {"a.whl": "1" * 64}
        release = {"isDraft": True, "targetCommitish": "a" * 40}
        got = classify_release(
            {"release": release, "tag_commit": None, "asset_hashes": {"a.whl": "1" * 64, "evil": "2" * 64}},
            "a" * 40,
            expected,
        )
        self.assertEqual(got["state"], "BLOCK_ARTIFACT_SET")

    def test_published_requires_immutable(self):
        expected = {"a.whl": "1" * 64}
        release = {"isDraft": False, "isImmutable": False}
        got = classify_release({"release": release, "tag_commit": "a" * 40, "asset_hashes": dict(expected)}, "a" * 40, expected)
        self.assertEqual(got["state"], "BLOCK_PROVIDER_MISMATCH")

    def test_published_exact(self):
        expected = {"a.whl": "1" * 64}
        release = {"isDraft": False, "isImmutable": True}
        got = classify_release({"release": release, "tag_commit": "a" * 40, "asset_hashes": dict(expected)}, "a" * 40, expected)
        self.assertEqual(got["state"], "PUBLISHED_EXACT")

    def test_pypi_partial_is_explicit(self):
        intended = {"a.whl": {"sha256": "1"}, "a.tar.gz": {"sha256": "2"}}
        observed = {"a.whl": {"sha256": "1", "trusted_publisher": True}}
        self.assertEqual(classify_files(intended, observed)["state"], "PARTIAL_PYPI_PUBLICATION")

    def test_pypi_wrong_hash_is_incident(self):
        intended = {"a.whl": {"sha256": "1"}}
        observed = {"a.whl": {"sha256": "2", "trusted_publisher": True}}
        self.assertEqual(classify_files(intended, observed)["state"], "INCIDENT")

    def test_publisher_binding_map_is_exact_and_unique(self):
        bindings = publisher_bindings()
        self.assertEqual(len(bindings), 11)
        self.assertEqual(bindings["qcax-fabric-contracts"]["environment"], "pypi")
        self.assertEqual(len({row["environment"] for row in bindings.values()}), 11)

    def test_integrity_identity_requires_full_tuple(self):
        provenance = {
            "version": 1,
            "attestation_bundles": [
                {
                    "publisher": {
                        "kind": "GitHub",
                        "repository": "qcax/qcax-fabric",
                        "workflow": "pypi-publish.yml",
                        "environment": "pypi-sdk",
                    }
                }
            ],
        }
        self.assertTrue(publisher_identity_matches(provenance, "qcax/qcax-fabric", "pypi-publish.yml", "pypi-sdk"))
        self.assertFalse(publisher_identity_matches(provenance, "qcax/qcax-fabric", "pypi-publish.yml", "pypi-host"))

    def test_integrity_identity_rejects_extra_publisher_bundle(self):
        publisher = {
            "kind": "GitHub",
            "repository": "qcax/qcax-fabric",
            "workflow": "pypi-publish.yml",
            "environment": "pypi",
        }
        provenance = {"version": 1, "attestation_bundles": [{"publisher": dict(publisher)}, {"publisher": dict(publisher)}]}
        self.assertFalse(publisher_identity_matches(provenance, "qcax/qcax-fabric", "pypi-publish.yml", "pypi"))

    def test_missing_matrix_uses_exact_project_environment(self):
        missing = ["sdk.whl", "host.tar.gz"]
        project_for = {"sdk.whl": "qcax-fabric-sdk", "host.tar.gz": "qcax-fabric-host"}
        matrix = publish_matrix_for_missing(missing, project_for)
        self.assertEqual(
            matrix,
            {
                "include": [
                    {"project": "qcax-fabric-sdk", "environment": "pypi-sdk"},
                    {"project": "qcax-fabric-host", "environment": "pypi-host"},
                ]
            },
        )

    def test_provider_receipt_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "r.json"
            path.write_text(json.dumps({"schema": "qcax.provider-configuration-receipt/1", "overall": "HOLD"}), encoding="utf-8")
            with self.assertRaises(ReleaseError):
                validate_provider_receipt(path, "qcax/qcax-fabric", "a" * 40)

    def test_provider_receipt_requires_exact_project_environment_map(self):
        bindings = publisher_bindings()
        receipt = {
            "schema": "qcax.provider-configuration-receipt/1",
            "overall": "PASS",
            "repository": "qcax/qcax-fabric",
            "observed_commit": "a" * 40,
            "observed_utc": "2026-08-23T23:00:00Z",
            "github": {
                "actions_sha_pinning_required": True,
                "immutable_releases": True,
                "main_ruleset_required_checks_verified": True,
                "github_release_environment_verified": True,
                "pypi_environments_verified": True,
            },
            "pypi": {
                "workflow": ".github/workflows/pypi-publish.yml",
                "environment_model": "per-project",
                "projects": [
                    {
                        "name": name,
                        "repository": "qcax/qcax-fabric",
                        "workflow": "pypi-publish.yml",
                        "environment": row["environment"],
                        "trusted_publisher_verified": True,
                    }
                    for name, row in bindings.items()
                ],
            },
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "r.json"
            path.write_text(json.dumps(receipt), encoding="utf-8")
            validate_provider_receipt(path, "qcax/qcax-fabric", "a" * 40)
            receipt["pypi"]["projects"][1]["environment"] = "pypi"
            path.write_text(json.dumps(receipt), encoding="utf-8")
            with self.assertRaises(ReleaseError):
                validate_provider_receipt(path, "qcax/qcax-fabric", "a" * 40)


if __name__ == "__main__":
    unittest.main()
