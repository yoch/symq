"""Every Markdown page must have working links, balanced fences and runnable Python examples."""
from __future__ import annotations

import importlib.util
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _pages() -> list[str]:
    try:
        tracked = subprocess.run(["git", "ls-files", "*.md"], cwd=ROOT, check=True,
                                 capture_output=True, text=True).stdout.split()
    except (OSError, subprocess.CalledProcessError):  # not a git checkout
        tracked = [str(p.relative_to(ROOT)) for p in ROOT.rglob("*.md")]
    return sorted(page for page in tracked if (ROOT / page).is_file())


PAGES = _pages()
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)\s]+)\)")
PYTHON_BLOCK = re.compile(r"^```python\n(.*?)^```", re.DOTALL | re.MULTILINE)
# Optional third-party modules: a page whose examples import one of them is skipped when it is
# missing, never reported as passing.
OPTIONAL_MODULES = {"mqt": "mqt.qcec", "dd": "dd", "brial": "brial"}


UNPUBLISHED = ROOT / "benchmarks" / "corpus" / "bilinear_kmb"
"""The one directory the source distribution leaves out (``pyproject.toml``). Pages link to its
provenance and licence files; those links are checked wherever the directory exists, which is
every checkout, and skipped where the whole directory is absent. A link into it to a file that
does not exist still fails in a checkout."""


def test_the_documentation_is_found():
    assert "README.md" in PAGES and "docs/index.md" in PAGES


@pytest.mark.parametrize("path", PAGES)
def test_pages_have_no_broken_relative_links(path):
    source = ROOT / path
    for raw_url in MARKDOWN_LINK.findall(source.read_text(encoding="utf-8")):
        url = urlsplit(raw_url)
        if url.scheme or url.netloc or raw_url.startswith("#") or not url.path:
            continue
        dest = (source.parent / unquote(url.path)).resolve()
        assert dest.is_relative_to(ROOT), f"{path}: link escapes the repository: {raw_url}"
        if dest.is_relative_to(UNPUBLISHED) and not UNPUBLISHED.exists():
            continue  # a source distribution: this one directory is left out on purpose
        assert dest.exists(), f"{path}: broken internal link: {raw_url}"


@pytest.mark.parametrize("path", PAGES)
def test_pages_have_balanced_fenced_code(path):
    markers = [line for line in (ROOT / path).read_text(encoding="utf-8").splitlines()
               if line.startswith("```")]
    assert len(markers) % 2 == 0, f"{path}: unterminated Markdown code fence"


RUNNABLE = [page for page in PAGES if PYTHON_BLOCK.search((ROOT / page).read_text("utf-8"))]


@pytest.mark.parametrize("path", RUNNABLE)
def test_python_examples_run(path, monkeypatch):
    """The ``python`` blocks of one page run in order, sharing one namespace."""
    blocks = PYTHON_BLOCK.findall((ROOT / path).read_text(encoding="utf-8"))
    source = "\n".join(blocks)
    for marker, module in OPTIONAL_MODULES.items():
        if re.search(rf"^\s*(from|import) {marker}\b", source, re.MULTILINE) and \
                importlib.util.find_spec(module.split(".")[0]) is None:
            pytest.skip(f"{path} imports the optional module {module}")
    # Without python-sat, every SAT engine raises SatUnavailable (often caught and turned into
    # an "unsupported" result, which then fails an `assert ....equivalent` example). Record
    # those raises: a page that fails after one was raised needs SAT; any other failure is real.
    from symq import sat
    from symq.errors import SatUnavailable

    sat_refusals: list[tuple] = []
    if not sat.available():
        original_init = SatUnavailable.__init__

        def recording_init(self, *args, **kwargs):
            sat_refusals.append(args)
            original_init(self, *args, **kwargs)

        monkeypatch.setattr(SatUnavailable, "__init__", recording_init)
    if "zdd-native" in source:
        from symq.backends import has_native

        if not has_native():
            pytest.skip(f"{path} needs the native core")
    monkeypatch.chdir(ROOT)
    namespace: dict = {"__name__": "__docs__"}
    without_qcec = importlib.util.find_spec("mqt") is None
    for index, block in enumerate(blocks):
        if without_qcec and "qcec" in block:
            continue  # the optional MQT QCEC adapter is absent; later blocks must not need it
        try:
            exec(compile(block, f"{path} (python block {index})", "exec"), namespace)  # noqa: S102
        except Exception:
            if sat_refusals:
                pytest.skip(f"{path} needs python-sat: {sat_refusals[0]}")
            raise
