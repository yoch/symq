"""Independent exact Kraus-trajectory oracle for tiny hybrid rewrites.

This test deliberately does not use the library's density-matrix evolution,
channel-composition leaf implementation or memoized branches. It enumerates
Kraus trajectories over *basis kets* (not density operators), then builds the
full matrix-unit channel by outer products of the two ket images.

The supported domain here is basis permutations, diagonal signs, X- and
Z-basis measurement, reset and deterministic classical feed-forward. It is a
small experimental qualification, not a general quantum simulation package.
"""
from __future__ import annotations

from fractions import Fraction
from itertools import product

from symq.experimental.hybrid import HOp, HybridProgram, coherence_image


def _condition(name: str | None, memory: dict[str, int]) -> bool:
    if name is None:
        return True
    if name.startswith("!"):
        return not bool(memory[name[1:]])
    return bool(memory[name])


def _ket_kraus_image(
    program: HybridProgram, basis: int, choices: tuple[int, ...],
    observed: tuple[str, ...],
) -> tuple[int, int, tuple[int, ...]] | None:
    """Apply a *fixed* sequence of Kraus outcomes to one computational ket.

    The total amplitude is sign / (sqrt(2) ** number_of_HMR_events); every
    admissible branch has that same denominator. Squaring the amplitude via
    an outer product yields exact rational channel coefficients.
    """
    state, phase = basis, 1
    classical: dict[str, int] = {}
    position = 0
    for op in program.ops:
        kind, qs = op.kind, op.wires
        if kind in {"hmr", "measure_z", "reset"}:
            outcome = choices[position]
            position += 1
            q = qs[0]
            bit = state >> q & 1
            if kind == "hmr":
                if outcome and bit:
                    phase = -phase
                state &= ~(1 << q)
                classical[op.slot] = outcome
            else:
                # Z measurement and reset use projectors |b><b|;
                # reset additionally maps the selected state to |0>.
                if bit != outcome:
                    return None
                if kind == "reset":
                    state &= ~(1 << q)
                else:
                    classical[op.slot] = outcome
            continue
        if kind == "store":
            classical[op.slot] = op.value
            continue
        if kind == "invert":
            classical[op.slot] ^= int(_condition(op.condition, classical))
            continue
        if kind == "oxor":
            classical[op.slot] ^= classical[op.source]
            continue
        if not _condition(op.condition, classical):
            continue
        if kind in {"x", "cx", "ccx", "mcx"}:
            *controls, target = qs
            if all((state >> q) & 1 for q in controls):
                state ^= 1 << target
        elif kind in {"swap", "cswap"}:
            if kind == "swap":
                a, b = qs
                enabled = True
            else:
                ctrl, a, b = qs
                enabled = bool(state >> ctrl & 1)
            if enabled and ((state >> a) & 1) != ((state >> b) & 1):
                state ^= (1 << a) | (1 << b)
        elif kind in {"z", "cz", "ccz", "neg"}:
            if kind == "neg" or all((state >> q) & 1 for q in qs):
                phase = -phase
        else:
            raise AssertionError(f"unqualified operation {kind!r}")
    return state, phase, tuple(classical[s] for s in observed)


def independent_kraus(
    program: HybridProgram, x: int, y: int, observed: tuple[str, ...] = (),
) -> dict[tuple[int, ...], dict[tuple[int, int], Fraction]]:
    """Construct E(|x><y|) by summing outer products of all matched Kraus paths."""
    program.validate()
    assert 0 <= x < 1 << program.data and 0 <= y < 1 << program.data
    count = sum(op.kind in {"hmr", "measure_z", "reset"} for op in program.ops)
    measurements = sum(op.kind == "hmr" for op in program.ops)
    assert count <= 8 and program.width <= 6
    factor = 1 << measurements
    images: dict[tuple[int, ...], dict[tuple[int, int], Fraction]] = {}
    for outcomes in product((0, 1), repeat=count):
        a = _ket_kraus_image(program, x, outcomes, observed)
        b = _ket_kraus_image(program, y, outcomes, observed)
        if a is None or b is None:
            continue
        assert a[2] == b[2]
        record = a[2]
        matrix = images.setdefault(record, {})
        key = (a[0], b[0])
        coefficient = matrix.get(key, Fraction(0)) + Fraction(a[1] * b[1], factor)
        if coefficient:
            matrix[key] = coefficient
        else:
            matrix.pop(key, None)
    return {record: image for record, image in images.items() if image}


