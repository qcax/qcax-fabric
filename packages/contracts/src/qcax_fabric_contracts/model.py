from __future__ import annotations
from dataclasses import dataclass
import re
from .versioning import is_semver, is_stable_contract_semver

_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
PLUGIN_CLASSES = {"SYSTEM_PINNED", "FIRST_PARTY", "THIRD_PARTY", "ADAPTER", "PROFILE"}
SIDE_EFFECT_CLASSES = {"NONE", "READ_ONLY", "LOCAL_REVERSIBLE", "EXTERNAL_MUTATION"}
EXECUTION_MODES = {"TRUSTED_IN_PROCESS", "SANDBOXED_PROCESS", "REMOTE"}
EVENT_MODES = {"emit", "waterfall", "serial", "guard"}
DURABILITY = {"EPHEMERAL", "DURABLE"}
PLUGIN_SCHEMA_VERSION = "qcax.plugin/v1alpha1"
PLUGIN_API_VERSION = "qcax.fabric/v1alpha1"

_DESCRIPTOR_KEYS = frozenset({
    "schema_version", "plugin_id", "plugin_version", "plugin_class", "api_version",
    "distribution_name", "distribution_version", "provides", "requires",
    "events_consumed", "events_emitted", "permissions", "target_scopes",
    "side_effect_class", "execution_mode", "config_schema", "state_schema",
    "rollback_receipt_schema",
})


class ContractError(ValueError):
    pass


@dataclass(frozen=True)
class Capability:
    capability_id: str
    contract_version: str = "1.0.0"

    def __post_init__(self):
        if not isinstance(self.capability_id, str) or not _ID.fullmatch(self.capability_id):
            raise ContractError("invalid capability id")
        if not is_stable_contract_semver(self.contract_version):
            raise ContractError("capability contract_version must be stable SemVer in v1alpha1")


@dataclass(frozen=True)
class EventSpec:
    name: str
    mode: str = "emit"
    durability: str = "EPHEMERAL"
    contract_version: str = "1.0.0"

    def __post_init__(self):
        if not isinstance(self.name, str) or not _ID.fullmatch(self.name):
            raise ContractError("invalid event id")
        if self.mode not in EVENT_MODES:
            raise ContractError("invalid event mode")
        if self.durability not in DURABILITY:
            raise ContractError("invalid durability")
        if not is_stable_contract_semver(self.contract_version):
            raise ContractError("event contract_version must be stable SemVer in v1alpha1")


@dataclass(frozen=True)
class PluginDescriptor:
    plugin_id: str
    plugin_version: str
    plugin_class: str
    schema_version: str = PLUGIN_SCHEMA_VERSION
    api_version: str = PLUGIN_API_VERSION
    distribution_name: str = ""
    distribution_version: str = ""
    provides: tuple[Capability, ...] = ()
    requires: tuple[Capability, ...] = ()
    events_consumed: tuple[EventSpec, ...] = ()
    events_emitted: tuple[EventSpec, ...] = ()
    permissions: tuple[str, ...] = ()
    target_scopes: tuple[str, ...] = ("*",)
    side_effect_class: str = "NONE"
    execution_mode: str = "TRUSTED_IN_PROCESS"
    config_schema: str = ""
    state_schema: str = ""
    rollback_receipt_schema: str = ""

    def __post_init__(self):
        if not isinstance(self.plugin_id, str) or not _ID.fullmatch(self.plugin_id):
            raise ContractError("invalid plugin id")
        if not is_semver(self.plugin_version):
            raise ContractError("plugin_version must be SemVer")
        if self.plugin_class not in PLUGIN_CLASSES:
            raise ContractError("invalid plugin class")
        if self.schema_version != PLUGIN_SCHEMA_VERSION:
            raise ContractError("unsupported descriptor schema version")
        if self.api_version != PLUGIN_API_VERSION:
            raise ContractError("unsupported api version")
        if self.side_effect_class not in SIDE_EFFECT_CLASSES:
            raise ContractError("invalid side effect class")
        if self.execution_mode not in EXECUTION_MODES:
            raise ContractError("invalid execution mode")
        if not isinstance(self.distribution_name, str) or not isinstance(self.distribution_version, str):
            raise ContractError("invalid distribution identity")
        if any(not isinstance(x, str) for x in self.permissions):
            raise ContractError("permissions must be strings")
        if any(not isinstance(x, str) for x in self.target_scopes):
            raise ContractError("target scopes must be strings")
        if len({x.capability_id for x in self.provides}) != len(self.provides):
            raise ContractError("duplicate provides")
        if len({x.capability_id for x in self.requires}) != len(self.requires):
            raise ContractError("duplicate requires")
        if self.side_effect_class in {"LOCAL_REVERSIBLE", "EXTERNAL_MUTATION"} and not self.rollback_receipt_schema:
            raise ContractError("mutating/reversible plugin needs rollback receipt schema")


