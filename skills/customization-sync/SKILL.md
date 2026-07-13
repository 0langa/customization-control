---
name: customization-sync
description: >
  Use this skill when syncing canonical customizations to provider discovery directories. Ensures
  symlinks from .codex/skills, .claude/skills, and .kimi-code/skills point
  to the correct canonical source. Creates missing links and repairs broken ones.
when_to_use: >
  Use when a skill exists in canonical source but is missing from one or more
  provider discovery dirs, when adding a new skill to multiple providers, or
  after audit found missing provider-link entries.
allowed-tools: Bash, Read, Write, Glob, Grep
---

# Customization Sync

Keep provider discovery directories aligned with canonical skill sources.

## Workflow

1. **Identify canonical sources** — find the source-of-truth location for each skill.
2. **Check provider links** — verify each provider that should see the skill has a working symlink.
3. **Plan** — list missing or broken links. Present dry-run.
4. **Apply** — create/repair symlinks after user confirmation.
5. **Validate** — confirm all links resolve correctly.

## Provider link targets

For a canonical skill at `{repo}/skill-name/`:

| Provider | Expected link location |
|---|---|
| Claude Code (project) | `{repo}/.claude/skills/skill-name` → `../../skill-name` |
| Codex (project) | `{repo}/.codex/skills/skill-name` → `../../skill-name` |
| Kimi Code (project) | `{repo}/.kimi-code/skills/skill-name` → `../../skill-name` |
| Codex (user) | `~/.codex/skills/skill-name` → `{repo}/skill-name` |

Use relative paths for in-repo links. Use absolute paths for user-wide links.

## Creating symlinks on Windows

On Windows, use directory junctions for maximum compatibility:

```powershell
cmd /c mklink /J "target-link-path" "canonical-source-path"
```

Junctions do not require elevated privileges on Windows.

For Unix-like environments, use standard symlinks:

```bash
ln -s "../canonical-source-path" "target-link-path"
```

## Dry-run plan format

```
| # | Skill | Provider | Link Path | Status | Action |
|---|-------|----------|-----------|--------|--------|
| 1 | muteman | codex-user | ~/.codex/skills/muteman | missing | create junction |
| 2 | official-ai-devdocs | kimi-code | .kimi-code/skills/... | broken | repair |
```

## Safety

- Never overwrite an existing non-link directory. Report as conflict.
- Verify canonical source exists before creating link.
- Resolve all paths to absolute before creating links.
- After creating links, verify they resolve to the intended target.
- Do not sync skills the user has explicitly excluded.
