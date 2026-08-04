# customization-control

Cross-provider plugin that audits, deduplicates, repairs, syncs, and manages agent customizations across Codex, Claude Code, and Kimi Code.

## Problem

After developing and installing skills/plugins across multiple AI coding agents, customization roots accumulate overlapping copies, broken symlinks, stale caches, and duplicate entries in the `@` picker. This plugin provides a safe, structured way to clean up and keep customizations consistent.

## Skills

| Skill | Purpose | Invocation |
|---|---|---|
| **customization-audit** | Inventory all customizations, detect issues, route to narrower skills | `/customization-control:customization-audit` |
| **customization-dedupe** | Remove identical duplicates with dry-run plan and quarantine safety | `/customization-control:customization-dedupe` |
| **customization-sync** | Create/repair provider discovery symlinks for canonical skills | `/customization-control:customization-sync` |
| **customization-repair** | Fix broken symlinks, invalid manifests, stale marketplace entries | `/customization-control:customization-repair` |
| **marketplace-manager** | Validate/update marketplace.json entries for already-ported plugins | `/customization-control:marketplace-manager` |
| **windows-customization-guard** | Windows path safety, junction handling, PowerShell guardrails (internal) | Auto-invoked by other skills on Windows |

## Safety guarantees

- **Inventory before mutation** — always scans before changing anything.
- **Dry-run before apply** — every destructive operation shows a plan first.
- **Quarantine before delete** — removals are backed up to `.customization-control/quarantine/` with a manifest.
- **Path boundary enforcement** — refuses to delete outside approved roots.
- **Resolved absolute paths** — no string-built destructive shell commands.
- **Conflict protection** — same-name/different-content customizations are never auto-deleted.
- **Unknown protection** — unrecognized customizations are reported, never modified.

## Scripts

The plugin ships both Windows-native PowerShell helpers and a cross-platform Python helper for WSL, Linux, and macOS. The helpers are deterministic; the skills contain the decision logic.

| Script | Purpose |
|---|---|
| `scripts/customization_control.py` | Cross-platform inventory, validation, dedupe plan/apply, and quarantine helper |
| `scripts/inventory.ps1` | Scan all known roots, produce structured inventory |
| `scripts/validate.ps1` | Validate symlinks, manifests, path bounds |
| `scripts/plan-dedupe.ps1` | Generate dry-run deduplication plan |
| `scripts/apply-dedupe.ps1` | Execute confirmed plan with quarantine |
| `scripts/quarantine.ps1` | List, restore, or purge quarantined items |

### Quick inventory

```powershell
pwsh -NoProfile -File scripts/inventory.ps1 -OutputFormat table
```

```bash
python3 scripts/customization_control.py inventory --output-format table
```

### Dry-run dedupe

```powershell
pwsh -NoProfile -File scripts/plan-dedupe.ps1 -OutputFormat table
```

```bash
python3 scripts/customization_control.py plan-dedupe --output-format table
```

## References

Policy files in `references/` encode the rules skills follow:

- `known-roots.json` — all customization root paths by provider
- `dedupe-policy.json` — classification categories and handling rules
- `repair-policy.json` — safe vs unsafe repair types, quarantine config
- `marketplace-policy.json` — marketplace entry management rules

## Installation

### As a Claude Code plugin (skills-directory plugin)

The `.claude-plugin/plugin.json` manifest makes this repo discoverable as a skills-directory plugin. Clone it and the skills appear in Claude Code:

```bash
git clone https://github.com/0langa/customization-control
cd customization-control
# Skills auto-discovered from skills/ directory
```

Or install via `--add-dir`:

```bash
claude --add-dir /path/to/customization-control
```

### Provider discovery

Canonical skills live in `skills/`. Provider discovery links are machine-local, git-ignored state; create or repair them only through the explicit sync workflow. A clone alone does not prove those links exist or that a provider has loaded the plugin.

## Tests

Requires Pester 5+:

```powershell
pwsh -NoProfile -Command "Import-Module Pester -MinimumVersion 5.0; Invoke-Pester -Path tests -Output Detailed"
```

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

## Dedupe categories

| Category | Meaning | Auto-action |
|---|---|---|
| `canonical` | Source of truth | Keep |
| `provider-link` | Symlink/junction to canonical | Keep/repair |
| `duplicate-copy` | Same content copied elsewhere | Quarantine + remove (with confirmation) |
| `stale-cache` | Old cache artifact | Remove if rebuildable |
| `conflict` | Same name, different content | Report only |
| `broken-link` | Dead symlink/junction | Repair or remove |
| `unknown` | Unrecognized | Report only |

## Known roots scanned

- `~/.claude/skills/` — Claude Code personal skills
- `.claude/skills/` — Claude Code project skills
- `.claude/commands/` — Claude Code legacy commands
- `~/.codex/skills/` — Codex user skills
- `.codex/skills/` — Codex project skills
- `~/.codex/plugins/cache/` — Codex plugin cache
- `.kimi-code/skills/` — Kimi Code project skills
- `~/.agents/skills/` — Legacy agent skills
- `~/.agents/plugins/marketplace.json` — Legacy marketplace
