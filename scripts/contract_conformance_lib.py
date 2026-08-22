from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import base64, hashlib, json, os, sys, tempfile


def _src_paths(root: Path):
    return [root/'packages/contracts/src', root/'packages/sdk/src', root/'packages/host/src'] + [p/'src' for p in (root/'packages/plugins').iterdir() if p.is_dir()]


def run_contract_conformance(root: Path):
    root = Path(root)
    sys.path[:0] = [str(x) for x in _src_paths(root)]
    try:
        from jsonschema import Draft202012Validator
    except Exception as exc:
        return {'status':'FAIL','checks':1,'errors':[f'jsonschema-unavailable:{type(exc).__name__}'], 'vectors':[]}
    from qcax_fabric_contracts import plugin_descriptor_from_mapping, is_semver, PluginDescriptor, ArtifactIdentity, PluginEnvelope
    from qcax_fabric_sdk import issue_admission_ticket, validate_admission_ticket
    from qcax_fabric_sdk.installation import installed_image_digest_from_record

    errors=[]; checks=0; vectors=[]
    def check(cond,msg):
        nonlocal checks
        checks += 1
        if not cond: errors.append(msg)

    schemas={}
    for p in sorted((root/'spec').glob('*.schema.json')):
        try:
            d=json.loads(p.read_text(encoding='utf-8')); Draft202012Validator.check_schema(d); schemas[p.name]=d; check(True,'')
        except Exception as exc:
            check(False,f'schema-invalid:{p.name}:{type(exc).__name__}:{exc}')

    desc_schema=schemas['plugin-descriptor-v1alpha1.schema.json']
    desc_validator=Draft202012Validator(desc_schema)
    plugin_files=sorted(root.glob('packages/plugins/*/src/*/qcax-plugin.json'))
    for p in plugin_files:
        d=json.loads(p.read_text(encoding='utf-8'))
        schema_ok=not list(desc_validator.iter_errors(d))
        try: plugin_descriptor_from_mapping(d); py_ok=True
        except Exception: py_ok=False
        check(schema_ok,f'descriptor-schema:{p}')
        check(py_ok,f'descriptor-python:{p}')
        check(schema_ok==py_ok,f'descriptor-parity:{p}')

    base=json.loads(plugin_files[0].read_text(encoding='utf-8'))
    cases=[]
    def add(name, mut, expected):
        d=deepcopy(base); mut(d); cases.append((name,d,expected))
    add('valid',lambda d:None,True)
    add('missing_schema_version',lambda d:d.pop('schema_version'),False)
    add('unknown_top_level',lambda d:d.__setitem__('unexpected',1),False)
    add('invalid_plugin_id',lambda d:d.__setitem__('plugin_id','Bad Plugin'),False)
    add('invalid_capability_id',lambda d:d['provides'][0].__setitem__('capability_id','BAD CAP'),False)
    add('missing_capability_version',lambda d:d['provides'][0].pop('contract_version'),False)
    add('unknown_capability_key',lambda d:d['provides'][0].__setitem__('x',1),False)
    def event_case(d): d['events_emitted']=[{'name':'BAD EVENT','mode':'emit','durability':'EPHEMERAL','contract_version':'1.0.0'}]
    add('invalid_event_id',event_case,False)
    def missing_event(d): d['events_emitted']=[{'name':'x.event','mode':'emit','contract_version':'1.0.0'}]
    add('missing_event_durability',missing_event,False)
    def mut_no_rollback(d): d['side_effect_class']='LOCAL_REVERSIBLE'; d['rollback_receipt_schema']=''
    add('mutating_without_rollback',mut_no_rollback,False)
    add('bad_semver_numeric_prerelease_zero',lambda d:d.__setitem__('plugin_version','1.0.0-01'),False)
    add('good_semver_prerelease',lambda d:d.__setitem__('plugin_version','1.0.0-alpha.1'),True)
    add('unknown_event_mode',lambda d:d['events_emitted'].append({'name':'x.event','mode':'fanout','durability':'EPHEMERAL','contract_version':'1.0.0'}),False)
    add('contract_prerelease_disallowed',lambda d:d['provides'][0].__setitem__('contract_version','1.0.0-alpha.1'),False)
    add('provides_wrong_type',lambda d:d.__setitem__('provides',{}),False)
    for name,d,expected in cases:
        schema_ok=not list(desc_validator.iter_errors(d))
        try: plugin_descriptor_from_mapping(d); py_ok=True
        except Exception: py_ok=False
        vectors.append({'id':name,'expected':expected,'schema_ok':schema_ok,'python_ok':py_ok})
        check(schema_ok==expected,f'vector-schema:{name}:{schema_ok}!={expected}')
        check(py_ok==expected,f'vector-python:{name}:{py_ok}!={expected}')
        check(schema_ok==py_ok,f'vector-parity:{name}')

    semver_vectors={
        '1.0.0':True, '0.1.0-alpha.1':True, '1.0.0-0.3.7':True,
        '1.0.0-x.7.z.92':True, '1.0.0+001':True,
        '1.0.0-01':False, '1.0.0-alpha..1':False, '01.0.0':False,
        '1.0':False, '1.0.0-':False,
    }
    for v,expected in semver_vectors.items(): check(is_semver(v)==expected,f'semver:{v}')

    # Normative InstallationReceipt emission and verifier-issued AdmissionTicket.
    with tempfile.TemporaryDirectory() as td:
        td=Path(td); site=td/'site'; site.mkdir(); pkg=site/'pkg'; pkg.mkdir(); payload=pkg/'a.py'; payload.write_bytes(b'x=1\n')
        dist=site/'example-0.1.dist-info'; dist.mkdir()
        h=base64.urlsafe_b64encode(hashlib.sha256(payload.read_bytes()).digest()).decode().rstrip('=')
        record=dist/'RECORD'; record.write_text(f'pkg/a.py,sha256={h},{payload.stat().st_size}\nexample-0.1.dist-info/RECORD,,\n',encoding='utf-8')
        digest=installed_image_digest_from_record(record)
        mapping=deepcopy(base); mapping['plugin_id']='example.receipt'; mapping['distribution_name']='example'; mapping['distribution_version']='0.1'; mapping['plugin_class']='THIRD_PARTY'; mapping['provides']=[]; mapping['requires']=[]
        descriptor=plugin_descriptor_from_mapping(mapping)
        ticket=issue_admission_ticket(descriptor,record,site,digest,'test-occurrence','test-site')
        validate_admission_ticket(ticket)
        receipt=ticket.receipt.public_record()
        irv=Draft202012Validator(schemas['installation-receipt-v1alpha1.schema.json'])
        check(not list(irv.iter_errors(receipt)),'normative-installation-receipt-schema')
        check(receipt['record_verified'] is True,'normative-installation-receipt-record')
        check(ticket.envelope.artifact.sha256==digest,'ticket-installed-image-binding')
        # Caller-constructed envelope is deliberately not a ticket.
        check(not hasattr(PluginEnvelope(descriptor,ArtifactIdentity('INSTALLED_IMAGE',digest,payload.stat().st_size,'x','x')),'ticket_sha256'),'raw-envelope-not-ticket')

    return {'status':'PASS' if not errors else 'FAIL','checks':checks,'errors':errors,'vectors':vectors,'plugin_descriptors':len(plugin_files),'schema_files':len(schemas),'semver_vectors':len(semver_vectors)}
