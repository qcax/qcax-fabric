"""Installed-image verification and verifier-issued admission tickets.

The host never accepts a caller-constructed PluginEnvelope for executable
admission. The SDK verifier first checks the installed RECORD payload and then
issues an AdmissionTicket bound to that exact InstalledImage identity.

This is an API trust boundary inside a trusted Python process, not a sandbox or
protection against malicious same-process code.
"""
from __future__ import annotations
from dataclasses import dataclass
import base64, csv, hashlib, io
from pathlib import Path
from qcax_fabric_contracts import ArtifactIdentity, PluginDescriptor, PluginEnvelope
from qcax_fabric_contracts.canonical import canonical_sha256

_INSTALLER_GENERATED_BASENAMES = frozenset({'INSTALLER', 'REQUESTED', 'direct_url.json'})
_TICKET_ISSUER = object()


def _is_installer_generated(path: str) -> bool:
    return '.dist-info/' in path and path.rsplit('/', 1)[-1] in _INSTALLER_GENERATED_BASENAMES


def _rows(text: str):
    out = []
    for row in csv.reader(io.StringIO(text)):
        if len(row) != 3:
            raise ValueError('malformed RECORD row')
        path, h, size = row
        if not h or _is_installer_generated(path):
            continue
        alg, val = h.split('=', 1)
        if alg != 'sha256':
            raise ValueError(f'unsupported RECORD hash: {alg}')
        out.append({'path': path, 'hash': h, 'size': int(size) if size else None})
    return sorted(out, key=lambda x: x['path'])


def installed_image_digest_from_record_text(text: str) -> str:
    return canonical_sha256({'schema': 'qcax.installed-image/v1alpha1', 'entries': _rows(text)})


def installed_image_digest_from_record(record_path: Path) -> str:
    return installed_image_digest_from_record_text(record_path.read_text(encoding='utf-8'))


def verify_installed_record(record_path: Path, site_root: Path, expected_installed_image_sha256: str):
    text = record_path.read_text(encoding='utf-8')
    rows = _rows(text)
    observed = installed_image_digest_from_record_text(text)
    errors = []
    verified = 0
    verified_bytes = 0
    if observed != expected_installed_image_sha256:
        errors.append('installed-image-digest-mismatch')
    expected = {x['path'] for x in rows}
    top = {x['path'].split('/')[0] for x in rows if '.dist-info/' not in x['path']}
    for row in rows:
        p = site_root / row['path']
        if not p.is_file():
            errors.append('missing:' + row['path'])
            continue
        data = p.read_bytes()
        got = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip('=')
        if got != row['hash'].split('=', 1)[1]:
            errors.append('hash:' + row['path'])
        if row['size'] is not None and len(data) != row['size']:
            errors.append('size:' + row['path'])
        verified += 1
        verified_bytes += len(data)
    for t in top:
        p = site_root / t
        if p.is_dir():
            for q in p.rglob('*'):
                if q.is_file() and q.suffix not in {'.pyc', '.pyo'} and '__pycache__' not in q.parts:
                    rel = q.relative_to(site_root).as_posix()
                    if rel not in expected:
                        errors.append('unexpected-package-file:' + rel)
    return {
        'status': 'PASS' if not errors else 'FAIL',
        'installed_image_sha256': observed,
        'verified_record_entries': verified,
        'verified_bytes': verified_bytes,
        'errors': errors,
    }


@dataclass(frozen=True)
class InstallationReceipt:
    schema: str
    distribution_name: str
    distribution_version: str
    installed_image_sha256: str
    record_verified: bool
    verified_record_entries: int
    verified_bytes: int
    occurrence_id: str
    site_root: str
    source_locator: str = ''
    wheel_filename: str | None = None
    wheel_sha256: str | None = None

    def public_record(self):
        return {
            'schema': self.schema,
            'distribution_name': self.distribution_name,
            'distribution_version': self.distribution_version,
            'installed_image_sha256': self.installed_image_sha256,
            'record_verified': self.record_verified,
            'verified_record_entries': self.verified_record_entries,
            'verified_bytes': self.verified_bytes,
            'occurrence_id': self.occurrence_id,
            'site_root': self.site_root,
            'source_locator': self.source_locator,
            'wheel_filename': self.wheel_filename,
            'wheel_sha256': self.wheel_sha256,
        }


class AdmissionTicket:
    """Opaque verifier-issued capability consumed by PluginHost admission."""
    __slots__ = ('envelope', 'receipt', 'ticket_sha256', '_issuer')

    def __init__(self, envelope: PluginEnvelope, receipt: InstallationReceipt, issuer):
        if issuer is not _TICKET_ISSUER:
            raise TypeError('AdmissionTicket is verifier-issued only')
        self.envelope = envelope
        self.receipt = receipt
        self._issuer = issuer
        self.ticket_sha256 = canonical_sha256({
            'schema': 'qcax.admission-ticket/v1alpha1',
            'plugin_id': envelope.descriptor.plugin_id,
            'plugin_version': envelope.descriptor.plugin_version,
            'artifact_kind': envelope.artifact.artifact_kind,
            'artifact_sha256': envelope.artifact.sha256,
            'artifact_size_bytes': envelope.artifact.size_bytes,
            'occurrence_id': envelope.artifact.occurrence_id,
            'installation_receipt': receipt.public_record(),
        })


