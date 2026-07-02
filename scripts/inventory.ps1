<#
.SYNOPSIS
    Inventory all agent customizations across Codex, Claude Code, Kimi Code, and legacy roots.
.DESCRIPTION
    Scans known customization roots and produces a structured JSON inventory of all
    discovered skills, plugins, commands, and config files.
.PARAMETER OutputFormat
    Output format: 'json' for machine-readable, 'table' for human-readable.
.PARAMETER DryRun
    If set, only shows what would be scanned without scanning.
.PARAMETER AdditionalRoots
    Additional root paths to scan beyond the defaults.
#>
[CmdletBinding()]
param(
    [ValidateSet('json', 'table')]
    [string]$OutputFormat = 'json',

    [switch]$DryRun,

    [string[]]$AdditionalRoots = @()
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

function Get-LinkTarget {
    param([string]$Path)
    try {
        $item = Get-Item $Path -Force -ErrorAction Stop
        if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
            return @{
                IsLink = $true
                Target = $item.Target
                LinkType = if ($item.LinkType) { $item.LinkType } else { 'Unknown' }
            }
        }
    } catch {}
    return @{ IsLink = $false; Target = $null; LinkType = $null }
}

function Get-ContentHash {
    param([string]$FilePath)
    if (Test-Path $FilePath -PathType Leaf) {
        return (Get-FileHash -Algorithm SHA256 -Path $FilePath).Hash
    }
    return $null
}

function Scan-SkillDir {
    param(
        [string]$RootPath,
        [string]$Provider,
        [string]$Scope
    )
    $results = @()
    $resolved = Resolve-HomePath $RootPath

    if (-not (Test-Path $resolved -PathType Container)) {
        return $results
    }

    Get-ChildItem -Path $resolved -Directory -ErrorAction SilentlyContinue | ForEach-Object {
        $skillDir = $_.FullName
        $skillMd = Join-Path $skillDir 'SKILL.md'
        $linkInfo = Get-LinkTarget $skillDir

        $entry = [ordered]@{
            name      = $_.Name
            type      = 'skill'
            provider  = $Provider
            scope     = $Scope
            path      = $skillDir
            isLink    = $linkInfo.IsLink
            linkTarget = $linkInfo.Target
            linkType  = $linkInfo.LinkType
            hash      = $null
            hasManifest = $false
        }

        if (Test-Path $skillMd -PathType Leaf) {
            $entry.hash = Get-ContentHash $skillMd
        }

        $pluginJson = Join-Path (Join-Path $skillDir '.claude-plugin') 'plugin.json'
        if (Test-Path $pluginJson -PathType Leaf) {
            $entry.hasManifest = $true
            $entry.type = 'skill-plugin'
        }

        $results += $entry
    }

    return $results
}

function Scan-CommandDir {
    param(
        [string]$RootPath,
        [string]$Provider,
        [string]$Scope
    )
    $results = @()
    $resolved = Resolve-HomePath $RootPath

    if (-not (Test-Path $resolved -PathType Container)) {
        return $results
    }

    Get-ChildItem -Path $resolved -File -Filter '*.md' -ErrorAction SilentlyContinue | ForEach-Object {
        $results += [ordered]@{
            name      = $_.BaseName
            type      = 'command'
            provider  = $Provider
            scope     = $Scope
            path      = $_.FullName
            isLink    = $false
            linkTarget = $null
            linkType  = $null
            hash      = Get-ContentHash $_.FullName
            hasManifest = $false
        }
    }

    return $results
}

