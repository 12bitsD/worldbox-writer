"""Lock the sprint docs directory to an allow-list so obsolete files can't re-appear."""

from pathlib import Path

SPRINTS_DIR = Path(__file__).parent.parent.parent / "docs" / "sprints"


def test_sprints_directory_only_has_recent_files() -> None:
    expected = {
        "README.md",
        "SPRINT_25.md",
    }

    actual = {path.name for path in SPRINTS_DIR.iterdir() if path.is_file()}

    assert actual == expected
