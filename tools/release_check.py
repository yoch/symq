"""Checks the release workflow runs before anything is published.

    python tools/release_check.py preflight --ref refs/tags/v0.2.0
    python tools/release_check.py artifacts dist/ --write-sums

``preflight`` refuses a tag that does not name the version of the tree it points to, a tagged
commit that is not on the release branch of its series, and a version without its changelog
section. ``artifacts`` refuses a set of built files that is not exactly what a release consists
of: one source distribution, one pure-Python wheel, and one binary wheel per supported Python
and platform, each with its native core and none with the C source.

Both are plain functions over paths and strings so that the tests can exercise them without a
tag, a network or a build.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
import tarfile
import zipfile
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PYTHONS = ("cp310", "cp311", "cp312", "cp313", "cp314")
PLATFORMS = ("manylinux_x86_64", "manylinux_aarch64", "musllinux_x86_64", "musllinux_aarch64",
             "macosx_x86_64", "macosx_arm64")
"""Platform families of the binary wheels; a wheel's tag belongs to exactly one."""

UNPUBLISHED = "benchmarks/corpus/bilinear_kmb"
"""Kept in the repository, left out of the source distribution (``pyproject.toml`` says why)."""

CEILINGS = {"manylinux": (2, 28), "musllinux": (1, 2), "macosx_x86_64": (10, 15),
            "macosx_arm64": (11, 0)}
"""The newest system a wheel may require: glibc 2.28, musl 1.2, macOS 10.15 on Intel and 11.0 on
Apple silicon. A wheel tagged for something newer (a lost deployment target, a base image that
moved) would install almost nowhere, and pip would quietly give those users the pure wheel."""

_VERSION = re.compile(r'^version = "([^"]+)"$', re.MULTILINE)
_RELEASE = re.compile(r"\d+\.\d+\.\d+(rc\d+)?")
_WHEEL = re.compile(r"(?P<name>[^-]+)-(?P<version>[^-]+)-(?P<python>[^-]+)-(?P<abi>[^-]+)-"
                    r"(?P<platform>.+)\.whl")


class ReleaseError(Exception):
    """The release must not proceed; the message says what to fix."""


def project_version(root: Path = ROOT) -> str:
    found = _VERSION.findall((root / "pyproject.toml").read_text(encoding="utf-8"))
    if len(found) != 1:
        raise ReleaseError(f"pyproject.toml must state the version exactly once, found {found}")
    return found[0]


def release_branch(version: str) -> str:
    """``release/0.2`` for every ``0.2.z``: the branch a tag of that series must be on."""
    major, minor, _rest = version.split(".", 2)
    return f"release/{major}.{minor}"


def release_notes(version: str, tag: str, root: Path = ROOT) -> str:
    """The changelog section as the body of a GitHub Release.

    The section links to files of the repository by relative path; in a release body those
    links would resolve under ``/releases/`` and be dead, so they are pointed at the tag.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("_symq_pypi_readme",
                                                  Path(__file__).with_name("pypi_readme.py"))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.absolute_links(changelog_section(version, root), tag)


def changelog_section(version: str, root: Path = ROOT) -> str:
    """The text of the ``## [version]`` section of the changelog, without its heading."""
    text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|\Z)", text,
                      re.MULTILINE | re.DOTALL)
    if match is None or not match.group(1).strip():
        raise ReleaseError(f"CHANGELOG.md has no section '## [{version}]' with content")
    return match.group(1).strip() + "\n"


def _is_ancestor(commit: str, branch: str, root: Path) -> bool:
    done = subprocess.run(["git", "merge-base", "--is-ancestor", commit, branch], cwd=root,
                          capture_output=True, text=True, check=False)
    if done.returncode not in (0, 1):
        raise ReleaseError(f"cannot compare {commit} with {branch}: {done.stderr.strip()}")
    return done.returncode == 0


def preflight(ref: str, *, root: Path = ROOT, commit: str = "HEAD",
              is_ancestor=_is_ancestor) -> str:
    """Check that ``ref`` may be released from ``root``; return the version.

    A tag ``refs/tags/vX.Y.Z`` must name the version in ``pyproject.toml``, which must be a
    release (or release-candidate) version; the tagged commit must be on ``origin/release/X.Y``;
    the changelog must have its section. Any other ref is a rehearsal (a manual run that
    builds, and uploads to the test index at most): the version is whatever the tree states.
    """
    version = project_version(root)
    if ref.startswith("refs/tags/"):
        tag = ref.removeprefix("refs/tags/")
        if tag != f"v{version}":
            raise ReleaseError(f"tag {tag!r} does not name the version of this tree, {version!r}")
        if not _RELEASE.fullmatch(version):
            raise ReleaseError(f"{version!r} is not a release version (X.Y.Z or X.Y.ZrcN)")
        branch = f"origin/{release_branch(version)}"
        if not is_ancestor(commit, branch, root):
            raise ReleaseError(f"the tagged commit is not on {branch}: releases are cut from "
                               "the release branch only")
        changelog_section(version.split("rc")[0], root)
        return version
    return version


def _family(platform: str) -> str | None:
    """The platform family of a wheel tag such as ``manylinux_2_28_x86_64.manylinux2014_x86_64``."""
    first = platform.split(".")[0]
    for family in PLATFORMS:
        system, architecture = family.split("_", 1)
        if first.startswith(system) and first.endswith("_" + architecture):
            return family
    return None


