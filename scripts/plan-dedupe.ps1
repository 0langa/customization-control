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

# Windows PowerShell 5.1 started from PowerShell 7 through cmd, bash or an agent
# inherits PowerShell 7's module folders, autoloads PowerShell 7's core modules
# and loses Get-FileHash. Drop those folders (...\PowerShell\... and the Store
# app's ...\WindowsApps\Microsoft.PowerShell_*); keep every other entry.
if ($PSVersionTable.PSEdition -eq 'Desktop' -and $env:PSModulePath) {
    $powerShell7Folder = '[\\/]PowerShell[\\/]|[\\/]WindowsApps[\\/]Microsoft\.PowerShell'
    $env:PSModulePath = (($env:PSModulePath -split ';') -notmatch $powerShell7Folder) -join ';'
}

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

function Get-PhysicalPath {
    # The final location of a path once every symlink, junction and mount point
    # along it is followed, or $null when it cannot be determined.
    param([string]$Path)
    if (-not ('CustomizationControl.PhysicalPath' -as [type])) {
        try {
            Add-Type -Namespace CustomizationControl -Name PhysicalPath -MemberDefinition @'
[System.Runtime.InteropServices.DllImport("kernel32.dll", CharSet = System.Runtime.InteropServices.CharSet.Unicode, SetLastError = true)]
public static extern Microsoft.Win32.SafeHandles.SafeFileHandle CreateFileW(string name, uint access, uint share, System.IntPtr security, uint disposition, uint flags, System.IntPtr template);
[System.Runtime.InteropServices.DllImport("kernel32.dll", CharSet = System.Runtime.InteropServices.CharSet.Unicode, SetLastError = true)]
public static extern uint GetFinalPathNameByHandleW(Microsoft.Win32.SafeHandles.SafeFileHandle handle, System.Text.StringBuilder buffer, uint size, uint flags);
'@
        } catch {
            return $null
        }
    }
    try {
        $full = [System.IO.Path]::GetFullPath($Path)
    } catch {
        return $null
    }
    # 0x80 FILE_READ_ATTRIBUTES, 7 share read/write/delete, 3 OPEN_EXISTING,
    # 0x02000000 FILE_FLAG_BACKUP_SEMANTICS (needed to open a directory).
    try {
        $handle = [CustomizationControl.PhysicalPath]::CreateFileW($full, 0x80, 7, [System.IntPtr]::Zero, 3, 0x02000000, [System.IntPtr]::Zero)
    } catch {
        # No kernel32 (PowerShell 7 off Windows): treat as unknown.
        return $null
    }
    try {
        if ($handle.IsInvalid) { return $null }
        $buffer = New-Object System.Text.StringBuilder 32768
        $length = [CustomizationControl.PhysicalPath]::GetFinalPathNameByHandleW($handle, $buffer, 32768, 0)
        if ($length -eq 0 -or $length -ge 32768) { return $null }
        $final = $buffer.ToString()
        if ($final.StartsWith('\\?\UNC\')) { return '\\' + $final.Substring(8) }
        if ($final.StartsWith('\\?\')) { return $final.Substring(4) }
        return $final
    } finally {
        $handle.Dispose()
    }
}

function Test-PathOverlap {
    # True when the paths are equal or one lies inside the other.
    param([string]$First, [string]$Second)
    $comparison = [System.StringComparison]::OrdinalIgnoreCase
    $a = $First.TrimEnd('\', '/') + '\'
    $b = $Second.TrimEnd('\', '/') + '\'
    return $a.StartsWith($b, $comparison) -or $b.StartsWith($a, $comparison)
}

# Entries that resolve to the same place (a link and its target, a path through
# a linked parent folder, or a project root that is the user root because the
# helper runs from home) are one copy: removing either deletes both.
$inventory = @($inventory | Where-Object { $null -ne $_ })
$physicalPaths = @{}
for ($index = 0; $index -lt $inventory.Count; $index++) {
    $inventory[$index] | Add-Member -NotePropertyName inventoryIndex -NotePropertyValue $index -Force
    $entryPath = [string]$inventory[$index].path
    $physicalPaths[$index] = if (-not $entryPath) {
        $null
    } elseif (Test-Path -LiteralPath $entryPath) {
        Get-PhysicalPath $entryPath
    } else {
        # Gone since the inventory ran: nothing on disk to share, compare as written.
        [System.IO.Path]::GetFullPath($entryPath)
    }
}

function Test-SharesCopy {
    # $true when another inventory entry is physically the same copy as $Item
    # (or contains it, or lies inside it); $null when that cannot be told.
    param($Item)
    $mine = $physicalPaths[$Item.inventoryIndex]
    if (-not $mine) { return $null }
    foreach ($other in $inventory) {
        if ($other.inventoryIndex -eq $Item.inventoryIndex) { continue }
        $theirs = $physicalPaths[$other.inventoryIndex]
        if ($theirs -and (Test-PathOverlap $mine $theirs)) { return $true }
    }
    return $false
}

# Group by name and find duplicates
# @() keeps one-element results countable under Set-StrictMode -Version Latest.
$nameGroups = @($inventory | Group-Object -Property name | Where-Object { $_.Count -gt 1 })

$plan = @()
$planId = 0

foreach ($group in $nameGroups) {
    $items = $group.Group
    $hashes = @($items | Where-Object { $_.hash } | Select-Object -ExpandProperty hash -Unique)
    $isConflict = ($hashes.Count -gt 1)

    if ($isConflict) {
        # Different content - conflict, report only
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
                action    = 'SKIP (conflict - different content)'
                risk      = 'n/a'
                isLink    = $item.isLink
            }
        }
    } else {
        # Same content - pick canonical, mark rest as duplicate-copy.
        # A copy without a content hash cannot be shown identical to the
        # others, so it is never canonical and never removed.
        foreach ($item in @($items | Where-Object { -not $_.hash -and -not $_.isLink })) {
            $planId++
            $plan += [ordered]@{
                id        = $planId
                name      = $item.name
                category  = 'unknown'
                path      = $item.path
                provider  = $item.provider
                scope     = $item.scope
                hash      = $item.hash
                action    = 'SKIP (no content hash to compare)'
                risk      = 'n/a'
                isLink    = $item.isLink
            }
        }

        $sorted = @($items | Where-Object { $_.hash -or $_.isLink } | Sort-Object { Get-Priority $_ })
        if ($sorted.Count -eq 0) {
            continue
        }
        $canonical = $sorted[0]
        $duplicates = @(if ($sorted.Count -gt 1) { $sorted[1..($sorted.Count - 1)] })

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

            $shared = if ($dup.isLink) { $false } else { Test-SharesCopy $dup }

            if ($dup.isLink) {
                $category = 'provider-link'
                $action = 'KEEP (provider link)'
                $risk = 'none'
            } elseif ($null -eq $shared) {
                $category = 'unknown'
                $action = 'SKIP (cannot resolve the physical path)'
                $risk = 'n/a'
            } elseif ($shared) {
                $category = 'canonical'
                $action = 'KEEP (same physical copy)'
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
        keep              = @($plan | Where-Object { $_.action -like 'KEEP*' }).Count
        quarantineRemove  = @($plan | Where-Object { $_.action -eq 'quarantine+remove' }).Count
        removeRebuildable = @($plan | Where-Object { $_.action -eq 'remove (rebuildable)' }).Count
        skipConflict      = @($plan | Where-Object { $_.action -like 'SKIP*' }).Count
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
