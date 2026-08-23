from pathlib import Path
import sys, tempfile, json, unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"release/tooling"))
from publish_github import classify_release
from pypi_precheck import classify_files, validate_provider_receipt
from common import ReleaseError

class W9ProviderSemantics(unittest.TestCase):
    def test_release_no_provider_state(self):
        e={"a.whl":"1"*64}
        got=classify_release({"release":None,"tag_commit":None,"asset_hashes":{}}, "a"*40, e)
        self.assertEqual(got["state"],"NO_RELEASE")

    def test_tag_without_release_blocks(self):
        e={"a.whl":"1"*64}
        got=classify_release({"release":None,"tag_commit":"a"*40,"asset_hashes":{}}, "a"*40, e)
        self.assertEqual(got["state"],"BLOCK_PROVIDER_MISMATCH")

    def test_draft_exact(self):
        e={"a.whl":"1"*64}
        rel={"isDraft":True,"targetCommitish":"a"*40}
        got=classify_release({"release":rel,"tag_commit":None,"asset_hashes":dict(e)}, "a"*40, e)
        self.assertEqual(got["state"],"DRAFT_EXACT")

    def test_draft_unexpected_blocks(self):
        e={"a.whl":"1"*64}
        rel={"isDraft":True,"targetCommitish":"a"*40}
        got=classify_release({"release":rel,"tag_commit":None,"asset_hashes":{"a.whl":"1"*64,"evil":"2"*64}}, "a"*40, e)
        self.assertEqual(got["state"],"BLOCK_ARTIFACT_SET")

    def test_published_requires_immutable(self):
        e={"a.whl":"1"*64}
        rel={"isDraft":False,"isImmutable":False}
        got=classify_release({"release":rel,"tag_commit":"a"*40,"asset_hashes":dict(e)}, "a"*40, e)
        self.assertEqual(got["state"],"BLOCK_PROVIDER_MISMATCH")

    def test_published_exact(self):
        e={"a.whl":"1"*64}
        rel={"isDraft":False,"isImmutable":True}
        got=classify_release({"release":rel,"tag_commit":"a"*40,"asset_hashes":dict(e)}, "a"*40, e)
        self.assertEqual(got["state"],"PUBLISHED_EXACT")

    def test_pypi_partial_is_explicit(self):
        intended={"a.whl":{"sha256":"1"},"a.tar.gz":{"sha256":"2"}}
        observed={"a.whl":{"sha256":"1","trusted_publisher":True}}
        self.assertEqual(classify_files(intended,observed)["state"],"PARTIAL_PYPI_PUBLICATION")

    def test_pypi_wrong_hash_is_incident(self):
        intended={"a.whl":{"sha256":"1"}}
        observed={"a.whl":{"sha256":"2","trusted_publisher":True}}
        self.assertEqual(classify_files(intended,observed)["state"],"INCIDENT")

    def test_provider_receipt_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"r.json"
            p.write_text(json.dumps({"schema":"qcax.provider-configuration-receipt/1","overall":"HOLD"}),encoding="utf-8")
            with self.assertRaises(ReleaseError):
                validate_provider_receipt(p,"qcax/qcax-fabric","a"*40)

if __name__=="__main__":
    unittest.main()
