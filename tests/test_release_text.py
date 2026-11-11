"""What the project says about its own release is consistent across the files that say it."""
from __future__ import annotations

import re

import yaml

from tests.conftest import ROOT


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def _project_field(name: str) -> str:
    match = re.search(rf'^{name} = (.+)$', _read("pyproject.toml"), re.MULTILINE)
    assert match is not None, name
    return match.group(1)


VERSION = _project_field("version").strip('"')
CITATION = yaml.safe_load(_read("CITATION.cff"))


def test_the_citation_file_states_the_version_and_licence_of_the_package():
    assert CITATION["version"] == VERSION
    assert CITATION["license"] == _project_field("license").strip('"')
    assert CITATION["cff-version"] == "1.2.0" and CITATION["type"] == "software"
    assert CITATION["repository-code"] == "https://github.com/yoch/symq"


def test_the_author_is_the_same_person_everywhere_and_no_address_is_published():
    names = [f"{author['given-names']} {author['family-names']}" for author in CITATION["authors"]]
    assert _project_field("authors") == "[" + ", ".join(f'{{name = "{name}"}}' for name in names) + "]"
    assert _project_field("maintainers") == _project_field("authors")
    # An address in package metadata is public for good; contact goes through the repository.
    for text in (_read("pyproject.toml"), _read("CITATION.cff")):
        assert "email" not in text
        assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", re.sub(r"\S+@[0-9a-f]{40}", "", text))


def test_the_readme_does_not_describe_another_version():
    """The README becomes the PyPI page of each release: a stale version there is public."""
    readme = _read("README.md")
    base = re.match(r"\d+\.\d+\.\d+", VERSION).group(0)
    status = next(line for line in readme.splitlines() if line.startswith("> **Status:**"))
    stated = re.findall(r"\b\d+\.\d+\.\d+\b", status)
    assert stated in ([], [base]), f"the status line names {stated}, the package is {base}"
    assert "There is no PyPI release" not in readme
    assert "python -m pip install symq" in readme


def test_the_first_release_is_named_consistently():
    """0.1.0 was an internal baseline; nothing may present it as a published release."""
    changelog = _read("CHANGELOG.md")
    section = changelog.split("## [0.1.0]", 1)[1].split("\n###", 1)[0]
    assert "never published" in section
    assert "(0.1.0)" not in _read("SECURITY.md")
    assert "the first release, 0.2.0" in _read("docs/stability.md")


def test_the_release_procedure_names_things_that_exist():
    text = _read("RELEASING.md")
    workflow = yaml.safe_load(_read(".github/workflows/release.yml"))
    assert workflow["name"] == "Release" and "**Release** workflow" in text
    for environment in ("pypi", "testpypi"):
        assert workflow["jobs"][environment]["environment"] == environment
        assert f"`{environment}`" in text
    options = workflow[True]["workflow_dispatch"]["inputs"]["target"]["options"]
    for option in options:
        assert f"Target `{option}`" in text, option
    assert "ci-ok" in yaml.safe_load(_read(".github/workflows/ci.yml"))["jobs"]
    assert "`ci-ok`" in text
    for file in ("pyproject.toml", "CITATION.cff", "CHANGELOG.md", "docs/stability.md"):
        assert (ROOT / file).is_file() and file in text, file


def test_the_changelog_opens_with_what_matters_to_users_of_the_core():
    unreleased = _read("CHANGELOG.md").split("## [Unreleased]", 1)[1]
    first_heading = re.search(r"^### (.+)$", unreleased, re.MULTILINE).group(1)
    assert first_heading == "Summary for users of the classical core"
    summary = unreleased.split("### Fixed", 1)[0]
    assert "docs/stability.md" in summary and "performance claim" in summary
