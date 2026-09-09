from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("cc_inventory", ROOT / "scripts/customization_control.py")
assert SPEC and SPEC.loader
HELPER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HELPER)


class InventoryLayoutsTests(unittest.TestCase):
    def test_versioned_caches_and_kimi_managed_plugins(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            for provider in ("codex", "claude"):
                for version in ("1.0.0", "1.1.0"):
                    manifest = home / f".{provider}/plugins/cache/market/demo/{version}/.{provider}-plugin/plugin.json"
                    manifest.parent.mkdir(parents=True)
                    manifest.write_text(json.dumps({"name": "demo", "version": version}), encoding="utf-8")
                    other = "claude" if provider == "codex" else "codex"
                    stale = manifest.parent.parent / f".{other}-plugin/plugin.json"
                    stale.parent.mkdir()
                    stale.write_text('{"name":"wrong-provider","version":"0.0.1"}', encoding="utf-8")
                    (manifest.parent.parent / "plugin.json").write_text('{"name":"legacy"}', encoding="utf-8")
            kimi_manifest = home / ".kimi-code/plugins/managed/demo/kimi.plugin.json"
            kimi_manifest.parent.mkdir(parents=True)
            kimi_manifest.write_text('{"name":"demo","version":"1.1.0"}', encoding="utf-8")
            stale = kimi_manifest.parent / ".codex-plugin/plugin.json"
            stale.parent.mkdir()
            stale.write_text('{"name":"demo","version":"0.0.1"}', encoding="utf-8")

            with patch.object(HELPER, "SCAN_TARGETS", []), patch.object(HELPER, "MARKETPLACE_TARGETS", []), patch.object(
                HELPER, "CACHE_TARGETS", [(str(home / ".codex/plugins/cache"), "codex"),
                                          (str(home / ".claude/plugins/cache"), "claude-code")]
            ), patch.object(HELPER, "MANAGED_TARGETS", [(str(home / ".kimi-code/plugins/managed"), "kimi-code")]):
                python_inventory = HELPER.build_inventory()["inventory"]
            self.assertEqual(len(python_inventory), 5)
            self.assertTrue(all(item["hash"] and item["hasManifest"] for item in python_inventory))
            self.assertTrue(all(item["name"] == "demo" for item in python_inventory))
            self.assertEqual(next(item["version"] for item in python_inventory if item["provider"] == "kimi-code"), "1.1.0")

            powershell = shutil.which("pwsh") or shutil.which("powershell")
            if powershell is None:
                return
            result = subprocess.run(
                [powershell, "-NoProfile", "-File", str(ROOT / "scripts/inventory.ps1"), "-OutputFormat", "json"],
                cwd=home, env={**os.environ, "USERPROFILE": str(home)},
                capture_output=True, text=True, check=True,
            )
            ps_inventory = json.loads(result.stdout)["inventory"]
            fields = ("provider", "name", "version", "path", "hasManifest", "hash")
            project = lambda rows: sorted(tuple(item[field] for field in fields) for item in rows)
            self.assertEqual(project(ps_inventory), project(python_inventory))

    def test_documented_helper_paths_resolve_in_a_versioned_install(self) -> None:
        for name in ("customization-audit", "customization-dedupe"):
            skill = ROOT / "skills" / name / "SKILL.md"
            self.assertNotIn("../../../scripts", skill.read_text(encoding="utf-8"))
            self.assertTrue((skill.parent / "../../scripts/customization_control.py").is_file())
