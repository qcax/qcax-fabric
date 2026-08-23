# Plugin identity contract

Each Python plugin distribution must provide both:
1. a Python entry point in group `qcax.fabric.plugins` for Python discovery; and
2. a packaged language-neutral `qcax-plugin.json` descriptor for QCAX identity/trust/semantic validation.

The release validator compares entry-point key, descriptor plugin ID, package release-lock identity and installed definition. No one surface is permitted to silently rename a plugin.
