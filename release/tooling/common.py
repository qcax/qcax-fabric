from pathlib import Path
import hashlib,json,re
HEX40=re.compile(r"^[0-9a-f]{40}$")
HEX64=re.compile(r"^[0-9a-f]{64}$")
class ReleaseError(RuntimeError): pass
def load_json(p): return json.loads(Path(p).read_text(encoding="utf-8"))
def sha256_file(p):
 h=hashlib.sha256();
 with Path(p).open("rb") as f:
  for b in iter(lambda:f.read(1048576),b""): h.update(b)
 return h.hexdigest()
def require_commit(x):
 if not isinstance(x,str) or not HEX40.fullmatch(x): raise ReleaseError("exact 40-hex commit required")
 return x
def require_sha256(x):
 if isinstance(x,str) and x.startswith("sha256:"): x=x[7:]
 if not isinstance(x,str) or not HEX64.fullmatch(x): raise ReleaseError("sha256 digest required")
 return x
def package_rows(c): return [x for x in c["package_set"]["packages"] if x.get("publish")]
def expected_asset_count(c): return 2*len(package_rows(c))+len(c["artifact_set"]["singleton_controls"])
def attempt_then_reconcile(mutate,reread,classify):
 err=None
 try: mutate()
 except Exception as e: err=f"{type(e).__name__}: {e}"
 snap=reread()
 return {"mutation_error":err,"snapshot":snap,"classification":classify(snap)}

def write_json(p,obj):
 Path(p).write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n",encoding="utf-8")
