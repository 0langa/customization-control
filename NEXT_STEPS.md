# Customization Control — Current State

_Verified against source on 2026-08-05._

## Current state

- `v0.1.3` is current source release. Claude, Codex, and Kimi manifests agree on version.
- Six canonical skills live under `skills/`, backed by PowerShell and Python helpers plus JSON safety policies in `references/`.
- Local `.handoff/`, `.recall/`, and provider discovery links are intentionally git-ignored. They are machine state, not release evidence.
- `customization-audit` routes requests limited to skill health, visibility, registration, or repair to `skill-doctor`; plugin, MCP, hook, marketplace, and configuration surfaces remain in this plugin's scope.
- Source checks include Pester tests, Python unittest coverage, and a tracked-file public-safety test.

## Verification

```powershell
pwsh -NoProfile -Command "Import-Module Pester -MinimumVersion 5.0; Invoke-Pester -Path tests -Output Detailed"
python -m unittest discover -s tests -p "test_*.py"
```

## Next work

- Add a synthetic audit-to-plan-to-apply integration test before changing remediation behavior.
- Run real-machine remediation only under an explicit, reviewed plan; it can alter provider directories and quarantine local files.
- Add CI only after pinning a compatible Pester setup and deciding how to provision Windows junction capability.
