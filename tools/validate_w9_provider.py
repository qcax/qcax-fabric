#!/usr/bin/env python3
from pathlib import Path
import json, sys
ROOT=Path(__file__).resolve().parents[1]
errors=[]; checks=0
def ck(c,m):
    global checks; checks+=1
    if not c: errors.append(m)

required=[
"release/tooling/provider.py","release/tooling/verify_github_attestations.py","release/tooling/record_preflight_receipt.py",
"release/tooling/reconcile_preflight.py","release/tooling/publish_github.py","release/tooling/verify_github_release.py",
"release/tooling/assert_release_event.py","release/tooling/record_replay_receipt.py","release/tooling/pypi_precheck.py","release/tooling/pypi_postverify.py",
"tests/release/test_w9_provider_mutations.py","tests/semantics/test_w9_provider.py",
]
for rel in required:
    p=ROOT/rel; ck(p.is_file(),"missing W9 interface "+rel)
    if p.is_file():
        try: compile(p.read_text(encoding="utf-8"),str(p),"exec")
        except Exception as exc: ck(False,f"{rel} compile: {exc}")

stub_phrases=(" is W9","requires successful W9 replay","exists only after W9 publication")
for rel in required[:10]:
    text=(ROOT/rel).read_text(encoding="utf-8") if (ROOT/rel).is_file() else ""
    ck(not any(x in text for x in stub_phrases),rel+" still contains W9 stub")

replay=(ROOT/".github/workflows/release-replay.yml").read_text(encoding="utf-8")
ck("gh release download" in replay,"replay workflow does not download immutable release assets")
ck("--published published-assets" in replay,"replay workflow does not pass provider-neutral published asset directory")
ck("finalize_payload.py replay-assets --replay" not in replay,"replay workflow passes unsupported --replay flag to finalizer")
ck("QCAX_EXPECTED_COMMIT: ${{ github.sha }}" in replay and "QCAX_RELEASE_TAG: ${{ github.event.release.tag_name }}" in replay,"replay candidate is not explicitly bound to event commit/tag")
ck("qcax-replay-receipt-${{ github.event.release.tag_name }}" in replay,"replay receipt is not uploaded with tag-bound name")

pypi=(ROOT/".github/workflows/pypi-publish.yml").read_text(encoding="utf-8")
ck(pypi.count("requirements/release-verify.txt")>=2,"PyPI precheck/postverify do not both install verifier environment")
ck("GH_TOKEN: ${{ github.token }}" in pypi,"PyPI workflow missing GitHub read token for release/replay verification")
req=(ROOT/"requirements/release-verify.txt").read_text(encoding="utf-8")
ck("pypi-attestations==0.0.30" in req,"pypi-attestations is not exact pinned admitted verifier")

template=json.loads((ROOT/"history/evidence/W9_PROVIDER_CONFIGURATION_TEMPLATE.json").read_text(encoding="utf-8"))
ck(template.get("overall")=="HOLD","provider configuration template must fail closed")
ck(template.get("observed_commit") is None,"provider configuration template must not masquerade as current evidence")
ck(template.get("observed_utc") is None,"provider configuration template must not carry a fake observation timestamp")

mut=(ROOT/"conformance/run_mutations.py").read_text(encoding="utf-8")
runall=(ROOT/"tools/run_all.py").read_text(encoding="utf-8")
ck("test_w9_provider_mutations.py" in mut,"W9 mutation family missing from conformance aggregate")
ck("test_w9_provider_mutations.py" in runall,"W9 mutation family missing from full assurance aggregate")

pub=(ROOT/"release/tooling/publish_github.py").read_text(encoding="utf-8")
ck(pub.count("reread()")>=7 and pub.count("run_mutation(")>=4,"GitHub publisher lacks complete mutation/reread coverage")
for rel in ("release/tooling/provider.py","release/tooling/publish_github.py","release/tooling/pypi_precheck.py","release/tooling/pypi_postverify.py"):
    text=(ROOT/rel).read_text(encoding="utf-8")
    for bad in ("gh ruleset","gh secret","gh variable","/environments/","branch-protection"):
        ck(bad not in text,f"{rel} contains forbidden provider-configuration mutation surface {bad}")

print(json.dumps({"status":"PASS" if not errors else "FAIL","checks":checks,"errors":errors},sort_keys=True))
sys.exit(1 if errors else 0)
