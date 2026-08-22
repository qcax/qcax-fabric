"""Deterministic canonicalization for QCAX control-plane records.

The public specification requires RFC 8785 JCS. The alpha Python reference intentionally accepts
an RFC-8785-safe subset: ASCII object keys and no floating-point values. Within that subset,
`json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False)` is deterministic
and avoids cross-runtime floating-point serialization ambiguity. Full JCS vectors remain a v0.1
release conformance requirement before claiming general RFC 8785 conformance.
"""
import json, hashlib, re
_ASCII_KEY = re.compile(r"^[\x20-\x7e]+$")
class CanonicalizationError(ValueError): pass

def _check(v):
    if v is None or isinstance(v,(bool,int,str)): return
    if isinstance(v,float): raise CanonicalizationError("floats forbidden in QCAX JCS-safe control profile")
    if isinstance(v,list):
        for x in v: _check(x)
        return
    if isinstance(v,dict):
        for k,x in v.items():
            if not isinstance(k,str) or not _ASCII_KEY.match(k):
                raise CanonicalizationError("control-plane object keys must be printable ASCII")
            _check(x)
        return
    raise CanonicalizationError(f"unsupported canonical type: {type(v).__name__}")

def canonical_bytes(v)->bytes:
    _check(v)
    return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode("utf-8")

def canonical_sha256(v)->str:
    return hashlib.sha256(canonical_bytes(v)).hexdigest()
