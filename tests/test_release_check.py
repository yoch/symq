"""The checks that stand between a tag and a publication (``tools/release_check.py``)."""
from __future__ import annotations

import io
import subprocess
import tarfile
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
    release_notes,
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


def _git(root, *arguments):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                    "-c", "commit.gpgsign=false", *arguments], cwd=root, check=True,
                   capture_output=True)


def test_the_ancestry_check_asks_git_in_the_right_direction(tmp_path):
    """A real repository: a commit on the release branch, one that is only on a side branch."""
    from tools.release_check import _is_ancestor

    _git(tmp_path, "init", "-q", "-b", "release/0.2")
    (tmp_path / "a").write_text("1")
    _git(tmp_path, "add", "a")
    _git(tmp_path, "commit", "-q", "-m", "on the release branch")
    _git(tmp_path, "tag", "released")
    _git(tmp_path, "checkout", "-q", "-b", "side")
    (tmp_path / "b").write_text("2")
    _git(tmp_path, "add", "b")
    _git(tmp_path, "commit", "-q", "-m", "only on the side branch")
    assert _is_ancestor("released", "release/0.2", tmp_path) is True
    assert _is_ancestor("side", "release/0.2", tmp_path) is False   # ahead of it, not on it
    assert _is_ancestor("release/0.2", "side", tmp_path) is True    # the other direction
    with pytest.raises(ReleaseError, match="cannot compare"):
        _is_ancestor("side", "no-such-branch", tmp_path)


def test_the_preflight_uses_the_real_ancestry_check(tmp_path):
    """End to end on a real repository: the same tag passes on the branch and fails off it."""
    root = _tree(tmp_path)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "release content")
    _git(root, "update-ref", "refs/remotes/origin/release/0.2", "HEAD")
    assert preflight("refs/tags/v0.2.0", root=root) == "0.2.0"
    (root / "later").write_text("x")
    _git(root, "add", "later")
    _git(root, "commit", "-q", "-m", "not on the release branch")
    with pytest.raises(ReleaseError, match="not on origin/release/0.2"):
        preflight("refs/tags/v0.2.0", root=root)


def test_the_changelog_section_stops_at_the_next_version_and_must_have_content(tmp_path):
    root = _tree(tmp_path, "0.2.0", ("0.2.0", "0.1.0"))
    section = changelog_section("0.2.0", root)
    assert "something in 0.2.0" in section and "something in 0.1.0" not in section
    text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    (root / "CHANGELOG.md").write_text(
        text.replace("### Added\n\n- something in 0.2.0\n\n", ""), encoding="utf-8")
    with pytest.raises(ReleaseError, match="no section"):
        changelog_section("0.2.0", root)


def test_release_notes_link_to_the_tag_not_to_a_dead_relative_path(tmp_path):
    root = _tree(tmp_path)
    text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    (root / "CHANGELOG.md").write_text(
        text.replace("- something in 0.2.0", "- see [the policy](docs/stability.md)"),
        encoding="utf-8")
    notes = release_notes("0.2.0", "v0.2.0", root)
    assert "](https://github.com/yoch/symq/blob/v0.2.0/docs/stability.md)" in notes
    assert "](docs/" not in notes


def test_the_project_version_must_be_stated_exactly_once(tmp_path):
    (tmp_path / "pyproject.toml").write_text('version = "1.0.0"\nversion = "2.0.0"\n')
    with pytest.raises(ReleaseError, match="exactly once"):
        project_version(tmp_path)