def _too_new(platform: str, family: str) -> bool:
    """Whether the first platform tag requires a system newer than the family's ceiling."""
    match = re.match(r"[a-z]+_(\d+)_(\d+)_", platform.split(".")[0])
    if match is None:
        return True  # a tag without a version (``linux_x86_64``) is not a release wheel
    ceiling = CEILINGS.get(family, CEILINGS.get(family.split("_")[0]))
    assert ceiling is not None
    return (int(match.group(1)), int(match.group(2))) > ceiling


def _native_members(wheel: Path) -> tuple[list[str], list[str]]:
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
    cores = [name for name in names if re.fullmatch(r"symq/backends/_zdd\.[^/]+\.(so|pyd)", name)]
    sources = [name for name in names if name.endswith("_zdd.c")]
    return cores, sources


def _sdist_problem(path: Path, version: str) -> str | None:
    """Why ``path`` is not the source distribution of ``version``, or ``None``."""
    root = f"symq-{version}"
    try:
        with tarfile.open(path) as archive:
            names = set(archive.getnames())
    except (tarfile.TarError, OSError) as error:
        return f"{path.name} is not a readable archive: {error}"
    for member in ("PKG-INFO", "pyproject.toml", "src/symq/__init__.py",
                   "src/symq/backends/_zdd.c"):
        if f"{root}/{member}" not in names:
            return f"{path.name} lacks {root}/{member}"
    unpublished = sorted(name for name in names if name.startswith(f"{root}/{UNPUBLISHED}/"))
    if unpublished:
        return (f"{path.name} contains {UNPUBLISHED}, which is not to be published "
                f"({len(unpublished)} files)")
    return None


def check_artifacts(files: Iterable[Path], version: str) -> list[str]:
    """Every reason why ``files`` is not exactly one release of ``version``; empty when it is."""
    problems: list[str] = []
    files = sorted(files)
    sdists = [path for path in files if path.name.endswith(".tar.gz")]
    wheels = [path for path in files if path.suffix == ".whl"]
    for path in files:
        if path not in sdists and path not in wheels:
            problems.append(f"unexpected file {path.name}")
    if [path.name for path in sdists] != [f"symq-{version}.tar.gz"]:
        problems.append(f"expected exactly symq-{version}.tar.gz, found "
                        f"{[path.name for path in sdists]}")
    else:
        problem = _sdist_problem(sdists[0], version)
        if problem is not None:
            problems.append(problem)
    seen: dict[tuple[str, str], str] = {}
    pure = []
    for wheel in wheels:
        match = _WHEEL.fullmatch(wheel.name)
        if match is None or match["name"] != "symq" or match["version"] != version:
            problems.append(f"{wheel.name} is not a symq {version} wheel")
            continue
        cores, sources = _native_members(wheel)
        if sources:
            problems.append(f"{wheel.name} ships the C source {sources}")
        if match["platform"] == "any":
            pure.append(wheel.name)
            if (match["python"], match["abi"]) != ("py3", "none"):
                problems.append(f"{wheel.name}: a pure wheel must be tagged py3-none-any")
            if cores:
                problems.append(f"{wheel.name} is tagged pure but contains {cores}")
            continue
        family = _family(match["platform"])
        if family is None or match["python"] not in PYTHONS or match["abi"] != match["python"]:
            problems.append(f"{wheel.name} is outside the release matrix")
            continue
        if _too_new(match["platform"], family):
            problems.append(f"{wheel.name} requires a newer system than the release supports")
        if len(cores) != 1:
            problems.append(f"{wheel.name} must contain exactly one native core, found {cores}")
        elif f".cpython-{match['python'][2:]}-" not in cores[0]:
            problems.append(f"{wheel.name} holds a core built for another Python: {cores[0]}")
        key = (match["python"], family)
        if key in seen:
            problems.append(f"{wheel.name} duplicates {seen[key]}")
        seen[key] = wheel.name
    if len(pure) != 1:
        problems.append(f"expected exactly one pure-Python wheel, found {pure}")
    missing = [f"{python}-{family}" for python in PYTHONS for family in PLATFORMS
               if (python, family) not in seen]
    if missing:
        problems.append(f"missing binary wheels: {missing}")
    return problems


def sha256sums(files: Iterable[Path]) -> str:
    """``sha256sum``-compatible lines, sorted by file name."""
    return "".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n"
                   for path in sorted(files, key=lambda path: path.name))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    entry = commands.add_parser("preflight", help="may this ref be released?")
    entry.add_argument("--ref", required=True, help="the git ref of the run, e.g. refs/tags/v0.2.0")
    entry.add_argument("--notes", type=Path,
                       help="write the changelog section of a tagged release here")
    entry = commands.add_parser("artifacts", help="is this exactly one release?")
    entry.add_argument("directory", type=Path)
    entry.add_argument("--write-sums", action="store_true",
                       help="write SHA256SUMS next to the files when they are complete")
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "preflight":
            version = preflight(arguments.ref)
            if arguments.notes is not None and arguments.ref.startswith("refs/tags/"):
                tag = arguments.ref.removeprefix("refs/tags/")
                arguments.notes.write_text(release_notes(version.split("rc")[0], tag),
                                           encoding="utf-8")
            print(f"version={version}")
            return 0
        files = [path for path in arguments.directory.iterdir() if path.name != "SHA256SUMS"]
        problems = check_artifacts(files, project_version())
        for problem in problems:
            print(f"release_check: {problem}", file=sys.stderr)
        if problems:
            return 1
        if arguments.write_sums:
            (arguments.directory / "SHA256SUMS").write_text(sha256sums(files), encoding="utf-8")
        print(f"{len(files)} files form one complete release")
        return 0
    except ReleaseError as error:
        print(f"release_check: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
