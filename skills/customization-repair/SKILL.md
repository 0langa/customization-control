---
name: customization-repair
description: >
  Use this skill when repairing broken customizations: fix dead symlinks, invalid manifests, stale
  marketplace entries, and corrupted config. Follows repair-policy.json for
  safe vs unsafe repairs. Always uses dry-run before applying.
when_to_use: >
  Use when audit found broken-link, invalid-manifest, or stale-marketplace
  entries; when symlinks are dead; when plugin.json or SKILL.md has invalid
  fields; or when the user reports a skill/plugin not loading.
allowed-tools: Bash, Read, Write, Glob, Grep, Edit
---

# Customization Repair

Fix broken customizations. Safe repairs apply automatically. Unsafe repairs require user confirmation.

## Workflow

1. **Assess** — identify broken items from audit or fresh scan.
2. **Classify** — apply [repair-policy.json](../../references/repair-policy.json) to each.
3. **Plan** — present dry-run with safe/unsafe split.
4. **Apply safe** — auto-apply safe repairs.
5. **Confirm unsafe** — ask user before applying unsafe repairs.
6. **Validate** — verify repairs resolved the issues.

## Repair types

### Safe (auto-apply)

**Broken symlink with known target:**
- Canonical source still exists at expected path.
- Remove dead link, recreate pointing to canonical.
- On Windows, use junction: `cmd /c mklink /J "link" "target"`

**Missing provider link:**
- Canonical exists but provider discovery dir lacks a link.
- Create the link. Same as sync skill but triggered by repair context.

### Unsafe (require confirmation)

**Stale marketplace entry:**
- `marketplace.json` references a path that no longer exists.
- Back up marketplace.json first.
- Remove the stale entry.
- Validate JSON after edit.

**Invalid manifest:**
- `plugin.json` or `SKILL.md` frontmatter has invalid/missing fields.
- Report specific issues. Do not auto-fix — user or author must decide.

**Conflicting duplicate:**
- Same name, different content in multiple locations.
- Present both versions. User chooses canonical.

**Unknown customization:**
- Report only. Never modify.

## Quarantine

When removing anything during repair:

1. Create `.customization-control/quarantine/{timestamp}_{name}/`
2. Copy item to quarantine preserving structure.
3. Write to `quarantine-manifest.json`: original path, hash, timestamp, reason, repair-type.
4. Then remove original.

## Validation

After repairs, verify:
- All previously broken symlinks now resolve.
- Provider discovery dirs show expected skills.
- marketplace.json parses as valid JSON.
- No new broken links were introduced.

## Safety

- Read [repair-policy.json](../../references/repair-policy.json) before every repair session.
- Never delete outside approved roots.
- Never modify unknown customizations.
- All paths resolved to absolute before any filesystem operation.
- Back up any file before modifying it (marketplace.json, config files).
