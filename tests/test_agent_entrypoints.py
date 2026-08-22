import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_AGENT_PATHS = (
    "README.md",
    "docs/FINAL_ARCHITECTURE.md",
    "docs/PLUGIN_AUTHOR_GUIDE.md",
    "docs/THREAT_MODEL.md",
    "spec/plugin-descriptor-v1alpha1.schema.json",
    "spec/artifact-envelope-v1alpha1.schema.json",
    "spec/installation-receipt-v1alpha1.schema.json",
    "spec/boot-lock-v1alpha1.schema.json",
    "spec/release-lock-v1alpha1.schema.json",
    "llms.txt",
)

REQUIRED_INDEX_PATHS = tuple(
    rel for rel in REQUIRED_AGENT_PATHS if rel != "llms.txt"
) + (
    "AGENTS.md",
    "docs/INSTALLATION_IDENTITY.md",
    "docs/COMPATIBILITY_POLICY.md",
    "docs/NAMESPACE_POLICY.md",
    "github/RELEASE_ARTIFACT_CONTRACT.json",
    "github/RELEASE_PROVIDER_STATE_MACHINE.json",
    "github/ACTION_PIN_LEDGER.json",
    "github/ALPHA1_EXIT_GATE.json",
    "github/SETUP_RUNBOOK.md",
    "release/RELEASE_NOTES-v0.1.0-alpha.1.md",
    "scripts/run_all.py",
    "scripts/validate_repo.py",
    "scripts/run_contract_conformance.py",
    "scripts/run_mutations.py",
    "scripts/verify_release_payload.py",
    "tests/test_microkernel.py",
    "tests/test_release_pipeline.py",
    "tests/test_agent_entrypoints.py",
)


class AgentEntrypointTests(unittest.TestCase):
    def test_agents_references_only_live_required_entrypoints(self):
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        for rel in REQUIRED_AGENT_PATHS:
            self.assertTrue((ROOT / rel).is_file(), rel)
            self.assertIn(f"`{rel}`", agents, rel)
        self.assertNotIn("`docs/ARCHITECTURE.md`", agents)
        self.assertNotIn("`spec/PROTOCOL.md`", agents)
        self.assertNotIn("`research/RESEARCH_SYSTEM.json`", agents)

    def test_agent_index_paths_exist_and_are_unique(self):
        index = (ROOT / "llms.txt").read_text(encoding="utf-8")
        paths = [line[5:].strip() for line in index.splitlines() if line.startswith("PATH ")]
        self.assertEqual(len(paths), len(set(paths)))
        self.assertEqual(set(REQUIRED_INDEX_PATHS), set(paths))
        for rel in paths:
            self.assertTrue((ROOT / rel).is_file(), rel)

    def test_agent_index_keeps_current_claim_boundaries(self):
        index = (ROOT / "llms.txt").read_text(encoding="utf-8")
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        for token in (
            "TRUSTED_IN_PROCESS",
            "DURABLE",
            "SYSTEM_PINNED",
            "python scripts/run_all.py",
            "PREFLIGHT",
            "PUBLISH",
        ):
            self.assertIn(token, index + "\n" + agents)


if __name__ == "__main__":
    unittest.main()