def validate_admission_ticket(ticket: AdmissionTicket) -> PluginEnvelope:
    if not isinstance(ticket, AdmissionTicket) or getattr(ticket, '_issuer', None) is not _TICKET_ISSUER:
        raise TypeError('verified AdmissionTicket required')
    e = ticket.envelope
    r = ticket.receipt
    d = e.descriptor
    if r.schema != 'qcax.installation-receipt/v1alpha1' or r.record_verified is not True:
        raise ValueError('invalid installation receipt')
    if e.artifact.artifact_kind != 'INSTALLED_IMAGE':
        raise ValueError('admission requires INSTALLED_IMAGE identity')
    if r.installed_image_sha256 != e.artifact.sha256:
        raise ValueError('receipt/artifact digest mismatch')
    if r.verified_bytes != e.artifact.size_bytes:
        raise ValueError('receipt/artifact size mismatch')
    if r.occurrence_id != e.artifact.occurrence_id:
        raise ValueError('receipt/artifact occurrence mismatch')
    if d.distribution_name != r.distribution_name or d.distribution_version != r.distribution_version:
        raise ValueError('receipt/descriptor distribution mismatch')
    expected = canonical_sha256({
        'schema': 'qcax.admission-ticket/v1alpha1',
        'plugin_id': d.plugin_id,
        'plugin_version': d.plugin_version,
        'artifact_kind': e.artifact.artifact_kind,
        'artifact_sha256': e.artifact.sha256,
        'artifact_size_bytes': e.artifact.size_bytes,
        'occurrence_id': e.artifact.occurrence_id,
        'installation_receipt': r.public_record(),
    })
    if expected != ticket.ticket_sha256:
        raise ValueError('admission ticket integrity mismatch')
    return e


def make_installation_receipt(
    distribution_name: str,
    distribution_version: str,
    record_path: Path,
    site_root: Path,
    expected_installed_image_sha256: str,
    occurrence_id: str,
    source_locator: str = '',
    wheel_path: Path | None = None,
) -> InstallationReceipt:
    if not distribution_name or not distribution_version:
        raise ValueError('distribution identity required')
    vr = verify_installed_record(record_path, site_root, expected_installed_image_sha256)
    if vr['status'] != 'PASS':
        raise ValueError('installed RECORD verification failed: ' + ';'.join(vr['errors']))
    wheel_filename = None
    wheel_sha256 = None
    if wheel_path is not None:
        wheel_path = Path(wheel_path)
        wheel_filename = wheel_path.name
        wheel_sha256 = hashlib.sha256(wheel_path.read_bytes()).hexdigest()
    return InstallationReceipt(
        schema='qcax.installation-receipt/v1alpha1',
        distribution_name=distribution_name,
        distribution_version=distribution_version,
        installed_image_sha256=vr['installed_image_sha256'],
        record_verified=True,
        verified_record_entries=vr['verified_record_entries'],
        verified_bytes=vr['verified_bytes'],
        occurrence_id=occurrence_id,
        site_root=str(site_root),
        source_locator=source_locator,
        wheel_filename=wheel_filename,
        wheel_sha256=wheel_sha256,
    )


def issue_admission_ticket(
    descriptor: PluginDescriptor,
    record_path: Path,
    site_root: Path,
    expected_installed_image_sha256: str,
    occurrence_id: str,
    source_locator: str = '',
    wheel_path: Path | None = None,
) -> AdmissionTicket:
    """Verify installed bytes and issue the only public executable-admission capability."""
    receipt = make_installation_receipt(
        descriptor.distribution_name, descriptor.distribution_version, record_path, site_root,
        expected_installed_image_sha256, occurrence_id, source_locator, wheel_path,
    )
    artifact = ArtifactIdentity(
        'INSTALLED_IMAGE', receipt.installed_image_sha256, receipt.verified_bytes,
        occurrence_id, source_locator or str(site_root),
    )
    return AdmissionTicket(PluginEnvelope(descriptor, artifact), receipt, _TICKET_ISSUER)


def _issue_development_ticket_for_tests(envelope: PluginEnvelope) -> AdmissionTicket:
    """Private test helper. Not exported by qcax_fabric_sdk.__init__."""
    d = envelope.descriptor
    artifact = ArtifactIdentity(
        'INSTALLED_IMAGE', envelope.artifact.sha256, envelope.artifact.size_bytes,
        envelope.artifact.occurrence_id, envelope.artifact.source_locator,
    )
    receipt = InstallationReceipt(
        schema='qcax.installation-receipt/v1alpha1',
        distribution_name=d.distribution_name,
        distribution_version=d.distribution_version,
        installed_image_sha256=artifact.sha256,
        record_verified=True,
        verified_record_entries=1,
        verified_bytes=artifact.size_bytes,
        occurrence_id=artifact.occurrence_id,
        site_root='TEST_ONLY',
        source_locator='TEST_ONLY',
    )
    return AdmissionTicket(PluginEnvelope(d, artifact), receipt, _TICKET_ISSUER)
