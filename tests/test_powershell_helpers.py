"""End-to-end checks for the Windows PowerShell helpers and their Python twins.

Every scenario runs against a throwaway USERPROFILE/HOME, so no real provider
directory is read or changed. PowerShell cases run once per available host
(PowerShell 7 and Windows PowerShell 5.1) and are skipped when neither exists.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
POWERSHELLS = [exe for exe in (shutil.which("pwsh"), shutil.which("powershell")) if exe]
SKILL_TEXT = "---\ndescription: same\n---\n# Demo\n"


class SandboxMixin:
    def make_home(self) -> tuple[Path, Path, dict[str, str]]:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        home = Path(temporary.name)
        project = home / "project"
        project.mkdir()
        env = {**os.environ, "USERPROFILE": str(home), "HOME": str(home)}
        return home, project, env

    def add_skill(self, home: Path, relative: str, text: str = SKILL_TEXT) -> Path:
        skill = home / relative
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(text, encoding="utf-8")
        return skill


class PowerShellHelperTests(SandboxMixin, unittest.TestCase):
    def ps(self, exe: str, script: str, *args: str, cwd: Path, env: dict[str, str]) -> str:
        completed = subprocess.run(
            [exe, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPTS / script), *args],
            cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
        )
        self.assertEqual(completed.returncode, 0, f"{script} failed under {exe}:\n{completed.stderr}")
        return completed.stdout

    def ps_json(self, exe: str, script: str, *args: str, cwd: Path, env: dict[str, str]) -> dict:
        output = self.ps(exe, script, *args, cwd=cwd, env=env)
        # apply-dedupe prints a Write-Host banner before its JSON result.
        return json.loads(output[output.index("{"):])

    def setUp(self) -> None:
        if not POWERSHELLS:
            self.skipTest("PowerShell is not installed")

    def test_dedupe_round_trip_with_a_single_duplicate(self) -> None:
        for exe in POWERSHELLS:
            with self.subTest(powershell=exe):
                home, project, env = self.make_home()
                self.add_skill(home, ".claude/skills/demo")
                duplicate = self.add_skill(home, ".agents/skills/demo")

                inventory = self.ps(exe, "inventory.ps1", "-OutputFormat", "json", cwd=project, env=env)
                inventory_path = home / "inventory.json"
                inventory_path.write_text(inventory, encoding="utf-8")

                validation = self.ps_json(exe, "validate.ps1", "-InventoryJson", str(inventory_path), cwd=project, env=env)
                self.assertEqual(validation["summary"]["valid"], 2)
                self.assertEqual(validation["summary"]["byStatus"], {"valid": 2})

                plan = self.ps_json(exe, "plan-dedupe.ps1", "-InventoryJson", str(inventory_path), cwd=project, env=env)
                self.assertEqual(plan["summary"]["duplicateGroups"], 1)
                self.assertEqual(plan["summary"]["actions"]["keep"], 1)
                self.assertEqual(plan["summary"]["actions"]["quarantineRemove"], 1)
                plan_path = home / "plan.json"
                plan_path.write_text(json.dumps(plan), encoding="utf-8")

                quarantine = home / ".customization-control" / "quarantine"
                applied = self.ps_json(
                    exe, "apply-dedupe.ps1", "-PlanJson", str(plan_path), "-QuarantineRoot", str(quarantine), "-Force",
                    cwd=project, env=env,
                )
                self.assertEqual(applied["summary"], {"removed": 1, "blocked": 0, "skipped": 0, "errors": 0})
                self.assertFalse(duplicate.exists())
                self.assertTrue((home / ".claude/skills/demo/SKILL.md").is_file())

                manifest = json.loads((quarantine / "quarantine-manifest.json").read_text(encoding="utf-8-sig"))
                self.assertIsInstance(manifest, list)
                self.assertEqual(len(manifest), 1)

                listed = self.ps_json(exe, "quarantine.ps1", "-Action", "list", "-QuarantineRoot", str(quarantine), cwd=project, env=env)
                self.assertEqual(listed["total"], 1)

                self.ps(exe, "quarantine.ps1", "-Action", "restore", "-Name", "demo", "-QuarantineRoot", str(quarantine), cwd=project, env=env)
                self.assertTrue((duplicate / "SKILL.md").is_file())
                remaining = json.loads((quarantine / "quarantine-manifest.json").read_text(encoding="utf-8-sig"))
                self.assertEqual(remaining, [])

    def test_apply_blocks_sibling_prefixes_roots_and_links(self) -> None:
        for exe in POWERSHELLS:
            with self.subTest(powershell=exe):
                home, project, env = self.make_home()
                sibling = self.add_skill(home, ".claude-backup/skills/demo")
                target = self.add_skill(home, "elsewhere/demo")
                (home / ".agents/skills").mkdir(parents=True)
                junction = home / ".agents/skills/demo"
                made_link = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(target)], capture_output=True).returncode == 0
                entries = [sibling, home / ".claude"] + ([junction] if made_link else [])
                plan = {"plan": [
                    {"id": index, "name": "demo", "category": "duplicate-copy", "path": str(path), "provider": "legacy",
                     "scope": "user", "hash": "A", "action": "quarantine+remove", "risk": "low", "isLink": False}
                    for index, path in enumerate(entries, start=1)
                ]}
                (home / ".claude").mkdir(exist_ok=True)
                plan_path = home / "plan.json"
                plan_path.write_text(json.dumps(plan), encoding="utf-8")
                applied = self.ps_json(
                    exe, "apply-dedupe.ps1", "-PlanJson", str(plan_path), "-QuarantineRoot", str(home / "q"), "-Force",
                    cwd=project, env=env,
                )
                self.assertEqual(applied["summary"]["blocked"], len(entries))
                self.assertEqual(applied["summary"]["removed"], 0)
                self.assertTrue((sibling / "SKILL.md").is_file())
                self.assertTrue((target / "SKILL.md").is_file())

    def test_plan_never_removes_copies_without_a_content_hash(self) -> None:
        for exe in POWERSHELLS:
            with self.subTest(powershell=exe):
                home, project, env = self.make_home()
                inventory_path = home / "inventory.json"
                inventory_path.write_text(json.dumps(hashless_inventory()), encoding="utf-8")
                plan = self.ps_json(exe, "plan-dedupe.ps1", "-InventoryJson", str(inventory_path), cwd=project, env=env)
                assert_hashless_plan(self, plan)

    def ps_dedupe(self, exe: str, home: Path, cwd: Path, env: dict[str, str]) -> tuple[dict, str]:
        inventory_path = home / "inventory.json"
        inventory_path.write_text(self.ps(exe, "inventory.ps1", "-OutputFormat", "json", cwd=cwd, env=env), encoding="utf-8")
        plan = self.ps_json(exe, "plan-dedupe.ps1", "-InventoryJson", str(inventory_path), cwd=cwd, env=env)
        plan_path = home / "plan.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        applied = self.ps(exe, "apply-dedupe.ps1", "-PlanJson", str(plan_path), "-QuarantineRoot", str(home / "q"), "-Force", cwd=cwd, env=env)
        return plan, applied

    def test_dedupe_keeps_copies_that_are_one_physical_folder(self) -> None:
        for exe in POWERSHELLS:
            for name, setup in ALIAS_SCENARIOS.items():
                with self.subTest(powershell=exe, scenario=name):
                    home, project, env = self.make_home()
                    precious, cwd = setup(self, home, project)
                    plan, _ = self.ps_dedupe(exe, home, cwd, env)
                    self.assertEqual(plan["summary"]["actions"]["quarantineRemove"], 0, plan["plan"])
                    self.assertTrue(precious.is_file())

    def test_apply_rechecks_a_stale_plan_before_removing(self) -> None:
        for exe in POWERSHELLS:
            with self.subTest(powershell=exe):
                home, project, env = self.make_home()
                plan_path, survivors = stale_plan(self, home)
                applied = self.ps_json(
                    exe, "apply-dedupe.ps1", "-PlanJson", str(plan_path), "-QuarantineRoot", str(home / "q"), "-Force",
                    cwd=project, env=env,
                )
                assert_stale_plan_blocked(self, applied, survivors)

    def test_each_quarantined_copy_gets_its_own_folder(self) -> None:
        for exe in POWERSHELLS:
            with self.subTest(powershell=exe):
                home, project, env = self.make_home()
                copies = [self.add_skill(home, f"{root}/skills/demo") for root in (".claude", ".codex", ".agents")]
                plan, _ = self.ps_dedupe(exe, home, project, env)
                self.assertEqual(plan["summary"]["actions"]["quarantineRemove"], 2)
                quarantine = home / "q"
                for _ in range(2):
                    self.ps(exe, "quarantine.ps1", "-Action", "restore", "-Name", "demo", "-QuarantineRoot", str(quarantine), cwd=project, env=env)
                assert_restored_copies(self, copies)


class PythonHelperParityTests(SandboxMixin, unittest.TestCase):
    def run_helper(self, *args: str, env: dict[str, str], cwd: Path) -> dict:
        completed = subprocess.run(
            [sys.executable, str(SCRIPTS / "customization_control.py"), *args],
            cwd=cwd, env=env, capture_output=True, text=True, check=True, timeout=120,
        )
        return json.loads(completed.stdout)

    def test_plan_never_removes_copies_without_a_content_hash(self) -> None:
        home, project, env = self.make_home()
        inventory_path = home / "inventory.json"
        inventory_path.write_text(json.dumps(hashless_inventory()), encoding="utf-8")
        assert_hashless_plan(self, self.run_helper("plan-dedupe", "--inventory-json", str(inventory_path), env=env, cwd=project))

    def test_apply_blocks_sibling_prefixes_and_roots(self) -> None:
        home, project, env = self.make_home()
        sibling = self.add_skill(home, ".claude-backup/skills/demo")
        (home / ".claude").mkdir()
        plan = {"plan": [
            {"id": index, "name": "demo", "category": "duplicate-copy", "path": str(path), "provider": "legacy",
             "scope": "user", "hash": "A", "action": "quarantine+remove", "risk": "low", "isLink": False}
            for index, path in enumerate([sibling, home / ".claude"], start=1)
        ]}
        plan_path = home / "plan.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        result = self.run_helper("apply-dedupe", str(plan_path), "--quarantine-root", str(home / "q"), env=env, cwd=project)
        self.assertEqual(result["summary"]["blocked"], 2)
        self.assertTrue((sibling / "SKILL.md").is_file())
        self.assertTrue((home / ".claude").is_dir())

    def py_dedupe(self, home: Path, cwd: Path, env: dict[str, str]) -> dict:
        inventory_path = home / "inventory.json"
        inventory_path.write_text(json.dumps(self.run_helper("inventory", env=env, cwd=cwd)), encoding="utf-8")
        plan = self.run_helper("plan-dedupe", "--inventory-json", str(inventory_path), env=env, cwd=cwd)
        plan_path = home / "plan.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        self.run_helper("apply-dedupe", str(plan_path), "--quarantine-root", str(home / "q"), env=env, cwd=cwd)
        return plan

    def test_dedupe_keeps_copies_that_are_one_physical_folder(self) -> None:
        for name, setup in ALIAS_SCENARIOS.items():
            with self.subTest(scenario=name):
                home, project, env = self.make_home()
                precious, cwd = setup(self, home, project)
                plan = self.py_dedupe(home, cwd, env)
                self.assertEqual(plan["summary"]["actions"]["quarantineRemove"], 0, plan["plan"])
                self.assertTrue(precious.is_file())

    def test_apply_rechecks_a_stale_plan_before_removing(self) -> None:
        home, project, env = self.make_home()
        plan_path, survivors = stale_plan(self, home)
        applied = self.run_helper("apply-dedupe", str(plan_path), "--quarantine-root", str(home / "q"), env=env, cwd=project)
        assert_stale_plan_blocked(self, applied, survivors)

    def test_each_quarantined_copy_gets_its_own_folder(self) -> None:
        home, project, env = self.make_home()
        copies = [self.add_skill(home, f"{root}/skills/demo") for root in (".claude", ".codex", ".agents")]
        plan = self.py_dedupe(home, project, env)
        self.assertEqual(plan["summary"]["actions"]["quarantineRemove"], 2)
        for _ in range(2):
            self.run_helper("quarantine", "restore", "--name", "demo", "--quarantine-root", str(home / "q"), env=env, cwd=project)
        assert_restored_copies(self, copies)

    def test_junctions_are_detected_without_os_path_isjunction(self) -> None:
        # os.path.isjunction only exists on Python 3.12+.
        home, _, _ = self.make_home()
        target = self.add_skill(home, "elsewhere/demo")
        junction = home / "link"
        if not make_junction(junction, target):
            self.skipTest("cannot create a junction here")
        import importlib.util
        from unittest import mock

        spec = importlib.util.spec_from_file_location("customization_control_under_test", SCRIPTS / "customization_control.py")
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with mock.patch.object(module.os.path, "isjunction", None, create=True):
            self.assertTrue(module.is_link_or_junction(junction))
        self.assertFalse(module.is_link_or_junction(target))

    def test_quarantine_reads_bom_and_single_object_manifests(self) -> None:
        home, project, env = self.make_home()
        quarantine = home / "q"
        quarantine.mkdir()
        entry = {"name": "demo", "originalPath": str(home / "x"), "quarantinePath": str(quarantine / "x"), "timestamp": "1"}
        (quarantine / "quarantine-manifest.json").write_text(json.dumps(entry), encoding="utf-8-sig")
        listed = self.run_helper("quarantine", "list", "--quarantine-root", str(quarantine), env=env, cwd=project)
        self.assertEqual(listed["total"], 1)


class ScriptHygieneTests(unittest.TestCase):
    def test_powershell_scripts_are_ascii(self) -> None:
        # Windows PowerShell 5.1 reads BOM-less scripts as ANSI; an em dash
        # turns into a smart quote there and breaks string parsing.
        for script in sorted(SCRIPTS.glob("*.ps1")) + sorted((ROOT / "tests").glob("*.ps1")):
            with self.subTest(script=script.name):
                script.read_bytes().decode("ascii")

    def test_skills_do_not_run_shell_commands_at_load_time(self) -> None:
        # A failing `!` command aborts the whole skill invocation in Claude Code.
        for skill in sorted((ROOT / "skills").glob("*/SKILL.md")):
            with self.subTest(skill=skill.parent.name):
                text = skill.read_text(encoding="utf-8")
                self.assertIsNone(re.search(r"(^|\s)!`", text))
                self.assertNotIn("```!", text)


def make_junction(link: Path, target: Path) -> bool:
    if os.name != "nt":
        return False
    link.parent.mkdir(parents=True, exist_ok=True)
    return subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True).returncode == 0


def alias_link_to_real_copy(case: SandboxMixin, home: Path, project: Path) -> tuple[Path, Path]:
    # ~/.claude/skills/demo is a junction to the only real copy in ~/.agents.
    real = case.add_skill(home, ".agents/skills/demo")
    if not make_junction(home / ".claude/skills/demo", real):
        case.skipTest("cannot create a junction here")
    return real / "SKILL.md", project


def alias_linked_parent_folder(case: SandboxMixin, home: Path, project: Path) -> tuple[Path, Path]:
    # ~/.codex/skills as a whole is a junction to ~/.claude/skills.
    real = case.add_skill(home, ".claude/skills/demo")
    if not make_junction(home / ".codex/skills", home / ".claude/skills"):
        case.skipTest("cannot create a junction here")
    return real / "SKILL.md", project


def alias_run_from_home(case: SandboxMixin, home: Path, project: Path) -> tuple[Path, Path]:
    # From the home directory the project root .claude/skills is ~/.claude/skills.
    real = case.add_skill(home, ".claude/skills/demo")
    return real / "SKILL.md", home


ALIAS_SCENARIOS = {
    "link to the real copy": alias_link_to_real_copy,
    "linked parent folder": alias_linked_parent_folder,
    "run from home": alias_run_from_home,
}


def stale_plan(case: SandboxMixin, home: Path) -> tuple[Path, list[Path]]:
    """A plan that is out of date or edited; apply must refuse every removal."""

    def entry(name: str, path: Path, action: str) -> dict:
        return {"id": 0, "name": name, "category": "x", "path": str(path), "provider": "legacy", "scope": "user",
                "hash": "A", "action": action, "risk": "low", "isLink": False}

    plan = []
    survivors = []
    linked = case.add_skill(home, ".agents/skills/linked")
    if make_junction(home / ".claude/skills/linked", linked):
        # The canonical is a link to the copy the plan wants removed.
        plan += [entry("linked", home / ".claude/skills/linked", "KEEP (canonical)"),
                 entry("linked", linked, "quarantine+remove")]
        survivors.append(linked / "SKILL.md")
    orphan = case.add_skill(home, ".agents/skills/orphan")
    plan.append(entry("orphan", orphan, "quarantine+remove"))
    gone = case.add_skill(home, ".agents/skills/gone")
    plan += [entry("gone", home / ".claude/skills/gone", "KEEP (canonical)"), entry("gone", gone, "quarantine+remove")]
    # Same SKILL.md, but the copy to remove has its own edits to a script.
    canonical = case.add_skill(home, ".claude/skills/edited")
    edited = case.add_skill(home, ".agents/skills/edited")
    for folder, text in ((canonical, "print(1)\n"), (edited, "print(2)\n")):
        (folder / "scripts").mkdir()
        (folder / "scripts" / "a.py").write_text(text, encoding="utf-8")
    plan += [entry("edited", canonical, "KEEP (canonical)"), entry("edited", edited, "quarantine+remove")]
    survivors += [orphan / "SKILL.md", gone / "SKILL.md", edited / "scripts" / "a.py"]
    plan_path = home / "stale-plan.json"
    plan_path.write_text(json.dumps({"plan": plan}), encoding="utf-8")
    return plan_path, survivors


def assert_stale_plan_blocked(case: unittest.TestCase, applied: dict, survivors: list[Path]) -> None:
    case.assertEqual(applied["summary"]["removed"], 0, applied["results"])
    case.assertEqual(applied["summary"]["blocked"], len(survivors), applied["results"])
    for path in survivors:
        case.assertTrue(path.is_file(), path)


def assert_restored_copies(case: unittest.TestCase, copies: list[Path]) -> None:
    for copy in copies:
        case.assertEqual(sorted(child.name for child in copy.iterdir()), ["SKILL.md"], copy)


def hashless_inventory() -> dict:
    def item(path: str, scope: str, provider: str, hash_: str | None) -> dict:
        return {"name": "demo", "type": "skill", "provider": provider, "scope": scope, "path": path,
                "hash": hash_, "isLink": False, "linkTarget": None, "linkType": None, "hasManifest": False}

    # The project copy outranks the user copy but has no SKILL.md to hash.
    return {"inventory": [
        item("C:/project/.claude/skills/demo", "project", "claude-code", None),
        item("C:/home/.claude/skills/demo", "user", "claude-code", "A"),
        item("C:/home/.agents/skills/demo", "user", "legacy", "A"),
    ]}


def assert_hashless_plan(case: unittest.TestCase, plan: dict) -> None:
    by_path = {entry["path"]: entry for entry in plan["plan"]}
    case.assertEqual(by_path["C:/project/.claude/skills/demo"]["category"], "unknown")
    case.assertTrue(by_path["C:/project/.claude/skills/demo"]["action"].startswith("SKIP"))
    case.assertEqual(by_path["C:/home/.claude/skills/demo"]["category"], "canonical")
    case.assertEqual(by_path["C:/home/.agents/skills/demo"]["action"], "quarantine+remove")
    case.assertEqual(plan["summary"]["actions"]["quarantineRemove"], 1)


if __name__ == "__main__":
    unittest.main()
