"""What gets published is what the project says it supports.

The wheel matrix lives in ``[tool.cibuildwheel]``; these guards keep it consistent with the
classifiers and with the files it names, without building anything.
"""
from __future__ import annotations

import re
import tomllib

from tests.conftest import ROOT

PROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
WHEELS = PROJECT["tool"]["cibuildwheel"]


def test_one_wheel_per_supported_python():
    classifiers = PROJECT["project"]["classifiers"]
    declared = sorted(re.fullmatch(r"Programming Language :: Python :: (3\.\d+)", line).group(1)
                      for line in classifiers
                      if re.fullmatch(r"Programming Language :: Python :: 3\.\d+", line))
    built = sorted(f"3.{tag[3:-2]}" for tag in WHEELS["build"].split())
    assert built == declared
    assert PROJECT["project"]["requires-python"] == f">={declared[0]}"


def test_no_wheel_is_built_where_the_core_cannot_be():
    skip = WHEELS["skip"]
    assert "cp3??t-*" in skip   # free-threaded: the C core refuses to compile there
    assert "*-win*" in skip     # Windows: not ported to MSVC, the pure-Python wheel serves it
    assert WHEELS["environment"]["SYMQ_REQUIRE_NATIVE"] == "1"


def test_the_wheel_test_command_names_existing_tests_and_demands_the_core():
    command = WHEELS["test-command"]
    assert command.startswith("symq doctor --require-native && ")
    files = re.findall(r"\{project\}/(\S+)", command)
    assert len(files) >= 4
    for file in files:
        assert (ROOT / file).is_file(), file
    assert "tests/test_zdd_native.py" in files


def test_the_version_is_static_and_the_description_is_built():
    """A static version: a version read from git tags would take the archive tag for one."""
    project = PROJECT["project"]
    assert re.fullmatch(r"\d+\.\d+\.\d+(\.dev\d+|rc\d+)?", project["version"])
    assert project["dynamic"] == ["readme"]
    assert PROJECT["tool"]["hatch"]["metadata"]["hooks"]["custom"]["path"] == "hatch_build.py"
    for target in ("sdist", "wheel"):
        assert PROJECT["tool"]["hatch"]["build"]["targets"][target]["core-metadata-version"] == "2.4"


def test_the_oldest_supported_python_is_the_same_everywhere_it_is_written():
    """requires-python names the oldest Python; the linters, the CI matrices and the release's
    install check must not keep testing or targeting a Python the package no longer claims, nor
    skip the oldest one it does (3.10 left in one of them would pass every other test)."""
    import yaml

    oldest = PROJECT["project"]["requires-python"].removeprefix(">=")
    assert PROJECT["tool"]["ruff"]["target-version"] == "py" + oldest.replace(".", "")
    assert PROJECT["tool"]["mypy"]["python_version"] == oldest
    workflows = ROOT / ".github" / "workflows"
    for name, job in (("ci.yml", "test"), ("research.yml", None)):
        document = yaml.safe_load((workflows / name).read_text(encoding="utf-8"))
        jobs = [document["jobs"][job]] if job else list(document["jobs"].values())
        versions = [str(v) for j in jobs
                    for v in ((j.get("strategy") or {}).get("matrix") or {}).get("python-version", [])]
        assert versions, name
        assert min(versions, key=lambda v: tuple(map(int, v.split(".")))) == oldest, name
    release = yaml.safe_load((workflows / "release.yml").read_text(encoding="utf-8"))
    rows = release["jobs"]["install"]["strategy"]["matrix"]["include"]
    pythons = [str(row["python"]) for row in rows if not str(row["python"]).endswith("t")]
    assert min(pythons, key=lambda v: tuple(map(int, v.split(".")))) == oldest
