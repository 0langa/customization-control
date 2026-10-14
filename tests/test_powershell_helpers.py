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
                self.dedupe_round_trip(exe)

    def test_windows_powershell_ignores_powershell_7_module_paths(self) -> None:
        # Started from PowerShell 7 through cmd, bash or an agent (pwsh resets the
        # path only for a powershell.exe it starts itself), Windows PowerShell 5.1
        # inherits PowerShell 7's module folders. Autoload then loads PowerShell 7's
        # core modules, Get-FileHash goes missing, inventory fails and apply blocks.
        windows_powershell = shutil.which("powershell") if os.name == "nt" else None
        if not windows_powershell:
            self.skipTest("Windows PowerShell 5.1 is not installed")
        module_path = powershell7_module_path()
        if not module_path:
            self.skipTest("PowerShell 7 is not installed")
        self.dedupe_round_trip(windows_powershell, module_path=module_path)

    def dedupe_round_trip(self, exe: str, module_path: str | None = None) -> None:
        home, project, env = self.make_home()
        if module_path is not None:
            env = with_module_path(env, module_path)
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

    def test_dedupe_never_removes_a_copy_in_another_scope(self) -> None:
        for exe in POWERSHELLS:
            with self.subTest(powershell=exe):
                home, project, env = self.make_home()
                kept, duplicate = cross_scope_copies(self, home, project)
                plan, _ = self.ps_dedupe(exe, home, project, env)
                assert_cross_scope_dedupe(self, plan, kept, duplicate)

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

    def test_dedupe_never_removes_a_copy_in_another_scope(self) -> None:
        home, project, env = self.make_home()
        kept, duplicate = cross_scope_copies(self, home, project)
        plan = self.py_dedupe(home, project, env)
        assert_cross_scope_dedupe(self, plan, kept, duplicate)

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


