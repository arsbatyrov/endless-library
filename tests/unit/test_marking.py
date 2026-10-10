"""TEST-006: the folder marker comes from the path below tests/, never from the absolute path."""

from pathlib import PurePosixPath, PureWindowsPath

import pytest

from tests.marking import FOLDER_MARKERS, folder_marker

ROOT = PurePosixPath("/home/me/my-app/tests")


@pytest.mark.parametrize("folder", FOLDER_MARKERS)
def test_a_marked_folder_gives_its_own_name(folder):
    assert folder_marker(ROOT / folder / "test_x.py", ROOT) == folder


@pytest.mark.parametrize("folder", ["unit", "api", "db", "migrations", "concurrency"])
def test_other_folders_give_no_marker(folder):
    assert folder_marker(ROOT / folder / "test_x.py", ROOT) is None


@pytest.mark.parametrize("outer", FOLDER_MARKERS)
def test_a_checkout_inside_a_folder_with_a_marker_name_is_not_marked(outer):
    """The bug of this ticket: the project itself lives in .../ui/my-app, .../smoke/my-app and so on."""
    root = PurePosixPath(f"/work/{outer}/my-app/tests")

    assert folder_marker(root / "unit" / "test_x.py", root) is None
    assert folder_marker(root / "api" / "test_x.py", root) is None


def test_the_same_bug_with_a_windows_path():
    root = PureWindowsPath("C:/work/ui/my-app/tests")

    assert folder_marker(root / "unit" / "test_x.py", root) is None
    assert folder_marker(root / "ui" / "test_x.py", root) == "ui"


def test_a_marker_name_deeper_than_the_first_folder_does_not_count():
    assert folder_marker(ROOT / "unit" / "ui" / "test_x.py", ROOT) is None


def test_the_first_folder_decides_even_when_a_deeper_one_has_another_name():
    assert folder_marker(ROOT / "ui" / "unit" / "test_x.py", ROOT) == "ui"


def test_a_file_directly_in_the_tests_folder_gives_no_marker():
    assert folder_marker(ROOT / "test_x.py", ROOT) is None


def test_a_path_outside_the_tests_folder_gives_no_marker_and_no_error():
    assert folder_marker(PurePosixPath("/elsewhere/ui/test_x.py"), ROOT) is None
