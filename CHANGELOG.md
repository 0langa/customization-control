# Changelog

## 0.1.10 - 2026-10-26

- Replace the plugin icon and logo with the approved Folded Crest artwork and include its SVG source.


## 0.1.9 - 2026-10-26

- Mark the plugin dormant while keeping existing functionality and installation IDs.
- Publish through https://github.com/0langa/plugins; Kimi compatibility is legacy.

## 0.1.8 - 2026-10-15

- Dedupe now compares copies only within one scope (project, personal, custom or cache). A personal copy such as `~/.claude/skills/<name>` and a project copy of the same name are never duplicates of each other, so dedupe keeps both. Before, the project copy was kept and the personal copy was removed.
- Upgrade note: apply now removes a copy only when the plan keeps a canonical copy in the same scope. A plan made with 0.1.7 or earlier that relied on a copy in another scope reports `BLOCKED` and removes nothing, so re-run the planner before applying.

## 0.1.7 - 2026-10-14

- The Windows helpers now work when Windows PowerShell 5.1 is started from a PowerShell 7 session through cmd, bash or an agent. Before, 5.1 picked up PowerShell 7's modules, so inventory failed on `Get-FileHash` and apply blocked every removal.

## 0.1.6 - 2026-10-14

- The audit and dedupe skills no longer run PowerShell while loading, so they load on every platform.
- Dedupe is much safer: it never removes a copy without a content hash, and resolves links and junctions to their real location before removing anything.
- Apply re-checks each removal against the kept copy, keeps copies with their own edits, and refuses links, the approved roots themselves, and look-alike paths such as `~/.claude-backup`.
- Each quarantined copy gets its own folder, so every copy can be restored.
- Fixed the Windows helpers: the dedupe planner no longer crashes on duplicates, and validate, apply, and quarantine work under PowerShell 7 and Windows PowerShell 5.1.
- Corrected the README install steps.

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
