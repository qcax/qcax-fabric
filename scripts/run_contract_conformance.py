from pathlib import Path
import json, sys
from contract_conformance_lib import run_contract_conformance
ROOT=Path(__file__).resolve().parents[1]
r=run_contract_conformance(ROOT)
print(json.dumps(r,sort_keys=True))
sys.exit(0 if r['status']=='PASS' else 1)
