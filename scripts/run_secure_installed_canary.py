from pathlib import Path
import json, os, subprocess, sys, tempfile

ROOT=Path(__file__).resolve().parents[1]
ENV=os.environ.copy(); ENV['PYTHONDONTWRITEBYTECODE']='1'

def run(cmd):
    r=subprocess.run(cmd,cwd='/',env=ENV,text=True,capture_output=True)
    if r.returncode: raise SystemExit(r.stdout+'\n'+r.stderr)
    return r.stdout.strip()

CANARY = r'''import importlib.metadata as md,json,sys
from pathlib import Path
from qcax_fabric_contracts import *
from qcax_fabric_sdk import issue_admission_ticket
from qcax_fabric_sdk.installation import installed_image_digest_from_record
from qcax_fabric_host import PluginHost

plugin_dists=[d for d in md.distributions() if any(ep.group=='qcax.fabric.plugins' for ep in d.entry_points)]
rows=[]; locks=[]; trusted=[]; tickets=[]; eps=[]
for dist in sorted(plugin_dists,key=lambda x:x.metadata['Name']):
    files=list(dist.files or [])
    mf=next((f for f in files if str(f).endswith('qcax-plugin.json')),None)
    rec=next((f for f in files if str(f).endswith('.dist-info/RECORD')),None)
    if mf is None or rec is None: raise SystemExit('missing static metadata')
    manifest=json.loads(dist.locate_file(mf).read_text(encoding='utf-8'))
    descriptor=plugin_descriptor_from_mapping(manifest)
    record_path=Path(dist.locate_file(rec)); site_root=Path(dist.locate_file(''))
    digest=installed_image_digest_from_record(record_path)
    occurrence=f"installed:{dist.metadata['Name']}:{dist.version}"
    ticket=issue_admission_ticket(descriptor,record_path,site_root,digest,occurrence,str(site_root))
    tickets.append(ticket)
    ep=next(ep for ep in dist.entry_points if ep.group=='qcax.fabric.plugins'); eps.append(ep)
    if descriptor.plugin_class=='SYSTEM_PINNED':
        for cap in descriptor.provides:
            locks.append(LockedProvider(cap.capability_id,descriptor.plugin_id,ticket.envelope.artifact.sha256))
    if descriptor.plugin_class in {'THIRD_PARTY','ADAPTER'}:
        trusted.append(TrustedArtifact(descriptor.plugin_id,ticket.envelope.artifact.sha256))
    rows.append({
        'distribution_name':dist.metadata['Name'],
        'distribution_version':dist.version,
        'plugin_id':descriptor.plugin_id,
        'plugin_class':descriptor.plugin_class,
        'installation_receipt':ticket.receipt.public_record(),
        'admission_ticket_sha256':ticket.ticket_sha256,
    })

h=PluginHost(BootLock('qcax-fabric-alpha1','bounded-alpha1-canary',tuple(locks),tuple(trusted),False,'alpha1-local-reference'))
pre=[]
norm=lambda x:x.lower().replace('-','_').replace('.','_')
for ticket in tickets:
    env=ticket.envelope
    ep=next(ep for ep in eps if norm(getattr(ep,'dist',None).metadata['Name'])==norm(env.descriptor.distribution_name))
    pkg=ep.value.split(':',1)[0].split('.',1)[0]
    if pkg in sys.modules: raise SystemExit('plugin imported before preflight:'+pkg)
    pre.append(h.preflight(ticket))
    if pkg in sys.modules: raise SystemExit('preflight imported plugin:'+pkg)
for ticket in tickets:
    env=ticket.envelope
    ep=next(ep for ep in eps if norm(getattr(ep,'dist',None).metadata['Name'])==norm(env.descriptor.distribution_name))
    definition=ep.load()
    h.add(ticket,definition)
active={t.envelope.descriptor.plugin_id:h.state(t.envelope.descriptor.plugin_id).value for t in tickets}
if not all(v=='ACTIVE' for v in active.values()): raise SystemExit(json.dumps(active))
required=['qcax.truth.read','qcax.identity','qcax.provenance','qcax.source.admission','qcax.authorization','qcax.prompt.compile','qcax.memory','example.hello']
for cap in required: h.service(cap)
print(json.dumps({
    'status':'PASS','plugins':len(tickets),
    'system_pinned':len({t.envelope.descriptor.plugin_id for t in tickets if t.envelope.descriptor.plugin_class=='SYSTEM_PINNED'}),
    'preflight_receipts':len(pre),'all_static_preflight_before_load':True,
    'active':active,'installed':rows,'generation_digest':h.generation_digest
},sort_keys=True))
'''

with tempfile.TemporaryDirectory() as td:
    td=Path(td)
    if len(sys.argv)>1:
        wh=Path(sys.argv[1]).resolve(); receipt={'status':'PASS','source':'provided-wheel-dir','wheel_count':len(list(wh.glob('*.whl')))}
    else:
        wh=td/'wheels'; receipt=json.loads(run([sys.executable,str(ROOT/'scripts/build_wheels.py'),str(wh)]))
    venv=td/'venv'; run([sys.executable,'-m','venv',str(venv)])
    py=venv/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    wheels=sorted(wh.glob('*.whl'))
    order=[]
    for key in ['contracts','sdk','host']:
        order += [p for p in wheels if f'qcax_fabric_{key}-' in p.name]
    order += [p for p in wheels if p not in order]
    for p in order: run([str(py),'-m','pip','install','--no-index','--no-deps',str(p)])
    run([str(py),'-m','pip','check'])
    canary=td/'canary.py'; canary.write_text(CANARY,encoding='utf-8')
    result=json.loads(run([str(py),str(canary)])); result['wheel_build']=receipt; result['pip_check']='PASS'
    print(json.dumps(result,sort_keys=True))
