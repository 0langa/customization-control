---
name: customization-audit
description: >
  Use this skill when auditing agent customizations across Codex, Claude Code,
  and Kimi Code.
  Inventory all skills, plugins, MCP servers, marketplaces, symlinks, and config
  across every known root. Detect duplicates, broken links, stale caches,
  conflicts, and unknown customizations. Use as the entrypoint — routes to
  customization-dedupe, customization-repair, customization-sync, or
  marketplace-manager when narrower action is needed.
when_to_use: >
  Use when the user asks to audit, check, scan, or inventory their agent
  customizations; when the @ picker shows duplicates; when the user wants to
  know what skills/plugins are installed and where; or as a starting point
  before deduplication or repair.
allowed-tools: Bash, Read, Glob, Grep, Skill
---

# Customization Audit

You are the entrypoint skill for the customization-control plugin. Your job is to produce a complete, accurate inventory of the user's agent customizations and flag issues.

## Workflow

1. **Inventory** — run the inventory script to discover all customizations.
2. **Classify** — for each finding, assign a dedupe category per the policy.
3. **Report** — produce a structured report of findings.
4. **Route** — if the user wants action, invoke the appropriate narrower skill.

## Step 1: Inventory

Run the inventory helper to scan all known roots. Use the Python helper on WSL, Linux, and macOS:

```bash
python3 "${CLAUDE_SKILL_DIR}/../../../scripts/customization_control.py" inventory --output-format json
```

On Windows, use the PowerShell helper:

!`powershell -NoProfile -File "${CLAUDE_SKILL_DIR}/../../../scripts/inventory.ps1" -OutputFormat json`

If the platform-specific helper is unavailable, perform manual inventory by scanning each root from [known-roots.json](../../references/known-roots.json).

### Roots to scan

Read [known-roots.json](../../references/known-roots.json) for the full list. Key locations:

**Claude Code:**
- `~/.claude/skills/` (personal skills)
- `.claude/skills/` (project skills)
- `.claude/commands/` (legacy commands)

**Codex:**
- `~/.codex/skills/` (user skills)
- `.codex/skills/` (project skills)
- `~/.codex/plugins/` and `~/.codex/plugins/cache/` (plugins and cache)

**Kimi Code:**
- `.kimi-code/skills/` (project skills)

**Legacy:**
- `~/.agents/skills/` (may overlap with provider-specific roots)
- `~/.agents/plugins/` (legacy plugin installs)

For each discovered customization, record:
- Name
- Type (skill, plugin, command, mcp-server, config)
- Provider (claude-code, codex, kimi-code, legacy)
- Path (absolute, resolved)
- Is symlink? Target path if so.
- Content hash (SHA-256 of SKILL.md or manifest)

## Step 2: Classify

Apply the [dedupe-policy.json](../../references/dedupe-policy.json) categories:

| Category | Meaning |
|---|---|
| `canonical` | Source of truth — keep |
| `provider-link` | Symlink to canonical — keep/repair |
| `duplicate-copy` | Same content elsewhere — candidate for removal |
| `stale-cache` | Old cache artifact — removable if rebuildable |
| `conflict` | Same name, different content — report only |
| `broken-link` | Dead symlink — repair or remove |
| `unknown` | Unrecognized — report only, never auto-delete |

To distinguish `duplicate-copy` from `conflict`: compare SHA-256 hashes of the main content file (SKILL.md, plugin.json, or equivalent). Identical hash = duplicate. Different hash = conflict.

## Step 3: Report

Produce a concise report with sections:
1. **Summary** — total customizations, by provider and type
2. **Issues** — duplicates, conflicts, broken links, stale caches, unknowns
3. **Recommendations** — which narrower skill to invoke for each issue class

Format as markdown. Include counts and specific paths for each issue.

## Step 4: Route

Based on findings, recommend or invoke:
- `/customization-control:customization-dedupe` for duplicate-copy and stale-cache issues
- `/customization-control:customization-repair` for broken-link and invalid-manifest issues
- `/customization-control:customization-sync` for missing provider links
- `/customization-control:marketplace-manager` for marketplace entry issues

Ask the user before invoking any skill that performs mutations.

## Safety

- This skill is read-only. It never modifies files.
- All paths must be resolved to absolute before display.
- On Windows, handle both `\` and `/` in paths.
- Never follow symlinks outside known roots without reporting it.
