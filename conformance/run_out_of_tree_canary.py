#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import argparse,hashlib,importlib.metadata as md,json,os,subprocess,sys,tempfile
from packaging.utils import canonicalize_name
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'release/tooling'))
from build_candidate import _backend_call
from common import sha256_file

class CanaryError(RuntimeError): pass

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('candidate'); a=ap.parse_args()
    candidate=Path(a.candidate)
    with tempfile.TemporaryDirectory() as td:
        td=Path(td); src=td/'external-src'; pkg=src/'src/qcax_out_of_tree_canary'; pkg.mkdir(parents=True)
        (src/'pyproject.toml').write_text("""[build-system]
requires = ["setuptools>=77"]
build-backend = "setuptools.build_meta"

[project]
name = "qcax-fabric-out-of-tree-canary"
version = "0.0.1"
requires-python = ">=3.11"
dependencies = ["qcax-fabric-contracts==0.1.0a1", "qcax-fabric-sdk==0.1.0a1"]

[project.entry-points."qcax.fabric.plugins"]
external_canary = "qcax_out_of_tree_canary:definition"

[tool.setuptools]
package-dir = {"" = "src"}
[tool.setuptools.packages.find]
where = ["src"]
""",encoding='utf-8')
        (pkg/'__init__.py').write_text("""from qcax_fabric_contracts import PluginDescriptor,Capability
from qcax_fabric_sdk import PluginDefinition
descriptor=PluginDescriptor(plugin_id='example.qcax.out-of-tree',plugin_version='0.0.1',
    plugin_class='THIRD_PARTY',distribution_name='qcax-fabric-out-of-tree-canary',
    distribution_version='0.0.1',provides=(Capability('example.out_of_tree','1.0.0'),),
    requires=(),events_consumed=(),events_emitted=(),permissions=(),target_scopes=('*',),
    side_effect_class='NONE',execution_mode='TRUSTED_IN_PROCESS',config_schema='',state_schema='',rollback_receipt_schema='')
def mount(ctx):
    ctx.provide('example.out_of_tree',lambda:'out-of-tree-pass')
definition=PluginDefinition(descriptor,mount)
""",encoding='utf-8')
        out=td/'external-wheel'; out.mkdir(); wheel_name=_backend_call(src,'build_wheel',out)
        ext_wheel=out/wheel_name
        site=td/'site'; site.mkdir()
        wheels=sorted(candidate.glob('*.whl'))
        if len(wheels)!=11: raise CanaryError('candidate wheel count != 11')
        p=subprocess.run([sys.executable,'-m','pip','install','--disable-pip-version-check','--no-index','--no-deps',
                          '--target',str(site),*map(str,wheels),str(ext_wheel)],
                         cwd=str(ROOT),capture_output=True,text=True,timeout=180)
        if p.returncode: raise CanaryError('pip install failed: '+p.stderr[-2000:])
        sys.path.insert(0,str(site))
        from qcax_fabric_sdk.installation import installed_image_digest_from_record,verify_installed_record,issue_admission_ticket
        from qcax_fabric_contracts import BootLock,TrustedArtifact
        from qcax_fabric_host import PluginHost,State
        info=next(site.glob('qcax_fabric_out_of_tree_canary-0.0.1.dist-info'))
        record=info/'RECORD'; digest=installed_image_digest_from_record(record)
        vr=verify_installed_record(record,site,digest)
        if vr['status']!='PASS': raise CanaryError('external RECORD verify failed: '+repr(vr['errors']))
        dist=md.PathDistribution(info)
        eps=[ep for ep in dist.entry_points if ep.group=='qcax.fabric.plugins']
        if len(eps)!=1: raise CanaryError('external entrypoint count != 1')
        definition=eps[0].load(); d=definition.descriptor
        ticket=issue_admission_ticket(d,record,site,digest,'out-of-tree-canary','out-of-tree',ext_wheel)
        host=PluginHost(BootLock('qcax/qcax-fabric','out-of-tree-canary',(),(TrustedArtifact(d.plugin_id,digest),),False,'ci'))
        if host.add(ticket,definition)!=State.ACTIVE: raise CanaryError('external plugin not active')
        if host.service('example.out_of_tree')()!='out-of-tree-pass': raise CanaryError('external capability failed')
        print(json.dumps({'status':'PASS','plugin_id':d.plugin_id,'wheel_sha256':sha256_file(ext_wheel),
                          'installed_image_sha256':digest,'verified_record_entries':vr['verified_record_entries']},sort_keys=True))
if __name__=='__main__':
    main()
