# Continuation Prompt — Claude Code

You are resuming work previously captured by another agent. Use Claude Code tools (`git`, `read`, `edit`, `bash`, etc.) as needed. Prefer shell and git inspection for workspace state.

## Task

**Build customization-control plugin**

Status: `in_progress`

### Objective

Develop a high-quality, reliable cross-provider customization-control plugin that audits, deduplicates, repairs, syncs, and publishes agent customizations across Codex, Claude Code, and Kimi Code without degrading into a CLI-only wrapper.

## What Was Done

- Created public repo 0langa/0langas-skill-center.
- Added official-ai-devdocs skill with provider-specific discovery symlinks for .codex, .claude, and .kimi-code.
- Added muteman skill and linked it into repo/provider paths and ~/.codex/skills.
- Discussed customization-control plugin surface and settled on combining skill-center-curator, agent-install-sync, addon-archive-miner, windows-agent-pathguard, and skill-release-publisher into one plugin.
- Confirmed this plugin should also dedupe customizations so the @ picker is not filled with duplicated skills/plugins from overlapping roots.

## What Is In Progress

- Handing off full plugin development to Claude Code.

## Next Steps

- Read this handoff and inspect repo state.
- Use official-ai-devdocs behavior: verify current provider docs for plugin, skill, marketplace, and MCP/customization shapes before implementation.
- Scaffold customization-control in `C:\Users\Julius\source\repos\customization-control` with real plugin manifests, skills, references, scripts, and tests.
- Implement inventory first. It should discover skills/plugins/MCP/marketplaces across Codex, Claude Code, Kimi Code, ~/.codex, ~/.agents, repo-local .codex/.claude/.kimi-code, plugin cache, and marketplace roots.
- Implement dry-run dedupe planning before any mutation. Distinguish identical duplicates from conflicting same-name customizations.
- Implement safe repair with quarantine/backups and resolved-path guardrails.
- Implement validation tests for path safety, duplicate classification, symlink handling, marketplace JSON editing, dry-run behavior, and no deletion outside approved roots.
- Document usage and update README when the plugin is ready.

## Blockers

- _(none)_

## Workspace State

Git status:

```text
?? .handoff/
```

Changed files:
- `.handoff/active.json`
- `.handoff/active.md`
- `.handoff/exports/claude-code.md`

Tests run:
- `Get-Content -Raw .handoff\active.json | ConvertFrom-Json` — passed
## Important Context

- File: `README.md`
- File: `official-ai-devdocs/SKILL.md`
- File: `muteman/SKILL.md`
- File: `.codex/skills/*`
- File: `.claude/skills/*`
- File: `.kimi-code/skills/*`
- File: `C:\Users\Julius\.codex\skills`
- File: `C:\Users\Julius\.agents\skills`
- File: `C:\Users\Julius\.agents\plugins\marketplace.json`
- File: `C:\Users\Julius\.codex\plugins`
- File: `C:\Users\Julius\.codex\plugins\cache`

- Decision: Plugin concept name: customization-control.
- Decision: Main objective: keep the user's agent customization layer clean across Codex, Claude Code, and Kimi Code: skills, plugins, marketplaces, MCP config, symlinks, stale installs, duplicate picker entries, and publish/install state.
- Decision: Skill surface should include six skills: customization-audit, customization-dedupe, customization-sync, customization-repair, marketplace-manager, windows-customization-guard.
- Decision: customization-audit is the entrypoint skill and should route to the narrower skills when appropriate.
- Decision: Dedupe categories: canonical, provider-link, duplicate-copy, stale-cache, conflict, broken-link, unknown.
- Decision: Safe default flow: inventory -> plan -> apply deterministic safe repairs -> quarantine risky removals -> revalidate provider visibility/config -> write concise machine-readable report.
- Decision: Marketplace manager should validate/update marketplace entries, remove stale entries, refresh/reinstall cleanly, and verify a plugin appears once. It should not convert plugin formats.
- Decision: Scripts should live under scripts/ and provide deterministic inventory/validation/plan/apply operations. They must support dry-run and structured JSON output.
- Decision: References should encode policies: known roots, dedupe policy, repair policy, marketplace policy, provider compatibility.
- Decision: The screenshot motivating this work shows duplicate entries in the @ picker from overlapping skill/plugin installs, e.g. Addon Archive and Algorithmic Art appearing more than once.

