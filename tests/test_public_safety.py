from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
PRIVATE_USER = "Juli" + "us"
PRIVATE_PATH = "C:\\Users\\" + PRIVATE_USER


class PublicSafetyTests(unittest.TestCase):
    def test_tracked_files_exclude_local_handoffs_and_personal_paths(self) -> None:
        tracked = subprocess.run(
            ["git", "ls-files"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()

        self.assertFalse(any(path.startswith(".handoff/") for path in tracked))
        for relative in tracked:
            path = ROOT / relative
            if not path.is_file():
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            self.assertNotIn(PRIVATE_PATH, content)
            self.assertNotIn(PRIVATE_USER, content)

    def test_audit_skill_defers_pure_skill_layer_requests(self) -> None:
        skill = (ROOT / "skills" / "customization-audit" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Boundary: if the request is ONLY about skills", skill)
        self.assertIn("Do not use when the task is purely skill-layer work", skill)
        self.assertIn("skill-doctor", skill)
