# Changelog

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
