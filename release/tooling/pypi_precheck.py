from pathlib import Path
import argparse, json, os, shutil, subprocess, tempfile, urllib.error, urllib.request
from common import ReleaseError, load_json, require_commit
from provider import download_run_artifact, workflow_run
from verify_github_release import verify_release

ROOT = Path(__file__).resolve().parents[2]
PROJECTS = [x["name"] for x in load_json(ROOT / "release/policy/release-contract.json")["package_set"]["packages"] if x.get("publish")]

def classify_files(intended, observed):
    exact=[]; missing=[]; mismatch=[]
    for n,e in intended.items():
        o=observed.get(n)
        if o is None: missing.append(n)
        elif o.get("sha256")!=e.get("sha256") or o.get("trusted_publisher") is not True: mismatch.append(n)
        else: exact.append(n)
    unexpected=[n for n in observed if n not in intended]
    state="INCIDENT" if mismatch or unexpected else ("PYPI_EXACT" if not missing else ("PARTIAL_PYPI_PUBLICATION" if exact else "PYPI_ALL_MISSING"))
    return {"state":state,"exact":sorted(exact),"missing":sorted(missing),"mismatch":sorted(mismatch),"unexpected":sorted(unexpected)}

def validate_provider_receipt(path: Path, repo: str, commit: str):
    path = Path(path)
    if not path.is_file():
        raise ReleaseError("current W9 provider-configuration receipt required before PyPI precheck")
    d = load_json(path)
    if d.get("schema") != "qcax.provider-configuration-receipt/1" or d.get("overall") != "PASS":
        raise ReleaseError("provider-configuration receipt is not PASS")
    if d.get("repository") != repo or d.get("observed_commit") != commit:
        raise ReleaseError("provider-configuration receipt source binding mismatch")
    if not isinstance(d.get("observed_utc"), str) or not d.get("observed_utc"):
        raise ReleaseError("provider-configuration receipt observation timestamp required")
    gh = d.get("github") or {}
    required_github = (
        "actions_sha_pinning_required",
        "immutable_releases",
        "main_ruleset_required_checks_verified",
        "github_release_environment_verified",
        "pypi_environment_verified",
    )
    if any(gh.get(k) is not True for k in required_github):
        raise ReleaseError("all GitHub provider-configuration gates must be directly verified")
    pypi = d.get("pypi") or {}
    if pypi.get("workflow") != ".github/workflows/pypi-publish.yml" or pypi.get("environment") != "pypi":
        raise ReleaseError("PyPI publisher workflow/environment mismatch")
    rows = pypi.get("projects") or []
    by = {x.get("name"): x for x in rows}
    if len(rows) != len(PROJECTS) or len(by) != len(PROJECTS) or set(by) != set(PROJECTS) or any(x.get("trusted_publisher_verified") is not True for x in by.values()):
        raise ReleaseError("all eleven exact Trusted Publisher bindings must be directly verified")
    return d

