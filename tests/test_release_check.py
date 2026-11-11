"""The checks that stand between a tag and a publication (``tools/release_check.py``)."""
from __future__ import annotations

import zipfile

import pytest

from tests.conftest import ROOT
from tools.release_check import (
    PLATFORMS,
    PYTHONS,
    ReleaseError,
    changelog_section,
    check_artifacts,
    main,
    preflight,
    project_version,
    release_branch,
    sha256sums,
)

_TAGS = {
    "manylinux_x86_64": "manylinux_2_28_x86_64.manylinux2014_x86_64",
    "manylinux_aarch64": "manylinux_2_28_aarch64",
    "musllinux_x86_64": "musllinux_1_2_x86_64",
    "musllinux_aarch64": "musllinux_1_2_aarch64",
    "macosx_x86_64": "macosx_10_13_x86_64",
    "macosx_arm64": "macosx_11_0_arm64",
}


def _tree(tmp_path, version="0.2.0", sections=("0.2.0",)):
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname = "symq"\nversion = "{version}"\n', encoding="utf-8")
    text = "# Changelog\n\n## [Unreleased]\n\n- pending\n\n"
    for section in sections:
        text += f"## [{section}] - 2026-12-01\n\n### Added\n\n- something in {section}\n\n"
    (tmp_path / "CHANGELOG.md").write_text(text, encoding="utf-8")
    return tmp_path


def _on(branches):
    def is_ancestor(commit, branch, root):
        return branch in branches
    return is_ancestor


