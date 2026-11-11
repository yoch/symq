"""The README published on PyPI has no dead link.

PyPI renders the long description away from the repository: a relative link there leads
nowhere. The build rewrites them to the file on GitHub at the tag of the version being built
(``tools/pypi_readme.py``, wired in ``hatch_build.py``).
"""
from __future__ import annotations

import pytest

from tests.conftest import ROOT
from tools.pypi_readme import REPOSITORY, absolute_links, main, relative_targets, release_ref

README = (ROOT / "README.md").read_text(encoding="utf-8")


@pytest.mark.parametrize(("version", "ref"), [
    ("0.2.0", "v0.2.0"), ("1.10.3", "v1.10.3"), ("0.2.0rc1", "v0.2.0rc1"), ("0.2.1.post1", "v0.2.1.post1"),
    ("0.2.0.dev0", "main"), ("0.3.0.dev12", "main"), ("0.2.0+local", "main"), ("0+unknown", "main"),
])
def test_a_release_points_to_its_tag_and_a_development_version_to_the_branch(version, ref):
    assert release_ref(version) == ref


def test_relative_links_become_absolute_and_nothing_else_changes():
    lines = [
        "See [the guide](docs/guide/sat.md#contracts), [license](LICENSE) and [here](./docs/index.md).",
        "[anchor](#quick-start) [site](https://example.org/a.md) [mail](mailto:a@example.org)",
        "![badge](https://img.shields.io/x.svg) plain (parentheses) and [brackets] stay",
        "```python",
        "values[index](docs/not-a-link.md)",
        "```",
    ]
    rewritten = absolute_links("\n".join(lines), "v0.2.0")
    base = f"{REPOSITORY}/blob/v0.2.0"
    assert rewritten.split("\n") == [
        (f"See [the guide]({base}/docs/guide/sat.md#contracts), [license]({base}/LICENSE) "
         f"and [here]({base}/docs/index.md)."),
        "[anchor](#quick-start) [site](https://example.org/a.md) [mail](mailto:a@example.org)",
        "![badge](https://img.shields.io/x.svg) plain (parentheses) and [brackets] stay",
        "```python",
        "values[index](docs/not-a-link.md)",
        "```",
    ]
    assert relative_targets(rewritten) == []
    assert absolute_links(rewritten, "v0.2.0") == rewritten  # idempotent


@pytest.mark.parametrize("target", ["../other/file.md", "/etc/passwd", "docs/../../x.md"])
def test_a_link_out_of_the_repository_is_refused(target):
    with pytest.raises(ValueError, match="leaves the repository"):
        absolute_links(f"[x]({target})", "main")


def test_every_relative_link_of_the_readme_names_an_existing_file():
    targets = relative_targets(README)
    assert len(targets) > 20  # the README really has relative links: the rewrite matters
    missing = [target for target in targets if not (ROOT / target.split("#")[0]).exists()]
    assert not missing


def test_the_published_readme_has_no_relative_link_and_keeps_its_text():
    published = absolute_links(README, "v0.2.0")
    assert relative_targets(published) == []
    assert published.count("](") == README.count("](")
    assert len(published.splitlines()) == len(README.splitlines())
    assert f"]({REPOSITORY}/blob/v0.2.0/docs/getting-started.md)" in published


def test_the_build_publishes_the_rewritten_readme():
    """The metadata hatchling computes for this project carries the rewritten text."""
    pytest.importorskip("hatchling")
    from hatchling.metadata.core import ProjectMetadata
    from hatchling.plugin.manager import PluginManager

    metadata = ProjectMetadata(str(ROOT), PluginManager())
    readme = metadata.core.readme
    assert metadata.core.readme_content_type == "text/markdown"
    assert relative_targets(readme) == []
    assert readme == absolute_links(README, release_ref(metadata.version))


def test_the_check_reads_built_distributions(tmp_path, capsys):
    import tarfile
    import zipfile

    good = "Metadata-Version: 2.4\nName: demo\n\n[a](https://example.org) [b](#x)\n"
    bad = "Metadata-Version: 2.4\nName: demo\n\n[a](docs/index.md)\n"
    wheel = tmp_path / "demo-1-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("demo-1.dist-info/METADATA", good)
    sdist = tmp_path / "demo-1.tar.gz"
    (tmp_path / "PKG-INFO").write_text(bad, encoding="utf-8")
    with tarfile.open(sdist, "w:gz") as archive:
        archive.add(tmp_path / "PKG-INFO", arcname="demo-1/PKG-INFO")
    assert main(["--check", str(wheel)]) == 0
    assert main(["--check", str(wheel), str(sdist)]) == 1
    assert "docs/index.md" in capsys.readouterr().err
    empty = tmp_path / "empty-1-py3-none-any.whl"
    with zipfile.ZipFile(empty, "w") as archive:
        archive.writestr("empty-1.dist-info/METADATA", "Metadata-Version: 2.4\nName: empty\n")
    assert main(["--check", str(empty)]) == 1
