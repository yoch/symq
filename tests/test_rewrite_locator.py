"""Exact-cut locator tests: partial maps and duplicate spans are never auto-authorized."""
from __future__ import annotations

import json

import pytest

from symq import Circuit
from symq.__main__ import main
from symq.experimental.hybrid import HOp, HybridProgram
from symq.experimental.serialization import program_to_dict
from symq.labs.channel_composition import HybridFragment
from symq.labs.rewrite_locator import locate_exact
from symq.labs.rewrite_request import fragment_to_dict


def _classical_pair():
    local = Circuit(3).ccx(0, 1, 2).cx(2, 0)
    prefix = Circuit(7).x(0)
    block = Circuit(7).ccx(4, 1, 6).cx(6, 4)
    suffix = Circuit(7).cx(0, 2)
    source = Circuit(7, prefix.gates + block.gates + suffix.gates)
    return source, local


def test_exact_injective_map_and_true_span_are_detected():
    source, local = _classical_pair()
    report = locate_exact(source, local)
    assert report["status"] == "unique"
    assert report["advisory_only"] is True
    assert report["theorem"] == "classical"
    assert report["matches"] == [{
        "span": [1, 3], "wires": [4, 1, 6],
        "unmapped_local_wires": [], "mapping_complete": True,
    }]
    assert len(report["source_sha256"]) == len(report["reference_pattern_sha256"]) == 64
    assert "candidate" not in report


def test_two_matches_are_ambiguous_even_when_their_maps_agree():
    source, local = _classical_pair()
    source = Circuit(source.width, list(source.gates[1:3] + source.gates[1:3]))
    report = locate_exact(source, local)
    assert report["status"] == "ambiguous"
    assert [x["span"] for x in report["matches"]] == [[0, 2], [2, 4]]


def test_unused_local_wires_are_not_invented():
    local = Circuit(4).ccx(0, 1, 2)
    source = Circuit(7).ccx(4, 1, 6)
    report = locate_exact(source, local)
    assert report["status"] == "unmapped_wires"
    assert report["matches"][0]["wires"] == [4, 1, 6, None]
    assert report["matches"][0]["unmapped_local_wires"] == [3]


def test_gate_mismatch_is_never_commuted_or_guessed():
    source, _ = _classical_pair()
    changed = Circuit(3).ccx(0, 1, 2).cx(1, 0)
    report = locate_exact(source, changed)
    assert report["status"] == "not_found"
    assert report["matches"] == []


def test_measured_fragment_matches_records_exactly_without_a_channel_claim():
    source = HybridProgram(5, 0, [
        HOp("reset", (4,)), HOp("measure_z", (4,), slot="b0"),
        HOp("cz", (0, 1), condition="b0"),
    ])
    local = HybridFragment(3, (
        HOp("measure_z", (2,), slot="b0"),
        HOp("cz", (0, 1), condition="b0"),
    ))
    record = locate_exact(source, local)
    assert record["status"] == "unique"
    assert record["matches"][0]["span"] == [1, 3]
    assert record["matches"][0]["wires"] == [0, 1, 4]
    assert record["advisory_only"]
    wrong = HybridFragment(3, (
        HOp("measure_z", (2,), slot="b1"),
        HOp("cz", (0, 1), condition="b1"),
    ))
    assert locate_exact(source, wrong)["status"] == "not_found"


def test_bad_local_grammar_or_oversized_scan_fails_closed():
    source, local = _classical_pair()
    with pytest.raises(ValueError, match="empty reference"):
        locate_exact(source, Circuit(3))
    with pytest.raises(ValueError, match="max_compares"):
        locate_exact(source, local, max_compares=1)
    with pytest.raises(ValueError, match="max_candidates"):
        locate_exact(source, local, max_candidates=0)


def test_cli_classical_locate_emits_parseable_advisory_and_no_implicit_rewrite(tmp_path, capsys):
    source, local = _classical_pair()
    original = tmp_path / "source.json"
    target = tmp_path / "reference.json"
    original.write_text(json.dumps(source.to_dict()))
    target.write_text(json.dumps(local.to_dict()))
    code = main(["locate", str(original), str(target), "--theorem", "classical"])
    report = json.loads(capsys.readouterr().out)
    assert code == 0
    assert report["kind"] == "symq_rewrite_locations"
    assert report["status"] == "unique"
    assert report["matches"][0]["wires"] == [4, 1, 6]
    assert len(report["source_file_sha256"]) == 64
    assert len(report["reference_file_sha256"]) == 64
    assert report["advisory_only"]
    assert not list(tmp_path.glob("*proof*"))


def test_cli_reports_multiple_spans_without_picking_one(tmp_path, capsys):
    source, local = _classical_pair()
    block = source.gates[1:3]
    p = tmp_path / "source.json"
    q = tmp_path / "reference.json"
    p.write_text(json.dumps(Circuit(7, block + block).to_dict()))
    q.write_text(json.dumps(local.to_dict()))
    assert main(["locate", str(p), str(q), "--theorem", "classical"]) == 2
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "ambiguous"
    assert len(out["matches"]) == 2


def test_cli_hmr_locator_preserves_observed_record_names(tmp_path, capsys):
    source = HybridProgram(5, 0, [
        HOp("reset", (4,)), HOp("measure_z", (4,), slot="b0"),
        HOp("cz", (0, 1), condition="b0"),
    ])
    fragment = HybridFragment(3, (
        HOp("measure_z", (2,), slot="b0"),
        HOp("cz", (0, 1), condition="b0"),
    ))
    p = tmp_path / "hybrid.json"
    q = tmp_path / "fragment.json"
    p.write_text(json.dumps(program_to_dict(source)))
    q.write_text(json.dumps(fragment_to_dict(fragment)))
    assert main(["locate", str(p), str(q), "--theorem", "coherent"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["matches"][0]["wires"] == [0, 1, 4]
    assert report["advisory_only"]


def test_cli_invalid_source_or_reference_is_json_not_traceback(tmp_path, capsys):
    assert main(["locate", str(tmp_path / "missing.json"), "unknown.json",
                 "--theorem", "classical"]) == 3
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "invalid"
    assert report["matches"] == []
