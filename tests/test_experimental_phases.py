"""Small exhaustive domains and a separate dense Kraus oracle for dyadic phases."""
from __future__ import annotations

import cmath
import itertools
import math
import random
from fractions import Fraction
from types import SimpleNamespace

import pytest

from symq.anf import ANF
from symq.circuit import UnsupportedOperation
from symq.experimental import qcec as adapter
from symq.experimental.cyclotomic import (
    Cyclotomic,
    CyclotomicProgram,
    QuantumGate,
    ReferenceLimits,
    affine_event_factor,
    channel_semantics,
    check_channel_equivalence,
)
from symq.experimental.phase import (
    PhaseGate,
    PhaseProgram,
    check_equivalence,
    eval_phase,
    lift_anf,
    symbolic,
)
from symq.resources import Budget, ResourceLimitExceeded, VerificationSession


@pytest.mark.parametrize("k", [1, 2, 3, 4, 5])
def test_every_three_bit_boolean_function_lifts_exactly(k):
    for support in range(256):
        fn = ANF(frozenset(mask for mask in range(8) if support >> mask & 1))
        lifted = lift_anf(fn, k=k)
        for x in range(8):
            assert eval_phase(lifted, x, k=k) == fn.evaluate(x)


@pytest.mark.parametrize("k", [3, 4, 5, 6])
def test_dyadic_symbolic_matches_integer_execution(k):
    rng = random.Random(0xD1AD + k)
    for _ in range(50):
        p = PhaseProgram(3, k=k)
        for _ in range(12):
            name = rng.choice(["phase", "x", "cx", "ccx"])
            if name == "phase":
                p.phase(rng.randrange(3), Fraction(rng.randrange(-(1 << k), 1 << k), 1 << k))
            else:
                arity = {"x": 1, "cx": 2, "ccx": 3}[name]
                p.append(name, *rng.sample(range(3), arity))
        result = symbolic(p)
        assert [result.run(x) for x in range(8)] == [p.run(x) for x in range(8)]


def test_cross_modulus_global_phase_and_relative_phase_mutants():
    a = PhaseProgram(2, k=4).cx(0, 1).phase(1, Fraction(1, 16))
    b = PhaseProgram(2, k=4).phase(0, Fraction(1, 16)).phase(1, Fraction(1, 16)).cx(0, 1)
    assert check_equivalence(a, b).status == "different"
    a = PhaseProgram(1, k=5).x(0).phase(0, Fraction(3, 32)).x(0).phase(0, Fraction(3, 32))
    verdict = check_equivalence(a, PhaseProgram(1))
    assert (verdict.status, verdict.k, verdict.global_phase_exponent) == ("global_phase", 5, 3)
    assert check_equivalence(PhaseProgram(1).t(0),
                             PhaseProgram(1, k=5).phase(0, Fraction(1, 8))).status == "equal"
    assert check_equivalence(PhaseProgram(1).t(0),
                             PhaseProgram(1, k=5).phase(0, Fraction(5, 32))).status == "different"


@pytest.mark.parametrize("angle", [0.125, Fraction(1, 3), Fraction(1, 32), True])
def test_non_exact_or_unrepresentable_angles_fail_closed(angle):
    with pytest.raises(UnsupportedOperation):
        PhaseProgram(1, k=4).phase(0, angle)


def test_phase_intermediates_and_mutated_instructions_are_guarded():
    with pytest.raises(ResourceLimitExceeded):
        symbolic(PhaseProgram(2, k=5).cx(0, 1).phase(1, Fraction(1, 32)), Budget(max_terms=2))
    with pytest.raises(ResourceLimitExceeded):
        lift_anf(ANF(frozenset([1, 2, 4])), Budget(max_terms=3).start(), k=5)
    p = PhaseProgram(1)
    p.gates.append(PhaseGate("x", (2,)))
    with pytest.raises(UnsupportedOperation):
        symbolic(p)
    with pytest.raises(ValueError, match="max_nodes"):
        symbolic(PhaseProgram(1), Budget(max_nodes=1))


def _multiply_matrix(a, b):
    n = len(a)
    return [[sum(a[i][r] * b[r][j] for r in range(n)) for j in range(n)] for i in range(n)]


