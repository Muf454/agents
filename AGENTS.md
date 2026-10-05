# Toolkit maintenance

This repository contains reusable development tooling, not an application.
The user explicitly authorized Codex to implement this toolkit. For projects
bootstrapped from it, Claude Code is the primary architect and implementer;
Codex defaults to independent review as defined in `templates/AGENTS.md`.

Keep dependencies minimal, preserve target-project files, and keep merge,
deployment, and irreversible external operations under human control. Test
changes to scripts with `./scripts/ai-check`. Do not modify desktop configuration.

## Keep the flow chart current
A human-readable flow chart of the whole workflow lives in the Obsidian vault:
`~/zWiki/zWiki/20 Projects/agents/agents-flow.md` (Mermaid; one big picture, one task,
recovery, notifications, roles). Any change to the flow (a step, gate, role, notification,
recovery rule or default) must update that note and its `updated:` date in the same
session, and the PR description should say "Flow chart updated" or "Flow unchanged".
