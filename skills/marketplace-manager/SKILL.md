---
name: marketplace-manager
description: >
  Manage marketplace entries for already-ported plugins. Validate entries,
  remove stale references, refresh metadata, verify uniqueness, and reinstall
  cleanly. Does not convert plugin formats between providers.
when_to_use: >
  Use when marketplace.json has stale or duplicate entries, when a plugin
  shows up multiple times in the picker, when reinstalling a plugin cleanly,
  or when audit flagged marketplace issues.
allowed-tools: Bash, Read, Write, Glob, Grep, Edit
---

# Marketplace Manager

Manage existing plugin marketplace entries. Scope: already-ported plugins only. Never convert formats.

## Workflow

1. **Locate marketplaces** — find all marketplace.json files.
2. **Validate entries** — check each entry points to real plugin with valid manifest.
3. **Plan** — present findings and proposed changes.
4. **Apply** — modify marketplace.json after user confirmation.
5. **Verify** — confirm each plugin appears exactly once.

## Marketplace locations

Check these paths for marketplace.json files:
- `~/.agents/plugins/marketplace.json` (legacy personal marketplace)
- Any marketplace.json referenced in Codex plugin config
- Repo-local marketplace definitions

## Validation checks

For each entry in marketplace.json:

1. **Path exists** — does the referenced plugin directory exist?
2. **Manifest valid** — does it contain a valid plugin.json or equivalent?
3. **Version match** — does the entry version match the manifest version?
4. **Unique** — does this plugin name appear only once?
5. **Provider match** — is the entry format correct for the target provider?

## Operations

### Remove stale entry
```json
// Entry references path that no longer exists
// Back up marketplace.json, remove entry, validate JSON
```

### Refresh entry
```json
// Re-read manifest from plugin dir, update entry fields
// Preserve user customizations in entry
```

### Verify uniqueness
```
// Scan for duplicate plugin names
// If found: keep the one pointing to valid/newest version, flag others
```

### Reinstall
```
// Remove cached copy at ~/.codex/plugins/cache/{name}
// Re-clone or re-copy from source repository
// Update marketplace entry to point to new cache location
```

## Safety

- Read [marketplace-policy.json](../../references/marketplace-policy.json) before operations.
- Always back up marketplace.json before any modification.
- Validate JSON parses correctly after every write.
- Never add new plugins to marketplace — only manage existing entries.
- Report but do not auto-fix version mismatches.
- Refuse operations on marketplace files outside known roots.