def _dense_oracle(program):
    """Independent floating dense matrices; no symbolic/cyclotomic operations."""
    n = 1 << program.width
    identity = [[complex(i == j) for j in range(n)] for i in range(n)]
    branches = [((), identity)]
    turns = {"z": .5, "cz": .5, "ccz": .5, "s": .25, "sdg": -.25,
             "t": .125, "tdg": -.125}
    for gate in program.gates:
        following = []
        for outcomes, matrix in branches:
            for measured in ((0, 1) if gate.name == "hmr" else (None,)):
                layer = [[0j for _ in range(n)] for _ in range(n)]
                for basis in range(n):
                    if gate.name in {"h", "hmr"}:
                        q = gate.wires[0]
                        bit = basis >> q & 1
                        for b in ((0, 1) if gate.name == "h" else (measured,)):
                            y = (basis & ~(1 << q)) | ((b if gate.name == "h" else 0) << q)
                            layer[y][basis] += (-1 if bit * b else 1) / math.sqrt(2)
                    elif gate.name in {"x", "cx", "ccx", "mcx"}:
                        *controls, target = gate.wires
                        y = basis ^ (1 << target) if all(basis >> q & 1 for q in controls) else basis
                        layer[y][basis] = 1
                    else:
                        active = all(basis >> q & 1 for q in gate.wires)
                        if gate.name == "phase_if":
                            active = active and bool(outcomes[gate.outcome])
                        angle = float(gate.angle) if gate.name in {"phase", "phase_if"} \
                            else turns[gate.name]
                        layer[basis][basis] = cmath.exp(2j * math.pi * angle) if active else 1
                following.append((outcomes + (measured,) if measured is not None else outcomes,
                                  _multiply_matrix(layer, matrix)))
        branches = following
    return {(x, xp, y, yp): sum(m[y][x] * m[yp][xp].conjugate() for _, m in branches)
            for x, xp, y, yp in itertools.product(range(n), repeat=4)}


def _assert_dense_matches(program):
    exact = channel_semantics(program)
    for key, value in _dense_oracle(program).items():
        assert abs(exact.coefficient(*key).approximate() - value) < 2e-12, (program, key)


def test_exhaustive_one_wire_h_t_hmr_words_against_dense_kraus():
    for size in range(4):
        for word in itertools.product(["x", "h", "t", "tdg", "hmr"], repeat=size):
            p = CyclotomicProgram(1)
            for name in word:
                if name == "hmr":
                    p.hmr(0)
                else:
                    p.append(name, 0)
            _assert_dense_matches(p)


def test_random_two_wire_channels_and_feed_forward_against_dense_kraus():
    rng = random.Random(0xC1C10)
    for _ in range(35):
        p = CyclotomicProgram(2, k=4)
        events = []
        for _ in range(7):
            name = rng.choice(["x", "h", "cx", "cz", "hmr", "phase", "phase_if"])
            q = rng.randrange(2)
            if name == "hmr":
                events.append(p.hmr(q))
            elif name == "phase_if" and events:
                p.phase_if(rng.choice(events), q, Fraction(3, 16))
            elif name in {"phase", "phase_if"}:
                p.phase(q, Fraction(1, 16))
            elif name in {"cx", "cz"}:
                p.append(name, q, 1 - q)
            else:
                p.append(name, q)
        _assert_dense_matches(p)


def test_exact_field_hadamard_identities_and_channel_mutants():
    z = Cyclotomic.root(3, 1)
    assert z * z * z * z == -Cyclotomic.root(3)
    assert check_channel_equivalence(CyclotomicProgram(1).h(0).h(0), CyclotomicProgram(1)).equivalent
    assert check_channel_equivalence(CyclotomicProgram(1).h(0).z(0).h(0),
                                     CyclotomicProgram(1).x(0)).equivalent
    assert not check_channel_equivalence(CyclotomicProgram(1).h(0).t(0).h(0),
                                         CyclotomicProgram(1).t(0)).equivalent
    p = CyclotomicProgram(1)
    p.hmr(0)
    assert channel_semantics(p).coefficient(0, 1, 0, 0) == Cyclotomic(3)
    assert not check_channel_equivalence(p, CyclotomicProgram(1)).equivalent
    # Any global phase vanishes in the channel, including non-real ones.
    global_phase = CyclotomicProgram(1).x(0).t(0).x(0).t(0)
    assert check_channel_equivalence(global_phase, CyclotomicProgram(1)).equivalent


@pytest.mark.parametrize("k", [1, 2, 3, 4, 5])
def test_affine_event_factor_matches_complete_sum(k):
    rng = random.Random(0xAFF1 + k)
    for _ in range(80):
        # Variable 0 is data, variables 1 and 2 are discarded events.
        phase = {mask: rng.randrange(1 << k) for mask in [0, 1, 2, 3, 4, 5]}
        for data in range(2):
            actual = affine_event_factor(phase, (1, 2), data, k=k)
            expected = Cyclotomic(max(3, k))
            for events in range(4):
                x = data | events << 1
                exponent = sum(c for m, c in phase.items() if x & m == m) % (1 << k)
                expected += Cyclotomic.root(max(3, k), exponent << (max(3, k) - k))
            assert actual == expected.scale(Fraction(1, 4))


