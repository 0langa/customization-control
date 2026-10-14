<#
.SYNOPSIS
    Validate customizations: check symlinks resolve, manifests parse, paths are within bounds.
.PARAMETER InventoryJson
    Path to a JSON inventory file from inventory.ps1, or '-' to read from stdin.
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

$approvedRootPaths = @(
    (Resolve-HomePath '~/.claude'),
    (Resolve-HomePath '~/.codex'),
    (Resolve-HomePath '~/.agents'),
    (Resolve-HomePath '~/.kimi-code')
)

function Test-InApprovedRoot {
    param([string]$Path)
    # Match the root itself or a child of it, never a sibling that merely
    # shares its prefix (e.g. ~/.claude-backup).
    $resolved = [System.IO.Path]::GetFullPath($Path).TrimEnd('\', '/')
    foreach ($root in $approvedRootPaths) {
        $rootPath = $root.TrimEnd('\', '/')
        if ($resolved.Equals($rootPath, [System.StringComparison]::OrdinalIgnoreCase) -or
            $resolved.StartsWith($rootPath + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
            return $true
        }
    }
    return $false
}

function Test-SkillManifest {
    param([string]$SkillMdPath)
    $issues = @()

    if (-not (Test-Path $SkillMdPath -PathType Leaf)) {
        $issues += "SKILL.md not found"
        return $issues
    }

    $content = Get-Content -Raw -Path $SkillMdPath
    if ($content -match '(?s)^---\r?\n(.+?)\r?\n---') {
        $frontmatter = $Matches[1]
        if ($frontmatter -notmatch 'description:') {
            $issues += "Missing recommended 'description' field in frontmatter"
        }
    } else {
        $issues += "No YAML frontmatter found"
    }

    return $issues
}

function Test-PluginManifest {
    param([string]$ManifestPath)
    $issues = @()

    if (-not (Test-Path $ManifestPath -PathType Leaf)) {
        $issues += "plugin.json not found"
        return $issues
    }

    try {
        $manifest = Get-Content -Raw -Path $ManifestPath | ConvertFrom-Json
        if (-not $manifest.name) {
            $issues += "Missing required 'name' field"
        }
    } catch {
        $issues += "Invalid JSON: $($_.Exception.Message)"
    }

    return $issues
}

# Load inventory
$inventory = @()
if ($InventoryJson -and (Test-Path $InventoryJson -PathType Leaf)) {
    $data = Get-Content -Raw -Path $InventoryJson | ConvertFrom-Json
    $inventory = $data.inventory
} else {
    # Run inventory inline
    $inventoryScript = Join-Path $PSScriptRoot 'inventory.ps1'
    if (Test-Path $inventoryScript) {
        $rawJson = & $inventoryScript -OutputFormat json
        $data = $rawJson | ConvertFrom-Json
        $inventory = $data.inventory
    } else {
        Write-Error "No inventory provided and inventory.ps1 not found"
        return
    }
}

$validationResults = @()

foreach ($item in $inventory) {
    $result = [ordered]@{
        name     = $item.name
        path     = $item.path
        type     = $item.type
        provider = $item.provider
        issues   = @()
        status   = 'valid'
    }

    # Check path exists
    if (-not (Test-Path -LiteralPath $item.path -ErrorAction SilentlyContinue)) {
        $itemObj = $null
        try { $itemObj = Get-Item -LiteralPath $item.path -Force -ErrorAction SilentlyContinue } catch {}
        if (-not $itemObj) {
            $result.issues += "Path does not exist"
            $result.status = 'missing'
        }
    }

    # Check symlink target
    if ($item.isLink -and $item.linkTarget) {
        if (-not (Test-Path -LiteralPath $item.linkTarget -ErrorAction SilentlyContinue)) {
            $result.issues += "Symlink target does not exist: $($item.linkTarget)"
            $result.status = 'broken-link'
        }
    }

    # Check path bounds for user-scope items
    if ($item.scope -eq 'user') {
        if (-not (Test-InApprovedRoot $item.path)) {
            $result.issues += "Path outside approved roots"
            $result.status = 'out-of-bounds'
        }
    }

    # Validate skill manifest
    if ($item.type -eq 'skill' -or $item.type -eq 'skill-plugin') {
        $skillMd = Join-Path $item.path 'SKILL.md'
        # @() so a function that returns nothing adds no $null issue.
        $result.issues += @(Test-SkillManifest $skillMd)
    }

    # Validate plugin manifest
    if ($item.hasManifest -and $item.type -eq 'skill-plugin') {
        $pluginJson = Join-Path (Join-Path $item.path '.claude-plugin') 'plugin.json'
        if (Test-Path $pluginJson) {
            $result.issues += @(Test-PluginManifest $pluginJson)
        }
    }

    if ($result.issues.Count -gt 0 -and $result.status -eq 'valid') {
        $result.status = 'warning'
    }

    $validationResults += $result
}

$validSummary = [ordered]@{
    timestamp  = (Get-Date -Format 'o')
    total      = $validationResults.Count
    valid      = @($validationResults | Where-Object { $_.status -eq 'valid' }).Count
    warnings   = @($validationResults | Where-Object { $_.status -eq 'warning' }).Count
    errors     = @($validationResults | Where-Object { $_.status -notin @('valid', 'warning') }).Count
    byStatus   = @{}
}

# Count by hand: Group-Object cannot read keys of the ordered dictionaries
# above and would put every result under an empty status.
foreach ($validationResult in $validationResults) {
    $status = $validationResult.status
    if (-not $validSummary.byStatus.ContainsKey($status)) { $validSummary.byStatus[$status] = 0 }
    $validSummary.byStatus[$status]++
}

$output = [ordered]@{
    summary = $validSummary
    results = $validationResults
}

if ($OutputFormat -eq 'json') {
    $output | ConvertTo-Json -Depth 10
} else {
    Write-Host "=== Validation Results ==="
    Write-Host "Total: $($validSummary.total) | Valid: $($validSummary.valid) | Warnings: $($validSummary.warnings) | Errors: $($validSummary.errors)"
    Write-Host ""

    $validationResults | Where-Object { $_.status -ne 'valid' } | ForEach-Object {
        Write-Host "[$($_.status)] $($_.name) ($($_.provider))"
        Write-Host "  Path: $($_.path)"
        $_.issues | ForEach-Object { Write-Host "  - $_" }
        Write-Host ""
    }
}
