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


def test_the_readme_does_not_present_the_internal_baseline_as_the_current_version():
    """The README becomes the PyPI page of each release: a stale version there is public.

    The status line may name the first release (0.2.0, a fact that stays true); it must not
    name 0.1.0, which was never released, nor say that nothing is released.
    """
    readme = _read("README.md")
    status = next(line for line in readme.splitlines() if line.startswith("> **Status:**"))
    assert "0.1.0" not in status
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
    # What the procedure says the workflow produces is what the workflow produces.
    assert "30 binary wheels" in text and "`SHA256SUMS`" in text and "`release` artifact" not in text
    verify = workflow["jobs"]["verify"]
    assert any("--write-sums" in str(step.get("run")) for step in verify["steps"])
    assert "--extra-index-url" not in text  # see the paragraph on indexes in the document
    assert "pending" in text and "`date-released`" in text


def test_the_notes_of_the_first_release_open_with_what_matters_to_users_of_the_core():
    """Wherever those notes are: under ``[Unreleased]`` until the release branch renames the
    section, under ``[0.2.0]`` from then on, on that branch and later on main."""
    changelog = _read("CHANGELOG.md")
    heading = "## [0.2.0]" if "## [0.2.0]" in changelog else "## [Unreleased]"
    section = changelog.split(heading, 1)[1].split("\n## [", 1)[0]
    first_heading = re.search(r"^### (.+)$", section, re.MULTILINE).group(1)
    assert first_heading == "Summary for users of the classical core"
    summary = section.split("### Fixed", 1)[0]
    assert "docs/stability.md" in summary and "performance claim" in summary
    assert "This will be" not in summary  # these words are published as the release notes


def test_a_final_version_states_its_release_date_once_and_the_same_everywhere():
    """A final version names its release date in ``CITATION.cff``, the day of the heading of its
    changelog section; a development or candidate version names none (RELEASING.md, step 4)."""
    if re.fullmatch(r"\d+\.\d+\.\d+", VERSION):
        heading = re.search(rf"^## \[{re.escape(VERSION)}\] — (\d{{4}}-\d{{2}}-\d{{2}})$",
                            _read("CHANGELOG.md"), re.MULTILINE)
        assert heading is not None, f"no dated section for {VERSION}"
        assert str(CITATION["date-released"]) == heading.group(1)
    else:
        assert "date-released" not in CITATION


def test_each_version_has_one_section_in_the_changelog():
    """The release notes are the first ``## [X.Y.Z]`` section: a second one for the same
    version would be silently left out of them, and of the date check above."""
    headings = re.findall(r"^## \[([^\]]+)\]", _read("CHANGELOG.md"), re.MULTILINE)
    assert headings and len(headings) == len(set(headings)), headings
    assert headings[0] == "Unreleased" or re.fullmatch(r"\d+\.\d+\.\d+", headings[0])
