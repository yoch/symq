"""Every engine must give the same answer to the same question, and the right one.

``tests/test_equivalence.py`` checks each backend against an exhaustive oracle on fixed seeds, and
``tests/test_backends.py`` checks the ring operations. What they do not check is that the engines
agree **with each other across the whole decision surface**: the symbolic backends, the SAT
miter, the ``verify`` facade and the command line, on inputs that Hypothesis can shrink to a
minimal disagreement. A verifier with two engines that can disagree has no verdict.

The reference is independent of every engine: for small widths, the two circuits are executed on
all inputs with ``Circuit.run``. For the width boundaries of the native engines (63/64/65 and
127/128/129 wires), where enumeration is impossible, the expected answer is known by
construction: sound rewrites give an equivalent circuit, and appending one CX to a permutation
gives a different one whose witness is replayed.

An engine may *refuse* (a degree or width limit); it may never return the wrong answer, and a
``different`` answer must carry an input on which the two circuits really differ.
"""
from __future__ import annotations

import contextlib
import io
import json
import random
import tempfile
from pathlib import Path

import pytest
from hypothesis import find, given, settings
from hypothesis import strategies as st

from symq import (
    BACKENDS,
    Budget,
    Circuit,
    InternalInconsistency,
    ResourceLimitExceeded,
    check_equivalence,
    verify,
)
from symq.__main__ import main
from symq.generators import equivalent_variant, mutate
from symq.sat import Contract, check_sat_equivalence
from tests.test_equivalence import ForgetfulXorSparse, MissingCrossTermZDD, NoCancellationSparse

SETTINGS = settings(max_examples=150, deadline=None)

SYMBOLIC = sorted(BACKENDS)
MAY_REFUSE_SMALL = {"linear", "packed"}
"""Engines with a degree limit: on a small circuit they may refuse, every other engine decides."""

WIDTH_LIMITS = {"zdd-native": 64, "zdd-native-wide": 128, "zdd": 256}
"""Documented width limits (docs/guide/backends.md); beyond them the engine must refuse."""


@st.composite
def circuits(draw, *, max_width: int = 6, affine: bool = False) -> Circuit:
    width = draw(st.integers(1, max_width))
    circuit = Circuit(width)
    for _ in range(draw(st.integers(0, 12))):
        size = draw(st.integers(1, min(width, 2 if affine else 4)))
        wires = draw(st.permutations(range(width)))[:size]
        circuit.append({1: "x", 2: "cx", 3: "ccx"}.get(size, "mcx"), *wires)
    return circuit


@st.composite
def pairs(draw, *, affine: bool = False) -> tuple[Circuit, Circuit]:
    """Two circuits of one width: a sound rewrite, a structural mutant, or an unrelated circuit.

    With ``affine`` every gate of both circuits is X or CX, so the linear engine applies.
    """
    left = draw(circuits(affine=affine))
    relation = draw(st.sampled_from(["variant", "mutant", "mutant of variant", "unrelated"]))
    rng = random.Random(draw(st.integers(0, 2**32 - 1)))
    if relation == "unrelated":
        right = draw(circuits(max_width=left.width, affine=affine))
        return left, Circuit(left.width, list(right.gates))
    right = left
    if "variant" in relation:
        right = equivalent_variant(right, rng, steps=8, max_controls=1 if affine else 3)
    if "mutant" in relation:
        if not affine:
            right, _kind = mutate(right, rng)
        elif right.gates:  # these two kinds keep every gate an X or a CX
            right, _kind = mutate(right, rng, rng.choice(["delete", "retarget"]))
    return left, right


def exhaustive(left: Circuit, right: Circuit) -> bool:
    return all(left.run(value) == right.run(value) for value in range(1 << left.width))


def decide(engine: str, left: Circuit, right: Circuit,
           budget: Budget | None = None) -> tuple[str, int | None]:
    """``("equivalent" | "different" | "refused", witness)`` for a symbolic backend."""
    try:
        result = check_equivalence(left, right, backend=engine, budget=budget)
    except ResourceLimitExceeded:
        return "refused", None
    return ("equivalent" if result.equivalent else "different"), result.witness


def assert_sound(engine: str, verdict: str, witness: int | None, left: Circuit, right: Circuit,
                 expected: bool) -> None:
    assert verdict == ("equivalent" if expected else "different"), (engine, verdict)
    if verdict == "different":
        assert witness is not None, engine
        assert left.run(witness) != right.run(witness), (engine, witness)
    else:
        assert witness is None, engine


@SETTINGS
@given(pairs())
def test_every_symbolic_engine_agrees_with_exhaustive_execution(pair):
    left, right = pair
    expected = exhaustive(left, right)
    for engine in SYMBOLIC:
        verdict, witness = decide(engine, left, right)
        if verdict == "refused":
            assert engine in MAY_REFUSE_SMALL, engine
            continue
        assert_sound(engine, verdict, witness, left, right, expected)


