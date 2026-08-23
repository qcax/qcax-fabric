from common import *
def classify_files(intended,observed):
 exact=[]; missing=[]; mismatch=[]
 for n,e in intended.items():
  o=observed.get(n)
  if o is None: missing.append(n)
  elif o.get("sha256")!=e.get("sha256") or o.get("trusted_publisher") is not True: mismatch.append(n)
  else: exact.append(n)
 unexpected=[n for n in observed if n not in intended]
 state="INCIDENT" if mismatch or unexpected else ("PYPI_EXACT" if not missing else ("PARTIAL_PYPI_PUBLICATION" if exact else "PYPI_ALL_MISSING"))
 return {"state":state,"exact":sorted(exact),"missing":sorted(missing),"mismatch":sorted(mismatch),"unexpected":sorted(unexpected)}
def publish_attempt_with_reconciliation(mutate,reread,intended): return attempt_then_reconcile(mutate,reread,lambda x:classify_files(intended,x))
if __name__=="__main__": raise ReleaseError("live PyPI precheck is W9")
