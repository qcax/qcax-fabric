from pathlib import Path
import argparse,shutil,zipfile
from common import ReleaseError
def prepare(candidate:Path,out:Path):
    if out.exists(): shutil.rmtree(out)
    out.mkdir(parents=True)
    wheels=sorted(candidate.glob('*.whl'))
    if not wheels: raise ReleaseError('no wheels')
    for w in wheels:
        d=out/w.name[:-4]; d.mkdir()
        with zipfile.ZipFile(w) as z:
            for n in z.namelist():
                if n.startswith('/') or '..' in Path(n).parts or '\\' in n: raise ReleaseError('unsafe wheel path')
            z.extractall(d)
    return len(wheels)
if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('candidate'); ap.add_argument('out'); a=ap.parse_args(); print(prepare(Path(a.candidate),Path(a.out)))
