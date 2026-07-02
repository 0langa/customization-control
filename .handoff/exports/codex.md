# Continuation Prompt — Codex

You are resuming work on `customization-control` previously done by Claude Code.

## Task

**Build customization-control plugin** — Status: `in_progress` (functional, needs next iteration)

### Objective

Cross-provider plugin to audit, deduplicate, repair, sync, and manage agent customizations across Codex, Claude Code, and Kimi Code.

## What Is Done

- Full plugin with 6 skills, 5 PowerShell scripts, 4 reference policies, 24 passing Pester tests.
- Skills: customization-audit (entrypoint), customization-dedupe, customization-sync, customization-repair, marketplace-manager, windows-customization-guard (internal).
- Scripts: inventory.ps1, validate.ps1, plan-dedupe.ps1, apply-dedupe.ps1, quarantine.ps1 — all support `-OutputFormat json|table` and `-DryRun`.
- Cross-provider manifests: `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`, `kimi.plugin.json`.
- In marketplace: `customization-control@0langas-plugins` — installed and enabled in Codex.
- Tested across all 3 providers with consistent results: 118 items, 10 broken links, 16 duplicate groups.
- Join-Path PS 5.1 compat fix applied.

## What To Do Next

1. **Implement dedupe execution**: run `scripts/plan-dedupe.ps1` → present dry-run to user → execute `scripts/apply-dedupe.ps1` with quarantine. The scripts exist and work, but the end-to-end user-facing workflow in the skill hasn't been exercised.
2. **Implement sync workflow**: detect missing provider links across `.codex/skills/`, `.claude/skills/`, `.kimi-code/skills/` and create junctions/symlinks to canonical sources.
3. **Implement repair**: fix the 10 broken symlinks in `~/.claude/skills/` — they are junctions pointing to `C:\Users\juliu\.agents\skills\*` targets that no longer exist (note the truncated username in the path).
4. **Migrate legacy roots**: user wants to move away from `~/.agents/skills/` to provider-specific roots. The dedupe + sync skills can facilitate this.
5. **Integration tests**: exercise full audit→plan→apply pipeline in a temp sandbox.
6. **Quality eval**: `/plugin-evaluation-kimi:certify`.

## Key Architecture

- **Skills contain decision logic** — not CLI wrappers. They have trigger surfaces, safety policies, recovery workflows.
- **Scripts are deterministic helpers** — pure functions with JSON output, no side effects beyond what's explicitly requested.
- **References encode policies** in `references/`:
  - `dedupe-policy.json`: 7 categories (canonical, provider-link, duplicate-copy, stale-cache, conflict, broken-link, unknown)
  - `repair-policy.json`: safe/unsafe split, quarantine config
  - `known-roots.json`: all provider paths
  - `marketplace-policy.json`: entry management rules

## Safety Rules

- Never delete conflict or unknown items.
- Always quarantine before removing duplicate-copy items.
- Dry-run before any mutation.
- All destructive ops use resolved absolute paths.
- Refuse to delete outside approved roots.
- Follow `references/*.json` policies.

## Live System State

- 118 customizations (84 skills, 34 cached plugins)
- Providers: codex 62, legacy 34, claude-code 16, kimi-code 6
- 10 broken symlinks: `~/.claude/skills/{caveman,caveman-commit,caveman-compress,caveman-help,caveman-review,compress,find-skills,openai-docs,python-testing-patterns,systematic-debugging}`
- 16 duplicate groups (9 identical, 1+ conflicts)

## Running Tests

```powershell
pwsh -NoProfile -Command "Import-Module Pester -MinimumVersion 5.0; Invoke-Pester -Path tests -Output Detailed"
```

## Git State

Branch: `main`, clean. Remote: `origin` → `https://github.com/0langa/customization-control.git`
