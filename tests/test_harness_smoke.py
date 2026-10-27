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

from symq import Circuit, make_algebra, simulate
from symq.backends import _zdd

MODES = ["zdd-native/fused", "zdd-native/loop", "zdd-native/loop-sorted",
         "zdd-native/algebra", "zdd-python/algebra", "sparse/algebra",
         "polybori/loop", "cudd-bdd/loop"]
WORKLOADS = ["simulate", "equiv", "nonequiv"]


@pytest.fixture(scope="module")
def circuit():
    return Circuit(4).cx(0, 1).ccx(0, 1, 2).mcx(0, 1, 2, 3).x(3).cx(2, 3)


def engine_or_skip(mode: str, width: int):
    name = mode.split("/", 1)[0]
    if name in {"polybori", "cudd-bdd"}:
        from symq import external

        if name not in external.EXTERNAL_BACKENDS:
            pytest.skip(f"{name} unavailable: {external.UNAVAILABLE.get(name)}")
    return matched.ENGINES[name](width)


def reference(circuit) -> tuple:
    algebra = make_algebra("zdd", circuit.width)
    return tuple(algebra.to_anf(value) for value in simulate(circuit, algebra))


def test_the_loaded_extension_is_the_current_build():
    module = Path(_zdd.__file__).resolve()
    assert module.is_file()
    assert _zdd.ABI_VERSION == 4
    source = (ROOT / "src" / "symq" / "backends" / "_zdd.c")
    assert source.is_file()
    assert module.stat().st_mtime >= source.stat().st_mtime - 1, (
        f"{module} is older than {source}: rebuild with 'python tools/build_native.py'")


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
