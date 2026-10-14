#!/usr/bin/env python3
"""Cross-platform helpers for customization-control.

The PowerShell scripts remain the Windows-native implementation. This module
provides the same read/plan/apply surface for Codex sessions running on WSL,
Linux, or macOS where PowerShell is not guaranteed to exist.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCAN_TARGETS = [
    ("~/.claude/skills", "claude-code", "user", "skills"),
    (".claude/skills", "claude-code", "project", "skills"),
    (".claude/commands", "claude-code", "project", "commands"),
    ("~/.codex/skills", "codex", "user", "skills"),
    (".codex/skills", "codex", "project", "skills"),
    ("~/.agents/skills", "legacy", "user", "skills"),
    (".kimi-code/skills", "kimi-code", "project", "skills"),
]

CACHE_TARGETS = [
    ("~/.codex/plugins/cache", "codex"),
    ("~/.claude/plugins/cache", "claude-code"),
]

MANAGED_TARGETS = [("~/.kimi-code/plugins/managed", "kimi-code")]

MARKETPLACE_TARGETS = [
    "~/.agents/plugins/marketplace.json",
]

SCOPE_PRIORITY = {
    "project": 1,
    "user": 2,
    "custom": 3,
    "cache": 4,
}

PROVIDER_PRIORITY = {
    "claude-code": 1,
    "codex": 2,
    "kimi-code": 3,
    "legacy": 4,
    "additional": 5,
    "marketplace": 6,
}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def resolve_path(path: str | Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def as_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, sort_keys=False))


def path_in_roots(path: Path, roots: list[Path]) -> bool:
    resolved = resolve_path(path)
    for root in roots:
        try:
            if os.path.commonpath([os.path.normcase(str(resolved)), os.path.normcase(str(root))]) == os.path.normcase(str(root)):
                return True
        except ValueError:
            continue
    return False


def approved_roots() -> list[Path]:
    home = Path.home()
    return [
        resolve_path(home / ".claude"),
        resolve_path(home / ".codex"),
        resolve_path(home / ".agents"),
        resolve_path(home / ".kimi-code"),
        resolve_path(".claude"),
        resolve_path(".codex"),
        resolve_path(".kimi-code"),
        resolve_path(".customization-control"),
    ]


def path_strictly_in_roots(path: Path, roots: list[Path]) -> bool:
    resolved = os.path.normcase(str(resolve_path(path)))
    return path_in_roots(path, roots) and all(resolved != os.path.normcase(str(root)) for root in roots)


def is_link_or_junction(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(os.path, "isjunction", None)
    if is_junction and is_junction(path):
        return True
    # os.path.isjunction is new in Python 3.12; before that a junction is only
    # visible as a reparse point.
    try:
        attributes = getattr(os.lstat(path), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def physical_path(path_text: str) -> str | None:
    """Where an item really lives once every link along its path is followed."""
    try:
        return os.path.normcase(os.path.realpath(os.path.expanduser(path_text)))
    except (OSError, ValueError):
        return None


def paths_overlap(first: str, second: str) -> bool:
    """True when the paths are equal or one lies inside the other."""
    first_dir = first.rstrip("\\/") + os.sep
    second_dir = second.rstrip("\\/") + os.sep
    return first_dir.startswith(second_dir) or second_dir.startswith(first_dir)


def tree_digest(path: Path) -> str | None:
    """SHA-256 over the relative name and content of every file below path.

    Links inside the tree are recorded by their target instead of followed.
    Returns None when something cannot be read.
    """
    try:
        if path.is_file():
            return file_hash(path)
        digest = hashlib.sha256()
        pending = [Path()]
        while pending:
            relative = pending.pop()
            with os.scandir(path / relative) as entries:
                for child_entry in sorted(entries, key=lambda item: item.name):
                    child = relative / child_entry.name
                    full = path / child
                    if is_link_or_junction(full):
                        digest.update(f"L {child.as_posix()} {os.readlink(full)}\n".encode("utf-8"))
                    elif child_entry.is_dir():
                        pending.append(child)
                    else:
                        digest.update(f"F {child.as_posix()} {file_hash(full)}\n".encode("utf-8"))
        return digest.hexdigest()
    except OSError:
        return None


def unique_path(base: Path, name: str) -> Path:
    candidate = base / name
    counter = 2
    while candidate.exists() or candidate.is_symlink():
        candidate = base / f"{name}-{counter}"
        counter += 1
    return candidate


def read_json(path: Path) -> Any:
    # utf-8-sig: Windows PowerShell 5.1 writes UTF-8 files with a BOM.
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_manifest(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    data = read_json(path)
    # Older PowerShell helpers wrote a one-entry manifest as a bare object.
    return [data] if isinstance(data, dict) else list(data or [])


def file_hash(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def link_info(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        target = os.readlink(path)
        return {"isLink": True, "linkTarget": target, "linkType": "SymbolicLink"}
    return {"isLink": False, "linkTarget": None, "linkType": None}


def entry(
    *,
    name: str,
    type_: str,
    provider: str,
    scope: str,
    path: Path,
    hash_: str | None = None,
    has_manifest: bool = False,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    info = link_info(path)
    payload: dict[str, Any] = {
        "name": name,
        "type": type_,
        "provider": provider,
        "scope": scope,
        "path": str(path),
        "isLink": info["isLink"],
        "linkTarget": info["linkTarget"],
        "linkType": info["linkType"],
        "hash": hash_,
        "hasManifest": has_manifest,
    }
    if extra:
        payload.update(extra)
    return payload


def scan_skill_dir(root_path: str, provider: str, scope: str) -> list[dict[str, Any]]:
    root = resolve_path(root_path)
    if not root.is_dir():
        return []
    results: list[dict[str, Any]] = []
    for child in sorted((item for item in root.iterdir() if item.is_dir() or item.is_symlink()), key=lambda p: p.name.lower()):
        skill_md = child / "SKILL.md"
        plugin_json = child / ".claude-plugin" / "plugin.json"
        type_ = "skill-plugin" if plugin_json.is_file() else "skill"
        results.append(
            entry(
                name=child.name,
                type_=type_,
                provider=provider,
                scope=scope,
                path=child,
                hash_=file_hash(skill_md),
                has_manifest=plugin_json.is_file(),
            )
        )
    return results


def scan_command_dir(root_path: str, provider: str, scope: str) -> list[dict[str, Any]]:
    root = resolve_path(root_path)
    if not root.is_dir():
        return []
    return [
        entry(
            name=child.stem,
            type_="command",
            provider=provider,
            scope=scope,
            path=child,
            hash_=file_hash(child),
        )
        for child in sorted(root.glob("*.md"), key=lambda p: p.name.lower())
    ]


def scan_plugin_cache(cache_path: str, provider: str) -> list[dict[str, Any]]:
    cache = resolve_path(cache_path)
    if not cache.is_dir():
        return []
    provider_manifest = {
        "codex": ".codex-plugin/plugin.json",
        "claude-code": ".claude-plugin/plugin.json",
    }.get(provider, "plugin.json")
    results: list[dict[str, Any]] = []
    for marketplace_dir in sorted((p for p in cache.iterdir() if p.is_dir()), key=lambda p: p.name.lower()):
        for plugin_dir in sorted((p for p in marketplace_dir.iterdir() if p.is_dir()), key=lambda p: p.name.lower()):
            for version_dir in sorted((p for p in plugin_dir.iterdir() if p.is_dir()), key=lambda p: p.name.lower()):
                manifest = next(
                    (
                        candidate
                        for candidate in [
                            version_dir / provider_manifest,
                            version_dir / "plugin.json",
                            version_dir / "SKILL.md",
                        ]
                        if candidate.is_file()
                    ),
                    None,
                )
                results.append(
                    entry(
                        name=plugin_dir.name,
                        type_="cached-plugin",
                        provider=provider,
                        scope="cache",
                        path=version_dir,
                        hash_=file_hash(manifest) if manifest else None,
                        has_manifest=manifest is not None,
                        extra={"version": version_dir.name, "marketplace": marketplace_dir.name},
                    )
                )
    return results


def scan_managed_plugins(root_path: str, provider: str) -> list[dict[str, Any]]:
    root = resolve_path(root_path)
    if not root.is_dir():
        return []
    results = []
    for plugin in sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: p.name.lower()):
        manifest = plugin / "kimi.plugin.json"
        metadata = {}
        if manifest.is_file():
            try:
                data = json.loads(manifest.read_text(encoding="utf-8-sig"))
                if isinstance(data, dict):
                    metadata = data
            except (OSError, ValueError):
                pass
        results.append(entry(
            name=metadata.get("name", plugin.name), type_="managed-plugin", provider=provider,
            scope="user", path=plugin, hash_=file_hash(manifest), has_manifest=manifest.is_file(),
            extra={"version": metadata.get("version", ""), "marketplace": ""},
        ))
    return results


def scan_marketplace(path_text: str) -> list[dict[str, Any]]:
    path = resolve_path(path_text)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [
            entry(
                name="marketplace.json",
                type_="invalid-marketplace",
                provider="marketplace",
                scope="user",
                path=path,
                extra={"error": str(exc)},
            )
        ]
    results = []
    for plugin in data.get("plugins", []):
        results.append(
            entry(
                name=plugin.get("name", "<unnamed>"),
                type_="marketplace-entry",
                provider="marketplace",
                scope="user",
                path=path,
                has_manifest=True,
                extra={"entryData": plugin, "linkTarget": plugin.get("path")},
            )
        )
    return results


def build_inventory(additional_roots: list[str] | None = None) -> dict[str, Any]:
    inventory: list[dict[str, Any]] = []
    for path, provider, scope, type_ in SCAN_TARGETS:
        if type_ == "commands":
            inventory.extend(scan_command_dir(path, provider, scope))
        else:
            inventory.extend(scan_skill_dir(path, provider, scope))
    for path, provider in CACHE_TARGETS:
        inventory.extend(scan_plugin_cache(path, provider))
    for path, provider in MANAGED_TARGETS:
        inventory.extend(scan_managed_plugins(path, provider))
    for path in MARKETPLACE_TARGETS:
        inventory.extend(scan_marketplace(path))
    for root in additional_roots or []:
        inventory.extend(scan_skill_dir(root, "additional", "custom"))

    summary: dict[str, Any] = {
        "timestamp": now_iso(),
        "totalItems": len(inventory),
        "byProvider": {},
        "byType": {},
        "byScope": {},
        "issues": {"brokenLinks": [], "duplicates": []},
    }
    for item in inventory:
        for key, bucket in [("provider", "byProvider"), ("type", "byType"), ("scope", "byScope")]:
            value = item[key]
            summary[bucket][value] = summary[bucket].get(value, 0) + 1
        if item["isLink"] and item["linkTarget"] and not resolve_path(item["linkTarget"]).exists():
            summary["issues"]["brokenLinks"].append(item["path"])

    by_name: dict[str, list[dict[str, Any]]] = {}
    for item in inventory:
        by_name.setdefault(item["name"], []).append(item)
    for name, items in sorted(by_name.items()):
        if len(items) <= 1:
            continue
        hashes = sorted({item["hash"] for item in items if item.get("hash")})
        summary["issues"]["duplicates"].append(
            {
                "name": name,
                "count": len(items),
                "locations": [item["path"] for item in items],
                "isConflict": len(hashes) > 1,
            }
        )
    return {"summary": summary, "inventory": inventory}


def inventory_command(args: argparse.Namespace) -> int:
    if args.dry_run:
        payload = {
            "skillDirs": [str(resolve_path(path)) for path, _, _, type_ in SCAN_TARGETS if type_ != "commands"],
            "commandDirs": [str(resolve_path(path)) for path, _, _, type_ in SCAN_TARGETS if type_ == "commands"],
            "cacheDirs": [str(resolve_path(path)) for path, _ in CACHE_TARGETS],
            "managedDirs": [str(resolve_path(path)) for path, _ in MANAGED_TARGETS],
            "marketplaces": [str(resolve_path(path)) for path in MARKETPLACE_TARGETS],
            "additionalRoots": args.additional_root,
        }
    else:
        payload = build_inventory(args.additional_root)
    if args.output_format == "json":
        as_json(payload)
    else:
        print_inventory_table(payload)
    return 0


def load_inventory(path_text: str | None) -> list[dict[str, Any]]:
    if path_text:
        data = read_json(Path(path_text))
    else:
        data = build_inventory()
    return list(data.get("inventory", []))


def validate_skill_manifest(skill_md: Path) -> list[str]:
    if not skill_md.is_file():
        return ["SKILL.md not found"]
    text = skill_md.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---"):
        return ["No YAML frontmatter found"]
    frontmatter = text.split("---", 2)[1] if text.count("---") >= 2 else ""
    return [] if "description:" in frontmatter else ["Missing recommended 'description' field in frontmatter"]


def validate_command(args: argparse.Namespace) -> int:
    results = []
    roots = approved_roots()
    for item in load_inventory(args.inventory_json):
        issues: list[str] = []
        path = resolve_path(item["path"])
        status = "valid"
        if not path.exists() and not path.is_symlink():
            issues.append("Path does not exist")
            status = "missing"
        if item.get("isLink") and item.get("linkTarget") and not resolve_path(item["linkTarget"]).exists():
            issues.append(f"Symlink target does not exist: {item['linkTarget']}")
            status = "broken-link"
        if item.get("scope") == "user" and not path_in_roots(path, roots):
            issues.append("Path outside approved roots")
            status = "out-of-bounds"
        if item.get("type") in {"skill", "skill-plugin"}:
            issues.extend(validate_skill_manifest(path / "SKILL.md"))
        if issues and status == "valid":
            status = "warning"
        results.append(
            {
                "name": item["name"],
                "path": item["path"],
                "type": item["type"],
                "provider": item["provider"],
                "issues": issues,
                "status": status,
            }
        )
    summary = {
        "timestamp": now_iso(),
        "total": len(results),
        "valid": sum(1 for item in results if item["status"] == "valid"),
        "warnings": sum(1 for item in results if item["status"] == "warning"),
        "errors": sum(1 for item in results if item["status"] not in {"valid", "warning"}),
        "byStatus": {},
    }
    for item in results:
        summary["byStatus"][item["status"]] = summary["byStatus"].get(item["status"], 0) + 1
    payload = {"summary": summary, "results": results}
    if args.output_format == "json":
        as_json(payload)
    else:
        print_validation_table(payload)
    return 0


def priority(item: dict[str, Any]) -> int:
    return SCOPE_PRIORITY.get(item.get("scope"), 99) * 10 + PROVIDER_PRIORITY.get(item.get("provider"), 99)


def plan_from_inventory(inventory: list[dict[str, Any]]) -> dict[str, Any]:
    # Copies are compared only within one scope. A personal copy and a project
    # copy of the same name are not duplicates of each other: each serves its
    # own scope, so neither may be removed because the other exists.
    by_name: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in inventory:
        by_name.setdefault((item["name"], str(item.get("scope") or "")), []).append(item)
    # Entries that resolve to the same place (a link and its target, a path
    # through a linked parent folder, or a project root that is the user root
    # because the helper runs from home) are one copy: removing either deletes both.
    physical = {id(item): physical_path(str(item["path"])) for item in inventory}

    def shares_copy(item: dict[str, Any]) -> bool | None:
        mine = physical[id(item)]
        if mine is None:
            return None
        return any(
            other is not item and physical[id(other)] is not None and paths_overlap(mine, physical[id(other)] or "")
            for other in inventory
        )

    plan = []
    plan_id = 0
    for _, items in sorted(by_name.items()):
        if len(items) <= 1:
            continue
        hashes = sorted({item["hash"] for item in items if item.get("hash")})
        if len(hashes) > 1:
            for item in items:
                plan_id += 1
                plan.append(plan_entry(plan_id, item, "conflict", "SKIP (conflict - different content)", "n/a"))
            continue
        # A copy without a content hash cannot be shown identical to the others,
        # so it is never canonical and never removed.
        unhashed: list[dict[str, Any]] = []
        comparable: list[dict[str, Any]] = []
        for item in items:
            (comparable if item.get("hash") or item.get("isLink") else unhashed).append(item)
        sorted_items = sorted(comparable, key=priority)
        for item in unhashed:
            plan_id += 1
            plan.append(plan_entry(plan_id, item, "unknown", "SKIP (no content hash to compare)", "n/a"))
        if not sorted_items:
            continue
        canonical = sorted_items[0]
        plan_id += 1
        plan.append(plan_entry(plan_id, canonical, "provider-link" if canonical.get("isLink") else "canonical", "KEEP (canonical)", "none"))
        for item in sorted_items[1:]:
            plan_id += 1
            shared = None if item.get("isLink") else shares_copy(item)
            if item.get("isLink"):
                plan.append(plan_entry(plan_id, item, "provider-link", "KEEP (provider link)", "none"))
            elif shared is None:
                plan.append(plan_entry(plan_id, item, "unknown", "SKIP (cannot resolve the physical path)", "n/a"))
            elif shared:
                plan.append(plan_entry(plan_id, item, "canonical", "KEEP (same physical copy)", "none"))
            elif item.get("type") == "cached-plugin":
                plan.append(plan_entry(plan_id, item, "stale-cache", "remove (rebuildable)", "low"))
            else:
                plan.append(plan_entry(plan_id, item, "duplicate-copy", "quarantine+remove", "low"))
    summary = {
        "timestamp": now_iso(),
        "totalEntries": len(plan),
        "duplicateGroups": len([items for items in by_name.values() if len(items) > 1]),
        "actions": {
            "keep": sum(1 for item in plan if item["action"].startswith("KEEP")),
            "quarantineRemove": sum(1 for item in plan if item["action"] == "quarantine+remove"),
            "removeRebuildable": sum(1 for item in plan if item["action"] == "remove (rebuildable)"),
            "skipConflict": sum(1 for item in plan if item["action"].startswith("SKIP")),
        },
        "isDryRun": True,
    }
    return {"summary": summary, "plan": plan}


def plan_entry(plan_id: int, item: dict[str, Any], category: str, action: str, risk: str) -> dict[str, Any]:
    return {
        "id": plan_id,
        "name": item["name"],
        "category": category,
        "path": item["path"],
        "provider": item["provider"],
        "scope": item["scope"],
        "hash": item.get("hash"),
        "action": action,
        "risk": risk,
        "isLink": item.get("isLink", False),
    }


def plan_command(args: argparse.Namespace) -> int:
    payload = plan_from_inventory(load_inventory(args.inventory_json))
    if args.output_format == "json":
        as_json(payload)
    else:
        print_plan_table(payload)
    return 0


def load_plan(path_text: str) -> list[dict[str, Any]]:
    return list(read_json(Path(path_text)).get("plan", []))


def removal_conflict(item: dict[str, Any], plan: list[dict[str, Any]]) -> str | None:
    """Why removing a plan entry could lose data, or None for a safe duplicate.

    Re-checked at apply time because the plan may be stale or edited: the
    canonical copy must be in the entry's own scope and still exist, the entry
    must not be the same physical copy as anything the plan keeps, and a
    duplicate-copy must match the canonical file for file (the plan only
    compared SKILL.md or plugin.json).
    """
    canonical = next(
        (
            entry
            for entry in plan
            if entry.get("name") == item["name"]
            and entry.get("scope") == item.get("scope")
            and entry.get("action") == "KEEP (canonical)"
        ),
        None,
    )
    if canonical is None:
        return "No KEEP (canonical) entry for this name in the same scope"
    canonical_path = Path(str(canonical["path"])).expanduser()
    if not canonical_path.exists():
        return f"Canonical copy is missing: {canonical['path']}"
    mine = physical_path(str(item["path"]))
    if mine is None:
        return f"Cannot resolve the physical path of {item['path']}"
    for kept in plan:
        if not str(kept.get("action", "")).startswith("KEEP"):
            continue
        theirs = physical_path(str(kept["path"]))
        if theirs is not None and paths_overlap(mine, theirs):
            return f"Same physical copy as kept entry {kept['path']}"
    if item.get("action") == "quarantine+remove":
        digest = tree_digest(Path(str(item["path"])).expanduser())
        if digest is None or digest != tree_digest(canonical_path):
            return f"Content differs from the canonical copy {canonical['path']}"
    return None


def apply_command(args: argparse.Namespace) -> int:
    plan = load_plan(args.plan_json)
    removals = [item for item in plan if item["action"] in {"quarantine+remove", "remove (rebuildable)"}]
    roots = approved_roots()
    quarantine_base = resolve_path(args.quarantine_root)
    manifest_path = quarantine_base / "quarantine-manifest.json"
    manifest = read_manifest(manifest_path)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    results = []
    for item in removals:
        raw_path = Path(item["path"]).expanduser().absolute()
        item_path = resolve_path(item["path"])
        result = {"name": item["name"], "path": str(item_path), "status": "pending", "error": None}
        if not path_strictly_in_roots(item_path, roots):
            result.update(status="BLOCKED", error=f"Path outside approved roots: {item_path}")
        elif is_link_or_junction(raw_path):
            # resolve() follows links, so removing "the item" would delete the link target.
            result.update(status="BLOCKED", error=f"Refusing to remove a symlink or junction: {raw_path}")
        elif not item_path.exists() and not item_path.is_symlink():
            result.update(status="skipped", error="Path does not exist")
        elif (conflict := removal_conflict(item, plan)) is not None:
            result.update(status="BLOCKED", error=conflict)
        elif args.dry_run:
            result["status"] = "dry-run"
        else:
            try:
                quarantine_base.mkdir(parents=True, exist_ok=True)
                # Copies of one name share the timestamp; give each its own folder.
                dest = unique_path(quarantine_base, f"{timestamp}_{item['name']}")
                is_dir = item_path.is_dir() and not item_path.is_symlink()
                if is_dir:
                    shutil.copytree(item_path, dest)
                else:
                    shutil.copy2(item_path, dest)
                # Record the copy before deleting anything, so a removal that
                # fails half way still leaves a restorable manifest entry.
                manifest.append(
                    {
                        "name": item["name"],
                        "originalPath": str(item_path),
                        "quarantinePath": str(dest),
                        "hash": item.get("hash"),
                        "category": item["category"],
                        "timestamp": timestamp,
                        "reason": f"Dedupe: {item['action']}",
                    }
                )
                if is_dir:
                    shutil.rmtree(item_path)
                else:
                    item_path.unlink()
                result["status"] = "removed"
            except Exception as exc:
                result.update(status="error", error=str(exc))
        results.append(result)
    if manifest and not args.dry_run:
        quarantine_base.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    as_json(
        {
            "timestamp": now_iso(),
            "isDryRun": bool(args.dry_run),
            "results": results,
            "summary": {
                "removed": sum(1 for item in results if item["status"] == "removed"),
                "blocked": sum(1 for item in results if item["status"] == "BLOCKED"),
                "skipped": sum(1 for item in results if item["status"] == "skipped"),
                "errors": sum(1 for item in results if item["status"] == "error"),
            },
        }
    )
    return 0


def quarantine_command(args: argparse.Namespace) -> int:
    base = resolve_path(args.quarantine_root)
    manifest_path = base / "quarantine-manifest.json"
    manifest = read_manifest(manifest_path)
    if args.action == "list":
        payload = {"total": len(manifest), "entries": manifest}
    else:
        if not args.name:
            raise SystemExit(f"--name is required for quarantine {args.action}")
        matches = [item for item in manifest if item.get("name") == args.name]
        if not matches:
            raise SystemExit(f"No quarantined item named {args.name!r}")
        item = matches[0]
        quarantine_path = resolve_path(item["quarantinePath"])
        original_path = resolve_path(item["originalPath"])
        if args.action == "restore":
            if original_path.exists():
                raise SystemExit(f"Original path already exists: {original_path}")
            if quarantine_path.is_dir():
                shutil.copytree(quarantine_path, original_path)
                shutil.rmtree(quarantine_path)
            else:
                original_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(quarantine_path, original_path)
                quarantine_path.unlink()
            message = f"Restored {args.name} to {original_path}"
        else:
            if quarantine_path.is_dir():
                shutil.rmtree(quarantine_path)
            elif quarantine_path.exists():
                quarantine_path.unlink()
            message = f"Purged {args.name} from quarantine"
        manifest = [entry for entry in manifest if entry is not item]
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        payload = {"message": message}
    if args.output_format == "json":
        as_json(payload)
    else:
        print(payload.get("message", f"Total: {payload.get('total', 0)}"))
    return 0


def print_inventory_table(payload: dict[str, Any]) -> None:
    summary = payload.get("summary", {})
    print("=== Customization Inventory ===")
    print(f"Total items: {summary.get('totalItems', 0)}")
    for provider, count in summary.get("byProvider", {}).items():
        print(f"  {provider}: {count}")


def print_validation_table(payload: dict[str, Any]) -> None:
    summary = payload["summary"]
    print(f"Total: {summary['total']} | Valid: {summary['valid']} | Warnings: {summary['warnings']} | Errors: {summary['errors']}")
    for item in payload["results"]:
        if item["status"] != "valid":
            print(f"[{item['status']}] {item['name']} ({item['provider']})")
            for issue in item["issues"]:
                print(f"  - {issue}")


def print_plan_table(payload: dict[str, Any]) -> None:
    summary = payload["summary"]
    print("=== Deduplication Plan (DRY RUN) ===")
    print(f"Duplicate groups: {summary['duplicateGroups']}")
    for item in payload["plan"]:
        print(f"{item['id']:>3} {item['name']:<24} {item['category']:<16} {item['action']:<30} {item['path']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Cross-platform customization-control helper")
    sub = parser.add_subparsers(dest="command", required=True)

    inventory = sub.add_parser("inventory")
    inventory.add_argument("--output-format", choices=["json", "table"], default="json")
    inventory.add_argument("--dry-run", action="store_true")
    inventory.add_argument("--additional-root", action="append", default=[])
    inventory.set_defaults(func=inventory_command)

    validate = sub.add_parser("validate")
    validate.add_argument("--inventory-json", default="")
    validate.add_argument("--output-format", choices=["json", "table"], default="json")
    validate.set_defaults(func=validate_command)

    plan = sub.add_parser("plan-dedupe")
    plan.add_argument("--inventory-json", default="")
    plan.add_argument("--output-format", choices=["json", "table"], default="json")
    plan.set_defaults(func=plan_command)

    apply = sub.add_parser("apply-dedupe")
    apply.add_argument("plan_json")
    apply.add_argument("--quarantine-root", default=".customization-control/quarantine")
    apply.add_argument("--dry-run", action="store_true")
    apply.set_defaults(func=apply_command)

    quarantine = sub.add_parser("quarantine")
    quarantine.add_argument("action", choices=["list", "restore", "purge"], nargs="?", default="list")
    quarantine.add_argument("--name", default="")
    quarantine.add_argument("--quarantine-root", default=".customization-control/quarantine")
    quarantine.add_argument("--output-format", choices=["json", "table"], default="json")
    quarantine.set_defaults(func=quarantine_command)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
