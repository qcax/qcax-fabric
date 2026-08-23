#!/usr/bin/env python3
from pathlib import Path
import json,os,shutil,subprocess,sys,tempfile
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
ENV={**os.environ,"PYTHONDONTWRITEBYTECODE":"1"}

def run(root):
    return subprocess.run([sys.executable,str(root/"tools/validate_w9_provider.py")],cwd=str(root),env=ENV,capture_output=True,text=True,timeout=60)

def main():
    with tempfile.TemporaryDirectory() as td:
        r=Path(td)/"r"; shutil.copytree(ROOT,r); cases=[]
        def mutate(mid,rel,old,new):
            p=r/rel; before=p.read_bytes()
            try:
                s=p.read_text(encoding="utf-8")
                if old not in s: raise RuntimeError(mid+" anchor missing")
                p.write_text(s.replace(old,new,1),encoding="utf-8")
                q=run(r); cases.append({"id":mid,"killed":q.returncode!=0})
            finally:
                p.write_bytes(before)
        mutate("W9_REMOVE_REPLAY_DOWNLOAD",".github/workflows/release-replay.yml","gh release download","echo disabled-release-download")
        mutate("W9_DROP_PUBLISHED_ARG",".github/workflows/release-replay.yml","--published published-assets","--published-disabled published-assets")
        mutate("W9_ADD_UNSUPPORTED_FINALIZE_FLAG",".github/workflows/release-replay.yml","finalize_payload.py replay-assets","finalize_payload.py replay-assets --replay")
        mutate("W9_DROP_REPLAY_SOURCE_BINDING",".github/workflows/release-replay.yml","QCAX_EXPECTED_COMMIT: ${{ github.sha }}","QCAX_EXPECTED_COMMIT_DISABLED: ${{ github.sha }}")
        mutate("W9_UNPIN_PYPI_ATTEST","requirements/release-verify.txt","pypi-attestations==0.0.30","pypi-attestations>=0")
        mutate("W9_PROMOTE_TEMPLATE","history/evidence/W9_PROVIDER_CONFIGURATION_TEMPLATE.json",'"overall": "HOLD"','"overall": "PASS"')
        mutate("W9_FAKE_OBSERVED_COMMIT","history/evidence/W9_PROVIDER_CONFIGURATION_TEMPLATE.json",'"observed_commit": null','"observed_commit": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"')
        mutate("W9_REMOVE_REREAD","release/tooling/publish_github.py","state = reread()","state = {\"classification\":{\"state\":\"DRAFT_EXACT\"}}")
        mutate("W9_REMOVE_MUTATION_FAMILY","conformance/run_mutations.py"," 'tests/release/test_w9_provider_mutations.py',\n","")
        mutate("W9_REMOVE_RUNALL_FAMILY","tools/run_all.py"," [sys.executable,str(ROOT/'tests/release/test_w9_provider_mutations.py')],\n","")
        mutate("W9_SYNTAX_BREAK","release/tooling/pypi_postverify.py","def postverify(tag,commit,repository):","def postverify(tag,commit,repository)")
        clean=run(r)
        survivors=[x["id"] for x in cases if not x["killed"]]
        result={"status":"PASS" if not survivors and clean.returncode==0 else "FAIL","mutations":len(cases),"killed":sum(x["killed"] for x in cases),"survivors":survivors,"post_restore_validator_returncode":clean.returncode}
        print(json.dumps(result,sort_keys=True))
        if result["status"]!="PASS": raise SystemExit(1)
if __name__=="__main__": main()