def test_the_preflight_command_reports_the_version_and_fails_with_status_1(
        tmp_path, monkeypatch, capsys):
    import tools.release_check as module

    root = _tree(tmp_path, "0.2.0.dev4", ())
    monkeypatch.setattr(module, "ROOT", root)
    monkeypatch.setattr(module.project_version, "__defaults__", (root,))
    monkeypatch.setattr(module.preflight, "__kwdefaults__",
                        {**module.preflight.__kwdefaults__, "root": root})
    notes = tmp_path / "notes.md"
    assert main(["preflight", "--ref", "refs/heads/main", "--notes", str(notes)]) == 0
    assert capsys.readouterr().out == "version=0.2.0.dev4\n"  # exactly what GITHUB_OUTPUT gets
    assert not notes.exists()  # notes are for a tagged release only
    assert main(["preflight", "--ref", "refs/tags/v9.9.9"]) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and "does not name the version" in captured.err


def _wheel(directory, name, members):
    path = directory / name
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("symq/__init__.py", "")
        for member in members:
            archive.writestr(member, "x")
    return path


def _sdist(directory, version, members=("PKG-INFO", "pyproject.toml", "src/symq/__init__.py",
                                        "src/symq/backends/_zdd.c")):
    path = directory / f"symq-{version}.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        for member in members:
            info = tarfile.TarInfo(f"symq-{version}/{member}")
            info.size = 1
            archive.addfile(info, io.BytesIO(b"x"))
    return path


