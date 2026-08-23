from pathlib import Path
import argparse,json,os
from common import *
from build_candidate import SOURCE_COMMIT,SOURCE_TREE
ROOT=Path(__file__).resolve().parents[2]
PRIMARY_EXCLUDE={'payload-manifest.json','SHA256SUMS'}
def finalize(root:Path):
    root=Path(root)
    files=sorted([p for p in root.iterdir() if p.is_file() and p.name not in PRIMARY_EXCLUDE],key=lambda p:p.name)
    contract=load_json(ROOT/'release/policy/release-contract.json')
    manifest={'schema':'qcax.payload-manifest/clean-slate-v1','source_commit':os.environ.get('QCAX_EXPECTED_COMMIT') or SOURCE_COMMIT,
      'source_tree':os.environ.get('QCAX_SOURCE_TREE') or SOURCE_TREE,'release_tag':os.environ.get('QCAX_RELEASE_TAG','v0.1.0-alpha.1'),
      'package_set_digest_sha256':contract['artifact_set'].get('package_set_digest_sha256') or load_json(ROOT/'release/policy/artifact-set.json')['package_set_digest_sha256'],
      'run_id':os.environ.get('GITHUB_RUN_ID','LOCAL_W8'),'run_attempt':os.environ.get('GITHUB_RUN_ATTEMPT','1'),
      'members':[{'name':p.name,'bytes':p.stat().st_size,'sha256':sha256_file(p)} for p in files]}
    write_json(root/'payload-manifest.json',manifest)
    checksum_files=files+[root/'payload-manifest.json']
    (root/'SHA256SUMS').write_text(''.join(f'{sha256_file(p)}  {p.name}\n' for p in sorted(checksum_files,key=lambda p:p.name)),encoding='utf-8')
    return manifest
if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('root'); a=ap.parse_args(); m=finalize(Path(a.root)); print(json.dumps({'status':'PASS','members':len(m['members'])},sort_keys=True))
