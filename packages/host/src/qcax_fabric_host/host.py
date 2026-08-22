from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable
from qcax_fabric_contracts import *
from qcax_fabric_contracts.canonical import canonical_sha256
from qcax_fabric_contracts.versioning import contract_compatible
from qcax_fabric_sdk import PluginDefinition, AdmissionTicket, validate_admission_ticket

class HostError(RuntimeError): pass
class ManifestError(HostError): pass
class ProviderConflict(HostError): pass
class ArtifactVariantConflict(HostError): pass
class BootLockViolation(HostError): pass
class GuardDenied(HostError): pass
class UnsupportedExecutionMode(HostError): pass
class DependencyCycle(HostError): pass

class State(str,Enum):
    DISCOVERED="DISCOVERED"; VALIDATED="VALIDATED"; WAITING="WAITING_DEPENDENCIES"; MOUNTING="MOUNTING"; ACTIVE="ACTIVE"; QUIESCING="QUIESCING"; UNMOUNTING="UNMOUNTING"; UNLOADED="UNLOADED"; HOLD="HOLD"; FAILED="FAILED"
@dataclass
class EffectRecord:
    seq:int; plugin_id:str; description:str; state:str="ACTIVE"; error:str|None=None
@dataclass
class PluginState:
    envelope:PluginEnvelope; definition:PluginDefinition; state:State=State.DISCOVERED; pending_services:dict[str,Any]=field(default_factory=dict); disposers:list[tuple[Callable[[],Any],EffectRecord]]=field(default_factory=list); failure:str|None=None

class PluginContext:
    def __init__(self,host,plugin_id): self._host=host; self.plugin_id=plugin_id
    @property
    def descriptor(self): return self._host._plugins[self.plugin_id].envelope.descriptor
    @property
    def boot_lock(self): return self._host.boot_lock
    def provide(self,capability_id,implementation):
        p=self._host._plugins[self.plugin_id]
        if p.state!=State.MOUNTING: raise HostError("provide is mount-scoped")
        declared={x.capability_id for x in p.envelope.descriptor.provides}
        if capability_id not in declared: raise ManifestError("undeclared capability")
        if capability_id in p.pending_services: raise ProviderConflict("duplicate pending service")
        p.pending_services[capability_id]=implementation
    def service(self,capability_id): return self._host.service(capability_id)
    def effect(self,disposer,description):
        if not callable(disposer): raise TypeError("disposer must be callable")
        p=self._host._plugins[self.plugin_id]
        if p.state!=State.MOUNTING: raise HostError("effect is mount-scoped")
        r=EffectRecord(len(self._host.effect_journal)+1,self.plugin_id,description)
        self._host.effect_journal.append(r); p.disposers.append((disposer,r)); return disposer
    def on(self,spec,handler,priority=0):
        if spec not in self.descriptor.events_consumed: raise ManifestError("undeclared event consume")
        if not isinstance(priority,int): raise TypeError("event priority must be int")
        token=self._host._register_handler(self.plugin_id,spec,handler,priority)
        try:
            self.effect(lambda:self._host._unregister_handler(token),f"event:{spec.name}")
        except Exception:
            self._host._unregister_handler(token)
            raise
    def dispatch(self,spec,payload):
        if spec not in self.descriptor.events_emitted: raise ManifestError("undeclared event emit")
        return self._host.dispatch(spec,payload,self.plugin_id)