def test_temporary_and_measurement_uncompute_independent_all_coherences():
    reference = HybridProgram(3, 1, [
        HOp("ccx", (0, 1, 3)), HOp("cx", (3, 2)),
        HOp("ccx", (0, 1, 3)),
    ])
    candidate = HybridProgram(3, 1, [
        HOp("ccx", (0, 1, 3)), HOp("cx", (3, 2)),
        HOp("hmr", (3,), slot="b0"),
        HOp("cz", (0, 1), condition="b0"),
    ])
    mutant = HybridProgram(3, 1, candidate.ops[:-1])
    equal, off_diagonal_mutant = 0, False
    for x, y in product(range(1 << 3), repeat=2):
        expected = independent_kraus(reference, x, y)
        actual = independent_kraus(candidate, x, y)
        assert expected == actual
        # Independent trajectory oracle agrees with the installed density oracle.
        assert expected[()] == coherence_image(reference, x, y)
        assert actual[()] == coherence_image(candidate, x, y)
        wrong = independent_kraus(mutant, x, y)
        if x == y:
            assert wrong == expected
        elif wrong != expected:
            off_diagonal_mutant = True
        equal += 1
    assert equal == 64 and off_diagonal_mutant


def test_real_public_qualtran_m1_independent_channel_and_phase_mutant():
    from benchmarks.hmr_qualification import hybrid, load_manifest, programs

    cases = {c["id"]: c for c in load_manifest()["cases"]}
    reference, candidate = (hybrid(p) for p in programs(cases["m1-full-none"]))
    _, missing = (hybrid(p) for p in programs(cases["m1-full-missing_correction"]))
    assert reference.data == candidate.data == missing.data == 2
    off_diagonal_mutant = False
    for x, y in product(range(1 << 2), repeat=2):
        image = independent_kraus(reference, x, y)
        assert image == independent_kraus(candidate, x, y)
        assert image[()] == coherence_image(reference, x, y)
        bad = independent_kraus(missing, x, y)
        if x == y:
            assert image == bad
        elif image != bad:
            off_diagonal_mutant = True
    assert off_diagonal_mutant


def test_independent_full_coherent_oracle_exposes_borrowed_phase_error():
    identity = HybridProgram(2)
    dirty = HybridProgram(2, 0, [HOp("cz", (0, 1))])
    assert all(
        independent_kraus(dirty, x, x) == independent_kraus(identity, x, x)
        for x in range(4)
    )
    assert independent_kraus(dirty, 3, 1) != independent_kraus(identity, 3, 1)


def test_independent_oracle_distinguishes_observed_instrument_and_liveness():
    operations = (
        HOp("reset", (1,)), HOp("measure_z", (1,), slot="b0"),
    )
    reference = HybridProgram(2, 0, list(operations))
    inverted = HybridProgram(2, 0, list(operations) + [HOp("invert", slot="b0")])
    # If the record is forgotten and never used again, channels are equal.
    for x, y in product(range(4), repeat=2):
        assert independent_kraus(reference, x, y) == independent_kraus(inverted, x, y)
    # If b0 is observed, the instruments are not equivalent.
    assert independent_kraus(reference, 0, 0, ("b0",)) != independent_kraus(
        inverted, 0, 0, ("b0",)
    )
    # If b0 drives a later X, even the unconditional channels differ.
    suffix = [HOp("x", (0,), condition="b0")]
    left = HybridProgram(2, 0, list(operations) + suffix)
    right = HybridProgram(2, 0, list(inverted.ops) + suffix)
    assert independent_kraus(left, 0, 0) != independent_kraus(right, 0, 0)


def test_independent_kraus_covers_reset_measurement_swap_and_signs():
    programs = (
        HybridProgram(2, 1, [
            HOp("cx", (0, 2)), HOp("measure_z", (2,), slot="b0"),
            HOp("x", (1,), condition="!b0"), HOp("reset", (2,)),
        ]),
        HybridProgram(2, 1, [
            HOp("cswap", (2, 0, 1)), HOp("x", (2,)),
            HOp("swap", (0, 1)), HOp("ccz", (0, 1, 2)),
            HOp("hmr", (2,), slot="b0"), HOp("cz", (0, 1), condition="b0"),
        ]),
        HybridProgram(2, 0, [
            HOp("store", slot="b0", value=1), HOp("invert", slot="b0"),
            HOp("oxor", slot="b0", source="b0"), HOp("neg"),
            HOp("z", (0,)), HOp("cz", (0, 1), condition="!b0"),
        ]),
    )
    for program in programs:
        for x, y in product(range(1 << program.data), repeat=2):
            exact = independent_kraus(program, x, y)
            assert exact.get((), {}) == coherence_image(program, x, y)
