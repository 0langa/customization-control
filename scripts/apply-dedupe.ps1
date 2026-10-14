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
    $handle = [CustomizationControl.PhysicalPath]::CreateFileW($full, 0x80, 7, [System.IntPtr]::Zero, 3, 0x02000000, [System.IntPtr]::Zero)
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

function Get-TreeFingerprint {
    # Relative name and SHA-256 of every file below $Path. Links inside the tree
    # are listed with their target instead of followed. '' when unreadable.
    param([string]$Path)
    try {
        $top = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
        if (-not $top.PSIsContainer) {
            return (Get-FileHash -Algorithm SHA256 -LiteralPath $top.FullName -ErrorAction Stop).Hash
        }
        $lines = New-Object System.Collections.Generic.List[string]
        $pending = New-Object System.Collections.Generic.Stack[string]
        $pending.Push('')
        while ($pending.Count -gt 0) {
            $relative = $pending.Pop()
            $directory = if ($relative) { Join-Path $top.FullName $relative } else { $top.FullName }
            foreach ($child in @(Get-ChildItem -LiteralPath $directory -Force -ErrorAction Stop)) {
                $childRelative = if ($relative) { "$relative\$($child.Name)" } else { $child.Name }
                if ($child.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
                    $lines.Add("L $childRelative $(@($child.Target) -join ';')")
                } elseif ($child.PSIsContainer) {
                    $pending.Push($childRelative)
                } else {
                    $lines.Add("F $childRelative $((Get-FileHash -Algorithm SHA256 -LiteralPath $child.FullName -ErrorAction Stop).Hash)")
                }
            }
        }
        $sorted = $lines.ToArray()
        [System.Array]::Sort($sorted, [System.StringComparer]::Ordinal)
        return ($sorted -join "`n")
    } catch {
        return ''
    }
}

function Get-RemovalConflict {
    # Why removing a plan entry could lose data, or '' for a safe duplicate.
    # Re-checked here because the plan may be stale or edited: the canonical
    # copy must still exist, the entry must not be the same physical copy as
    # anything the plan keeps, and a duplicate-copy must match the canonical
    # file for file (the plan only compared SKILL.md or plugin.json).
    param($Item, [string]$ItemPath)
    $canonical = @($plan | Where-Object { $_.name -eq $Item.name -and $_.action -eq 'KEEP (canonical)' }) | Select-Object -First 1
    if (-not $canonical) { return 'No KEEP (canonical) entry for this name in the plan' }
    $canonicalPath = [System.IO.Path]::GetFullPath([string]$canonical.path)
    if (-not (Test-Path -LiteralPath $canonicalPath)) { return "Canonical copy is missing: $canonicalPath" }
    $mine = Get-PhysicalPath $ItemPath
    if (-not $mine) { return "Cannot resolve the physical path of $ItemPath" }
    foreach ($kept in @($plan | Where-Object { $_.action -like 'KEEP*' })) {
        $theirs = Get-PhysicalPath ([string]$kept.path)
        if ($theirs -and (Test-PathOverlap $mine $theirs)) {
            return "Same physical copy as kept entry $($kept.path)"
        }
    }
    if ($Item.action -eq 'quarantine+remove') {
        $fingerprint = Get-TreeFingerprint $ItemPath
        if (-not $fingerprint -or $fingerprint -cne (Get-TreeFingerprint $canonicalPath)) {
            return "Content differs from the canonical copy $canonicalPath"
        }
    }
    return ''
}

# Load plan
$planData = Get-Content -Raw -LiteralPath $PlanJson | ConvertFrom-Json
$plan = @($planData.plan | Where-Object { $null -ne $_ })

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

    $conflict = Get-RemovalConflict $item $itemPath
    if ($conflict) {
        $result.status = 'BLOCKED'
        $result.error = $conflict
        $results += $result
        continue
    }

    if ($DryRun) {
        $result.status = 'dry-run'
        $results += $result
        continue
    }

    try {
        # Quarantine. Copies of one name share the timestamp; give each its own folder.
        $quarantineDest = Join-Path $quarantineBase "${timestamp}_$($item.name)"
        $suffix = 2
        while (Test-Path -LiteralPath $quarantineDest) {
            $quarantineDest = Join-Path $quarantineBase "${timestamp}_$($item.name)-$suffix"
            $suffix++
        }
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
