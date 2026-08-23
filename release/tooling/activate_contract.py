#!/usr/bin/env python3
from pathlib import Path
import argparse,json
from common import ReleaseError,load_json,require_commit

ROOT=Path(__file__).resolve().parents[2]
CONTRACT=ROOT/'release/policy/release-contract.json'

def verify_activation(c,tag,commit):
 require_commit(commit)
 if not isinstance(tag,str) or not tag:
  raise ReleaseError('exact release tag required')
 r=c.get('release_identity',{})
 if r.get('status')!='ACTIVE':
  raise ReleaseError('release identity is not ACTIVE')
 version=r.get('selected_version')
 if tag!=r.get('selected_tag') or not isinstance(version,str) or not version:
  raise ReleaseError('release identity mismatch')
 return {'commit':commit,'status':'ACTIVE','tag':tag,'version':version}

def main():
 p=argparse.ArgumentParser(description='Fail-closed QCAX release-contract activation verifier')
 p.add_argument('--tag',required=True)
 p.add_argument('--commit',required=True)
 p.add_argument('--verify-only',action='store_true')
 a=p.parse_args()
 if not a.verify_only:
  raise ReleaseError('--verify-only is required; this tool performs no provider or repository mutation')
 result=verify_activation(load_json(CONTRACT),a.tag,a.commit)
 print(json.dumps(result,sort_keys=True,separators=(',',':')))

if __name__=='__main__':
 main()