- Constraint: Target provider is Claude Code. Continue from this repo root.
- Constraint: Use official provider documentation before asserting current Codex, Claude Code, or Kimi Code customization syntax, install paths, plugin manifests, marketplace fields, MCP config shapes, or skill discovery behavior.
- Constraint: Do not build a plugin that is merely a CLI app with thin skill wrappers. Skills must contain the decision logic, trigger surface, safety policy, and recovery workflow; scripts are deterministic helpers only.
- Constraint: Highest reliability standard: inventory before mutation, dry-run plan before repair, explicit safety classes, backups/quarantine for risky removals, and validation after every applied change.
- Constraint: Windows-first implementation. Use PowerShell-safe path handling and resolved absolute path checks. Avoid string-built destructive shell commands and avoid mixing shells for file deletion/moving.
- Constraint: Never delete unknown customizations silently. Unknown, conflicting, or non-identical duplicates must be reported or quarantined, not removed outright.
- Constraint: Keep provider surfaces tidy and explicit: .codex, .claude, .kimi-code in repos; user-wide Codex skills under ~/.codex/skills; existing .agents roots may still exist and are part of dedupe analysis.
- Constraint: Marketplace support is in scope only for already-ported plugins. Porting plugins between provider formats belongs to a future plugin.

- Decision: Plugin destination is confirmed: `C:\Users\Julius\source\repos\customization-control`, private GitHub repo `0langa/customization-control`.
- Open question: Confirm exact marketplace destination before publishing: personal marketplace at ~/.agents/plugins/marketplace.json versus a repo/team marketplace.
- Open question: Confirm whether the plugin should manage only local Windows roots initially or include portable macOS/Linux roots in references for later.

## Capability Warnings

- **Required:** `local workspace` (filesystem via claude-code): Develop plugin files and tests in the repo or selected plugin workspace.  Fallback: local-equivalent — Use Claude Code local filesystem access in the same workspace.
- **Required:** `PowerShell or local shell` (shell via claude-code): Run validation scripts, tests, and safe filesystem inspections.  Fallback: local-equivalent — Use whatever shell Claude Code provides for local commands; on Windows prefer PowerShell-safe commands.

## Safety Notes

- Privacy note: No secrets captured. Paths to local skill/plugin roots are included because they are necessary for the task.

## Resume Summary

User wants Claude Code to fully develop a high-quality customization-control plugin. The plugin should manage the user's agent customization layer across Codex, Claude Code, and Kimi Code. It should audit, dedupe, sync, repair, and marketplace-manage skills/plugins/MCP/config without becoming a CLI-only wrapper. Core problem: duplicate customizations from overlapping roots clutter the @ picker and old plugin installs/caches can accumulate after development/reinstall cycles.

Continue from C:\Users\Julius\source\repos\customization-control. Read .handoff/active.json and .handoff/active.md. Build the customization-control plugin to the highest reliability standard. Use C:\Users\Julius\source\repos\0langas-skill-center as context for the user's existing skill-center layout, but implement the plugin in this customization-control repo. Start by verifying current official docs for Codex, Claude Code, and Kimi Code customization/plugin/skill/marketplace paths and schemas. Then scaffold the plugin with real skill surfaces, references, scripts, and tests. Do not make it just a CLI app: skills must contain decision logic and safe workflows; scripts are deterministic helpers. Implement inventory, dry-run dedupe planning, safe repair/quarantine, marketplace management for already-ported plugins, Windows path guardrails, and validation. Preserve existing repo conventions and avoid destructive cleanup without a plan and safety checks.
