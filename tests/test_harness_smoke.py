"""Smoke tests for the experiment harness against the current native ABI.

The benchmark drivers are not part of the package, but the paper's numbers come from them, so
every ``(mode, workload)`` they can run is executed here once, on a circuit small enough to be
instant, and compared with an independent reference. A stale ``.so`` or a changed return shape
fails here instead of in a long campaign.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmarks"))

import matched

from symq import Circuit, has_native, make_algebra, simulate

MODES = [mode for mode in matched.MODES if mode != "qcec"]
WORKLOADS = ["simulate", "equiv", "nonequiv"]


@pytest.fixture(scope="module")
def circuit():
    return Circuit(4).cx(0, 1).ccx(0, 1, 2).mcx(0, 1, 2, 3).x(3).cx(2, 3)


def engine_or_skip(mode: str, width: int):
    name = mode.split("/", 1)[0]
    if name == "zdd-native" and not has_native():
        pytest.skip("optional native extension unavailable")
    if name in {"polybori", "cudd-bdd", "cudd-bdd-static"}:
        from symq import external
        dependency = "cudd-bdd" if name == "cudd-bdd-static" else name
        if dependency not in external.EXTERNAL_BACKENDS:
            pytest.skip(f"{name} unavailable: {external.UNAVAILABLE.get(dependency)}")
    return matched.ENGINES[name](width)


def reference(circuit) -> tuple:
    algebra = make_algebra("truthtable", circuit.width)
    return tuple(algebra.to_anf(value) for value in simulate(circuit, algebra))


def test_the_loaded_extension_is_the_current_build():
    if not has_native():
        pytest.skip("optional native extension unavailable")
    from native_contract import EXPECTED_ABI, native_provenance

    from symq.backends.zdd_native import ABI_VERSION
    receipt = native_provenance()
    assert receipt["abi"] == ABI_VERSION == EXPECTED_ABI
    assert len(receipt["source_sha256"]) == len(receipt["binary_sha256"]) == 64


@pytest.mark.parametrize("mode", MODES)
def test_simulate_matches_the_reference_in_every_mode(mode, circuit):
    engine = engine_or_skip(mode, circuit.width)
    gates = matched.compile_for(mode, circuit)
    outputs = matched.run_mode(mode, engine, circuit, gates)
    assert len(outputs) == circuit.width
    expected = reference(circuit)
    algebra = engine.algebra
    assert [algebra.to_anf(value) for value in outputs] == list(expected)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("workload", ["equiv", "nonequiv"])
def test_verdicts_match_the_reference_in_every_mode(mode, workload, circuit):
    engine = engine_or_skip(mode, circuit.width)
    other = matched.prepare(circuit, "smoke", workload)
    gates = matched.compile_for(mode, circuit)
    other_gates = matched.compile_for(mode, other)
    phases, _, _, verdict = matched.one_run(mode, circuit, other, gates, other_gates,
                                           engine=engine)
    assert phases["compute"] > 0
    assert verdict["equivalent"] is (workload == "equiv")
    if workload == "nonequiv":
        witness = verdict["witness"]
        assert witness is not None and circuit.run(witness) != other.run(witness)


def test_the_fused_result_is_unpacked_and_width_checked(circuit):
    engine = engine_or_skip("zdd-native/fused", circuit.width)
    gates = matched.compile_for("zdd-native/fused", circuit)
    result = engine.algebra.manager.simulate(list(engine.state), *gates)
    assert isinstance(result, tuple) and len(result) == 3
    roots, peak_terms, products = result
    assert len(roots) == circuit.width and products > 0
    assert peak_terms is None or peak_terms >= 1
    assert matched.fused_simulate(engine, circuit, gates) == list(roots)


def test_an_inconsistent_root_count_is_detected(circuit, monkeypatch):
    engine = engine_or_skip("zdd-native/fused", circuit.width)
    gates = matched.compile_for("zdd-native/fused", circuit)
    real = engine.algebra.manager.simulate

    class Short:
        def simulate(self, *args, **kwargs):
            roots, peak, products = real(*args, **kwargs)
            return list(roots)[:-1], peak, products

    monkeypatch.setattr(engine.algebra, "manager", Short())
    with pytest.raises(RuntimeError, match="does not match this harness"):
        matched.fused_simulate(engine, circuit, gates)


@pytest.mark.parametrize("bad", ([0, 1], ([0, 1], None, -1), ([0, True], None, 0),
                                ([0, 1], -1, 0), ([0, 1], None, "2")))
def test_legacy_shapes_and_invalid_counters_fail_closed(bad):
    from native_contract import unpack_simulation
    with pytest.raises(RuntimeError, match="does not match this harness"):
        unpack_simulation(bad, 2)


@pytest.mark.parametrize("abi", (None, 3, 4, 6))
def test_incompatible_abi_is_refused(abi):
    from types import SimpleNamespace

    from native_contract import native_provenance
    with pytest.raises(RuntimeError, match="incompatible native ABI"):
        native_provenance(module=SimpleNamespace(ABI_VERSION=abi))


def test_source_or_binary_change_invalidates_provenance(tmp_path):
    import hashlib
    import json
    from types import SimpleNamespace

    from native_contract import EXPECTED_ABI, native_provenance
    folder = tmp_path / "src" / "symq" / "backends"
    folder.mkdir(parents=True)
    source, binary = folder / "_zdd.c", folder / "_zdd.test.so"
    source.write_bytes(b"source")
    binary.write_bytes(b"binary")
    receipt = {"schema": "symq/native-build/v1",
               "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
               "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest()}
    Path(str(binary) + ".build.json").write_text(json.dumps(receipt))
    module = SimpleNamespace(ABI_VERSION=EXPECTED_ABI, __file__=str(binary))
    assert native_provenance(root=tmp_path, module=module)["abi"] == EXPECTED_ABI
    source.write_bytes(b"changed")
    with pytest.raises(RuntimeError, match="provenance mismatch"):
        native_provenance(root=tmp_path, module=module)
    source.write_bytes(b"source")
    binary.write_bytes(b"changed")
    with pytest.raises(RuntimeError, match="provenance mismatch"):
        native_provenance(root=tmp_path, module=module)


def test_invalid_backend_driver_is_refused(circuit):
    engine = engine_or_skip("sparse/algebra", circuit.width)
    with pytest.raises(ValueError, match="unsupported"):
        matched.run_mode("sparse/fused", engine, circuit, None)


def test_fused_preserves_term_and_node_limits(circuit):
    from symq import Budget, ResourceLimitExceeded
    from symq.resources import Guard
    engine = engine_or_skip("zdd-native/fused", circuit.width)
    engine.algebra.bind_guard(Guard(Budget(max_nodes=engine.algebra.node_count)))
    with pytest.raises(ResourceLimitExceeded, match="nodes"):
        matched.fused_simulate(engine, circuit, matched.compile_for("zdd-native/fused", circuit))
    engine.algebra = make_algebra("zdd-native", circuit.width, Budget(max_terms=1))
    engine.state = [engine.algebra.variable(q) for q in range(circuit.width)]
    outputs = matched.fused_simulate(engine, circuit, matched.compile_for("zdd-native/fused", circuit))
    # The compact graph is node-bounded; max_terms bounds explicit ANF export.
    with pytest.raises(ResourceLimitExceeded, match="terms"):
        for root in outputs:
            engine.algebra.to_anf(root)
    with pytest.raises(ResourceLimitExceeded, match="seconds"):
        engine.algebra.bind_guard(Guard(Budget(max_seconds=1e-12)))
        matched.fused_simulate(engine, circuit, matched.compile_for("zdd-native/fused", circuit))


@pytest.mark.parametrize("workload", WORKLOADS)
def test_qcec_declared_workloads(workload, circuit):
    from symq import external
    if external.qcec_check_computations is None:
        pytest.skip("optional QCEC unavailable")
    other = matched.prepare(circuit, "smoke", workload)
    result = matched.qcec_worker({"repetitions": 1, "timeout": 5, "workload": workload},
                                 circuit, other, {})
    assert result["status"] == ("not_applicable" if workload == "simulate" else "ok")
