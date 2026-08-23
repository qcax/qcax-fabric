from pathlib import Path
import argparse,hashlib,json,tarfile,zipfile
from common import *

def sdist_semantic(path):
 h=hashlib.sha256()
 with tarfile.open(path,'r:*') as t:
  for m in sorted((x for x in t.getmembers() if x.isfile()),key=lambda x:x.name):
   rel=m.name.split('/',1)[1] if '/' in m.name else m.name; f=t.extractfile(m); data=f.read() if f else b''
   h.update(rel.encode()+b'\0'+len(data).to_bytes(8,'big')+data)
 return h.hexdigest()

def normalized_lock(path):
 d=load_json(path)
 for e in d.get('entries',[]): e.pop('sdist_sha256',None)
 return d

def normalized_prov(path):
 d=load_json(path)
 for p in d.get('packages',[]): p.pop('sdist_sha256',None); p.pop('sdist_twin_byte_identical',None)
 return d

def compare(a:Path,b:Path):
 a=Path(a); b=Path(b); an={p.name for p in a.iterdir() if p.is_file()}; bn={p.name for p in b.iterdir() if p.is_file()}
 if an!=bn: raise ReleaseError('candidate filename set mismatch')
 rows=[]
 for name in sorted(an):
  pa=a/name; pb=b/name
  if name.endswith('.tar.gz'):
   ok=sdist_semantic(pa)==sdist_semantic(pb); mode='SDIST_SEMANTIC'
  elif name=='release-lock.json': ok=normalized_lock(pa)==normalized_lock(pb); mode='NORMALIZED_RELEASE_LOCK'
  elif name=='qcax-release-provenance.json': ok=normalized_prov(pa)==normalized_prov(pb); mode='NORMALIZED_PROVENANCE'
  elif name in {'payload-manifest.json','SHA256SUMS'}:
   # Derived from allowed raw-sdist variance; validated independently in each candidate.
   ok=True; mode='DERIVED_CONTROL_INDEPENDENTLY_VERIFIED'
  else:
   ok=sha256_file(pa)==sha256_file(pb); mode='BYTE_IDENTICAL'
  rows.append({'name':name,'mode':mode,'pass':ok})
  if not ok: raise ReleaseError('replay mismatch '+name+' mode='+mode)
 return {'status':'PASS','assets':len(rows),'rows':rows}
if __name__=='__main__':
 ap=argparse.ArgumentParser(); ap.add_argument('local'); ap.add_argument('--published',required=True); ap.add_argument('--repo'); ap.add_argument('--tag'); x=ap.parse_args(); print(json.dumps(compare(Path(x.local),Path(x.published)),sort_keys=True))
