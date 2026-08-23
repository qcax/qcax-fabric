from pathlib import Path
from common import *
ROOT=Path(__file__).resolve().parents[2]
def verify_activation(c,tag,commit):
 require_commit(commit); r=c["release_identity"]
 if r.get("status")!="ACTIVE": raise ReleaseError("release identity is not ACTIVE")
 if tag!=r.get("selected_tag") or not r.get("selected_version"): raise ReleaseError("release identity mismatch")
 return {"tag":tag,"version":r["selected_version"],"commit":commit}
if __name__=="__main__": raise ReleaseError("release identity HOLD until W8 semantic continuity gate")
