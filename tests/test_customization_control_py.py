from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "customization_control.py"


class CustomizationControlPyTests(unittest.TestCase):
    def run_helper(self, *args: str, cwd: Path | None = None) -> dict:
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=cwd or ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        return json.loads(completed.stdout)

    def test_inventory_dry_run_expands_home_paths(self) -> None:
        payload = self.run_helper("inventory", "--dry-run")
        self.assertIn("skillDirs", payload)
        self.assertTrue(payload["skillDirs"])
        self.assertFalse(any("~" in path for path in payload["skillDirs"]))

    def test_plan_dedupe_classifies_identical_and_conflicting_skills(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            loc1 = root / "loc1" / "cc-test-cross-platform-skill"
            loc2 = root / "loc2" / "cc-test-cross-platform-skill"
            loc3 = root / "loc3" / "cc-test-cross-platform-skill"
            for path in (loc1, loc2, loc3):
                path.mkdir(parents=True)
            (loc1 / "SKILL.md").write_text("---\ndescription: same\n---\n# Test\n", encoding="utf-8")
            (loc2 / "SKILL.md").write_text("---\ndescription: same\n---\n# Test\n", encoding="utf-8")
            (loc3 / "SKILL.md").write_text("---\ndescription: different\n---\n# Test\n", encoding="utf-8")

            inventory = self.run_helper(
                "inventory",
                "--additional-root",
                str(root / "loc1"),
                "--additional-root",
                str(root / "loc2"),
            )
            inv_path = root / "inventory.json"
            inv_path.write_text(json.dumps(inventory), encoding="utf-8")
            plan = self.run_helper("plan-dedupe", "--inventory-json", str(inv_path))
            categories = {
                entry["category"]
                for entry in plan["plan"]
                if entry["name"] == "cc-test-cross-platform-skill"
            }
            self.assertIn("canonical", categories)
            self.assertIn("duplicate-copy", categories)

            conflict_inventory = self.run_helper(
                "inventory",
                "--additional-root",
                str(root / "loc1"),
                "--additional-root",
                str(root / "loc3"),
            )
            conflict_path = root / "conflict.json"
            conflict_path.write_text(json.dumps(conflict_inventory), encoding="utf-8")
            conflict_plan = self.run_helper("plan-dedupe", "--inventory-json", str(conflict_path))
            self.assertEqual(
                {
                    entry["category"]
                    for entry in conflict_plan["plan"]
                    if entry["name"] == "cc-test-cross-platform-skill"
                },
                {"conflict"},
            )

    def test_apply_dedupe_blocks_paths_outside_approved_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            doomed = root / "duplicate-skill"
            doomed.mkdir()
            (doomed / "SKILL.md").write_text("---\ndescription: test\n---\n# Test\n", encoding="utf-8")
            plan = {
                "plan": [
                    {
                        "id": 1,
                        "name": "duplicate-skill",
                        "category": "duplicate-copy",
                        "path": str(doomed),
                        "provider": "additional",
                        "scope": "custom",
                        "hash": None,
                        "action": "quarantine+remove",
                        "risk": "low",
                        "isLink": False,
                    }
                ]
            }
            plan_path = root / "plan.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            result = self.run_helper("apply-dedupe", str(plan_path), "--quarantine-root", str(root / "q"))
            self.assertEqual(result["summary"]["blocked"], 1)
            self.assertTrue(doomed.exists())


if __name__ == "__main__":
    unittest.main()
