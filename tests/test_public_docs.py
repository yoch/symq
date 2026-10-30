"""Keep the public repository navigation build-independent and usable."""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_PAGES = (
    "README.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "docs/ARCHITECTURE.md",
    "docs/PUBLIC_DEMO.md",
    "docs/PUBLIC_READINESS.md",
)
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]\n]+\]\(([^)\n]+)\)")


@pytest.mark.parametrize("path", PUBLIC_PAGES)
def test_public_pages_have_no_broken_relative_links(path):
    source = ROOT / path
    text = source.read_text(encoding="utf-8")
    for raw_url in MARKDOWN_LINK.findall(text):
        url = urlsplit(raw_url)
        if url.scheme or url.netloc or raw_url.startswith("#"):
            continue
        relative = unquote(url.path)
        if not relative:
            continue
        dest = (source.parent / relative).resolve()
        assert dest.is_relative_to(ROOT), f"{path}: link escapes the repository: {raw_url}"
        assert dest.exists(), f"{path}: broken internal link: {raw_url}"


@pytest.mark.parametrize("path", PUBLIC_PAGES)
def test_public_pages_have_balanced_fenced_code(path):
    source = ROOT / path
    markers = [line for line in source.read_text(encoding="utf-8").splitlines()
               if line.startswith("```")]
    assert len(markers) % 2 == 0, f"{path}: unterminated Markdown code fence"
