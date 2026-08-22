from qcax_fabric_contracts import PluginDescriptor, Capability, EventSpec
from qcax_fabric_sdk import PluginDefinition

descriptor=PluginDescriptor(plugin_id='org.qcax.authorization',plugin_version="0.1.0-alpha.1",plugin_class='SYSTEM_PINNED',distribution_name='qcax-fabric-plugin-authorization',distribution_version="0.1.0a1",provides=(Capability('qcax.authorization',"1.0.0"),),requires=(),events_consumed=(),events_emitted=(),side_effect_class='NONE',execution_mode="TRUSTED_IN_PROCESS",rollback_receipt_schema='')

def mount(ctx):
    ctx.provide("qcax.authorization", lambda side_effect: bool(ctx.boot_lock.external_mutation_authorized) if side_effect=="EXTERNAL_MUTATION" else True)

definition=PluginDefinition(descriptor,mount)