function Scan-PluginCache {
    param(
        [string]$CachePath,
        [string]$Provider
    )
    $results = @()
    $resolved = Resolve-HomePath $CachePath

    if (-not (Test-Path $resolved -PathType Container)) {
        return $results
    }

    Get-ChildItem -Path $resolved -Directory -ErrorAction SilentlyContinue | ForEach-Object {
        $pluginDir = $_.FullName
        $linkInfo = Get-LinkTarget $pluginDir

        Get-ChildItem -Path $pluginDir -Directory -ErrorAction SilentlyContinue | ForEach-Object {
            $subDir = $_.FullName
            $manifestCandidates = @(
                (Join-Path $subDir 'plugin.json'),
                (Join-Path (Join-Path $subDir '.claude-plugin') 'plugin.json'),
                (Join-Path $subDir 'SKILL.md')
            )

            $manifest = $manifestCandidates | Where-Object { Test-Path $_ -PathType Leaf } | Select-Object -First 1
            $hash = if ($manifest) { Get-ContentHash $manifest } else { $null }

            $results += [ordered]@{
                name      = $_.Name
                type      = 'cached-plugin'
                provider  = $Provider
                scope     = 'cache'
                path      = $subDir
                isLink    = (Get-LinkTarget $subDir).IsLink
                linkTarget = (Get-LinkTarget $subDir).Target
                linkType  = (Get-LinkTarget $subDir).LinkType
                hash      = $hash
                hasManifest = ($null -ne $manifest)
            }
        }
    }

    return $results
}

function Scan-MarketplaceJson {
    param([string]$Path)
    $results = @()
    $resolved = Resolve-HomePath $Path

    if (-not (Test-Path $resolved -PathType Leaf)) {
        return $results
    }

    try {
        $content = Get-Content -Raw -Path $resolved | ConvertFrom-Json
        if ($content.plugins) {
            foreach ($plugin in $content.plugins) {
                $results += [ordered]@{
                    name      = $plugin.name
                    type      = 'marketplace-entry'
                    provider  = 'marketplace'
                    scope     = 'user'
                    path      = $resolved
                    isLink    = $false
                    linkTarget = if ($plugin.path) { $plugin.path } else { $null }
                    linkType  = $null
                    hash      = $null
                    hasManifest = $true
                    entryData = $plugin
                }
            }
        }
    } catch {
        $results += [ordered]@{
            name      = 'marketplace.json'
            type      = 'invalid-marketplace'
            provider  = 'marketplace'
            scope     = 'user'
            path      = $resolved
            isLink    = $false
            linkTarget = $null
            linkType  = $null
            hash      = $null
            hasManifest = $false
            error     = $_.Exception.Message
        }
    }

    return $results
}

# Define scan targets
$scanTargets = @(
    @{ Path = '~/.claude/skills';       Provider = 'claude-code'; Scope = 'user';    Type = 'skills' }
    @{ Path = '.claude/skills';         Provider = 'claude-code'; Scope = 'project'; Type = 'skills' }
    @{ Path = '.claude/commands';       Provider = 'claude-code'; Scope = 'project'; Type = 'commands' }
    @{ Path = '~/.codex/skills';        Provider = 'codex';       Scope = 'user';    Type = 'skills' }
    @{ Path = '.codex/skills';          Provider = 'codex';       Scope = 'project'; Type = 'skills' }
    @{ Path = '~/.agents/skills';       Provider = 'legacy';      Scope = 'user';    Type = 'skills' }
    @{ Path = '.kimi-code/skills';      Provider = 'kimi-code';   Scope = 'project'; Type = 'skills' }
)

$cacheTargets = @(
    @{ Path = '~/.codex/plugins/cache'; Provider = 'codex' }
)

$marketplaceTargets = @(
    '~/.agents/plugins/marketplace.json'
)

if ($DryRun) {
    $scanInfo = @{
        skillDirs = $scanTargets | ForEach-Object { Resolve-HomePath $_.Path }
        cacheDirs = $cacheTargets | ForEach-Object { Resolve-HomePath $_.Path }
        marketplaces = $marketplaceTargets | ForEach-Object { Resolve-HomePath $_ }
        additionalRoots = $AdditionalRoots
    }

    if ($OutputFormat -eq 'json') {
        $scanInfo | ConvertTo-Json -Depth 5
    } else {
        Write-Host "=== Scan Targets ==="
        $scanInfo.skillDirs | ForEach-Object { Write-Host "  Skill dir: $_" }
        $scanInfo.cacheDirs | ForEach-Object { Write-Host "  Cache dir: $_" }
        $scanInfo.marketplaces | ForEach-Object { Write-Host "  Marketplace: $_" }
    }
    return
}

