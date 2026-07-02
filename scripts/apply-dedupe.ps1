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
    $resolved = [System.IO.Path]::GetFullPath($Path)
    foreach ($root in $approvedRoots) {
        if ($resolved.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase)) {
            return $true
        }
    }
    return $false
}

# Load plan
$planData = Get-Content -Raw -Path $PlanJson | ConvertFrom-Json
$plan = $planData.plan

# Filter to actionable items
$removals = $plan | Where-Object {
    $_.action -eq 'quarantine+remove' -or $_.action -eq 'remove (rebuildable)'
}

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

# Load or create manifest
$manifest = @()
if (Test-Path $manifestPath -PathType Leaf) {
    try {
        $manifest = @(Get-Content -Raw -Path $manifestPath | ConvertFrom-Json)
    } catch {
        $manifest = @()
    }
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

    if (-not (Test-Path $itemPath -ErrorAction SilentlyContinue)) {
        $result.status = 'skipped'
        $result.error = 'Path does not exist'
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
        if (-not (Test-Path $quarantineBase)) {
            New-Item -Path $quarantineBase -ItemType Directory -Force | Out-Null
        }

        Copy-Item -Path $itemPath -Destination $quarantineDest -Recurse -Force -ErrorAction Stop

        # Verify copy
        if (-not (Test-Path $quarantineDest)) {
            throw "Quarantine copy failed — not removing original"
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
        Remove-Item -Path $itemPath -Recurse -Force -ErrorAction Stop

        $result.status = 'removed'
    } catch {
        $result.status = 'error'
        $result.error = $_.Exception.Message
    }

    $results += $result
}

# Save manifest
if (-not $DryRun -and $manifest.Count -gt 0) {
    if (-not (Test-Path $quarantineBase)) {
        New-Item -Path $quarantineBase -ItemType Directory -Force | Out-Null
    }
    $manifest | ConvertTo-Json -Depth 10 | Set-Content -Path $manifestPath -Encoding UTF8
}

$output = [ordered]@{
    timestamp = (Get-Date -Format 'o')
    isDryRun  = [bool]$DryRun
    results   = $results
    summary   = [ordered]@{
        removed = ($results | Where-Object { $_.status -eq 'removed' }).Count
        blocked = ($results | Where-Object { $_.status -eq 'BLOCKED' }).Count
        skipped = ($results | Where-Object { $_.status -eq 'skipped' }).Count
        errors  = ($results | Where-Object { $_.status -eq 'error' }).Count
    }
}

$output | ConvertTo-Json -Depth 10