@dataclass(frozen=True)
class ArtifactIdentity:
    artifact_kind: str
    sha256: str
    size_bytes: int
    occurrence_id: str
    source_locator: str = ""

    def __post_init__(self):
        if not isinstance(self.sha256, str) or not _HEX64.fullmatch(self.sha256):
            raise ContractError("invalid sha256")
        if not isinstance(self.size_bytes, int) or isinstance(self.size_bytes, bool) or self.size_bytes < 0:
            raise ContractError("negative/invalid artifact size")
        if not isinstance(self.occurrence_id, str) or not self.occurrence_id:
            raise ContractError("occurrence required")


@dataclass(frozen=True)
class PluginEnvelope:
    descriptor: PluginDescriptor
    artifact: ArtifactIdentity


@dataclass(frozen=True)
class LockedProvider:
    capability_prefix: str
    plugin_id: str
    artifact_sha256: str

    def __post_init__(self):
        if not isinstance(self.capability_prefix, str) or not self.capability_prefix:
            raise ContractError("invalid lock")
        if not isinstance(self.plugin_id, str) or not _ID.fullmatch(self.plugin_id):
            raise ContractError("invalid lock")
        if not isinstance(self.artifact_sha256, str) or not _HEX64.fullmatch(self.artifact_sha256):
            raise ContractError("invalid lock digest")


@dataclass(frozen=True)
class TrustedArtifact:
    plugin_id: str
    artifact_sha256: str

    def __post_init__(self):
        if not isinstance(self.plugin_id, str) or not _ID.fullmatch(self.plugin_id):
            raise ContractError("invalid trusted plugin id")
        if not isinstance(self.artifact_sha256, str) or not _HEX64.fullmatch(self.artifact_sha256):
            raise ContractError("invalid trusted artifact digest")


@dataclass(frozen=True)
class BootLock:
    target: str
    claim_ceiling: str
    locked_providers: tuple[LockedProvider, ...]
    trusted_in_process_artifacts: tuple[TrustedArtifact, ...] = ()
    external_mutation_authorized: bool = False
    generation_label: str = ""

    def __post_init__(self):
        prefixes = [x.capability_prefix for x in self.locked_providers]
        if len(prefixes) != len(set(prefixes)):
            raise ContractError("duplicate locked capability prefix")
        trust_ids = [x.plugin_id for x in self.trusted_in_process_artifacts]
        if len(trust_ids) != len(set(trust_ids)):
            raise ContractError("duplicate trusted plugin id")
        by_pid = {}
        for x in self.locked_providers:
            old = by_pid.setdefault(x.plugin_id, x.artifact_sha256)
            if old != x.artifact_sha256:
                raise ContractError("SYSTEM_PINNED plugin has conflicting artifact digests")

    def lock_for(self, capability_id):
        xs = [x for x in self.locked_providers if capability_id == x.capability_prefix or capability_id.startswith(x.capability_prefix + ".")]
        return sorted(xs, key=lambda x: (-len(x.capability_prefix), x.capability_prefix))[0] if xs else None

    def pinned_plugin_ids(self):
        return frozenset(x.plugin_id for x in self.locked_providers)

    def trusted_artifact(self, plugin_id, sha256):
        return any(x.plugin_id == plugin_id and x.artifact_sha256 == sha256 for x in self.trusted_in_process_artifacts)

    def public_record(self):
        # Boot generation identity is a set-semantic identity. Construction order
        # must not change the digest.
        locked = sorted(self.locked_providers, key=lambda x: (x.capability_prefix, x.plugin_id, x.artifact_sha256))
        trusted = sorted(self.trusted_in_process_artifacts, key=lambda x: (x.plugin_id, x.artifact_sha256))
        return {
            "target": self.target,
            "claim_ceiling": self.claim_ceiling,
            "locked_providers": [
                {"capability_prefix": x.capability_prefix, "plugin_id": x.plugin_id, "artifact_sha256": x.artifact_sha256}
                for x in locked
            ],
            "trusted_in_process_artifacts": [
                {"plugin_id": x.plugin_id, "artifact_sha256": x.artifact_sha256}
                for x in trusted
            ],
            "external_mutation_authorized": self.external_mutation_authorized,
            "generation_label": self.generation_label,
        }


