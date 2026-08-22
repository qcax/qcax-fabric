from qcax_fabric_contracts import PluginDescriptor, Capability, EventSpec
from qcax_fabric_sdk import PluginDefinition

descriptor=PluginDescriptor(plugin_id='org.qcax.source-admission',plugin_version="0.1.0-alpha.1",plugin_class='SYSTEM_PINNED',distribution_name='qcax-fabric-plugin-source-admission',distribution_version="0.1.0a1",provides=(Capability('qcax.source.admission',"1.0.0"),),requires=(Capability('qcax.truth.read',"1.0.0"), Capability('qcax.provenance',"1.0.0"),),events_consumed=(),events_emitted=(),side_effect_class='NONE',execution_mode="TRUSTED_IN_PROCESS",rollback_receipt_schema='')

def mount(ctx):
    ctx.provide("qcax.source.admission", lambda r: bool(r.get("eligible",False)))

definition=PluginDefinition(descriptor,mount)