def test_the_real_tree_states_one_version_and_its_release_branch():
    version = project_version()
    assert version.count(".") >= 2
    assert release_branch("0.2.0") == release_branch("0.2.7rc1") == "release/0.2"
    assert release_branch("1.10.3") == "release/1.10"
    assert version in ((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_a_tag_on_its_release_branch_with_its_changelog_section_passes(tmp_path):
    root = _tree(tmp_path)
    assert preflight("refs/tags/v0.2.0", root=root,
                     is_ancestor=_on({"origin/release/0.2"})) == "0.2.0"
    assert "something in 0.2.0" in changelog_section("0.2.0", root)
    assert "pending" not in changelog_section("0.2.0", root)


@pytest.mark.parametrize(("version", "sections", "ref", "branches", "message"), [
    ("0.2.0", ("0.2.0",), "refs/tags/v0.2.1", {"origin/release/0.2"}, "does not name the version"),
    ("0.2.0", ("0.2.0",), "refs/tags/0.2.0", {"origin/release/0.2"}, "does not name the version"),
    ("0.2.0.dev0", ("0.2.0",), "refs/tags/v0.2.0.dev0", {"origin/release/0.2"},
     "not a release version"),
    ("0.2.0", ("0.2.0",), "refs/tags/v0.2.0", {"origin/main"}, "not on origin/release/0.2"),
    ("0.2.0", ("0.2.0",), "refs/tags/v0.2.0", {"origin/release/0.3"}, "not on origin/release/0.2"),
    ("0.2.0", ("0.1.0",), "refs/tags/v0.2.0", {"origin/release/0.2"}, "no section"),
    ("0.2.0", (), "refs/tags/v0.2.0", {"origin/release/0.2"}, "no section"),
])
def test_a_tag_that_must_not_be_released_is_refused(tmp_path, version, sections, ref, branches,
                                                    message):
    root = _tree(tmp_path, version, sections)
    with pytest.raises(ReleaseError, match=message):
        preflight(ref, root=root, is_ancestor=_on(branches))


def test_a_release_candidate_uses_the_section_of_its_final_version(tmp_path):
    root = _tree(tmp_path, "0.2.0rc1", ("0.2.0",))
    assert preflight("refs/tags/v0.2.0rc1", root=root,
                     is_ancestor=_on({"origin/release/0.2"})) == "0.2.0rc1"


def test_a_manual_run_is_a_rehearsal_of_whatever_the_tree_states(tmp_path):
    root = _tree(tmp_path, "0.2.0.dev3", ())
    assert preflight("refs/heads/main", root=root, is_ancestor=_on(set())) == "0.2.0.dev3"


def test_the_ancestry_check_really_asks_git():
    """On this checkout: HEAD is its own ancestor, and an unknown branch is an error."""
    from tools.release_check import _is_ancestor

    assert _is_ancestor("HEAD", "HEAD", ROOT) is True
    with pytest.raises(ReleaseError, match="cannot compare"):
        _is_ancestor("HEAD", "origin/no-such-branch-for-symq-tests", ROOT)


test_the_ancestry_check_really_asks_git = pytest.mark.checkout(
    test_the_ancestry_check_really_asks_git)


def _wheel(directory, name, members):
    path = directory / name
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("symq/__init__.py", "")
        for member in members:
            archive.writestr(member, "x")
    return path


def _release(directory, version="0.2.0"):
    files = [directory / f"symq-{version}.tar.gz"]
    files[0].write_bytes(b"sdist")
    files.append(_wheel(directory, f"symq-{version}-py3-none-any.whl", []))
    for python in PYTHONS:
        for family in PLATFORMS:
            core = f"symq/backends/_zdd.{'cpython-' + python[2:]}-x.so"
            files.append(_wheel(directory, f"symq-{version}-{python}-{python}-{_TAGS[family]}.whl",
                                [core]))
    return files


def test_a_complete_release_is_32_files_and_passes(tmp_path):
    files = _release(tmp_path)
    assert len(files) == 2 + len(PYTHONS) * len(PLATFORMS) == 32
    assert check_artifacts(files, "0.2.0") == []
    sums = sha256sums(files).splitlines()
    assert len(sums) == 32 and sums == sorted(sums, key=lambda line: line.split("  ")[1])
    assert all(len(line.split("  ")[0]) == 64 for line in sums)


def _mutations():
    def missing_wheel(directory, files):
        files.remove(directory / f"symq-0.2.0-cp312-cp312-{_TAGS['musllinux_aarch64']}.whl")
        return "missing binary wheels: ['cp312-musllinux_aarch64']"

    def no_pure_wheel(directory, files):
        files.remove(directory / "symq-0.2.0-py3-none-any.whl")
        return "exactly one pure-Python wheel"

    def no_sdist(directory, files):
        files.remove(directory / "symq-0.2.0.tar.gz")
        return "expected exactly symq-0.2.0.tar.gz"

    def wheel_without_its_core(directory, files):
        _wheel(directory, f"symq-0.2.0-cp311-cp311-{_TAGS['macosx_arm64']}.whl", [])
        return "exactly one native core"

    def wheel_with_the_c_source(directory, files):
        _wheel(directory, f"symq-0.2.0-cp311-cp311-{_TAGS['macosx_arm64']}.whl",
               ["symq/backends/_zdd.cpython-311-darwin.so", "symq/backends/_zdd.c"])
        return "ships the C source"

    def pure_wheel_with_a_core(directory, files):
        _wheel(directory, "symq-0.2.0-py3-none-any.whl", ["symq/backends/_zdd.cpython-312-x.so"])
        return "tagged pure but contains"

    def another_version(directory, files):
        files.append(_wheel(directory, f"symq-0.2.1-cp312-cp312-{_TAGS['manylinux_x86_64']}.whl",
                            ["symq/backends/_zdd.cpython-312-x.so"]))
        return "is not a symq 0.2.0 wheel"

    def unsupported_python(directory, files):
        files.append(_wheel(directory, f"symq-0.2.0-cp315-cp315-{_TAGS['manylinux_x86_64']}.whl",
                            ["symq/backends/_zdd.cpython-315-x.so"]))
        return "outside the release matrix"

    def free_threaded_wheel(directory, files):
        files.append(_wheel(directory, f"symq-0.2.0-cp314-cp314t-{_TAGS['manylinux_x86_64']}.whl",
                            ["symq/backends/_zdd.cpython-314t-x.so"]))
        return "outside the release matrix"

    def windows_binary_wheel(directory, files):
        files.append(_wheel(directory, "symq-0.2.0-cp312-cp312-win_amd64.whl",
                            ["symq/backends/_zdd.cp312-win_amd64.pyd"]))
        return "outside the release matrix"

    def duplicate_platform(directory, files):
        files.append(_wheel(directory, "symq-0.2.0-cp312-cp312-manylinux_2_34_x86_64.whl",
                            ["symq/backends/_zdd.cpython-312-x.so"]))
        return "duplicates"

    def stray_file(directory, files):
        files.append(directory / "notes.txt")
        files[-1].write_text("x")
        return "unexpected file notes.txt"

    return [missing_wheel, no_pure_wheel, no_sdist, wheel_without_its_core,
            wheel_with_the_c_source, pure_wheel_with_a_core, another_version, unsupported_python,
            free_threaded_wheel, windows_binary_wheel, duplicate_platform, stray_file]


@pytest.mark.parametrize("mutate", _mutations(), ids=lambda mutate: mutate.__name__)
def test_an_incomplete_or_wrong_set_of_files_is_refused(tmp_path, mutate):
    files = _release(tmp_path)
    expected = mutate(tmp_path, files)
    problems = check_artifacts(files, "0.2.0")
    assert any(expected in problem for problem in problems), problems


def test_the_command_writes_checksums_only_for_a_complete_release(tmp_path, monkeypatch, capsys):
    import tools.release_check as module

    monkeypatch.setattr(module, "project_version", lambda root=ROOT: "0.2.0")
    _release(tmp_path)
    assert main(["artifacts", str(tmp_path), "--write-sums"]) == 0
    sums = (tmp_path / "SHA256SUMS").read_text(encoding="utf-8")
    assert len(sums.splitlines()) == 32 and "SHA256SUMS" not in sums
    assert main(["artifacts", str(tmp_path)]) == 0  # the checksum file itself is not a stray
    (tmp_path / "SHA256SUMS").unlink()
    (tmp_path / "symq-0.2.0.tar.gz").unlink()
    assert main(["artifacts", str(tmp_path), "--write-sums"]) == 1
    assert not (tmp_path / "SHA256SUMS").exists()
    assert "expected exactly symq-0.2.0.tar.gz" in capsys.readouterr().err


def test_the_release_matrix_is_the_wheel_matrix_of_the_project():
    """``PYTHONS`` here and ``[tool.cibuildwheel] build`` must name the same interpreters."""
    import re

    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    build = re.search(r'^build = "([^"]+)"$', text, re.MULTILINE).group(1)
    assert tuple(tag.removesuffix("-*") for tag in build.split()) == PYTHONS
