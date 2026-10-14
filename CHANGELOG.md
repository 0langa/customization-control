# Changelog

## Unreleased

- Stop the audit and dedupe skills from running PowerShell at load time; a failing `!` command aborted both skills, including on every non-Windows host.
- Fix the PowerShell dedupe, apply, validate, and quarantine helpers under `Set-StrictMode` and Windows PowerShell 5.1 (single-result crashes, wrong counts, non-ASCII parse errors, nested or non-array quarantine manifests).
- Dedupe planning no longer treats a copy without a content hash as identical; apply refuses symlinks, junctions, approved roots themselves, and sibling paths such as `~/.claude-backup`.
- Dedupe no longer removes a copy that is physically the same folder as a kept one: the target of a provider link, a path through a linked parent folder such as a `~/.codex/skills` junction, or every user skill when the helpers run from the home directory (where `.claude/skills` is `~/.claude/skills`).
- Apply re-checks each removal against the plan's canonical copy: it must still exist, must be a different physical folder, and a `duplicate-copy` must match it file for file, not just in `SKILL.md`.
- Each quarantined copy gets its own folder, so several copies of one name can all be restored; quarantine restore and purge no longer drop sibling entries from the manifest. The Python apply records a copy in the manifest before deleting the original, and detects junctions on Python versions without `os.path.isjunction`.
- Correct the README install steps (`--plugin-dir` or the marketplace, not `--add-dir`).

## 0.1.5 - 2026-09-09

- Scan complete Codex and Claude cache paths through marketplace, plugin, and version directories, including Codex plugin manifests.
- Include Kimi managed plugins in both PowerShell and Python inventories and dry-run root listings.
- Correct the audit and dedupe skills' relative paths to their helper scripts.

## 0.1.4 - 2026-08-05

- Made public-safety and skill-routing assertions run under documented Python unittest discovery.
- Corrected provider-discovery and project-status documentation to distinguish source truth from local machine state.

## 0.1.3 - 2026-07-27

- Removed tracked agent-handoff artifacts containing machine-specific paths.
- Ignored local `.handoff/` state and added public-safety regression coverage.
