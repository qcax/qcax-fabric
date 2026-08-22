from pathlib import Path
import hashlib, importlib.metadata as md, json, sys, zipfile
from email.parser import Parser
from qcax_fabric_sdk import make_installation_receipt
from qcax_fabric_sdk.installation import installed_image_digest_from_record


def wheel_metadata(wheel: Path):
    with zipfile.ZipFile(wheel) as z:
        name = next(n for n in z.namelist() if n.endswith('.dist-info/METADATA'))
        m = Parser().parsestr(z.read(name).decode('utf-8'))
    return m['Name'], m['Version']


def verify(wheel: Path, root: Path):
    name, version = wheel_metadata(wheel)
    dist = md.distribution(name)
    files = list(dist.files or [])
    plugin_ids=[]
    for f in files:
        if str(f).endswith('qcax-plugin.json'):
            try: plugin_ids.append(json.loads(dist.locate_file(f).read_text(encoding='utf-8'))['plugin_id'])
            except Exception as exc: return {'status':'FAIL','errors':[f'plugin-descriptor:{type(exc).__name__}:{exc}'],'wheel':wheel.name}
    plugin_ids=sorted(set(plugin_ids))
    rec = next((f for f in files if str(f).endswith('.dist-info/RECORD')), None)
    if rec is None:
        return {'status':'FAIL','errors':['installed-RECORD-missing'],'wheel':wheel.name}
    record_path = Path(dist.locate_file(rec))
    site_root = Path(dist.locate_file(''))
    digest = installed_image_digest_from_record(record_path)
    try:
        receipt = make_installation_receipt(
            name, version, record_path, site_root, digest,
            f'installed:{name}:{version}', str(site_root), wheel,
        )
        return {
            'status':'PASS',
            'wheel':wheel.name,
            'wheel_sha256':hashlib.sha256(wheel.read_bytes()).hexdigest(),
            'wheel_bytes':wheel.stat().st_size,
            'installed_image_sha256':receipt.installed_image_sha256,
            'verified_record_entries':receipt.verified_record_entries,
            'verified_bytes':receipt.verified_bytes,
            'installation_receipt':receipt.public_record(),
            'plugin_ids':plugin_ids,
            'distribution_name':name,
            'distribution_version':version,
            'errors':[],
        }
    except Exception as exc:
        return {'status':'FAIL','wheel':wheel.name,'errors':[f'{type(exc).__name__}:{exc}']}


if __name__=='__main__':
    if len(sys.argv)!=3: raise SystemExit('usage: verify_installed_wheel.py WHEEL SITE_PACKAGES')
    r=verify(Path(sys.argv[1]),Path(sys.argv[2])); print(json.dumps(r,sort_keys=True)); raise SystemExit(0 if r['status']=='PASS' else 1)
