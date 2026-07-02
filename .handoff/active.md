# Build customization-control plugin

> Handoff ID: `20260702-071855-749`  
> Created: 2026-07-02T07:18:55.749497Z  
> Updated: 2026-07-02T07:24:00.000000Z  
> Created by: `codex`  
> Target provider: `claude-code`

## Objective

Develop a high-quality, reliable cross-provider `customization-control` plugin that audits, deduplicates, repairs, syncs, and publishes agent customizations across Codex, Claude Code, and Kimi Code without degrading into a CLI-only wrapper.

## Current State

The implementation repository is `C:\Users\Julius\source\repos\customization-control`.

The existing skill-center context repository is `C:\Users\Julius\source\repos\0langas-skill-center`.

The skill-center context repo currently contains:

- `official-ai-devdocs/`
- `muteman/`
- `.codex/skills/*`
- `.claude/skills/*`
- `.kimi-code/skills/*`
- `README.md`

Git was clean before creating this handoff. Current expected git status is:

```text
?? .handoff/
```

## What Was Done

- Created public repo `0langa/0langas-skill-center`.
- Added `official-ai-devdocs` with provider-specific discovery symlinks for `.codex`, `.claude`, and `.kimi-code`.
- Added `muteman`, including provider symlinks and `~/.codex/skills/muteman`.
- Discussed a combined plugin that absorbs the useful parts of:
  - `skill-center-curator`
  - `agent-install-sync`
  - `addon-archive-miner`
  - `windows-agent-pathguard`
  - `skill-release-publisher`
- User wants a plugin that can clean up duplicated customizations, stale plugin installs, duplicate skill roots, marketplace drift, broken symlinks, and config mess across Codex, Claude Code, and Kimi Code.

## Key Product Direction

Plugin concept name: `customization-control`.

Core problem: the user's `@` picker and customization environment can get noisy after repeated plugin development, reinstalling, cache churn, and overlapping roots such as `.agents`, `.codex`, user skill homes, and plugin cache directories.

The plugin should provide a reliable, safe path to:

1. Inventory agent customizations.
2. Detect duplicates and stale installs.
3. Choose or confirm canonical sources.
4. Repair broken links/config.
5. Quarantine risky duplicates.
6. Validate each provider still sees the correct customization set.
7. Manage marketplace entries for already-ported plugins.

## Required Skill Surface

Build the plugin with real skill surfaces. Do not make it just a CLI app.

Recommended skills:

- `customization-audit`: entrypoint; inventory and plan.
- `customization-dedupe`: duplicate picker entries, duplicate skill/plugin installs, stale copies.
- `customization-sync`: keep canonical folder, provider links, and user homes aligned.
- `customization-repair`: fix broken symlinks, invalid paths, stale marketplace entries, invalid manifests.
- `marketplace-manager`: manage existing/ported plugin marketplace entries and reinstall/update flow.
- `windows-customization-guard`: Windows path, symlink, PowerShell, and deletion safety.

Scripts may exist, but they are deterministic helpers only. The skills must contain the decision logic, trigger behavior, safety policy, and recovery workflow.

## Dedupe Policy

Classify findings before mutation:

- `canonical`: source of truth, keep.
- `provider-link`: symlink/junction into canonical folder, keep or repair.
- `duplicate-copy`: same content copied elsewhere, remove only with dry-run plan and backup/quarantine.
- `stale-cache`: old generated/cache artifact, remove only if rebuildable.
- `conflict`: same name but different content, do not auto-delete.
- `broken-link`: remove/recreate if target and intent are clear.
- `unknown`: report only.

Never delete unknown or conflicting customizations silently.

## Quality Bar

- Verify current official provider docs before asserting Codex, Claude Code, or Kimi Code customization paths, plugin manifests, marketplace fields, MCP config shapes, or skill discovery behavior.
- Inventory before mutation.
- Dry-run plan before repair.
- Apply only deterministic safe repairs automatically.
- Quarantine or back up risky removals.
- Use resolved absolute path checks for every destructive filesystem operation.
- Keep Windows behavior first-class.
- Avoid shell mixing for file deletion/move operations.
- Tests must cover path safety, duplicate classification, symlink handling, marketplace JSON editing, dry-run behavior, and no deletion outside approved roots.

## Important Paths

- Repo: `C:\Users\Julius\source\repos\0langas-skill-center`
- Codex user skills: `C:\Users\Julius\.codex\skills`
- Legacy/user agent skills: `C:\Users\Julius\.agents\skills`
- Personal marketplace candidate: `C:\Users\Julius\.agents\plugins\marketplace.json`
- Codex plugins/cache: `C:\Users\Julius\.codex\plugins`
- Codex plugin cache: `C:\Users\Julius\.codex\plugins\cache`

## Open Questions

- Plugin destination is confirmed: `C:\Users\Julius\source\repos\customization-control`.
- Confirm marketplace destination before publishing: personal marketplace versus repo/team marketplace.
- Decide whether initial implementation is Windows-only or includes portable roots for macOS/Linux references.

## Resume Prompt

Continue from `C:\Users\Julius\source\repos\customization-control`. Read `.handoff/active.json`, `.handoff/active.md`, and `.handoff/exports/claude-code.md`.

Build the `customization-control` plugin to the highest reliability standard. Use `C:\Users\Julius\source\repos\0langas-skill-center` as context for the user's current skill-center layout, but implement the plugin in this repository. Start by verifying current official docs for Codex, Claude Code, and Kimi Code customization/plugin/skill/marketplace paths and schemas. Then scaffold the plugin with real skill surfaces, references, scripts, and tests. Do not make it just a CLI app: skills must contain decision logic and safe workflows; scripts are deterministic helpers.