class PluginHost:
    """Tiny generic TCB. High-level QCAX systems remain plugin-shaped; authority is BootLock-bound."""
    def __init__(self,boot_lock:BootLock):
        self.boot_lock=boot_lock; self._plugins={}; self._services={}; self._events={}; self._handlers={}; self._handler_seq=0
        self.artifact_occurrences={}; self.variant_conflicts=[]; self.effect_journal=[]; self.lifecycle=[]; self.event_receipts=[]
        self.generation_digest=canonical_sha256(boot_lock.public_record())
    def _tr(self,p,to,reason):
        prev=p.state; p.state=to; self.lifecycle.append({"seq":len(self.lifecycle)+1,"plugin_id":p.envelope.descriptor.plugin_id,"from":prev.value,"to":to.value,"reason":reason})
    def _check_artifact_variant(self,d:PluginDescriptor,a:ArtifactIdentity):
        key=(d.plugin_id,d.plugin_version); known=self.artifact_occurrences.get(key,set()); dig={x[0] for x in known}
        if dig and a.sha256 not in dig:
            raise ArtifactVariantConflict("same plugin id/version has different bytes")
    def observe_artifact(self,d:PluginDescriptor,a:ArtifactIdentity):
        self._check_artifact_variant(d,a)
        key=(d.plugin_id,d.plugin_version); known=self.artifact_occurrences.setdefault(key,set())
        known.add((a.sha256,a.occurrence_id))
    def _validate(self,e:PluginEnvelope):
        d=e.descriptor
        if "*" not in d.target_scopes and self.boot_lock.target not in d.target_scopes: raise ManifestError("target mismatch")
        if d.execution_mode!="TRUSTED_IN_PROCESS": raise UnsupportedExecutionMode("alpha host executes only TRUSTED_IN_PROCESS plugins")
        if d.plugin_class in {"THIRD_PARTY","ADAPTER"} and not self.boot_lock.trusted_artifact(d.plugin_id,e.artifact.sha256):
            raise BootLockViolation("third-party/adapter requires exact-artifact TRUSTED_IN_PROCESS BootLock trust")
        if d.side_effect_class=="EXTERNAL_MUTATION" and not self.boot_lock.external_mutation_authorized: raise BootLockViolation("external mutation not authorized")
        for c in d.provides:
            lock=self.boot_lock.lock_for(c.capability_id)
            if lock:
                if d.plugin_class!="SYSTEM_PINNED": raise BootLockViolation("reserved capability requires SYSTEM_PINNED")
                if lock.plugin_id!=d.plugin_id or lock.artifact_sha256!=e.artifact.sha256: raise BootLockViolation("pinned identity mismatch")
        if d.plugin_class=="SYSTEM_PINNED" and d.plugin_id not in self.boot_lock.pinned_plugin_ids(): raise BootLockViolation("unlocked SYSTEM_PINNED plugin")
    def _validate_event_contracts(self,d):
        pending={}
        for s in (*d.events_consumed,*d.events_emitted):
            if s.durability=="DURABLE":
                raise ManifestError("DURABLE events are reserved but unsupported by alpha1 host")
            old=self._events.get(s.name) or pending.get(s.name)
            if old and old!=s: raise ManifestError("event contract conflict")
            pending[s.name]=s
        return pending
    def _ticket_envelope(self,ticket:AdmissionTicket):
        try:
            return validate_admission_ticket(ticket)
        except Exception as exc:
            raise ManifestError(f"verified AdmissionTicket required: {type(exc).__name__}") from exc
    def preflight(self,ticket:AdmissionTicket):
        """Side-effect-free admission of a verifier-issued InstalledImage ticket.

        Call this before EntryPoint.load(). The ticket itself is created only after
        RECORD/InstalledImage verification; caller-constructed PluginEnvelope objects
        are not executable admission capabilities.
        """
        envelope=self._ticket_envelope(ticket)
        d=envelope.descriptor
        if d.plugin_id in self._plugins: raise HostError("duplicate installed plugin id")
        self._validate_event_contracts(d)
        self._validate(envelope)
        self._check_artifact_variant(d,envelope.artifact)
        rec={"plugin_id":d.plugin_id,"plugin_version":d.plugin_version,"artifact_sha256":envelope.artifact.sha256,
             "admission_ticket_sha256":ticket.ticket_sha256,"installation_receipt_sha256":canonical_sha256(ticket.receipt.public_record()),
             "decision":"PASS","generation_digest":self.generation_digest}
        rec["receipt_sha256"]=canonical_sha256(rec)
        return rec

    def add(self,ticket:AdmissionTicket,definition:PluginDefinition):
        envelope=self._ticket_envelope(ticket)
        d=envelope.descriptor
        if d!=definition.descriptor: raise ManifestError("descriptor/code definition mismatch")
        if d.plugin_id in self._plugins: raise HostError("duplicate installed plugin id")
        event_contracts=self._validate_event_contracts(d)
        self._validate(envelope)
        self.observe_artifact(d,envelope.artifact)
        p=PluginState(envelope,definition)
        self._plugins[d.plugin_id]=p
        try:
            self._events.update(event_contracts)
            self._tr(p,State.VALIDATED,"descriptor+artifact+bootlock")
            self._reconcile()
            return p.state
        except Exception:
            # add is transactional with respect to installed plugin/event contracts.
            self._plugins.pop(d.plugin_id,None)
            for name,spec in event_contracts.items():
                if not any(spec2.name==name for q in self._plugins.values() for spec2 in (*q.envelope.descriptor.events_consumed,*q.envelope.descriptor.events_emitted)):
                    self._events.pop(name,None)
            raise
    def _providers_declared(self,cap):
        out=[]
        for pid,p in self._plugins.items():
            for c in p.envelope.descriptor.provides:
                if c.capability_id==cap.capability_id and contract_compatible(cap.contract_version,c.contract_version): out.append(pid)
        return out
    def _requirements_ready(self,p):
        for r in p.envelope.descriptor.requires:
            svc=self._services.get(r.capability_id)
            if not svc or not contract_compatible(r.contract_version,svc[1]): return False
        return True
    def _cycle_members(self):
        graph={pid:set() for pid,p in self._plugins.items() if p.state in {State.VALIDATED,State.WAITING}}
        for pid in list(graph):
            p=self._plugins[pid]
            for r in p.envelope.descriptor.requires:
                if r.capability_id in self._services: continue
                for prov in self._providers_declared(r):
                    if prov in graph: graph[pid].add(prov)
        seen=set(); stack=[]; on=set(); cyc=set()
        def dfs(v):
            seen.add(v); stack.append(v); on.add(v)
            for n in graph[v]:
                if n not in seen: dfs(n)
                elif n in on:
                    i=stack.index(n); cyc.update(stack[i:])
            stack.pop(); on.remove(v)
        for v in graph:
            if v not in seen: dfs(v)
        return cyc
    def _reconcile(self):
        changed=True
        while changed:
            changed=False
            for p in list(self._plugins.values()):
                if p.state in {State.VALIDATED,State.WAITING}:
                    if self._requirements_ready(p):
                        if self._mount(p): changed=True
                    elif p.state!=State.WAITING:
                        p.failure="dependencies"; self._tr(p,State.WAITING,"dependencies")
            for p in list(self._plugins.values()):
                if p.state==State.ACTIVE and not self._requirements_ready(p): self._deactivate(p,State.WAITING,"dependency-loss"); changed=True
        cyc=self._cycle_members()
        for pid in sorted(cyc):
            p=self._plugins[pid]
            if p.state in {State.VALIDATED,State.WAITING}:
                p.failure="dependency cycle"; self._tr(p,State.HOLD,"dependency-cycle")
    def _mount(self,p):
        d=p.envelope.descriptor
        for cap in d.provides:
            if cap.capability_id in self._services:
                p.failure="provider conflict"
                if p.state!=State.WAITING: self._tr(p,State.WAITING,"provider-conflict")
                return False
        self._tr(p,State.MOUNTING,"requirements-ready"); ctx=PluginContext(self,d.plugin_id)
        try:
            if p.definition.on_mount: p.definition.on_mount(ctx)
            declared={x.capability_id for x in d.provides}
            if set(p.pending_services)!=declared: raise ManifestError("mount must provide exactly declared capabilities")
            for c in d.provides: self._services[c.capability_id]=(d.plugin_id,c.contract_version,p.pending_services[c.capability_id])
            p.failure=None; self._tr(p,State.ACTIVE,"mounted"); return True
        except Exception as exc:
            p.failure=f"{type(exc).__name__}: {exc}"; self._dispose(p); p.pending_services.clear(); self._tr(p,State.FAILED,"mount-failure")
            if isinstance(exc,HostError): raise
            return False
    def _dispose(self,p):
        for fn,rec in reversed(p.disposers):
            try: fn(); rec.state="DISPOSED"
            except Exception as exc: rec.state="DISPOSE_ERROR"; rec.error=f"{type(exc).__name__}: {exc}"
        p.disposers.clear()
    def _deactivate(self,p,next_state,reason):
        d=p.envelope.descriptor; self._tr(p,State.QUIESCING,reason); self._tr(p,State.UNMOUNTING,reason); ctx=PluginContext(self,d.plugin_id)
        try:
            if p.definition.on_unmount: p.definition.on_unmount(ctx)
        finally:
            for cap in d.provides:
                if self._services.get(cap.capability_id,(None,))[0]==d.plugin_id: self._services.pop(cap.capability_id,None)
            self._dispose(p); p.pending_services.clear(); self._tr(p,next_state,reason)
    def remove(self,plugin_id):
        p=self._plugins[plugin_id]
        if plugin_id in self.boot_lock.pinned_plugin_ids(): raise BootLockViolation("pinned plugin cannot be removed within generation")
        if p.state==State.ACTIVE: self._deactivate(p,State.UNLOADED,"remove")
        else: self._tr(p,State.UNLOADED,"remove")
        del self._plugins[plugin_id]; self._reconcile()
    def shutdown(self):
        active={pid for pid,p in self._plugins.items() if p.state==State.ACTIVE}
        while active:
            leaves=[]
            for pid in active:
                provides={c.capability_id for c in self._plugins[pid].envelope.descriptor.provides}
                used=any(any(r.capability_id in provides for r in self._plugins[qid].envelope.descriptor.requires) for qid in active-{pid})
                if not used: leaves.append(pid)
            if not leaves: leaves=sorted(active)
            for pid in sorted(leaves):
                self._deactivate(self._plugins[pid],State.UNLOADED,"generation-shutdown"); active.remove(pid)
    def service(self,capability_id):
        if capability_id not in self._services: raise KeyError(capability_id)
        return self._services[capability_id][2]
    def state(self,pid): return self._plugins[pid].state
    def _register_handler(self,pid,spec,handler,priority=0):
        old=self._events.get(spec.name)
        if old and old!=spec: raise ManifestError("event contract conflict")
        self._events[spec.name]=spec; self._handler_seq+=1
        token=(spec.name,self._handler_seq)
        self._handlers.setdefault(spec.name,[]).append((priority,pid,self._handler_seq,handler))
        return token
    def _unregister_handler(self,token):
        name,seq=token; self._handlers[name]=[x for x in self._handlers.get(name,[]) if x[2]!=seq]
    def _active_handlers(self,event_name):
        rows=[x for x in self._handlers.get(event_name,[]) if self._plugins.get(x[1]) and self._plugins[x[1]].state==State.ACTIVE]
        return sorted(rows,key=lambda x:(x[0],x[1],x[2]))
    def _event_receipt(self,spec,emitter,pdig,decision,reason="",**extra):
        rec={"seq":len(self.event_receipts)+1,"event":spec.name,"mode":spec.mode,"emitter":emitter,"payload_sha256":pdig,"decision":decision}
        if reason: rec["reason"]=reason
        rec.update(extra)
        rec["receipt_sha256"]=canonical_sha256(rec); self.event_receipts.append(rec); return rec
    def _handler_error(self,spec,emitter,pdig,handler_plugin_id,exc):
        etype=f"{type(exc).__module__}.{type(exc).__qualname__}"
        edig=canonical_sha256({"event":spec.name,"mode":spec.mode,"handler_plugin_id":handler_plugin_id,"error_type":etype})
        self._event_receipt(spec,emitter,pdig,"ERROR","HANDLER_EXCEPTION",handler_plugin_id=handler_plugin_id,error_type=etype,error_sha256=edig)
    def dispatch(self,spec,payload,emitter="host"):
        if spec.durability=="DURABLE": raise ManifestError("DURABLE events are reserved but unsupported by alpha1 host")
        old=self._events.get(spec.name)
        if old and old!=spec: raise ManifestError("event contract conflict")
        pdig=canonical_sha256(payload)
        hs=self._active_handlers(spec.name)
        result=None
        if spec.mode=="emit":
            for _,pid,_,h in hs:
                try: h(payload)
                except Exception as exc:
                    self._handler_error(spec,emitter,pdig,pid,exc); raise
        elif spec.mode=="serial":
            result=[]
            for _,pid,_,h in hs:
                try: result.append(h(payload))
                except Exception as exc:
                    self._handler_error(spec,emitter,pdig,pid,exc); raise
        elif spec.mode=="waterfall":
            result=payload
            for _,pid,_,h in hs:
                try: x=h(result)
                except Exception as exc:
                    self._handler_error(spec,emitter,pdig,pid,exc); raise
                result=result if x is None else x
        elif spec.mode=="guard":
            if not hs:
                self._event_receipt(spec,emitter,pdig,"DENY","NO_ACTIVE_GUARD_HANDLER")
                raise GuardDenied(spec.name)
            decisions=[]
            for _,pid,_,h in hs:
                try: x=h(payload)
                except Exception as exc:
                    self._handler_error(spec,emitter,pdig,pid,exc); raise
                decisions.append((x is True) or (isinstance(x,dict) and x.get("allow") is True))
            if not all(decisions):
                self._event_receipt(spec,emitter,pdig,"DENY","GUARD_DENIED")
                raise GuardDenied(spec.name)
            result=True
        self._event_receipt(spec,emitter,pdig,"PASS"); return result
