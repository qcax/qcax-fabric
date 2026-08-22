from qcax_fabric_contracts import PluginDescriptor, Capability, EventSpec
from qcax_fabric_sdk import PluginDefinition

descriptor=PluginDescriptor(plugin_id='org.qcax.memory',plugin_version="0.1.0-alpha.1",plugin_class='FIRST_PARTY',distribution_name='qcax-fabric-plugin-memory',distribution_version="0.1.0a1",provides=(Capability('qcax.memory',"1.0.0"),),requires=(Capability('qcax.source.admission',"1.0.0"), Capability('qcax.identity',"1.0.0"), Capability('qcax.provenance',"1.0.0"),),events_consumed=(),events_emitted=(),side_effect_class='LOCAL_REVERSIBLE',execution_mode="TRUSTED_IN_PROCESS",rollback_receipt_schema='urn:qcax:schema:rollback-receipt:v1alpha1')

def mount(ctx):
    store={}
    def put(key,value,evidence):
        if not ctx.service("qcax.source.admission")(evidence): raise ValueError("ineligible evidence")
        store[key]=value
        return key
    def get(key): return store.get(key)
    ctx.provide("qcax.memory", {"put":put,"get":get})
    ctx.effect(store.clear,"memory-store-clear")

definition=PluginDefinition(descriptor,mount)