def test_non_real_affine_factor_is_not_a_boolean_kernel_and_nonlinearity_refused():
    value = affine_event_factor({1: 1}, (0,))
    assert value != Cyclotomic(3)
    assert value != Cyclotomic.root(3)
    assert value == (Cyclotomic.root(3) + Cyclotomic.root(3, 1)).scale(Fraction(1, 2))
    with pytest.raises(UnsupportedOperation, match="nonlinear"):
        affine_event_factor({3: 1}, (0, 1))


def test_cyclotomic_reference_resource_and_grammar_limits():
    with pytest.raises(ResourceLimitExceeded, match="width"):
        channel_semantics(CyclotomicProgram(5))
    with pytest.raises(ResourceLimitExceeded, match="k"):
        channel_semantics(CyclotomicProgram(1, k=9))
    with pytest.raises(ResourceLimitExceeded, match="terms"):
        channel_semantics(CyclotomicProgram(1).h(0), Budget(max_terms=1))
    with pytest.raises(ResourceLimitExceeded, match="entries"):
        channel_semantics(CyclotomicProgram(2).h(0).h(1), limits=ReferenceLimits(max_entries=2))
    with pytest.raises(ValueError, match="max_nodes"):
        channel_semantics(CyclotomicProgram(1), Budget(max_nodes=1))
    p = CyclotomicProgram(1)
    with pytest.raises(UnsupportedOperation, match="earlier"):
        p.phase_if(0, 0, Fraction(1, 8))
    assert not p.gates
    p.gates.append(QuantumGate("hmr", (0,), outcome=True))
    with pytest.raises(UnsupportedOperation, match="sequential"):
        channel_semantics(p)


def test_all_phase_engines_inherit_outer_session_deadline(monkeypatch):
    from symq import resources
    clock = [100.0]
    monkeypatch.setattr(resources.time, "perf_counter", lambda: clock[0])
    with VerificationSession(Budget(max_seconds=1)):
        symbolic(PhaseProgram(1))
        clock[0] += 2
        with pytest.raises(ResourceLimitExceeded, match="seconds"):
            channel_semantics(CyclotomicProgram(1))
        clock[0] = 100.0


def test_qcec_is_optional_and_unitary_grammar_is_checked_before_import(monkeypatch):
    def missing():
        raise ModuleNotFoundError("No module named 'mqt'")
    monkeypatch.setattr(adapter, "_external", missing)
    with pytest.raises(ModuleNotFoundError, match="mqt"):
        adapter.check_unitary_equivalence(CyclotomicProgram(1).h(0), CyclotomicProgram(1),
                                          up_to_global=True)
    p = CyclotomicProgram(1)
    p.hmr(0)
    with pytest.raises(UnsupportedOperation, match="unitary"):
        adapter.check_unitary_equivalence(p, p, up_to_global=True)
    with pytest.raises(UnsupportedOperation, match="named"):
        adapter.check_unitary_equivalence(PhaseProgram(1, k=4).phase(0, Fraction(1, 16)),
                                          PhaseProgram(1), up_to_global=True)


@pytest.mark.parametrize(("verdict", "allow", "expected"), [
    ("equivalent", False, True), ("equivalent_up_to_global_phase", True, True),
    ("equivalent_up_to_global_phase", False, False), ("not_equivalent", True, False),
    ("probably_equivalent", True, None), ("no_information", False, None),
])
def test_qcec_global_phase_convention_and_inconclusive_are_explicit(monkeypatch, verdict, allow,
                                                                  expected):
    calls = []
    class Computation:
        def __init__(self, width):
            self.num_qubits = width
        def h(self, q):
            calls.append(("h", q))
    def verify(a, b, *, timeout):
        assert a.num_qubits == b.num_qubits == 1
        assert 0 < timeout <= 2
        return SimpleNamespace(verdict=verdict, check_seconds=.1, preprocessing_seconds=.01)
    external = SimpleNamespace(QuantumComputation=Computation, qcec_check_computations=verify)
    monkeypatch.setattr(adapter, "_external", lambda: external)
    result = adapter.check_unitary_equivalence(CyclotomicProgram(1).h(0), CyclotomicProgram(1),
                                               up_to_global=allow, budget=Budget(max_seconds=2))
    assert result.equivalent is expected
    assert result.up_to_global is allow
    assert calls == [("h", 0)]


def test_real_optional_qcec_hadamard_and_non_real_global_phase():
    pytest.importorskip("mqt.qcec")
    hh = CyclotomicProgram(1).h(0).h(0)
    identity = CyclotomicProgram(1)
    assert adapter.check_unitary_equivalence(hh, identity, up_to_global=False).equivalent
    global_phase = CyclotomicProgram(1).x(0).t(0).x(0).t(0)
    assert adapter.check_unitary_equivalence(global_phase, identity, up_to_global=True).equivalent
    assert not adapter.check_unitary_equivalence(global_phase, identity,
                                                 up_to_global=False).equivalent
