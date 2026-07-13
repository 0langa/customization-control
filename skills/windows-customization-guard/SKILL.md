---
name: windows-customization-guard
description: >
  Use this skill when applying Windows-specific safety guardrails to customization operations. Validates
  paths, handles junctions vs symlinks, ensures PowerShell-safe operations,
  prevents deletion outside approved roots, and guards against common Windows
  path pitfalls.
when_to_use: >
  Use proactively during any customization-control operation on Windows.
  Activated automatically by other skills when they detect Windows environment.
  Also use when debugging Windows-specific symlink, junction, or path issues
  with agent customizations.
user-invocable: false
---

# Windows Customization Guard

Safety layer for all customization operations on Windows. Other skills in this plugin should apply these rules when running on Windows.

## Path safety rules

### Resolution
- Always resolve paths to absolute using `[System.IO.Path]::GetFullPath()` or `Resolve-Path`.
- Never use string concatenation to build paths for destructive operations.
- Handle both `\` and `/` separators — normalize to `\` for Windows operations.
- Expand `~` to `$env:USERPROFILE` explicitly.

### Boundary checking
Before any destructive operation (delete, move, overwrite):

```powershell
$resolvedPath = [System.IO.Path]::GetFullPath($targetPath)
$approvedRoots = @(
    [System.IO.Path]::GetFullPath("$env:USERPROFILE\.claude"),
    [System.IO.Path]::GetFullPath("$env:USERPROFILE\.codex"),
    [System.IO.Path]::GetFullPath("$env:USERPROFILE\.agents"),
    [System.IO.Path]::GetFullPath("$env:USERPROFILE\.kimi-code")
    # Plus any repo roots from known-roots.json
)
$inBounds = $approvedRoots | Where-Object { $resolvedPath.StartsWith($_, [System.StringComparison]::OrdinalIgnoreCase) }
if (-not $inBounds) {
    throw "BLOCKED: $resolvedPath is outside all approved roots"
}
```

### Long path handling
- Enable long paths if needed: paths over 260 chars.
- Use `\\?\` prefix for very long paths in Windows API calls.

## Symlinks and junctions

### Prefer junctions for directories
- Directory junctions (`mklink /J`) work without elevated privileges.
- Directory symlinks (`mklink /D`) may require Developer Mode or elevation.
- File symlinks (`mklink`) may require elevation.

### Creating junctions
```powershell
cmd /c mklink /J "$linkPath" "$targetPath"
```

### Detecting link type
```powershell
$item = Get-Item $path -Force
if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
    # It's a symlink or junction
    $target = (Get-Item $path).Target
}
```

### Junction vs symlink behavior differences
- Junctions resolve at the filesystem level — they work even if the creating user is not logged in.
- Junctions only work for local directories (not network paths or files).
- Symlinks can point to files or network paths but may need elevation.

## PowerShell-safe operations

### File operations — use cmdlets, not string commands
```powershell
# Good
Copy-Item -Path $source -Destination $dest -Recurse -Force
Remove-Item -Path $target -Recurse -Force

# Bad — never do this
Invoke-Expression "rm -rf $target"
cmd /c "del /s /q $target"
```

### Path comparison — case-insensitive
```powershell
$path1.Equals($path2, [System.StringComparison]::OrdinalIgnoreCase)
```

### Error handling
```powershell
try {
    Remove-Item -Path $target -Recurse -Force -ErrorAction Stop
} catch {
    Write-Error "Failed to remove $target: $_"
    # Do not silently continue
}
```

## Quarantine on Windows

When quarantining items:
1. Use `Copy-Item -Recurse` to quarantine directory.
2. Verify copy succeeded before removing original.
3. Use absolute resolved paths for both source and destination.
4. Write quarantine manifest with Windows-style paths.

## Common pitfalls

- `~` in PowerShell resolves differently than in bash — always expand explicitly.
- `Join-Path` is safer than string concatenation for building paths.
- `Test-Path` on a broken symlink returns `$false` — use `Get-Item -Force` to detect reparse points.
- `Remove-Item` on a junction removes the junction, not the target contents (correct behavior).
