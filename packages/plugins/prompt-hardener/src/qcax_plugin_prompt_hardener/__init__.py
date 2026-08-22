from qcax_fabric_contracts import PluginDescriptor, Capability, EventSpec
from qcax_fabric_sdk import PluginDefinition

descriptor=PluginDescriptor(plugin_id='org.qcax.prompt-hardener',plugin_version="0.1.0-alpha.1",plugin_class='FIRST_PARTY',distribution_name='qcax-fabric-plugin-prompt-hardener',distribution_version="0.1.0a1",provides=(Capability('qcax.prompt.compile',"1.0.0"),),requires=(Capability('qcax.truth.read',"1.0.0"), Capability('qcax.authorization',"1.0.0"),),events_consumed=(),events_emitted=(),side_effect_class='NONE',execution_mode="TRUSTED_IN_PROCESS",rollback_receipt_schema='')

def mount(ctx):
    truth=ctx.service("qcax.truth.read")
    def compile_prompt(raw):
        return {"raw":raw,"target":truth["target"],"claim_ceiling":truth["claim_ceiling"],"external_mutation":False}
    ctx.provide("qcax.prompt.compile", compile_prompt)

definition=PluginDefinition(descriptor,mount)
