from pathlib import Path
import json, os, subprocess, sys, tempfile, textwrap

ROOT=Path(__file__).resolve().parents[1]
ENV=os.environ.copy(); ENV['PYTHONDONTWRITEBYTECODE']='1'; ENV['SOURCE_DATE_EPOCH']='1787356800'

def run(cmd,cwd='/'):
    r=subprocess.run(cmd,cwd=cwd,env=ENV,text=True,capture_output=True)
    if r.returncode: raise RuntimeError(r.stdout+'\n'+r.stderr)
    return r.stdout.strip()

INNER=r'''import importlib.metadata as md,json,sys
from pathlib import Path
from qcax_fabric_contracts import *
from qcax_fabric_sdk import issue_admission_ticket
from qcax_fabric_sdk.installation import installed_image_digest_from_record
from qcax_fabric_host import PluginHost

dist=md.distribution('qcax-external-canary')
files=list(dist.files or [])
mf=next(f for f in files if str(f).endswith('qcax-plugin.json'))
rec=next(f for f in files if str(f).endswith('.dist-info/RECORD'))
manifest=json.loads(dist.locate_file(mf).read_text(encoding='utf-8'))
d=plugin_descriptor_from_mapping(manifest)
record=Path(dist.locate_file(rec)); site=Path(dist.locate_file('')); digest=installed_image_digest_from_record(record)
t=issue_admission_ticket(d,record,site,digest,'external-canary-install',str(site))
h=PluginHost(BootLock('external-canary','bounded',(),(TrustedArtifact(d.plugin_id,digest),),False,'external-canary'))
ep=next(ep for ep in dist.entry_points if ep.group=='qcax.fabric.plugins')
pkg=ep.value.split(':',1)[0].split('.',1)[0]
if pkg in sys.modules: raise SystemExit('imported-before-preflight')
pre=h.preflight(t)
if pkg in sys.modules: raise SystemExit('preflight-imported-plugin')
definition=ep.load(); h.add(t,definition)
result=h.service('external.echo')('x')
print(json.dumps({'status':'PASS','state':h.state(d.plugin_id).value,'result':result,'preflight':pre,'installation_receipt':t.receipt.public_record(),'generation_digest':h.generation_digest},sort_keys=True))
'''

with tempfile.TemporaryDirectory() as td:
    td=Path(td); src=td/'src'; pkg=src/'src/qcax_external_canary'; pkg.mkdir(parents=True)
    (src/'pyproject.toml').write_text(textwrap.dedent('''
    [build-system]
    requires = ["setuptools>=77"]
    build-backend = "setuptools.build_meta"
    [project]
    name = "qcax-external-canary"
    version = "0.1.0a1"
    requires-python = ">=3.11"
    dependencies = ["qcax-fabric-contracts==0.1.0a1", "qcax-fabric-sdk==0.1.0a1"]
    [project.entry-points."qcax.fabric.plugins"]
    canary = "qcax_external_canary:definition"
    [tool.setuptools]
    package-dir = {"" = "src"}
    include-package-data = true
    [tool.setuptools.packages.find]
    where = ["src"]
    [tool.setuptools.package-data]
    "qcax_external_canary" = ["qcax-plugin.json"]
    '''),encoding='utf-8')
    manifest={
      'schema_version':'qcax.plugin/v1alpha1','plugin_id':'example.external-canary','plugin_version':'0.1.0-alpha.1','plugin_class':'THIRD_PARTY','api_version':'qcax.fabric/v1alpha1','distribution_name':'qcax-external-canary','distribution_version':'0.1.0a1',
      'provides':[{'capability_id':'external.echo','contract_version':'1.0.0'}],'requires':[],'events_consumed':[],'events_emitted':[],'permissions':[],'target_scopes':['*'],'side_effect_class':'NONE','execution_mode':'TRUSTED_IN_PROCESS','config_schema':'','state_schema':'','rollback_receipt_schema':''}
    (pkg/'qcax-plugin.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    (pkg/'__init__.py').write_text("from qcax_fabric_contracts import *\nfrom qcax_fabric_sdk import PluginDefinition\ndescriptor=plugin_descriptor_from_mapping(__import__('json').loads(__import__('importlib').resources.files(__package__).joinpath('qcax-plugin.json').read_text()))\ndef mount(ctx): ctx.provide('external.echo',lambda x:{'echo':x,'source':'out-of-tree'})\ndefinition=PluginDefinition(descriptor,mount)\n",encoding='utf-8')
    wh=td/'wh'; wh.mkdir(); run([sys.executable,'-m','pip','wheel','--no-deps','--no-build-isolation','-w',str(wh),str(src)])
    ext=next(wh.glob('*.whl'))
    core=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else td/'core'
    if len(sys.argv)<=1: run([sys.executable,str(ROOT/'scripts/build_wheels.py'),str(core)])
    venv=td/'venv'; run([sys.executable,'-m','venv',str(venv)]); py=venv/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    for key in ('qcax_fabric_contracts','qcax_fabric_sdk','qcax_fabric_host'):
        wheel=next(p for p in core.glob('*.whl') if p.name.startswith(key+'-'))
        run([str(py),'-m','pip','install','--no-index','--no-deps',str(wheel)])
    run([str(py),'-m','pip','install','--no-index','--no-deps',str(ext)])
    script=td/'inner.py'; script.write_text(INNER,encoding='utf-8')
    print(run([str(py),str(script)]))
