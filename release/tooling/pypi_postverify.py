from pathlib import Path
import argparse, json, os, subprocess, sys, tempfile, urllib.error, urllib.request, venv
from common import ReleaseError, load_json, require_commit, sha256_file
from verify_github_release import verify_release

ROOT=Path(__file__).resolve().parents[2]

def fetch_json(url):
    req=urllib.request.Request(url,headers={"User-Agent":"QCAX-W9-PyPI-Postverify/1"})
    try:
        with urllib.request.urlopen(req,timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise ReleaseError(f"PyPI HTTP {e.code}: {url}") from e

def download(url,path):
    req=urllib.request.Request(url,headers={"User-Agent":"QCAX-W9-PyPI-Postverify/1"})
    with urllib.request.urlopen(req,timeout=60) as r:
        Path(path).write_bytes(r.read())

def live_index_install(projects,version):
    with tempfile.TemporaryDirectory() as td:
        td=Path(td); envdir=td/"venv"
        venv.EnvBuilder(with_pip=True,clear=True).create(envdir)
        py=envdir/("Scripts/python.exe" if os.name=="nt" else "bin/python")
        specs=[f"{p}=={version}" for p in projects]
        p=subprocess.run([str(py),"-m","pip","install","--disable-pip-version-check","--index-url","https://pypi.org/simple",*specs],
                         capture_output=True,text=True,timeout=300)
        if p.returncode:
            raise ReleaseError("live-index install failed: "+p.stderr[-2000:])
        code="import importlib.metadata as m,json; ds={d.metadata['Name'].lower():d.version for d in m.distributions()}; eps=list(m.entry_points(group='qcax.fabric.plugins')); print(json.dumps({'entry_points':len(eps),'versions':ds}))"
        q=subprocess.run([str(py),"-c",code],capture_output=True,text=True,timeout=60)
        if q.returncode:
            raise ReleaseError("live-index metadata canary failed: "+q.stderr[-1200:])
        data=json.loads(q.stdout)
        if any(data["versions"].get(p)!=version for p in projects) or data["entry_points"]!=8:
            raise ReleaseError("live-index installed identity mismatch")
        return {"status":"PASS","projects":len(projects),"entry_points":data["entry_points"]}

def postverify(tag,commit,repository):
    commit=require_commit(commit)
    if not repository.startswith("https://github.com/"):
        raise ReleaseError("canonical repository URL required")
    repo=repository.removeprefix("https://github.com/").rstrip("/")
    with tempfile.TemporaryDirectory() as td:
        td=Path(td); expected=td/"github-release"; expected.mkdir()
        p=subprocess.run(["gh","release","download",tag,"--repo",repo,"--dir",str(expected)],capture_output=True,text=True,timeout=180)
        if p.returncode:
            raise ReleaseError("GitHub release download failed: "+p.stderr[-1200:])
        verify_release(expected,repo,tag,commit)
        lock=load_json(expected/"release-lock.json")
        entries=lock.get("entries") or []
        projects=[e["distribution_name"] for e in entries]
        if len(entries)!=11 or len(set(projects))!=11:
            raise ReleaseError("release lock package set mismatch")
        version=entries[0]["distribution_version"]
        downloaded=td/"pypi"; downloaded.mkdir()
        rows=[]
        for e in entries:
            data=fetch_json(f"https://pypi.org/pypi/{e['distribution_name']}/{version}/json")
            urls=data.get("urls") or []
            by={x.get("filename"):x for x in urls}
            for n,hkey in ((e["wheel_filename"],"wheel_sha256"),(e["sdist_filename"],"sdist_sha256")):
                row=by.get(n)
                if row is None:
                    raise ReleaseError("published PyPI file absent: "+n)
                digest=(row.get("digests") or {}).get("sha256")
                if digest!=e[hkey]:
                    raise ReleaseError("PyPI digest mismatch: "+n)
                path=downloaded/n; download(row["url"],path)
                if sha256_file(path)!=e[hkey]:
                    raise ReleaseError("downloaded PyPI file hash mismatch: "+n)
                v=subprocess.run(["pypi-attestations","verify","pypi","--repository",repository,"pypi:"+n],
                                 capture_output=True,text=True,timeout=120)
                if v.returncode:
                    raise ReleaseError("PyPI provenance verification failed: "+n+" :: "+v.stderr[-1000:])
                rows.append({"name":n,"sha256":e[hkey],"pep740":"PASS"})
        for rel in ("conformance/run_exact_wheel_canaries.py","conformance/run_out_of_tree_canary.py"):
            q=subprocess.run([sys.executable,str(ROOT/rel),str(downloaded)],cwd=str(ROOT),capture_output=True,text=True,timeout=300)
            if q.returncode:
                raise ReleaseError(rel+" failed on PyPI-downloaded wheels: "+q.stderr[-1600:]+" "+q.stdout[-1600:])
        live=live_index_install(projects,version)
        return {"status":"PASS","overall_state":"PYPI_POSTVERIFY_PASS","projects":len(projects),"files":len(rows),"pep740_verified":len(rows),"live_index":live}

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--tag",required=True); ap.add_argument("--commit",required=True); ap.add_argument("--repository",required=True)
    a=ap.parse_args()
    print(json.dumps(postverify(a.tag,a.commit,a.repository),sort_keys=True))
