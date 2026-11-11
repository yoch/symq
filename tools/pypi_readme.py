"""The README as PyPI shows it: relative links made absolute.

    python tools/pypi_readme.py --check dist/*.whl dist/*.tar.gz

``README.md`` links to files of the repository by relative path. On GitHub they resolve; on the
PyPI project page the same text is rendered away from the repository and every such link is
dead. The build (``hatch_build.py``) therefore publishes a copy whose relative links point to the
file on GitHub **at the tag of the version being built**, so that the page of an old release
keeps describing that release. A development version has no tag and points to the default
branch.

``--check`` reads the description back from built distributions and fails if a relative link is
left or the description is empty.
"""
from __future__ import annotations

import argparse
import re
import sys
import tarfile
import zipfile
from email import message_from_string
from pathlib import Path

REPOSITORY = "https://github.com/yoch/symq"
DEFAULT_BRANCH = "main"

_LINK = re.compile(r"\]\(([^)\s]+)\)")
_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:")
_RELEASE = re.compile(r"\d+(\.\d+)*((a|b|rc)\d+)?(\.post\d+)?")


def release_ref(version: str) -> str:
    """The git ref whose files match ``version``: ``v<version>`` for a release or a release
    candidate, the default branch for a development or local version (it has no tag)."""
    return f"v{version}" if _RELEASE.fullmatch(version) else DEFAULT_BRANCH


def relative_targets(text: str) -> list[str]:
    """Link targets of ``text`` that are neither absolute URLs nor in-page anchors.

    Fenced code blocks are skipped: ``](`` there is code, not a link.
    """
    found, fenced = [], False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
        elif not fenced:
            found += [target for target in _LINK.findall(line)
                      if not target.startswith("#") and not _SCHEME.match(target)]
    return found


def absolute_links(text: str, ref: str) -> str:
    """``text`` with every relative link pointing to the file at ``ref`` on GitHub."""

    def replace(match: re.Match[str]) -> str:
        target = match.group(1)
        if target.startswith("#") or _SCHEME.match(target):
            return match.group(0)
        if target.startswith("/") or ".." in Path(target.split("#")[0]).parts:
            raise ValueError(f"README link leaves the repository: {target!r}")
        return f"]({REPOSITORY}/blob/{ref}/{target.removeprefix('./')})"

    lines, fenced = [], False
    for line in text.split("\n"):
        if line.lstrip().startswith("```"):
            fenced = not fenced
        elif not fenced:
            line = _LINK.sub(replace, line)
        lines.append(line)
    return "\n".join(lines)


def description(distribution: Path) -> str:
    """The long description stored in a wheel (``METADATA``) or an sdist (``PKG-INFO``)."""
    if distribution.suffix == ".whl":
        with zipfile.ZipFile(distribution) as archive:
            name = next(name for name in archive.namelist()
                        if name.endswith(".dist-info/METADATA"))
            raw = archive.read(name).decode("utf-8")
    else:
        with tarfile.open(distribution) as archive:
            member = min((member for member in archive.getmembers()
                          if member.name.endswith("/PKG-INFO")), key=lambda m: m.name.count("/"))
            extracted = archive.extractfile(member)
            assert extracted is not None
            raw = extracted.read().decode("utf-8")
    payload = message_from_string(raw).get_payload()
    assert isinstance(payload, str)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("--check", nargs="+", type=Path, required=True, metavar="DIST",
                        help="built wheels or sdists whose description must have no relative link")
    failed = False
    for distribution in parser.parse_args(argv).check:
        text = description(distribution)
        left = relative_targets(text)
        if not text.strip() or left:
            failed = True
            print(f"{distribution.name}: {'empty description' if not text.strip() else left}",
                  file=sys.stderr)
        else:
            print(f"{distribution.name}: description has no relative link")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
