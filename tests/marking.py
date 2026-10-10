"""Which marker a test gets from the folder it lives in (TEST-006).

Only the FIRST folder below `tests/` counts. Looking at the whole absolute path would mark every test when the project
is checked out under a folder that happens to be called `ui`, `smoke`, `contract` or `security`.
"""

from pathlib import Path

FOLDER_MARKERS = ("ui", "smoke", "contract", "security")


def folder_marker(path: Path, tests_root: Path) -> str | None:
    """The marker name for a test file, or None (another folder, a file directly in tests/, or a path outside it)."""
    try:
        relative = path.relative_to(tests_root)
    except ValueError:
        return None
    if len(relative.parts) < 2:  # a file directly in tests/ has no folder
        return None
    first_folder = relative.parts[0]
    return first_folder if first_folder in FOLDER_MARKERS else None