@SETTINGS
@given(pairs(affine=True))
def test_the_linear_engine_decides_every_affine_pair(pair):
    """On X/CX circuits the linear backend has no excuse to refuse, and must agree."""
    left, right = pair
    verdict, witness = decide("linear", left, right)
    assert_sound("linear", verdict, witness, left, right, exhaustive(left, right))


@SETTINGS
@given(pairs())
def test_the_facade_reports_what_the_engine_decided(pair):
    left, right = pair
    expected = exhaustive(left, right)
    for engine in SYMBOLIC:
        record = verify(left, right, theorem="classical_full", engine=engine)
        if record.outcome == "inconclusive":
            assert engine in MAY_REFUSE_SMALL, engine
            assert not record.equivalent and not record.different and record.witness is None
            continue
        assert record.outcome == ("equivalent" if expected else "different"), engine
        assert record.equivalent is expected and record.different is (not expected)
        if record.different:
            assert record.witness_kind == "input"
            assert left.run(record.witness) != right.run(record.witness)


@pytest.mark.parametrize("broken", [NoCancellationSparse, MissingCrossTermZDD, ForgetfulXorSparse])
def test_the_comparison_catches_a_deliberately_broken_backend(broken):
    """The check above is only worth something if a wrong engine cannot pass it.

    Each class is a real backend with one algebraic rule removed. Hypothesis must find, **with
    the same ``pairs()`` strategy the properties use**, a pair on which the broken backend either
    contradicts exhaustive execution or is stopped by the witness replay inside
    ``check_equivalence``. If it cannot, the generator of this file does not reach that bug.
    """
    def caught(pair) -> bool:
        left, right = pair
        try:
            result = check_equivalence(left, right, backend=broken)
            assert_sound(broken.__name__, "equivalent" if result.equivalent else "different",
                         result.witness, left, right, exhaustive(left, right))
        except (AssertionError, InternalInconsistency):
            return True
        return False

    find(pairs(), caught, settings=settings(max_examples=2000, deadline=None, derandomize=True,
                                            database=None))


@pytest.mark.native
def test_the_native_engines_take_part_in_the_comparison():
    """Without this, an environment that did not build the C core would compare fewer engines."""
    assert {"zdd-native", "zdd-native-wide"} <= set(SYMBOLIC)


@pytest.mark.sat
@SETTINGS
@given(pairs())
def test_the_sat_miter_agrees_with_exhaustive_execution(pair):
    left, right = pair
    expected = exhaustive(left, right)
    verdict = check_sat_equivalence(left, right)
    assert verdict.outcome == ("equivalent" if expected else "different")
    if verdict.outcome == "different":
        assert verdict.witness_checked is True
        assert left.run(verdict.witness) != right.run(verdict.witness)
    record = verify(left, right, theorem="classical_full", engine="sat")
    assert record.outcome == verdict.outcome


@st.composite
def contracts(draw, width: int) -> Contract:
    wires = list(range(width))
    observed = draw(st.none() | st.lists(st.sampled_from(wires), unique=True, min_size=1))
    restored = draw(st.lists(st.sampled_from(wires), unique=True))
    constants = draw(st.dictionaries(st.sampled_from(wires), st.integers(0, 1)))
    if draw(st.booleans()):
        # An output map compares left wire ``a`` with right wire ``b``; it must be injective and
        # may name a restored wire on neither side.
        sources = draw(st.lists(st.sampled_from(wires), unique=True, min_size=1))
        targets = draw(st.permutations(wires))[:len(sources)]
        mapping = {a: b for a, b in zip(sources, targets)
                   if a not in restored and b not in restored}
        if mapping:
            return Contract(input_constants=constants, output_map=mapping,
                            restored_wires=tuple(restored))
    return Contract(input_constants=constants,
                    observed_outputs=None if observed is None else tuple(observed),
                    restored_wires=tuple(restored))


def contract_counterexample(left: Circuit, right: Circuit, contract: Contract,
                            value: int) -> bool:
    """Does ``value`` violate the contract? Written from the contract's documentation alone."""
    if any(((value >> wire) & 1) != bit for wire, bit in contract.input_constants.items()):
        return False  # outside the declared input domain
    left_out, right_out = left.run(value), right.run(value)
    if contract.output_map:
        observed = contract.output_map.items()
    elif contract.observed_outputs is not None:
        observed = [(wire, wire) for wire in contract.observed_outputs]
    else:
        observed = [(wire, wire) for wire in range(left.width)]
    if any(((left_out >> a) & 1) != ((right_out >> b) & 1) for a, b in observed):
        return True
    return any(((out >> wire) & 1) != ((value >> wire) & 1)
               for wire in contract.restored_wires for out in (left_out, right_out))


