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

RAW = "https://raw.githubusercontent.com/yoch/symq"

_LINK = re.compile(r"\]\(([^)\s]+)\)")
_IMAGE = re.compile(r"(!\[[^\]]*\])\(([^)\s]+)\)")
_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:")
_RELEASE = re.compile(r"\d+(\.\d+)*((a|b|rc)\d+)?(\.post\d+)?")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})[^`]*$")
_CODE_SPAN = re.compile(r"(`+[^`]*`+)")
# Link forms the rewriter does not handle. They are refused rather than left as they are: a
# link written in one of them would be published dead.
_UNSUPPORTED = (
    ("a link with a title, spaces or angle brackets", re.compile(r"\]\(\s*<|\]\(\s+\S|\]\([^)\s]+\s+[\"'(]")),
    ("a reference-style link definition", re.compile(r"^ {0,3}\[[^\]]+\]:\s*(\S+)")),
    ("an HTML link or image", re.compile(r"(?:href|src)\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)),
)


def release_ref(version: str) -> str:
    """The git ref whose files match ``version``: ``v<version>`` for a release or a release
    candidate, the default branch for a development or local version (it has no tag)."""
    return f"v{version}" if _RELEASE.fullmatch(version) else DEFAULT_BRANCH


def _relative(target: str) -> bool:
    return not target.startswith("#") and not _SCHEME.match(target)


def _prose(text: str):
    """``(line, segments)`` for every line outside fenced code: the segments alternate between
    prose (even positions) and inline code spans (odd positions)."""
    fence = None
    for line in text.split("\n"):
        match = _FENCE.match(line)
        if match and (fence is None or match.group(1)[0] == fence):
            fence = None if fence else match.group(1)[0]
            yield line, None
        elif fence is not None:
            yield line, None
        else:
            yield line, _CODE_SPAN.split(line)


def relative_targets(text: str) -> list[str]:
    """Targets of ``text`` that are neither absolute URLs nor in-page anchors, in any link form
    this module knows: inline links and images, reference definitions, HTML ``href``/``src``.

    Fenced code blocks and inline code spans are skipped: ``](`` there is code, not a link.
    """
    found = []
    for _line, segments in _prose(text):
        for prose in (segments or [])[::2]:
            candidates = _LINK.findall(prose)
            for _name, pattern in _UNSUPPORTED[1:]:
                candidates += pattern.findall(prose)
            found += [target for target in candidates if _relative(target)]
    return found


def unsupported_links(text: str) -> list[str]:
    """Links written in a form the rewriter cannot make absolute, each with its reason."""
    found = []
    for line, segments in _prose(text):
        for prose in (segments or [])[::2]:
            for name, pattern in _UNSUPPORTED:
                for match in pattern.finditer(prose):
                    target = match.group(1) if pattern.groups else None
                    if target is None or _relative(target):
                        found.append(f"{name}: {line.strip()[:80]}")
    return found


def absolute_links(text: str, ref: str) -> str:
    """``text`` with every relative link pointing to the file at ``ref`` on GitHub.

    A link to a file becomes its page (``/blob/``), an image its content (the raw file): a
    page URL in an image would be published as a broken picture. A link in a form this function
    does not rewrite is an error, not a link left dead.
    """
    refused = unsupported_links(text)
    if refused:
        raise ValueError(f"README links that cannot be made absolute: {refused}")

    def path_of(target: str) -> str:
        if target.startswith("/") or ".." in Path(target.split("#")[0]).parts:
            raise ValueError(f"README link leaves the repository: {target!r}")
        return target.removeprefix("./")

    def image(match: re.Match[str]) -> str:
        target = match.group(2)
        if not _relative(target):
            return match.group(0)
        return f"{match.group(1)}({RAW}/{ref}/{path_of(target)})"

    def link(match: re.Match[str]) -> str:
        target = match.group(1)
        if not _relative(target):
            return match.group(0)
        return f"]({REPOSITORY}/blob/{ref}/{path_of(target)})"

    lines = []
    for line, segments in _prose(text):
        if segments is not None:
            segments[::2] = [_LINK.sub(link, _IMAGE.sub(image, prose)) for prose in segments[::2]]
            line = "".join(segments)
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
        left = relative_targets(text) + unsupported_links(text)
        if not text.strip() or left:
            failed = True
            print(f"{distribution.name}: {'empty description' if not text.strip() else left}",
                  file=sys.stderr)
        else:
            print(f"{distribution.name}: description has no relative link")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
