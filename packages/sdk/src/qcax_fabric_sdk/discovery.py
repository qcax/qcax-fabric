"""Metadata-only discovery. This function never calls EntryPoint.load().
Static QCAX descriptors and artifact admission must be validated before code loading.
"""
from importlib.metadata import entry_points

def discover_entry_points(group="qcax.fabric.plugins"):
    eps=entry_points(group=group)
    return tuple({"name":ep.name,"value":ep.value,"group":ep.group,"distribution":getattr(getattr(ep,"dist",None),"name",None)} for ep in eps)