class ModulePathGuardTests(SandboxMixin, unittest.TestCase):
    """Each helper first drops PowerShell 7's module folders under Windows PowerShell."""

    POWERSHELL_7_FOLDERS = [
        r"C:\Users\me\Documents\PowerShell\Modules",
        r"C:\Program Files\PowerShell\Modules",
        r"C:\Program Files\PowerShell\7\Modules",
        r"C:\Program Files\WindowsApps\Microsoft.PowerShell_7.6.6.0_x64__8wekyb3d8bbwe\Modules",
    ]
    OTHER_FOLDERS = [
        r"C:\Users\me\Documents\WindowsPowerShell\Modules",
        r"C:\Program Files\WindowsPowerShell\Modules",
        r"C:\Windows\system32\WindowsPowerShell\v1.0\Modules",
        r"D:\Modules",
    ]

    def test_every_helper_runs_the_same_guard_first(self) -> None:
        # First thing after the param block, before any cmdlet can autoload a module.
        guard = module_path_guard(SCRIPTS / "inventory.ps1")
        self.assertIn("$PSVersionTable.PSEdition -eq 'Desktop'", guard)
        for script in sorted(SCRIPTS.glob("*.ps1")):
            with self.subTest(script=script.name):
                self.assertEqual(module_path_guard(script), guard)

    def test_guard_drops_only_powershell_7_folders_and_only_under_windows_powershell(self) -> None:
        if not POWERSHELLS:
            self.skipTest("PowerShell is not installed")
        home, _, env = self.make_home()
        script = home / "guard.ps1"
        script.write_text(
            "$PSVersionTable.PSEdition\n$env:PSModulePath\n"
            + module_path_guard(SCRIPTS / "inventory.ps1")
            + "$env:PSModulePath\n",
            encoding="ascii",
        )
        folders = [folder for pair in zip(self.POWERSHELL_7_FOLDERS, self.OTHER_FOLDERS) for folder in pair]
        env = with_module_path(env, ";".join(folders))
        for exe in POWERSHELLS:
            with self.subTest(powershell=exe):
                completed = subprocess.run(
                    [exe, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                    env=env, capture_output=True, text=True, timeout=120,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                edition, before, after = completed.stdout.splitlines()
                before, after = before.split(";"), after.split(";")
                self.assertEqual(set(folders) - set(before), set(), before)
                if edition == "Desktop":
                    self.assertEqual(after, [folder for folder in before if folder not in self.POWERSHELL_7_FOLDERS])
                else:
                    self.assertEqual(after, before)


def powershell7_module_path() -> str:
    """PSModulePath inside PowerShell 7, as the programs it starts inherit it."""
    pwsh = shutil.which("pwsh")
    if not pwsh:
        return ""
    completed = subprocess.run(
        [pwsh, "-NoProfile", "-NonInteractive", "-Command", "$env:PSModulePath"],
        capture_output=True, text=True, timeout=120,
    )
    return completed.stdout.strip()


def with_module_path(env: dict[str, str], module_path: str) -> dict[str, str]:
    # os.environ upper-cases names on Windows: replace the variable rather than
    # adding a second spelling of it that the child may or may not see.
    env = {key: value for key, value in env.items() if key.upper() != "PSMODULEPATH"}
    env["PSModulePath"] = module_path
    return env


def module_path_guard(script: Path) -> str:
    """The block right after a helper's param block, through its closing brace."""
    text = script.read_text(encoding="ascii")
    start = text.index("\n)\n\n") + len("\n)\n\n")
    return text[start:text.index("\n}\n", start) + len("\n}\n")]


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


def cross_scope_copies(case: SandboxMixin, home: Path, project: Path) -> tuple[list[Path], Path]:
    """One skill as a project copy and two identical personal copies.

    The project copy outranks the personal ones, but it serves a different
    scope: only the second personal copy duplicates one in its own scope.
    """
    kept = [case.add_skill(project, ".claude/skills/demo"), case.add_skill(home, ".claude/skills/demo")]
    return kept, case.add_skill(home, ".agents/skills/demo")


def assert_cross_scope_dedupe(case: unittest.TestCase, plan: dict, kept: list[Path], duplicate: Path) -> None:
    case.assertEqual(plan["summary"]["actions"]["quarantineRemove"], 1, plan["plan"])
    canonical = [entry for entry in plan["plan"] if entry["action"] == "KEEP (canonical)"]
    case.assertEqual([(entry["scope"], entry["provider"]) for entry in canonical], [("user", "claude-code")], plan["plan"])
    case.assertFalse(any(entry["scope"] == "project" for entry in plan["plan"]), plan["plan"])
    for copy in kept:
        case.assertTrue((copy / "SKILL.md").is_file(), copy)
    case.assertFalse(duplicate.exists())


def stale_plan(case: SandboxMixin, home: Path) -> tuple[Path, list[Path]]:
    """A plan that is out of date or edited; apply must refuse every removal."""

    def entry(name: str, path: Path, action: str, scope: str = "user") -> dict:
        return {"id": 0, "name": name, "category": "x", "path": str(path), "provider": "legacy", "scope": scope,
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
    # An identical personal copy whose only canonical is a project copy: another scope.
    project_copy = case.add_skill(home, "project/.claude/skills/scoped")
    personal = case.add_skill(home, ".claude/skills/scoped")
    plan += [entry("scoped", project_copy, "KEEP (canonical)", scope="project"), entry("scoped", personal, "quarantine+remove")]
    survivors += [orphan / "SKILL.md", gone / "SKILL.md", edited / "scripts" / "a.py", personal / "SKILL.md"]
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

    # The Claude copy outranks the others in its scope but has no SKILL.md to hash.
    return {"inventory": [
        item("C:/home/.claude/skills/demo", "user", "claude-code", None),
        item("C:/home/.codex/skills/demo", "user", "codex", "A"),
        item("C:/home/.agents/skills/demo", "user", "legacy", "A"),
    ]}


def assert_hashless_plan(case: unittest.TestCase, plan: dict) -> None:
    by_path = {entry["path"]: entry for entry in plan["plan"]}
    case.assertEqual(by_path["C:/home/.claude/skills/demo"]["category"], "unknown")
    case.assertTrue(by_path["C:/home/.claude/skills/demo"]["action"].startswith("SKIP"))
    case.assertEqual(by_path["C:/home/.codex/skills/demo"]["category"], "canonical")
    case.assertEqual(by_path["C:/home/.agents/skills/demo"]["action"], "quarantine+remove")
    case.assertEqual(plan["summary"]["actions"]["quarantineRemove"], 1)


if __name__ == "__main__":
    unittest.main()