def _release(directory, version="0.2.0"):
    files = [_sdist(directory, version)]
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

    def sdist_under_another_name(directory, files):
        files.remove(directory / "symq-0.2.0.tar.gz")
        files.append(_sdist(directory, "0.2.0").rename(directory / "symq-0.2.0.post1.tar.gz"))
        return "expected exactly symq-0.2.0.tar.gz"

    def sdist_that_is_not_an_archive(directory, files):
        (directory / "symq-0.2.0.tar.gz").write_bytes(b"thirteen byte")
        return "is not a readable archive"

    def sdist_with_the_unpublished_corpus(directory, files):
        _sdist(directory, "0.2.0", members=(
            "PKG-INFO", "pyproject.toml", "src/symq/__init__.py", "src/symq/backends/_zdd.c",
            "benchmarks/corpus/bilinear_kmb/manifest.json"))
        return "which is not to be published"

    def sdist_without_the_c_source(directory, files):
        _sdist(directory, "0.2.0", members=("PKG-INFO", "pyproject.toml", "src/symq/__init__.py"))
        return "lacks symq-0.2.0/src/symq/backends/_zdd.c"

    def two_pure_wheels(directory, files):
        files.append(_wheel(directory, "symq-0.2.0-1-py3-none-any.whl", []))
        return "outside the release matrix"  # a build tag: a second wheel for the same slot

    def pure_wheel_tagged_for_one_python(directory, files):
        files.remove(directory / "symq-0.2.0-py3-none-any.whl")
        files.append(_wheel(directory, "symq-0.2.0-cp312-none-any.whl", []))
        return "a pure wheel must be tagged py3-none-any"

    def pure_wheel_with_the_c_source(directory, files):
        _wheel(directory, "symq-0.2.0-py3-none-any.whl", ["symq/backends/_zdd.c"])
        return "ships the C source"

    def wheel_of_another_project(directory, files):
        files.append(_wheel(directory, f"other-0.2.0-cp312-cp312-{_TAGS['manylinux_x86_64']}.whl",
                            ["symq/backends/_zdd.cpython-312-x.so"]))
        return "is not a symq 0.2.0 wheel"

    def wheel_with_two_cores(directory, files):
        _wheel(directory, f"symq-0.2.0-cp311-cp311-{_TAGS['macosx_arm64']}.whl",
               ["symq/backends/_zdd.cpython-311-darwin.so", "symq/backends/_zdd.cpython-311-x.so"])
        return "exactly one native core"

    def core_built_for_another_python(directory, files):
        _wheel(directory, f"symq-0.2.0-cp313-cp313-{_TAGS['manylinux_x86_64']}.whl",
               ["symq/backends/_zdd.cpython-312-x86_64-linux-gnu.so"])
        return "holds a core built for another Python"

    def macos_wheel_that_needs_a_recent_system(directory, files):
        files.remove(directory / f"symq-0.2.0-cp312-cp312-{_TAGS['macosx_x86_64']}.whl")
        files.append(_wheel(directory, "symq-0.2.0-cp312-cp312-macosx_15_0_x86_64.whl",
                            ["symq/backends/_zdd.cpython-312-darwin.so"]))
        return "requires a newer system"

    def linux_wheel_that_needs_a_recent_glibc(directory, files):
        files.remove(directory / f"symq-0.2.0-cp312-cp312-{_TAGS['manylinux_x86_64']}.whl")
        files.append(_wheel(directory, "symq-0.2.0-cp312-cp312-manylinux_2_39_x86_64.whl",
                            ["symq/backends/_zdd.cpython-312-x.so"]))
        return "requires a newer system"

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

    return [missing_wheel, no_pure_wheel, no_sdist, sdist_under_another_name,
            sdist_that_is_not_an_archive, sdist_with_the_unpublished_corpus,
            sdist_without_the_c_source, two_pure_wheels,
            pure_wheel_tagged_for_one_python, pure_wheel_with_the_c_source,
            wheel_of_another_project, wheel_with_two_cores, core_built_for_another_python,
            macos_wheel_that_needs_a_recent_system, linux_wheel_that_needs_a_recent_glibc,
            wheel_without_its_core,
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


@pytest.mark.parametrize("name", [
    "symq-0.2.0-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl",
    "symq-0.2.0-cp312-cp312-manylinux_2_17_aarch64.manylinux2014_aarch64.whl",
    "symq-0.2.0-cp310-cp310-macosx_10_9_x86_64.whl",
    "symq-0.2.0-cp314-cp314-macosx_10_15_x86_64.whl",
    "symq-0.2.0-cp312-cp312-macosx_11_0_arm64.whl",
    "symq-0.2.0-cp312-cp312-musllinux_1_2_aarch64.whl",
])
def test_real_wheel_names_of_the_builders_are_accepted(tmp_path, name):
    """Names as auditwheel and delocate write them, with the real suffixes of the core."""
    python = name.split("-")[2]
    family = next(family for family in PLATFORMS
                  if name.split("-")[4].split(".")[0].startswith(family.split("_")[0])
                  and name.removesuffix(".whl").endswith(family.split("_", 1)[1]))
    files = _release(tmp_path)
    files.remove(tmp_path / f"symq-0.2.0-{python}-{python}-{_TAGS[family]}.whl")
    suffix = "darwin" if "macosx" in name else "x86_64-linux-musl" if "musl" in name else "x86_64-linux-gnu"
    files.append(_wheel(tmp_path, name, [f"symq/backends/_zdd.cpython-{python[2:]}-{suffix}.so"]))
    assert check_artifacts(files, "0.2.0") == []


def test_the_release_matrix_is_the_wheel_matrix_of_the_project():
    """``PYTHONS`` here and ``[tool.cibuildwheel] build`` must name the same interpreters."""
    import re

    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    build = re.search(r'^build = "([^"]+)"$', text, re.MULTILINE).group(1)
    assert tuple(tag.removesuffix("-*") for tag in build.split()) == PYTHONS


def test_the_unpublished_corpus_is_named_the_same_way_everywhere():
    """One directory, four places: the sdist exclusion, the release check, the test capability
    and the link checker. If they named different paths, one of them would guard nothing."""
    import tools.release_check as module
    from tests import conftest, test_public_docs

    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert f'exclude = ["{module.UNPUBLISHED}"]' in text
    assert ROOT / module.UNPUBLISHED == conftest.BILINEAR_CORPUS
    assert test_public_docs.UNPUBLISHED == conftest.BILINEAR_CORPUS
    # In a checkout the directory is there and the capability is available; in a source
    # distribution neither is.
    assert (conftest.corpus_bilinear_unavailable_reason() is None) == conftest.BILINEAR_CORPUS.is_dir()
