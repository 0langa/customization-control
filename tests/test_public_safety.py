from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
PRIVATE_USER = "Juli" + "us"
PRIVATE_PATH = "C:\\Users\\" + PRIVATE_USER


def test_tracked_files_exclude_local_handoffs_and_personal_paths() -> None:
    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()

    assert not any(path.startswith(".handoff/") for path in tracked)
    for relative in tracked:
        path = ROOT / relative
        if not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        assert PRIVATE_PATH not in content
        assert PRIVATE_USER not in content
