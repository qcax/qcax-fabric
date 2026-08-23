from qcax_fabric_contracts import PluginDescriptor, Capability, EventSpec
from qcax_fabric_sdk import PluginDefinition

descriptor=PluginDescriptor(plugin_id='org.qcax.truth-policy',plugin_version="0.1.0-alpha.1",plugin_class='SYSTEM_PINNED',distribution_name='qcax-fabric-plugin-truth-policy',distribution_version="0.1.0a1",provides=(Capability('qcax.truth.read',"1.0.0"),),requires=(),events_consumed=(),events_emitted=(),side_effect_class='NONE',execution_mode="TRUSTED_IN_PROCESS",rollback_receipt_schema='')

def mount(ctx):
    ctx.provide("qcax.truth.read", {"target":ctx.boot_lock.target,"claim_ceiling":ctx.boot_lock.claim_ceiling})

definition=PluginDefinition(descriptor,mount)
