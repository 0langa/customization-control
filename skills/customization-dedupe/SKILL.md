---
name: customization-dedupe
description: >
  Use this skill when deduplicating agent customizations. Identifies identical copies across
  overlapping roots (e.g. ~/.codex/skills and ~/.agents/skills), produces a
  dry-run removal plan, quarantines risky removals, and cleans up duplicate
  entries that clutter the @ picker.
when_to_use: >
  Use when the @ picker shows duplicate skills/plugins, when audit found
  duplicate-copy or stale-cache entries, or when the user wants to clean up
  redundant customization installs.
allowed-tools: Bash, Read, Write, Glob, Grep, Edit
---

# Customization Dedupe

Remove duplicate customizations safely. Never delete without a plan. Never delete unknowns or conflicts.

## Workflow

1. **Receive inventory** — use audit results or run inventory fresh.
2. **Build dedupe plan** — classify each duplicate, choose action.
3. **Dry-run** — present plan to user. No mutations until confirmed.
4. **Execute** — quarantine then remove confirmed duplicates.
5. **Validate** — verify providers still see correct customizations.

## Classification

Read [dedupe-policy.json](../../references/dedupe-policy.json) for full policy.

### Choosing canonical

When multiple copies exist, prefer in this order:
1. Repo-local source directory (e.g. `0langas-skill-center/muteman/`)
2. User-wide provider skill dir (e.g. `~/.codex/skills/muteman/` if it's a symlink to #1)
3. Legacy roots (e.g. `~/.agents/skills/muteman/`)
4. Plugin cache copies

If no clear canonical exists, mark as `conflict` and ask user.

### Content comparison

Use SHA-256 hash of the primary content file:
- Skills: hash of `SKILL.md`
- Plugins: hash of `plugin.json` or `.claude-plugin/plugin.json`
- Commands: hash of the `.md` file

On WSL, Linux, and macOS, use the cross-platform helper for inventory and planning:

```bash
python3 "${CLAUDE_SKILL_DIR}/../../../scripts/customization_control.py" inventory --output-format json > inventory.json
python3 "${CLAUDE_SKILL_DIR}/../../../scripts/customization_control.py" plan-dedupe --inventory-json inventory.json --output-format json > dedupe-plan.json
```

On Windows, use the PowerShell helpers:

!`powershell -NoProfile -Command "Get-FileHash -Algorithm SHA256 -Path $args[0]" "$ARGUMENTS"`

Identical hashes → `duplicate-copy`. Different hashes → `conflict`.

## Dry-run plan format

Present a table before any mutation:

```
| # | Name | Category | Path | Action | Risk |
|---|------|----------|------|--------|------|
| 1 | muteman | duplicate-copy | ~/.agents/skills/muteman | quarantine+remove | low |
| 2 | addon-archive | conflict | ~/.codex/skills/addon-archive | SKIP (conflict) | — |
```

## Execution

For each confirmed removal:

1. Create quarantine directory: `.customization-control/quarantine/{timestamp}_{name}/`
2. Copy the item to quarantine (preserve structure).
3. Write entry to `quarantine-manifest.json` with original path, hash, timestamp, reason.
4. Remove the original.

On WSL, Linux, and macOS, use `python3 scripts/customization_control.py apply-dedupe dedupe-plan.json`. On Windows, use PowerShell `Copy-Item` and `Remove-Item` with resolved absolute paths. Never use string-built `rm` commands.

## Post-removal validation

After removals, verify each provider still discovers the intended customizations:
- Check `~/.claude/skills/` entries still resolve
- Check `~/.codex/skills/` entries still resolve
- Check no broken symlinks were created by removal

Report any issues found during validation.

## Safety

- Never delete `canonical` or `provider-link` entries.
- Never delete `conflict` or `unknown` entries.
- Always quarantine before removing `duplicate-copy` entries.
- `stale-cache` entries can be removed if confirmed rebuildable, but still quarantine.
- All file operations use resolved absolute paths.
- Refuse to delete anything outside known roots.