def pypi_json(project):
    url = f"https://pypi.org/pypi/{project}/json"
    req = urllib.request.Request(url, headers={"User-Agent":"QCAX-W9-PyPI-Precheck/1"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return 404, None
        raise ReleaseError(f"PyPI HTTP {e.code} for {project}") from e

def verify_pypi_provenance(filename, repository_url):
    p = subprocess.run(
        ["pypi-attestations","verify","pypi","--repository",repository_url,"pypi:"+filename],
        capture_output=True,text=True,timeout=120
    )
    return p.returncode == 0

def observed_project(project, version, intended_names, repository_url):
    status, data = pypi_json(project)
    if status == 404:
        return {}
    files = (data.get("releases") or {}).get(version) or []
    rows = {}
    for f in files:
        name = f.get("filename")
        if not name:
            continue
        if name in rows:
            rows[name] = {"sha256":"DUPLICATE","trusted_publisher":False}
            continue
        digest = ((f.get("digests") or {}).get("sha256"))
        rows[name] = {"sha256":digest, "trusted_publisher": verify_pypi_provenance(name, repository_url) if name in intended_names else False}
    return rows

def verify_replay(repo, tag, commit, replay_run_id, dest):
    run = workflow_run(repo, replay_run_id)
    if run.get("status")!="completed" or run.get("conclusion")!="success" or run.get("event")!="release" or run.get("head_sha")!=commit:
        raise ReleaseError("replay workflow run identity/status mismatch")
    name=f"qcax-replay-receipt-{tag}"
    download_run_artifact(repo,replay_run_id,name,dest)
    files=[p for p in Path(dest).rglob("*") if p.is_file()]
    if len(files)!=1 or files[0].name!="replay-receipt.json":
        raise ReleaseError("replay receipt artifact content mismatch")
    rr=load_json(files[0])
    if rr.get("stage")!="replay" or rr.get("overall_state")!="REPLAY_PASS" or rr.get("source_commit")!=commit or rr.get("release_tag")!=tag:
        raise ReleaseError("replay receipt binding mismatch")
    return rr

def precheck(repo, tag, commit, replay_run_id, confirmation, missing_out, github_output, provider_receipt):
    commit=require_commit(commit)
    if confirmation != "PYPI-"+tag:
        raise ReleaseError("explicit PyPI confirmation mismatch")
    contract=load_json(ROOT/"release/policy/release-contract.json")
    ident=contract.get("release_identity") or {}
    if ident.get("status")!="ACTIVE" or ident.get("selected_tag")!=tag:
        raise ReleaseError("release identity not activated for requested tag")
    version=ident.get("selected_version")
    validate_provider_receipt(provider_receipt,repo,commit)
    repository_url="https://github.com/"+repo
    with tempfile.TemporaryDirectory() as td:
        td=Path(td); assets=td/"release-assets"; assets.mkdir()
        q=subprocess.run(["gh","release","download",tag,"--repo",repo,"--dir",str(assets)],capture_output=True,text=True,timeout=180)
        if q.returncode:
            raise ReleaseError("GitHub release download failed: "+q.stderr[-1200:])
        verify_release(assets,repo,tag,commit)
        verify_replay(repo,tag,commit,replay_run_id,td/"replay-receipt")
        lock=load_json(assets/"release-lock.json")
        intended={}
        project_for={}
        for e in lock.get("entries") or []:
            for key,hkey in (("wheel_filename","wheel_sha256"),("sdist_filename","sdist_sha256")):
                n=e[key]; intended[n]={"sha256":e[hkey]}; project_for[n]=e["distribution_name"]
        observed={}
        for project in PROJECTS:
            names={n for n,p in project_for.items() if p==project}
            observed.update(observed_project(project,version,names,repository_url))
        result=classify_files(intended,observed)
        if result["state"]=="INCIDENT":
            raise ReleaseError("PyPI precheck incident: "+json.dumps(result,sort_keys=True))
        out=Path(missing_out)
        if out.exists(): shutil.rmtree(out)
        out.mkdir(parents=True)
        for n in result["missing"]:
            shutil.copy2(assets/n,out/n)
        publish_required=bool(result["missing"])
        if github_output:
            with Path(github_output).open("a",encoding="utf-8") as f:
                f.write("publish_required="+("true" if publish_required else "false")+"\n")
        result.update({"status":"PASS","publish_required":publish_required,"missing_count":len(result["missing"])})
        return result

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo",required=True); ap.add_argument("--tag",required=True); ap.add_argument("--commit",required=True)
    ap.add_argument("--replay-run-id",required=True); ap.add_argument("--confirmation",required=True)
    ap.add_argument("--missing-out",required=True); ap.add_argument("--github-output")
    ap.add_argument("--provider-receipt",default="history/evidence/W9_PROVIDER_CONFIGURATION.json")
    a=ap.parse_args()
    print(json.dumps(precheck(a.repo,a.tag,a.commit,a.replay_run_id,a.confirmation,a.missing_out,a.github_output,Path(a.provider_receipt)),sort_keys=True))
