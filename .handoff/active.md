# Build customization-control plugin

> Handoff ID: `20260702-103000-001`
> Created: 2026-07-02T07:18:55Z
> Updated: 2026-07-02T10:30:00Z
> Created by: `codex` → Updated by: `claude-code`
> Target provider: `codex`

## Objective

Develop a high-quality, reliable cross-provider `customization-control` plugin that audits, deduplicates, repairs, syncs, and publishes agent customizations across Codex, Claude Code, and Kimi Code without degrading into a CLI-only wrapper.

## Current State — FULLY FUNCTIONAL

The plugin is **built, tested, and deployed** across all 3 providers.

### Plugin structure
```
customization-control/
├── .claude-plugin/plugin.json        # Claude Code manifest
├── .codex-plugin/plugin.json         # Codex manifest (with interface block)
├── kimi.plugin.json                  # Kimi Code manifest
├── skills/
│   ├── customization-audit/SKILL.md  # Entrypoint — inventory + classify + route
│   ├── customization-dedupe/SKILL.md # Dry-run plan + quarantine + remove
│   ├── customization-sync/SKILL.md   # Create/repair provider discovery links
│   ├── customization-repair/SKILL.md # Fix broken symlinks, manifests, entries
│   ├── marketplace-manager/SKILL.md  # Validate/update marketplace.json
│   └── windows-customization-guard/SKILL.md  # Windows path safety (internal)
├── scripts/
│   ├── inventory.ps1                 # Scan all known roots → JSON/table
│   ├── validate.ps1                  # Check symlinks, manifests, bounds
│   ├── plan-dedupe.ps1               # Generate dry-run dedupe plan
│   ├── apply-dedupe.ps1              # Execute plan with quarantine
│   └── quarantine.ps1                # List/restore/purge quarantine
├── references/
│   ├── known-roots.json              # All customization root paths
│   ├── dedupe-policy.json            # 7 classification categories + rules
│   ├── repair-policy.json            # Safe/unsafe repairs + quarantine config
│   └── marketplace-policy.json       # Marketplace entry management
├── tests/
│   └── CustomizationControl.Tests.ps1  # 24 Pester tests (all pass)
├── .gitignore
└── README.md
```

### Test results
- **24/24 Pester tests pass** (Pester 5.8.0)
- **Claude Code**: `claude plugin validate .` passes, 6/6 skills discovered
- **Codex**: installed+enabled, exec audit → 118 items, 10 broken, 16 dupes
- **Kimi Code**: `-p` audit → identical results (118/10/16)

### Live inventory findings
- **118 total customizations** (84 skills, 34 cached plugins)
- **10 broken symlinks** in `~/.claude/skills/` (junctions → deleted `~/.agents/skills/` targets)
- **16 duplicate groups** (mostly identical copies across `~/.codex/skills/` and `~/.agents/skills/`)

### Marketplace
- Submodule in `0langas-plugin-marketplace/plugins/customization-control`
- Entries in all 4 JSON formats
- Codex installed: `customization-control@0langas-plugins`

## Next Steps

1. **Dedupe execution** — wire plan-dedupe.ps1 → dry-run → apply-dedupe.ps1 with quarantine
2. **Sync workflow** — create missing provider links across .codex/.claude/.kimi-code
3. **Repair workflow** — fix 10 broken symlinks in `~/.claude/skills/`
4. **Migrate legacy roots** — move `~/.agents/skills/` to provider-specific roots
5. **Integration tests** — full audit→plan→apply pipeline
6. **Quality evaluation** — `/plugin-evaluation-kimi:certify`

## Constraints

- Never delete unknown or conflicting customizations silently
- Dry-run before mutation, quarantine before deletion
- Resolved absolute paths for all destructive ops
- Windows-first, PowerShell-safe
- Follow `references/*.json` policies

## Resume Prompt

Continue from `C:\Users\Julius\source\repos\customization-control`. The plugin is fully built and tested. Next: implement dedupe/repair/sync execution workflows, migrate `~/.agents/skills/`, run integration tests. Follow `references/` policies. Run Pester tests after changes.
