from qcax_fabric_contracts import PluginDescriptor, Capability, EventSpec
from qcax_fabric_sdk import PluginDefinition

descriptor=PluginDescriptor(plugin_id='org.qcax.provenance',plugin_version="0.1.0-alpha.1",plugin_class='SYSTEM_PINNED',distribution_name='qcax-fabric-plugin-provenance',distribution_version="0.1.0a1",provides=(Capability('qcax.provenance',"1.0.0"),),requires=(),events_consumed=(),events_emitted=(),side_effect_class='NONE',execution_mode="TRUSTED_IN_PROCESS",rollback_receipt_schema='')

def mount(ctx):
    ctx.provide("qcax.provenance", {"events":[]})

definition=PluginDefinition(descriptor,mount)
