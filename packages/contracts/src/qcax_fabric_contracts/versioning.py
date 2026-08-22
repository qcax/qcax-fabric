import re

# SemVer 2.0.0 core + identifier character grammar. Numeric prerelease
# identifiers are checked separately so leading zeroes are rejected.
_SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)


def _match_semver(v: str):
    if not isinstance(v, str):
        return None
    m = _SEMVER.fullmatch(v)
    if not m:
        return None
    prerelease = m.group(4)
    if prerelease:
        for ident in prerelease.split('.'):
            # SemVer 2.0.0 §9: numeric prerelease identifiers MUST NOT
            # contain leading zeroes.
            if ident.isdigit() and len(ident) > 1 and ident.startswith('0'):
                return None
    return m


def is_semver(v: str) -> bool:
    return _match_semver(v) is not None


def is_stable_contract_semver(v: str) -> bool:
    m = _match_semver(v)
    return bool(m and m.group(4) is None and m.group(5) is None)


def _parts(v):
    m = _match_semver(v)
    if not m:
        raise ValueError(f"not SemVer: {v}")
    return tuple(map(int, m.group(1, 2, 3)))


def contract_compatible(required: str, provided: str) -> bool:
    if not is_stable_contract_semver(required) or not is_stable_contract_semver(provided):
        raise ValueError("capability/event contract versions must be stable SemVer in v1alpha1")
    r = _parts(required)
    p = _parts(provided)
    if r[0] == 0 or p[0] == 0:
        return r[:2] == p[:2] and p[2] >= r[2]
    return r[0] == p[0] and p >= r
