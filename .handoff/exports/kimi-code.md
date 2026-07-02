# Continuation Prompt — Kimi Code

You are resuming work previously captured by another agent. Use Kimi Code tools and commands as needed. Check workspace state via shell/git when possible.

## Task

**Build customization-control plugin**

Status: `in_progress`

### Objective

Develop a high-quality, reliable cross-provider customization-control plugin that audits, deduplicates, repairs, syncs, and publishes agent customizations across Codex, Claude Code, and Kimi Code without degrading into a CLI-only wrapper.

## What Was Done

- Implemented plugin scaffold with README, Codex/Claude/Kimi manifests, six canonical skills, provider junctions, policy references, PowerShell helper scripts, and Pester tests.
- Latest commits on main: e6f10e2 initial plugin implementation, da90179 provider manifests, c42af42 PowerShell 5.1 Join-Path compatibility fix.
- Validation scripts were run from Codex: inventory.ps1 and validate.ps1 both execute successfully and produce structured JSON.

## What Is In Progress

- Project is functional enough to inspect real local customization state, but needs follow-up hardening before it should be trusted for cleanup.

## Next Steps

- Fix the accidentally-created provider junctions named skills$skill under .claude, .codex, and .kimi-code; they point to nonexistent skills$skill targets and trigger git/status warnings.
- Review inventory duplicate logic: expected provider junctions for this plugin are currently reported as duplicates; they should likely classify as provider-link rather than duplicate issue noise.
- Address validate.ps1 findings: 118 total items, 106 valid, 2 warnings, 10 errors from broken Claude user-skill links pointing at C:\Users\juliu\.agents\skills\*.
- Install or otherwise provide Pester 5, then run the test suite and fix any test failures.
- Review manifests against current official Codex, Claude Code, and Kimi Code plugin docs before publishing or installing broadly.
- Decide whether to repair real user-home customization issues now or leave this plugin as report-only until tests pass.

## Blockers

- Pester 5 is not installed in this shell; Invoke-Pester could not run tests.
- There are broken junction artifacts named skills$skill in each provider folder.

## Workspace State

Git status:

```text
## main...origin/main
```


Tests run:
- `powershell -NoProfile -Command Import-Module Pester -MinimumVersion 5.0; Invoke-Pester -Path tests -Output Detailed` — failed: Pester 5 module is not installed; tests did not run.
## Important Context

- File: `README.md`
- File: `C:\Users\Julius\source\repos\0langas-skill-center\README.md`
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
- Decision: Keep customization-control as the plugin name.
- Decision: Treat PowerShell scripts as deterministic helpers; skill files remain the decision and safety surface.
- Decision: Do not auto-delete conflicts, unknown customizations, or non-identical duplicates; use quarantine/confirmation flow.

- Constraint: Target provider is Claude Code. Continue from this repo root.
- Constraint: Use official provider documentation before asserting current Codex, Claude Code, or Kimi Code customization syntax, install paths, plugin manifests, marketplace fields, MCP config shapes, or skill discovery behavior.
- Constraint: Do not build a plugin that is merely a CLI app with thin skill wrappers. Skills must contain the decision logic, trigger surface, safety policy, and recovery workflow; scripts are deterministic helpers only.
- Constraint: Highest reliability standard: inventory before mutation, dry-run plan before repair, explicit safety classes, backups/quarantine for risky removals, and validation after every applied change.
- Constraint: Windows-first implementation. Use PowerShell-safe path handling and resolved absolute path checks. Avoid string-built destructive shell commands and avoid mixing shells for file deletion/moving.
- Constraint: Never delete unknown customizations silently. Unknown, conflicting, or non-identical duplicates must be reported or quarantined, not removed outright.
- Constraint: Keep provider surfaces tidy and explicit: .codex, .claude, .kimi-code in repos; user-wide Codex skills under ~/.codex/skills; existing .agents roots may still exist and are part of dedupe analysis.
- Constraint: Marketplace support is in scope only for already-ported plugins. Porting plugins between provider formats belongs to a future plugin.
- Constraint: Do not run destructive cleanup against user skill/plugin roots until the plan/dedupe/apply path is reviewed and tests pass.

- Open question: Plugin destination is confirmed: C:\Users\Julius\source\repos\customization-control, private GitHub repo 0langa/customization-control.
- Open question: Confirm exact marketplace destination before publishing: personal marketplace at ~/.agents/plugins/marketplace.json versus a repo/team marketplace.
- Open question: Confirm whether the plugin should manage only local Windows roots initially or include portable macOS/Linux roots in references for later.

## Capability Warnings

- **Required:** `local workspace` (filesystem via claude-code): Develop plugin files and tests in the repo or selected plugin workspace.  Fallback: local-equivalent — Use Claude Code local filesystem access in the same workspace.
- **Required:** `PowerShell or local shell` (shell via claude-code): Run validation scripts, tests, and safe filesystem inspections.  Fallback: local-equivalent — Use whatever shell Claude Code provides for local commands; on Windows prefer PowerShell-safe commands.

## Safety Notes

- Privacy note: No secrets captured. Paths to local skill/plugin roots are included because they are necessary for the task.

## Resume Summary

customization-control has progressed from handoff brief to a real plugin repo. It now contains provider manifests, six skill surfaces, provider junctions, policy references, PowerShell scripts for inventory/validate/plan/apply/quarantine, and Pester tests. Current state is clean on main and pushed to origin, but follow-up is needed: remove/fix stray skills$skill junctions, refine duplicate classification for provider links, install/run Pester tests, and review provider manifests against official docs before broad install or cleanup use.

Continue in C:\Users\Julius\source\repos\customization-control. Read .handoff/active.json and .handoff/active.md, then inspect the current repo. The plugin is implemented but needs hardening: fix stray skills$skill junctions, refine inventory/dedupe classification so expected provider links are not noisy duplicates, install/provide Pester 5 and run tests, review manifests against official docs, and only then consider actual cleanup operations. Do not perform destructive cleanup against user customization roots until tests pass and the plan/apply safety path is reviewed.
