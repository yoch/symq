"""The recorded performance evidence is intact and the published tables are derived from it."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

from benchmarks import paired

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs" / "evidence" / "data" / "2026-10-31"
REPORT = ROOT / "docs" / "evidence" / "performance-2026-10-31.md"
ROUNDS = [DATA / "round1", DATA / "round2"]


def test_raw_records_match_their_checksums():
    lines = (DATA / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2 * len(paired.SPLITS) * len(ROUNDS)
    for line in lines:
        digest, name = line.split()
        assert hashlib.sha256((DATA / name).read_bytes()).hexdigest() == digest, name


def test_both_sides_are_single_clean_identified_builds():
    seen = paired.receipts(ROUNDS)
    for side in ("base", "head"):
        assert len(seen[side]) == 1, side
        commit, dirty, source, native, abi = next(iter(seen[side]))
        assert re.fullmatch(r"[0-9a-f]{40}", commit) and dirty is False
        assert len(source) == 64 and len(native) == 64 and abi == 6
    assert next(iter(seen["base"]))[0] != next(iter(seen["head"]))[0]


@pytest.mark.parametrize("backend", ["sat", "sparse", "zdd", "zdd-native"])
def test_published_tables_are_regenerated_from_the_records(backend):
    text = REPORT.read_text(encoding="utf-8")
    match = re.search(rf"<!-- paired:{re.escape(backend)} -->\n(.*?)\n<!-- /paired -->", text,
                      re.DOTALL)
    assert match, f"no generated table for {backend}"
    assert match.group(1).strip() == paired.table(ROUNDS, backend)


def _geomeans(rounds, backend):
    """``split -> geometric mean`` parsed from the generated table."""
    rows = paired.table(rounds, backend).splitlines()[2:]
    return {cells[1].strip(): cells[3].strip() for cells in (row.split("|") for row in rows)}


def test_numbers_quoted_in_the_prose_come_from_the_records():
    text = " ".join(REPORT.read_text(encoding="utf-8").split())
    pooled, first, second = (_geomeans(ROUNDS, "zdd"), _geomeans(ROUNDS[0], "zdd"),
                             _geomeans(ROUNDS[1], "zdd"))
    assert (f"({pooled['dev']} dev, {pooled['holdout']} holdout, {pooled['extension']} "
            "extension)") in text
    assert f"round 2 gives {second['dev']}, {second['holdout']} and {second['extension']}" in text
    assert f"round 1 gives {first['dev']}, {first['holdout']} and {first['extension']}" in text
    holdout = {round_: [float(_geomeans(directory, backend)["holdout"])
                        for backend in ("sparse", "zdd", "zdd-native")]
               for round_, directory in zip((1, 2), ROUNDS)}
    low, high = (round(100 * (value - 1)) for value in (min(holdout[1]), max(holdout[1])))
    assert f"looked {low}–{high} % slower on the holdout split" in text
    assert f"found ratios of {min(holdout[2]):.2f}–{max(holdout[2]):.2f} there" in text


SINGLE_SAMPLE = {
    "dev": {("c2_181", "equiv", "sparse")},
    "synthetic": {("random_14x60_1", "equiv", "zdd"), ("random_14x60_1", "nonequiv", "zdd"),
                  ("random_14x60_1", "simulate", "sparse"), ("random_14x60_1", "simulate", "zdd"),
                  ("random_14x90_2", "simulate", "zdd-native")},
}


def test_single_sample_cells_are_the_ones_the_report_names():
    import json

    for directory in ROUNDS:
        for path in sorted(directory.glob("*.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            single = {(row["circuit"], row["workload"], row["backend"]) for row in record["rows"]
                      if row["status"] == "ok" and len(row["seconds"]) < record["repetitions"]}
            assert single == SINGLE_SAMPLE.get(record["split"], set()), path.name
    text = " ".join(REPORT.read_text(encoding="utf-8").split())
    assert ("`c2_181` sparse equivalence on dev; four `random_14x60_1` cells and "
            "`random_14x90_2` native simulation on synthetic") in text


def test_records_contain_no_absolute_paths():
    for path in sorted(DATA.parent.rglob("*.json")):
        text = path.read_text(encoding="utf-8")
        assert '": "/' not in text and "/home/" not in text and "/tmp/" not in text, path.name


def test_the_summary_refuses_records_from_different_machines(tmp_path):
    import json
    import shutil

    for directory in ROUNDS:
        shutil.copytree(directory, tmp_path / directory.name)
    head = tmp_path / "round2" / "dev-head.json"
    record = json.loads(head.read_text(encoding="utf-8"))
    record["environment"]["cpu_model"] = "another machine"
    head.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError, match="different machines"):
        paired.table([tmp_path / "round1", tmp_path / "round2"], "sat")
    base = tmp_path / "round2" / "dev-base.json"
    base.write_text(json.dumps(record), encoding="utf-8")  # now both sides match, round 1 differs
    with pytest.raises(ValueError, match="rounds were measured on different machines"):
        paired.table([tmp_path / "round1", tmp_path / "round2"], "sat")


PILOT = ROOT / "docs" / "evidence" / "data" / "2026-11-01"
PILOT_PAGE = ROOT / "docs" / "evidence" / "comparative-pilot-2026-11-01.md"


def _pilot(name):
    import json

    return json.loads((PILOT / name).read_text(encoding="utf-8"))


def test_pilot_records_match_their_checksums_and_name_a_clean_build():
    for line in (PILOT / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, name = line.split()
        assert hashlib.sha256((PILOT / name).read_bytes()).hexdigest() == digest, name
    for name in ("coverage.json", "paired.json"):
        record = _pilot(name)
        assert record["source_unchanged"] is True
        before = record["source_before"]
        assert before == record["source_after"] and before["git_dirty"] is False
        assert re.fullmatch(r"[0-9a-f]{40}", before["git_commit"])
        assert before["git_commit"] in PILOT_PAGE.read_text(encoding="utf-8")


def test_pilot_tables_and_quoted_numbers_come_from_the_record():
    from benchmarks.comparative_report import render

    page = PILOT_PAGE.read_text(encoding="utf-8")
    rendered = render(_pilot("paired.json"))
    for marker in ("cases", "ratios"):
        block = re.search(rf"<!-- comparative:{marker} -->\n(.*?)\n<!-- /comparative -->", page,
                          re.DOTALL).group(1)
        assert block in rendered
    ratios = {}
    for row in re.findall(r"^\| (\S+) \| (\w[\w-]*) / (\w[\w-]*) decision wall seconds \| 15 \| "
                          r"([0-9.]+) \|", rendered, re.MULTILINE):
        ratios.setdefault(row[1], []).append(float(row[3]))
    sat, zdd = ratios["sat"], ratios["zdd"]
    text = " ".join(page.split())
    assert f"{min(sat):.1f} to {max(sat):.1f} times QCEC" in text
    assert f"{min(zdd):.1f} to {max(zdd):.1f} times the Kraus oracle" in text
    coverage, paired = _pilot("coverage.json"), _pilot("paired.json")
    assert coverage["qualification_counts"] == {"matched": coverage["eligible_trials"]} \
        and f"**{coverage['eligible_trials']} of {coverage['eligible_trials']}**" in page
    assert paired["qualification_counts"] == {"matched": paired["eligible_trials"]} \
        and f"**{paired['eligible_trials']} of {paired['eligible_trials']}**" in page
