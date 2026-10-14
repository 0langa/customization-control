<#
.SYNOPSIS
    Manage quarantine: list, restore, or purge quarantined customizations.
.PARAMETER Action
    Action to perform: 'list', 'restore', 'purge'.
.PARAMETER Name
    Name of quarantined item (for restore/purge).
.PARAMETER QuarantineRoot
    Root directory for quarantine.
.PARAMETER OutputFormat
    Output format: 'json' or 'table'.
#>
[CmdletBinding()]
param(
    [ValidateSet('list', 'restore', 'purge')]
    [string]$Action = 'list',

    [string]$Name = '',

    [string]$QuarantineRoot = '.customization-control\quarantine',

    [ValidateSet('json', 'table')]
    [string]$OutputFormat = 'json'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$quarantineBase = [System.IO.Path]::GetFullPath($QuarantineRoot)
$manifestPath = Join-Path $quarantineBase 'quarantine-manifest.json'

if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    if ($OutputFormat -eq 'json') {
        [ordered]@{ entries = @(); message = 'No quarantine manifest found.' } | ConvertTo-Json
    } else {
        Write-Host "No quarantine manifest found at $manifestPath"
    }
    return
}

# Assign before wrapping in @(): Windows PowerShell 5.1 emits a JSON array as
# one object, which @(pipeline) would nest inside another array.
$parsedManifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
$manifest = @($parsedManifest | Where-Object { $null -ne $_ })

switch ($Action) {
    'list' {
        if ($OutputFormat -eq 'json') {
            [ordered]@{
                total   = $manifest.Count
                entries = $manifest
            } | ConvertTo-Json -Depth 10
        } else {
            Write-Host "=== Quarantined Items ==="
            Write-Host "Total: $($manifest.Count)"
            Write-Host ""
            foreach ($entry in $manifest) {
                Write-Host "  $($entry.name) [$($entry.category)]"
                Write-Host "    Original: $($entry.originalPath)"
                Write-Host "    Quarantine: $($entry.quarantinePath)"
                Write-Host "    When: $($entry.timestamp)"
                Write-Host "    Reason: $($entry.reason)"
                Write-Host ""
            }
        }
    }

    'restore' {
        if (-not $Name) {
            Write-Error "Must specify -Name for restore"
            return
        }

        $entry = $manifest | Where-Object { $_.name -eq $Name } | Select-Object -First 1
        if (-not $entry) {
            Write-Error "No quarantined item named '$Name'"
            return
        }

        if (-not (Test-Path -LiteralPath $entry.quarantinePath)) {
            Write-Error "Quarantine copy not found at $($entry.quarantinePath)"
            return
        }

        if (Test-Path -LiteralPath $entry.originalPath) {
            Write-Error "Original path already occupied: $($entry.originalPath)"
            return
        }

        Copy-Item -LiteralPath $entry.quarantinePath -Destination $entry.originalPath -Recurse -Force
        Write-Host "Restored '$Name' to $($entry.originalPath)"

        # Remove from manifest
        $manifest = @($manifest | Where-Object { $_.name -ne $Name -or $_.timestamp -ne $entry.timestamp })
        ConvertTo-Json -InputObject @($manifest) -Depth 10 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

        # Clean quarantine copy
        Remove-Item -LiteralPath $entry.quarantinePath -Recurse -Force
        Write-Host "Removed quarantine copy."
    }

    'purge' {
        if (-not $Name) {
            Write-Error "Must specify -Name for purge"
            return
        }

        $entry = $manifest | Where-Object { $_.name -eq $Name } | Select-Object -First 1
        if (-not $entry) {
            Write-Error "No quarantined item named '$Name'"
            return
        }

        if (Test-Path -LiteralPath $entry.quarantinePath) {
            Remove-Item -LiteralPath $entry.quarantinePath -Recurse -Force
        }

        $manifest = @($manifest | Where-Object { $_.name -ne $Name -or $_.timestamp -ne $entry.timestamp })
        ConvertTo-Json -InputObject @($manifest) -Depth 10 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

        Write-Host "Purged '$Name' from quarantine."
    }
}
