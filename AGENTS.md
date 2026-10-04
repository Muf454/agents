# Toolkit maintenance

This repository contains reusable development tooling, not an application.
The user explicitly authorized Codex to implement this toolkit. For projects
bootstrapped from it, Claude Code is the primary architect and implementer;
Codex defaults to independent review as defined in `templates/AGENTS.md`.

Keep dependencies minimal, preserve target-project files, and keep merge,
deployment, and irreversible external operations under human control. Test
changes to scripts with `./scripts/ai-check`. Do not modify desktop configuration.