# Run inventory
$inventory = @()

foreach ($target in $scanTargets) {
    if ($target.Type -eq 'commands') {
        $inventory += Scan-CommandDir -RootPath $target.Path -Provider $target.Provider -Scope $target.Scope
    } else {
        $inventory += Scan-SkillDir -RootPath $target.Path -Provider $target.Provider -Scope $target.Scope
    }
}

foreach ($target in $cacheTargets) {
    $inventory += Scan-PluginCache -CachePath $target.Path -Provider $target.Provider
}

foreach ($mp in $marketplaceTargets) {
    $inventory += Scan-MarketplaceJson -Path $mp
}

# Scan additional roots
foreach ($root in $AdditionalRoots) {
    $inventory += Scan-SkillDir -RootPath $root -Provider 'additional' -Scope 'custom'
}

# Build summary
$summary = [ordered]@{
    timestamp       = (Get-Date -Format 'o')
    totalItems      = $inventory.Count
    byProvider      = @{}
    byType          = @{}
    byScope         = @{}
    issues          = @{
        brokenLinks = @()
        duplicates  = @()
    }
}

foreach ($item in $inventory) {
    $p = $item['provider']
    $t = $item['type']
    $s = $item['scope']
    if (-not $summary.byProvider.ContainsKey($p)) { $summary.byProvider[$p] = 0 }
    if (-not $summary.byType.ContainsKey($t)) { $summary.byType[$t] = 0 }
    if (-not $summary.byScope.ContainsKey($s)) { $summary.byScope[$s] = 0 }
    $summary.byProvider[$p]++
    $summary.byType[$t]++
    $summary.byScope[$s]++

    # Detect broken links
    if ($item['isLink'] -and $item['linkTarget']) {
        if (-not (Test-Path $item['linkTarget'] -ErrorAction SilentlyContinue)) {
            $summary.issues.brokenLinks += $item['path']
        }
    }
}

# Detect duplicates by name
$nameGroups = $inventory | ForEach-Object { [PSCustomObject]$_ } | Group-Object -Property name | Where-Object { $_.Count -gt 1 }
foreach ($group in $nameGroups) {
    $hashes = @($group.Group | ForEach-Object { $_.hash } | Where-Object { $_ } | Select-Object -Unique)
    $summary.issues.duplicates += [ordered]@{
        name      = $group.Name
        count     = $group.Count
        locations = @($group.Group | ForEach-Object { $_.path })
        isConflict = ($hashes.Count -gt 1)
    }
}

$output = [ordered]@{
    summary   = $summary
    inventory = $inventory
}

if ($OutputFormat -eq 'json') {
    $output | ConvertTo-Json -Depth 10
} else {
    Write-Host "=== Customization Inventory ==="
    Write-Host "Total items: $($summary.totalItems)"
    Write-Host ""
    Write-Host "By provider:"
    $summary.byProvider.GetEnumerator() | ForEach-Object { Write-Host "  $($_.Key): $($_.Value)" }
    Write-Host ""
    Write-Host "By type:"
    $summary.byType.GetEnumerator() | ForEach-Object { Write-Host "  $($_.Key): $($_.Value)" }
    Write-Host ""

    if ($summary.issues.brokenLinks.Count -gt 0) {
        Write-Host "Broken links:"
        $summary.issues.brokenLinks | ForEach-Object { Write-Host "  $_" }
    }

    if ($summary.issues.duplicates.Count -gt 0) {
        Write-Host ""
        Write-Host "Duplicates:"
        foreach ($dup in $summary.issues.duplicates) {
            $tag = if ($dup.isConflict) { 'CONFLICT' } else { 'identical' }
            Write-Host "  $($dup.name) ($tag) - $($dup.count) copies:"
            $dup.locations | ForEach-Object { Write-Host "    $_" }
        }
    }
}
