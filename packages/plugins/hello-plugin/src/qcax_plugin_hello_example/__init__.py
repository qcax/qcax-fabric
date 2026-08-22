from qcax_fabric_contracts import PluginDescriptor, Capability, EventSpec
from qcax_fabric_sdk import PluginDefinition

descriptor=PluginDescriptor(plugin_id='example.qcax.hello',plugin_version="0.1.0-alpha.1",plugin_class='THIRD_PARTY',distribution_name='qcax-fabric-plugin-hello-example',distribution_version="0.1.0a1",provides=(Capability('example.hello',"1.0.0"),),requires=(),events_consumed=(),events_emitted=(),side_effect_class='NONE',execution_mode="TRUSTED_IN_PROCESS",rollback_receipt_schema='')

def mount(ctx):
    ctx.provide("example.hello", lambda name: f"hello {name}")

definition=PluginDefinition(descriptor,mount)
