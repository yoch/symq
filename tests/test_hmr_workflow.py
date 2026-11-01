"""P0 coherent HMR: strict JSON import, Kraus/instrument theorem, frozen replay.

All unit tests exercise research-only source-pinned Qualtran m=1/m=2
fixtures or clearly labeled synthetic counterexamples. Missing
feed-forward is invisible on classical diagonals but detectable on
off-diagonal coherences. Negative checks never export a candidate.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.hmr_qualification import hybrid, load_manifest, oracle_case, programs
from benchmarks.public_qualtran_hmr_p0 import _one_case
from symq.experimental.hybrid import HOp, HybridProgram
from symq.experimental.serialization import program_to_dict
from symq.hashing import canonical_sha256
from symq.labs.channel_composition import HybridFragment
from symq.labs.hmr_workflow import (
    _load_report,
    _source,
    fragment_to_dict,
    main,
    prove_request,
    replay_report,
)

DATA = Path(__file__).parents[1] / "benchmarks/corpus/qualtran"


def _write(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def _inputs(
    tmp_path: Path, source: HybridProgram,
    candidate: HybridFragment, *,
    clean: list[int] | None = None, preserved: list[int] | None = None,
    observed: list[str] | None = None, require_saving: bool = False,
    weights: list[list] | None = None,
    span: list[int] | None = None,
) -> Path:
    _write(tmp_path / "source.json", program_to_dict(source))
    _write(tmp_path / "replacement.json", fragment_to_dict(candidate))
    req = {
        "schema_version": 1, "kind": "symq_hmr_contextual_request",
        "source": "source.json", "replacement": "replacement.json",
        "contract": {
            "span": span if span is not None else [0, len(source.ops)],
            "wires": list(range(source.width)),
            "clean": clean or [], "preserved": preserved or [],
            "discarded": [], "discarded_global": [],
            "observed_slots": observed or [],
            "weights": {
                "unit": "synthetic_declared_gate_proxy",
                "by_kind": weights or [["ccx", 10], ["hmr", 0], ["cz", 2]],
            },
            "max_local_width": 6, "max_events": 8,
            "max_branches": 256, "require_saving": require_saving,
        },
    }
    _write(tmp_path / "request.json", req)
    return tmp_path / "request.json"


def _m1():
    data = {r["id"]: r for r in load_manifest()["cases"]}
    source, good = (hybrid(p) for p in programs(data["m1-full-none"]))
    return source, HybridFragment(source.width, tuple(good.ops))


@pytest.mark.parametrize("degree", (1, 2))
def test_public_source_gadget_full_coherent_application_and_mutant_replay(tmp_path, degree):
    positive = _one_case(tmp_path, degree, "none")
    negative = _one_case(tmp_path, degree, "missing_correction")
    assert positive["expected"] == positive["actual"] == "equivalent"
    assert positive["proven_application"]
    assert negative["expected"] == negative["actual"] == "not_proved"
    assert not negative["proven_application"]
    assert negative["offdiagonal_missing_correction"]
    assert positive["input_coherences_exhaustively_checked"] == (1 << (4 * degree))
    assert negative["input_coherences_exhaustively_checked"] == (1 << (4 * degree))

    pos_report = _load_report(tmp_path / f"m{degree}-full-none" / "hmr-proof.json")
    bad_report = _load_report(
        tmp_path / f"m{degree}-full-missing_correction" / "hmr-proof.json"
    )
    assert pos_report["result"]["checked_pairs"] == (1 << (4 * degree))
    assert pos_report["candidate"] is not None
    assert bad_report["candidate"] is None
    assert replay_report(pos_report)["result"]["outcome"] == "equivalent"
    assert replay_report(bad_report)["result"]["outcome"] == "not_proved"


def test_missing_ancilla_preparation_is_not_assumed(tmp_path):
    source, good = _m1()
    # The physical third wire is arbitrary coherent data, NOT a zero
    # ancilla; claiming it clean does not establish it at the cut.
    unprepared = HybridProgram(source.width, 0, list(source.ops))
    req = _inputs(tmp_path, unprepared, good, clean=[2], preserved=[0, 1])
    result = prove_request(req)
    assert result["result"]["outcome"] == "not_proved"
    assert result["candidate"] is None


def test_declared_operation_cost_can_refuse_a_proved_channel(tmp_path):
    source, good = _m1()
    req = _inputs(
        tmp_path, source, good, clean=[2], preserved=[0, 1],
        weights=[["ccx", 1], ["hmr", 1000], ["cz", 1000]],
        require_saving=True,
    )
    report = prove_request(req)
    assert report["result"]["outcome"] == "equivalent"
    assert report["application_status"] == "cost_policy_refused"
    assert report["candidate"] is None
    assert replay_report(report)["application_status"] == "cost_policy_refused"


def test_observed_record_is_instrument_not_channel(tmp_path):
    original = HybridProgram(2, 0, [
        HOp("reset", (1,)), HOp("measure_z", (1,), slot="b0"),
        HOp("x", (0,), condition="b0"),
    ])
    # An output-classical inversion is invisible after forgetting outcomes,
    # but changes the instrument. Same quantum operations, different record.
    candidate = HybridFragment(2, (
        HOp("reset", (1,)), HOp("measure_z", (1,), slot="b0"),
        HOp("x", (0,), condition="b0"), HOp("invert", slot="b0"),
    ))
    req = _inputs(tmp_path, original, candidate, observed=[])
    channel = prove_request(req)
    assert channel["result"]["outcome"] == "equivalent"
    doc = json.loads(req.read_text())
    doc["contract"]["observed_slots"] = ["b0"]
    _write(req, doc)
    instrument = prove_request(req)
    assert instrument["result"]["outcome"] == "not_proved"
    assert instrument["candidate"] is None

    # A trivially compensated pair is a *positive* observed-instrument
    # example: it must preserve both record and all coherent outputs.
    candidate_positive = HybridFragment(2, tuple(original.ops) + (
        HOp("x", (0,)), HOp("x", (0,)),
    ))
    _write(tmp_path / "replacement.json", fragment_to_dict(candidate_positive))
    proved = prove_request(req)
    assert proved["result"]["outcome"] == "equivalent"
    assert proved["candidate"] is not None
    assert replay_report(proved)["candidate"] == proved["candidate"]


def test_forged_positive_and_resigned_report_are_not_proof(tmp_path):
    source, good = _m1()
    correction = next(
        i for i, op in enumerate(good.ops)
        if op.kind == "cz" and op.condition is not None
    )
    bad = HybridFragment(
        good.width, good.ops[:correction] + good.ops[correction + 1:]
    )
    req = _inputs(tmp_path, source, bad, clean=[2], preserved=[0, 1])
    report = prove_request(req)
    assert report["result"]["outcome"] == "not_proved"
    report["result"]["outcome"] = "equivalent"
    report.pop("semantic_sha256")
    report["semantic_sha256"] = canonical_sha256(report)
    with pytest.raises(ValueError, match="fresh coherent proof"):
        replay_report(report)


def test_self_contained_fresh_replay_detects_source_and_cost_tampering(tmp_path):
    source, good = _m1()
    req = _inputs(tmp_path, source, good, clean=[2], preserved=[0, 1])
    report = prove_request(req)
    assert report["application_status"] == "applied_after_reproof"
    (tmp_path / "source.json").unlink()
    (tmp_path / "replacement.json").unlink()
    (tmp_path / "request.json").unlink()
    assert replay_report(report)["semantic_sha256"] == report["semantic_sha256"]

    import copy

    changed = copy.deepcopy(report)
    changed["inputs"]["contract"]["clean"] = []
    changed.pop("semantic_sha256")
    changed["semantic_sha256"] = canonical_sha256(changed)
    with pytest.raises(ValueError, match="fresh coherent proof|differs"):
        replay_report(changed)
    changed = copy.deepcopy(report)
    changed["result"]["cost"]["weighted_delta"] = 999
    changed.pop("semantic_sha256")
    changed["semantic_sha256"] = canonical_sha256(changed)
    with pytest.raises(ValueError, match="fresh coherent proof"):
        replay_report(changed)


def test_closed_parser_refuses_bad_assumptions_and_unsupported_ops(tmp_path):
    source, good = _m1()
    req = _inputs(tmp_path, source, good, clean=[2], preserved=[0, 1])
    data = json.loads(req.read_text())
    data["contract"]["classical_input_predicate"] = "basis-only"
    _write(req, data)
    with pytest.raises(ValueError, match="closed JSON"):
        prove_request(req)
    del data["contract"]["classical_input_predicate"]
    data["contract"]["wires"] = [0, 1, 1]
    _write(req, data)
    with pytest.raises(ValueError, match="wire map"):
        prove_request(req)
    data["contract"]["wires"] = [0, 1, 2]
    _write(req, data)
    doc = json.loads((tmp_path / "replacement.json").read_text())
    doc["ops"].append({"kind": "rzz", "wires": [0, 1],
                       "slot": None, "condition": None, "source": None, "value": None})
    _write(tmp_path / "replacement.json", doc)
    with pytest.raises(ValueError):
        prove_request(req)


def test_file_cli_isolated_memory_and_sha_sidecar(tmp_path, capsys):
    source, good = _m1()
    req = _inputs(tmp_path, source, good, clean=[2], preserved=[0, 1])
    dest = tmp_path / "proof.json"
    assert main(["verify", str(req), "--report", str(dest), "--timeout", "30"]) == 0
    assert dest.exists() and (tmp_path / "proof.json.sha256").exists()
    assert main(["replay", str(dest), "--timeout", "30"]) == 0
    assert "applied_after_reproof" in capsys.readouterr().out
    dest.write_text(dest.read_text().replace('"equivalent"', '"not_proved"', 1))
    with pytest.raises(ValueError, match="sidecar"):
        _load_report(dest)


def test_refuses_overwrite_and_unknown_grammar(tmp_path):
    source, good = _m1()
    req = _inputs(tmp_path, source, good, clean=[2], preserved=[0, 1])
    source_path = tmp_path / "source.json"
    initial = source_path.read_bytes()
    assert main(["verify", str(req), "--report", str(source_path),
                 "--no-isolate"]) == 3
    assert source_path.read_bytes() == initial
    doc = json.loads(req.read_text())
    doc["contract"]["max_local_width"] = 7
    _write(req, doc)
    with pytest.raises(ValueError, match="max_local_width"):
        prove_request(req)


def test_source_pinned_qualtran_input_oracle_checks_coherences():
    cases = load_manifest()["cases"]
    for row in cases:
        if row["id"] in ("m1-full-none", "m1-full-missing_correction"):
            oracle = oracle_case(row)
            assert oracle["expected_label_verified"]
            assert oracle["all_coherences_checked"] == 16
    missing = next(r for r in cases if r["id"] == "m1-full-missing_correction")
    result = oracle_case(missing)
    assert result["diagonals_equal"]
    assert result["first_witness"][0] != result["first_witness"][1]


def test_hybrid_parser_rejects_sign_only_or_non_hybrid_sources():
    with pytest.raises(ValueError):
        _source({"schema_version": 1, "kind": "sign_hmr",
                 "data": 2, "ancillas": 1, "ops": []})