def plugin_descriptor_from_mapping(x: dict) -> PluginDescriptor:
    """Construct the typed descriptor from the normative static mapping.

    This parser deliberately mirrors `plugin-descriptor-v1alpha1.schema.json`:
    missing required keys and unknown keys fail closed instead of silently
    defaulting. JSON Schema is the language-neutral contract; this function is
    the Python binding.
    """
    if not isinstance(x, dict):
        raise ContractError("descriptor must be an object")
    keys = frozenset(x)
    missing = _DESCRIPTOR_KEYS - keys
    extra = keys - _DESCRIPTOR_KEYS
    if missing:
        raise ContractError("missing descriptor keys: " + ",".join(sorted(missing)))
    if extra:
        raise ContractError("unknown descriptor keys: " + ",".join(sorted(extra)))
    if x["schema_version"] != PLUGIN_SCHEMA_VERSION:
        raise ContractError("unsupported descriptor schema version")
    def parse_cap(v):
        if not isinstance(v, dict) or frozenset(v) != {"capability_id", "contract_version"}:
            raise ContractError("capability mapping must contain exactly capability_id,contract_version")
        return Capability(v["capability_id"], v["contract_version"])

    def parse_event(v):
        required = {"name", "mode", "durability", "contract_version"}
        if not isinstance(v, dict) or frozenset(v) != required:
            raise ContractError("event mapping must contain exactly name,mode,durability,contract_version")
        return EventSpec(v["name"], v["mode"], v["durability"], v["contract_version"])

    for field in ("provides", "requires", "events_consumed", "events_emitted", "permissions", "target_scopes"):
        if not isinstance(x[field], list):
            raise ContractError(f"{field} must be an array")
    try:
        return PluginDescriptor(
            plugin_id=x["plugin_id"],
            plugin_version=x["plugin_version"],
            plugin_class=x["plugin_class"],
            schema_version=x["schema_version"],
            api_version=x["api_version"],
            distribution_name=x["distribution_name"],
            distribution_version=x["distribution_version"],
            provides=tuple(parse_cap(v) for v in x["provides"]),
            requires=tuple(parse_cap(v) for v in x["requires"]),
            events_consumed=tuple(parse_event(v) for v in x["events_consumed"]),
            events_emitted=tuple(parse_event(v) for v in x["events_emitted"]),
            permissions=tuple(x["permissions"]),
            target_scopes=tuple(x["target_scopes"]),
            side_effect_class=x["side_effect_class"],
            execution_mode=x["execution_mode"],
            config_schema=x["config_schema"],
            state_schema=x["state_schema"],
            rollback_receipt_schema=x["rollback_receipt_schema"],
        )
    except (TypeError, KeyError) as exc:
        raise ContractError(f"malformed descriptor: {exc}") from exc