@pytest.mark.sat
@SETTINGS
@given(st.data())
def test_a_sat_contract_agrees_with_its_truth_table_projection(data):
    left, right = data.draw(pairs())
    contract = data.draw(contracts(left.width))
    counterexamples = [value for value in range(1 << left.width)
                       if contract_counterexample(left, right, contract, value)]
    verdict = check_sat_equivalence(left, right, contract)
    assert verdict.outcome == ("different" if counterexamples else "equivalent")
    if verdict.outcome == "different":
        assert verdict.witness in counterexamples
    record = verify(left, right, theorem="classical_contract", engine="sat", contract=contract)
    assert record.outcome == verdict.outcome
    if record.different:
        assert record.witness in counterexamples


def run_cli(arguments: list[str]) -> tuple[int, str]:
    output = io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
        code = main(arguments)
    return code, output.getvalue()


def cli_engines() -> list:
    return ["auto", "sparse", "zdd", pytest.param("sat", marks=pytest.mark.sat)]


@pytest.mark.parametrize("engine", cli_engines())
@settings(max_examples=40, deadline=None)
@given(pair=pairs())
def test_the_command_line_agrees_with_exhaustive_execution(engine, pair):
    """Exit status 0 means equivalent and 1 different, whatever engine ``auto`` picks."""
    left, right = pair
    expected = exhaustive(left, right)
    with tempfile.TemporaryDirectory() as directory:
        paths = []
        for name, circuit in (("left.json", left), ("right.json", right)):
            path = Path(directory) / name
            path.write_text(json.dumps(circuit.to_dict()), encoding="utf-8")
            paths.append(str(path))
        code, output = run_cli(["check", *paths, "--engine", engine, "--json"])
    assert code == (0 if expected else 1), output
    record = json.loads(output)
    assert record["outcome"] == ("equivalent" if expected else "different")
    if not expected:
        assert left.run(record["witness"]) != right.run(record["witness"])


# --- width boundaries of the native engines --------------------------------------------------

BOUNDARY_WIDTHS = (63, 64, 65, 127, 128, 129)
BOUNDARY_ENGINES = [
    pytest.param("zdd-native", marks=pytest.mark.native),
    pytest.param("zdd-native-wide", marks=pytest.mark.native),
    "zdd",
    "sparse",
    "packed-fallback",
]


def wide_circuit(width: int) -> Circuit:
    """Touches every wire, including both sides of the 64- and 128-wire word boundaries.

    The Toffolis act on disjoint triples, so every output polynomial stays small and no engine
    is limited by size: only the width is under test.
    """
    circuit = Circuit(width)
    for first in range(0, width - 2, 3):
        circuit.ccx(first, first + 1, first + 2)
    circuit.cx(width - 1, 0).cx(width - 2, width - 1).x(width - 1)
    return circuit


def wide_pairs(width: int) -> tuple[Circuit, Circuit, Circuit]:
    reference = wide_circuit(width)
    variant = equivalent_variant(reference, random.Random(width), steps=12, max_controls=1)
    # A permutation takes some input to wire 0 = 1, so one more CX from it changes the function.
    different = Circuit(width, [*reference.gates]).cx(0, width - 1)
    return reference, variant, different


@pytest.mark.parametrize("engine", BOUNDARY_ENGINES)
@pytest.mark.parametrize("width", BOUNDARY_WIDTHS)
def test_width_boundaries_are_decided_or_refused_never_wrong(engine, width):
    reference, variant, different = wide_pairs(width)
    budget = Budget(max_seconds=60)
    limit = WIDTH_LIMITS.get(engine)
    if limit is not None and width > limit:
        for other in (variant, different):
            with pytest.raises(ResourceLimitExceeded) as refusal:
                check_equivalence(reference, other, backend=engine, budget=budget)
            assert refusal.value.resource == "width"
        return
    same = check_equivalence(reference, variant, backend=engine, budget=budget)
    assert same.equivalent and same.witness is None
    changed = check_equivalence(reference, different, backend=engine, budget=budget)
    assert not changed.equivalent
    assert changed.witness is not None and changed.witness < (1 << width)
    assert reference.run(changed.witness) != different.run(changed.witness)


@pytest.mark.sat
@pytest.mark.parametrize("width", BOUNDARY_WIDTHS)
def test_the_sat_miter_decides_the_width_boundary_pairs(width):
    reference, variant, different = wide_pairs(width)
    budget = Budget(max_seconds=60)
    assert check_sat_equivalence(reference, variant, budget=budget).outcome == "equivalent"
    changed = check_sat_equivalence(reference, different, budget=budget)
    assert changed.outcome == "different" and changed.witness_checked is True
    assert reference.run(changed.witness) != different.run(changed.witness)


def test_the_width_boundary_pairs_are_what_they_claim_on_a_small_instance():
    """The by-construction argument, checked exhaustively where enumeration is possible."""
    for width in (3, 4, 5, 8, 9, 10):
        reference, variant, different = wide_pairs(width)
        assert exhaustive(reference, variant)
        assert not exhaustive(reference, different)
