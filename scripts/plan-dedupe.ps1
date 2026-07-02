<#
.SYNOPSIS
    Generate a dry-run deduplication plan from inventory data.
.DESCRIPTION
    Analyzes inventory for duplicates, classifies them per dedupe-policy.json,
    and produces a plan of proposed actions. No mutations are performed.
.PARAMETER InventoryJson
    Path to inventory JSON file.
.PARAMETER OutputFormat
    Output format: 'json' or 'table'.
#>
[CmdletBinding()]
param(
    [string]$InventoryJson = '',
    [ValidateSet('json', 'table')]
    [string]$OutputFormat = 'json'
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

# Load inventory
if ($InventoryJson -and (Test-Path $InventoryJson -PathType Leaf)) {
    $data = Get-Content -Raw -Path $InventoryJson | ConvertFrom-Json
} else {
    $inventoryScript = Join-Path $PSScriptRoot 'inventory.ps1'
    $rawJson = & $inventoryScript -OutputFormat json
    $data = $rawJson | ConvertFrom-Json
}

$inventory = $data.inventory

# Canonical preference order
$scopePriority = @{
    'project' = 1
    'user'    = 2
    'custom'  = 3
    'cache'   = 4
}

$providerPriority = @{
    'claude-code' = 1
    'codex'       = 2
    'kimi-code'   = 3
    'legacy'      = 4
    'additional'  = 5
    'marketplace' = 6
}

function Get-Priority {
    param($Item)
    $sp = if ($scopePriority.ContainsKey($Item.scope)) { $scopePriority[$Item.scope] } else { 99 }
    $pp = if ($providerPriority.ContainsKey($Item.provider)) { $providerPriority[$Item.provider] } else { 99 }
    return $sp * 10 + $pp
}

# Group by name and find duplicates
$nameGroups = $inventory | Group-Object -Property name | Where-Object { $_.Count -gt 1 }

$plan = @()
$planId = 0

foreach ($group in $nameGroups) {
    $items = $group.Group
    $hashes = $items | Where-Object { $_.hash } | Select-Object -ExpandProperty hash -Unique
    $isConflict = ($hashes.Count -gt 1)

    if ($isConflict) {
        # Different content — conflict, report only
        foreach ($item in $items) {
            $planId++
            $plan += [ordered]@{
                id        = $planId
                name      = $item.name
                category  = 'conflict'
                path      = $item.path
                provider  = $item.provider
                scope     = $item.scope
                hash      = $item.hash
                action    = 'SKIP (conflict — different content)'
                risk      = 'n/a'
                isLink    = $item.isLink
            }
        }
    } else {
        # Same content — pick canonical, mark rest as duplicate-copy
        $sorted = $items | Sort-Object { Get-Priority $_ }
        $canonical = $sorted[0]
        $duplicates = $sorted[1..($sorted.Count - 1)]

        $planId++
        $plan += [ordered]@{
            id        = $planId
            name      = $canonical.name
            category  = if ($canonical.isLink) { 'provider-link' } else { 'canonical' }
            path      = $canonical.path
            provider  = $canonical.provider
            scope     = $canonical.scope
            hash      = $canonical.hash
            action    = 'KEEP (canonical)'
            risk      = 'none'
            isLink    = $canonical.isLink
        }

        foreach ($dup in $duplicates) {
            $planId++
            $category = 'duplicate-copy'
            $action = 'quarantine+remove'
            $risk = 'low'

            if ($dup.isLink) {
                $category = 'provider-link'
                $action = 'KEEP (provider link)'
                $risk = 'none'
            } elseif ($dup.type -eq 'cached-plugin') {
                $category = 'stale-cache'
                $action = 'remove (rebuildable)'
                $risk = 'low'
            }

            $plan += [ordered]@{
                id        = $planId
                name      = $dup.name
                category  = $category
                path      = $dup.path
                provider  = $dup.provider
                scope     = $dup.scope
                hash      = $dup.hash
                action    = $action
                risk      = $risk
                isLink    = $dup.isLink
            }
        }
    }
}

$planSummary = [ordered]@{
    timestamp       = (Get-Date -Format 'o')
    totalEntries    = $plan.Count
    duplicateGroups = $nameGroups.Count
    actions         = @{
        keep              = ($plan | Where-Object { $_.action -like 'KEEP*' }).Count
        quarantineRemove  = ($plan | Where-Object { $_.action -eq 'quarantine+remove' }).Count
        removeRebuildable = ($plan | Where-Object { $_.action -eq 'remove (rebuildable)' }).Count
        skipConflict      = ($plan | Where-Object { $_.action -like 'SKIP*' }).Count
    }
    isDryRun = $true
}

$output = [ordered]@{
    summary = $planSummary
    plan    = $plan
}

if ($OutputFormat -eq 'json') {
    $output | ConvertTo-Json -Depth 10
} else {
    Write-Host "=== Deduplication Plan (DRY RUN) ==="
    Write-Host "Duplicate groups: $($planSummary.duplicateGroups)"
    Write-Host "Keep: $($planSummary.actions.keep) | Remove: $($planSummary.actions.quarantineRemove + $planSummary.actions.removeRebuildable) | Skip: $($planSummary.actions.skipConflict)"
    Write-Host ""
    Write-Host ("{0,-4} {1,-25} {2,-16} {3,-50} {4,-30} {5}" -f '#', 'Name', 'Category', 'Path', 'Action', 'Risk')
    Write-Host ("{0,-4} {1,-25} {2,-16} {3,-50} {4,-30} {5}" -f '---', '----', '--------', '----', '------', '----')
    foreach ($entry in $plan) {
        $shortPath = $entry.path
        if ($shortPath.Length -gt 48) {
            $shortPath = '...' + $shortPath.Substring($shortPath.Length - 45)
        }
        Write-Host ("{0,-4} {1,-25} {2,-16} {3,-50} {4,-30} {5}" -f $entry.id, $entry.name, $entry.category, $shortPath, $entry.action, $entry.risk)
    }
}
