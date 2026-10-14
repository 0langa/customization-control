<#
.SYNOPSIS
    Apply a deduplication plan: quarantine and remove confirmed duplicates.
.DESCRIPTION
    Reads a plan from plan-dedupe.ps1 output and executes quarantine+remove
    actions. Creates backups before any deletion. Validates after completion.
.PARAMETER PlanJson
    Path to plan JSON file from plan-dedupe.ps1.
.PARAMETER QuarantineRoot
    Root directory for quarantine. Defaults to .customization-control/quarantine.
.PARAMETER DryRun
    If set, shows what would be done without executing.
.PARAMETER Force
    Skip confirmation prompt (for scripted use).
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$PlanJson,

    [string]$QuarantineRoot = '.customization-control\quarantine',

    [switch]$DryRun,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Resolve-HomePath {
    param([string]$Path)
    if ($Path.StartsWith('~')) {
        $Path = $Path.Replace('~', $env:USERPROFILE)
    }
    return [System.IO.Path]::GetFullPath($Path)
}

$approvedRoots = @(
    (Resolve-HomePath '~/.claude'),
    (Resolve-HomePath '~/.codex'),
    (Resolve-HomePath '~/.agents'),
    (Resolve-HomePath '~/.kimi-code')
)

function Test-InApprovedRoot {
    param([string]$Path)
    # Only paths strictly inside a root qualify: never the root itself, and
    # never a sibling that merely shares its prefix (e.g. ~/.claude-backup).
    $resolved = [System.IO.Path]::GetFullPath($Path).TrimEnd('\', '/')
    foreach ($root in $approvedRoots) {
        $prefix = $root.TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
        if ($resolved.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            return $true
        }
    }
    return $false
}

# Load plan
$planData = Get-Content -Raw -LiteralPath $PlanJson | ConvertFrom-Json
$plan = $planData.plan

# Filter to actionable items. @() keeps a single match countable under
# Set-StrictMode -Version Latest.
$removals = @($plan | Where-Object {
    $_.action -eq 'quarantine+remove' -or $_.action -eq 'remove (rebuildable)'
})

if ($removals.Count -eq 0) {
    Write-Host "No items to remove. Plan contains only KEEP and SKIP entries."
    return
}

Write-Host "=== Apply Deduplication ==="
Write-Host "Items to remove: $($removals.Count)"
Write-Host ""

foreach ($item in $removals) {
    Write-Host "  [$($item.category)] $($item.name) at $($item.path)"
}

if (-not $Force -and -not $DryRun) {
    $confirm = Read-Host "`nProceed? (yes/no)"
    if ($confirm -ne 'yes') {
        Write-Host "Aborted."
        return
    }
}

$quarantineBase = Resolve-HomePath $QuarantineRoot
$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$manifestPath = Join-Path $quarantineBase 'quarantine-manifest.json'

# Load or create manifest. Assign before wrapping in @(): Windows PowerShell
# 5.1 emits a JSON array as one object, which @(pipeline) would nest.
$manifest = @()
if (Test-Path -LiteralPath $manifestPath -PathType Leaf) {
    try {
        $existing = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
    } catch {
        # Never overwrite a manifest we cannot read: it indexes earlier quarantines.
        throw "Cannot parse quarantine manifest at ${manifestPath}: $($_.Exception.Message)"
    }
    $manifest = @($existing | Where-Object { $null -ne $_ })
}

$results = @()

foreach ($item in $removals) {
    $itemPath = [System.IO.Path]::GetFullPath($item.path)
    $result = [ordered]@{
        name   = $item.name
        path   = $itemPath
        status = 'pending'
        error  = $null
    }

    # Safety check
    if (-not (Test-InApprovedRoot $itemPath)) {
        $result.status = 'BLOCKED'
        $result.error = "Path outside approved roots: $itemPath"
        $results += $result
        continue
    }

    if (-not (Test-Path -LiteralPath $itemPath -ErrorAction SilentlyContinue)) {
        $result.status = 'skipped'
        $result.error = 'Path does not exist'
        $results += $result
        continue
    }

    # Links are provider links, not copies. Windows PowerShell 5.1's recursive
    # Remove-Item can follow a junction and delete the target's contents.
    $existingItem = Get-Item -LiteralPath $itemPath -Force
    if ($existingItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
        $result.status = 'BLOCKED'
        $result.error = "Refusing to remove a symlink or junction: $itemPath"
        $results += $result
        continue
    }

    if ($DryRun) {
        $result.status = 'dry-run'
        $results += $result
        continue
    }

    try {
        # Quarantine
        $quarantineDest = Join-Path $quarantineBase "${timestamp}_$($item.name)"
        if (-not (Test-Path -LiteralPath $quarantineBase)) {
            New-Item -Path $quarantineBase -ItemType Directory -Force | Out-Null
        }

        Copy-Item -LiteralPath $itemPath -Destination $quarantineDest -Recurse -Force -ErrorAction Stop

        # Verify copy
        if (-not (Test-Path -LiteralPath $quarantineDest)) {
            throw "Quarantine copy failed - not removing original"
        }

        # Update manifest
        $manifest += [ordered]@{
            name         = $item.name
            originalPath = $itemPath
            quarantinePath = $quarantineDest
            hash         = $item.hash
            category     = $item.category
            timestamp    = $timestamp
            reason       = "Dedupe: $($item.action)"
        }

        # Remove original
        Remove-Item -LiteralPath $itemPath -Recurse -Force -ErrorAction Stop

        $result.status = 'removed'
    } catch {
        $result.status = 'error'
        $result.error = $_.Exception.Message
    }

    $results += $result
}

# Save manifest
if (-not $DryRun -and $manifest.Count -gt 0) {
    if (-not (Test-Path -LiteralPath $quarantineBase)) {
        New-Item -Path $quarantineBase -ItemType Directory -Force | Out-Null
    }
    # -InputObject keeps a one-entry manifest a JSON array.
    ConvertTo-Json -InputObject @($manifest) -Depth 10 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
}

$output = [ordered]@{
    timestamp = (Get-Date -Format 'o')
    isDryRun  = [bool]$DryRun
    results   = $results
    summary   = [ordered]@{
        removed = @($results | Where-Object { $_.status -eq 'removed' }).Count
        blocked = @($results | Where-Object { $_.status -eq 'BLOCKED' }).Count
        skipped = @($results | Where-Object { $_.status -eq 'skipped' }).Count
        errors  = @($results | Where-Object { $_.status -eq 'error' }).Count
    }
}

$output | ConvertTo-Json -Depth 10
