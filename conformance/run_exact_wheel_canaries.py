#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import argparse,hashlib,importlib.metadata as md,json,subprocess,sys,tempfile
from packaging.utils import canonicalize_name

ROOT=Path(__file__).resolve().parents[1]

class CanaryError(RuntimeError): pass

def sha256_file(path:Path)->str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def install_wheels(candidate:Path,site:Path,extra_wheels=()):
    candidate=Path(candidate); site=Path(site); site.mkdir(parents=True,exist_ok=True)
    wheels=sorted(candidate.glob('*.whl'))
    if len(wheels)!=11: raise CanaryError(f'expected 11 candidate wheels, got {len(wheels)}')
    cmd=[sys.executable,'-m','pip','install','--disable-pip-version-check','--no-index','--no-deps',
         '--target',str(site),*map(str,wheels),*map(str,extra_wheels)]
    p=subprocess.run(cmd,cwd=str(ROOT),capture_output=True,text=True,timeout=180)
    if p.returncode: raise CanaryError('pip target install failed: '+p.stderr[-2000:])
    return wheels

def path_distributions(site:Path):
    out={}
    for info in sorted(Path(site).glob('*.dist-info')):
        d=md.PathDistribution(info); name=d.metadata.get('Name')
        if not name: continue
        key=canonicalize_name(name)
        if key in out: raise CanaryError('duplicate installed distribution '+key)
        out[key]=(d,info)
    return out

def verify_candidate_install(candidate:Path,site:Path):
    candidate=Path(candidate); site=Path(site)
    lock=json.loads((candidate/'release-lock.json').read_text(encoding='utf-8'))
    entries={canonicalize_name(x['distribution_name']):x for x in lock['entries']}
    if len(entries)!=11: raise CanaryError('release-lock package count != 11')
    dists=path_distributions(site)
    expected=set(entries)
    observed={x for x in dists if x.startswith('qcax-fabric')}
    if observed!=expected: raise CanaryError(f'installed distribution set mismatch: {sorted(observed^expected)}')

    sys.path.insert(0,str(site))
    from qcax_fabric_sdk.installation import installed_image_digest_from_record,verify_installed_record,issue_admission_ticket
    from qcax_fabric_contracts import BootLock,LockedProvider,TrustedArtifact
    from qcax_fabric_host import PluginHost,State

    dist_receipts=[]; verified={}
    for name,e in sorted(entries.items()):
        dist,info=dists[name]; record=info/'RECORD'
        if not record.is_file(): raise CanaryError('RECORD missing '+name)
        digest=installed_image_digest_from_record(record)
        if digest!=e['installed_image_sha256']: raise CanaryError('installed identity mismatch '+name)
        vr=verify_installed_record(record,site,digest)
        if vr['status']!='PASS': raise CanaryError('RECORD verification failed '+name+': '+repr(vr['errors']))
        wheel=candidate/e['wheel_filename']
        if not wheel.is_file() or sha256_file(wheel)!=e['wheel_sha256']: raise CanaryError('wheel binding mismatch '+name)
        verified[name]={'dist':dist,'info':info,'record':record,'digest':digest,'wheel':wheel,'entry':e}
        dist_receipts.append({'name':name,'version':dist.version,'installed_image_sha256':digest,
                              'verified_record_entries':vr['verified_record_entries'],'verified_bytes':vr['verified_bytes']})

    # Only after all distribution bytes are verified may executable entry points load.
    plugin_rows=[]
    definitions=[]; tickets=[]
    for name,v in sorted(verified.items()):
        eps=[ep for ep in v['dist'].entry_points if ep.group=='qcax.fabric.plugins']
        for ep in eps:
            obj=ep.load()
            definition=obj
            d=definition.descriptor
            if canonicalize_name(d.distribution_name)!=name: raise CanaryError('entrypoint/descriptor distribution mismatch '+name)
            ticket=issue_admission_ticket(d,v['record'],site,v['digest'],
                    occurrence_id=f'{name}@{v["dist"].version}',source_locator='installed-canary',wheel_path=v['wheel'])
            definitions.append(definition); tickets.append(ticket)
            plugin_rows.append({'distribution':name,'name':ep.name,'value':ep.value,'plugin_id':d.plugin_id})

    if len(definitions)!=8: raise CanaryError(f'expected 8 plugin entry points, got {len(definitions)}')
    if len({x.descriptor.plugin_id for x in definitions})!=8: raise CanaryError('duplicate plugin ids')

    locks=[]; trusted=[]
    by_pid={t.envelope.descriptor.plugin_id:t for t in tickets}
    for definition,ticket in zip(definitions,tickets):
        d=definition.descriptor; digest=ticket.envelope.artifact.sha256
        if d.plugin_class=='SYSTEM_PINNED':
            for cap in d.provides: locks.append(LockedProvider(cap.capability_id,d.plugin_id,digest))
        if d.plugin_class in {'THIRD_PARTY','ADAPTER'}:
            trusted.append(TrustedArtifact(d.plugin_id,digest))
    host=PluginHost(BootLock('qcax/qcax-fabric','installed-wheel-canary',tuple(locks),tuple(trusted),False,'ci'))

    remaining={d.descriptor.plugin_id:(d,by_pid[d.descriptor.plugin_id]) for d in definitions}
    supplied=set()
    while remaining:
        ready=[]
        for pid,(definition,ticket) in remaining.items():
            req={r.capability_id for r in definition.descriptor.requires}
            if req<=supplied: ready.append(pid)
        if not ready: raise CanaryError('plugin dependency cycle/unmet dependency: '+','.join(sorted(remaining)))
        for pid in sorted(ready):
            definition,ticket=remaining.pop(pid)
            st=host.add(ticket,definition)
            if st!=State.ACTIVE: raise CanaryError(f'plugin not active after dependency-ready mount: {pid} {st}')
            supplied.update(c.capability_id for c in definition.descriptor.provides)

    active=sorted(x.descriptor.plugin_id for x in definitions if host.state(x.descriptor.plugin_id)==State.ACTIVE)
    if len(active)!=8: raise CanaryError('active plugin count mismatch')
    if host.service('example.hello')('QCAX')!='hello QCAX': raise CanaryError('hello capability failed')
    return {'status':'PASS','distributions':dist_receipts,'entry_points':sorted(plugin_rows,key=lambda x:x['plugin_id']),
            'active_plugins':active,'generation_digest':host.generation_digest}

def run(candidate:Path):
    with tempfile.TemporaryDirectory() as td:
        site=Path(td)/'site'; install_wheels(candidate,site)
        return verify_candidate_install(candidate,site)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('candidate'); a=ap.parse_args()
    print(json.dumps(run(Path(a.candidate)),sort_keys=True))
if __name__=='__main__':
    main()
