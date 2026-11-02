"""HMR-uncomputed finite-table XOR loaders (issue #144 research, ``symq.labs``).

Every checker verdict is compared with the independent dense cq-state oracle in
``tests/testkit/table_channel_oracle.py``: the full channel on every legal ``|x><y|``,
plus a state whose borrowed wire is entangled with an external reference qubit.
"""
from __future__ import annotations

import random
from collections import Counter
from fractions import Fraction
from itertools import product

import pytest

from symq.experimental.hybrid import HOp, HybridProgram, coherence_image
from symq.labs.hmr_table_contract import (
    HmrTableContract,
    and_uncompute_example,
    check_hmr_table_xor,
)
from symq.phase import PhaseProgram, phase_semantics
from symq.resources import Budget
from tests.testkit import table_channel_oracle as oracle

ADDRESS, TARGET, BORROWED = (0, 1), (2, 3), (4,)
TABLE = (0b00, 0b01, 0b11, 0b11)  # row 3 is illegal; 0b11 is what the example does there
LEGAL = (0, 1, 2)
STATES = oracle.basis_states(ADDRESS, TARGET, BORROWED, LEGAL)
ALL_STATES = oracle.basis_states(ADDRESS, TARGET, BORROWED, (0, 1, 2, 3))
REFERENCE = 7  # above every program wire used here (widths 6 and 7)


def contract(table=(0b00, 0b01, 0b11, None), clean=(5,), width=6):
    return HmrTableContract(width=width, address_wires=ADDRESS, target_wires=TARGET,
                            clean_wires=clean, borrowed_wires=BORROWED, table=table,
                            legal_addresses=LEGAL)


def loader(*, correction="cz", condition="b0", restore=True, uncompute="hmr",
           extra_event=False, extra=()):
    """The example loader with one controlled change at a time."""
    p = HybridProgram(5, 2 if extra_event else 1)
    p.x(0).x(1).ccx(0, 1, 5).x(0).x(1)
    p.cx(5, 2).x(2)
    p.cx(4, 3).cx(1, 4).cx(4, 3)
    if restore:
        p.cx(1, 4)
    if extra_event:
        p.hmr(6, "b1")  # a second, independent X-basis event on a clean ancilla
    if uncompute == "hmr":
        p.hmr(5, "b0")
    elif uncompute == "measure_z":  # Z-basis "uncomputation": measure, then flip back
        p.measure_z(5, "b0").x(5, condition="b0")
    elif uncompute == "reset":
        p.reset(5)
    elif uncompute == "none":
        pass
    if correction == "cz":
        p.x(0).x(1).cz(0, 1, condition=condition).x(0).x(1)
    elif correction == "cz_twice":
        p.x(0).x(1).cz(0, 1, condition=condition).cz(0, 1, condition=condition).x(0).x(1)
    elif correction == "cz_unsandwiched":  # corrects [a == 3] instead of [a == 0]
        p.cz(0, 1, condition=condition)
    elif correction == "linear":  # (-1)^(1 + a0 + a1) equals (-1)^[a == 0] on legal a only
        p.neg(condition=condition).z(0, condition=condition).z(1, condition=condition)
    for op in extra:
        p.ops.append(op)
    p.validate()
    return p


def reference_state(states, weight=lambda s: 1 + (s & 3)):
    """Borrowed wire 4 maximally entangled with reference wire 6, address weighted."""
    return oracle.pure({s | ((s >> 4) & 1) << REFERENCE: weight(s) for s in states})


def channel_matches(program, table=TABLE, states=STATES) -> bool:
    if oracle.first_difference(program, states, ADDRESS, TARGET, table) is not None:
        return False
    rho = reference_state(states)
    return oracle.forgotten(program, rho) == oracle.ideal(rho, ADDRESS, TARGET, table)


# ----------------------------------------------------------------------------- positive


def test_public_example_is_proved_and_matches_the_oracle():
    program, spec = and_uncompute_example()
    result = check_hmr_table_xor(program, spec)
    assert result.equivalent, result
    assert (result.checked_inputs, result.branches, result.hmr_events) == (24, 2, 1)
    assert spec.legal_inputs() == STATES
    assert channel_matches(program)
    assert loader().ops == program.ops


def test_example_matches_the_library_density_oracle_on_every_legal_coherence():
    program, spec = and_uncompute_example()
    for x, y in product(STATES, repeat=2):
        image = coherence_image(program, x, y)
        assert image == {(spec.ideal(x), spec.ideal(y)): Fraction(1)}


def test_reference_entanglement_is_kept_not_only_basis_behaviour():
    program, _ = and_uncompute_example()
    rho = reference_state(STATES)
    out = oracle.forgotten(program, rho)
    assert out == oracle.ideal(rho, ADDRESS, TARGET, TABLE)
    # The reduced state of the reference is untouched AND the joint state stays pure:
    # an off-diagonal between borrowed values 0 and 1 survives.
    assert any(((r >> 4) ^ (c >> 4)) & 1 and ((r >> REFERENCE) ^ (c >> REFERENCE)) & 1
               for r, c in out)


def test_outcome_dependent_global_sign_is_accepted_but_strict_o2_refuses_it():
    program = loader(extra=(HOp("neg", (), condition="b0"),))
    result = check_hmr_table_xor(program, contract())
    assert result.equivalent and channel_matches(program)
    # The strict sign/HMR theory demands one Kraus operator for all outcomes (O2), so an
    # outcome-only sign is refused there although the forgotten channel is unchanged.
    strict = PhaseProgram(2, 1).x(2)
    strict.hmr(2)
    assert any(v.startswith("O2") for v in phase_semantics(strict).violations())
    same = HybridProgram(2, 1).x(2).hmr(2, "b0")
    spec = HmrTableContract(width=3, address_wires=(0,), target_wires=(1,), clean_wires=(2,),
                            borrowed_wires=(), table=(0, 0), legal_addresses=(0, 1))
    assert check_hmr_table_xor(same, spec).equivalent
    for x, y in product(spec.legal_inputs(), repeat=2):
        assert oracle.forgotten(same, oracle.unit(x, y)) == oracle.unit(x, y)


def test_correction_valid_only_on_the_legal_support():
    program = loader(correction="linear")
    assert check_hmr_table_xor(program, contract()).equivalent
    assert channel_matches(program)
    # Including the illegal address 3, no table row makes the channel an XOR isometry.
    for row in range(4):
        table = (0, 1, 3, row)
        assert oracle.first_difference(program, ALL_STATES, ADDRESS, TARGET, table)
    # The exact CZ correction extends to address 3 with row 0b11.
    assert oracle.first_difference(loader(), ALL_STATES, ADDRESS, TARGET, TABLE) is None


# ----------------------------------------------------------------------------- mutations


MUTATIONS = {
    "correction omitted": ({"correction": "none"}, "branch_phase"),
    "correction doubled": ({"correction": "cz_twice"}, "branch_phase"),
    "correction on the wrong event": ({"condition": "b1", "extra_event": True}, "branch_phase"),
    "correction on the negated event": ({"condition": "!b0"}, "branch_phase"),
    "correction on the wrong address": ({"correction": "cz_unsandwiched"}, "branch_phase"),
    "borrowed wire not restored": ({"restore": False}, "permutation"),
    "ancilla never uncomputed": ({"uncompute": "none", "correction": "none"}, "permutation"),
    "Z-measurement uncomputation": ({"uncompute": "measure_z", "correction": "none"},
                                    "branch_support"),
    "reset uncomputation": ({"uncompute": "reset", "correction": "none"}, "branch_support"),
}


@pytest.mark.parametrize("name", sorted(MUTATIONS))
def test_mutation_is_refused_and_the_oracle_confirms_the_witness(name):
    options, obligation = MUTATIONS[name]
    program = loader(**options)
    clean = (5, 6) if options.get("extra_event") else (5,)
    spec = contract(clean=clean, width=program.width)
    result = check_hmr_table_xor(program, spec)
    assert result.status == "not_proved" and result.obligation == obligation, result
    x, y = result.witness["pair"]
    image = oracle.forgotten(program, oracle.unit(x, y))
    assert image != oracle.ideal(oracle.unit(x, y), ADDRESS, TARGET, TABLE)
    if obligation != "permutation":
        # All outputs are right, so the image is coefficient * W|x><y|W^T exactly.
        coefficient = Fraction(result.witness["coefficient"])
        assert coefficient != 1
        assert image == ({(spec.ideal(x), spec.ideal(y)): coefficient} if coefficient else {})
    assert not channel_matches(program)


def test_wrong_table_cell_is_refused():
    program, _ = and_uncompute_example()
    result = check_hmr_table_xor(program, contract(table=(0, 1, 0b10, None)))
    assert result.obligation == "permutation"
    x, y = result.witness["pair"]
    assert result.witness["input"]["address"] == 2
    assert oracle.forgotten(program, oracle.unit(x, y)) != oracle.ideal(
        oracle.unit(x, y), ADDRESS, TARGET, (0, 1, 0b10, 0))


def test_visible_record_is_refused_and_the_instrument_differs():
    program, spec = and_uncompute_example()
    result = check_hmr_table_xor(program, spec, observed_slots=("b0",))
    assert result.status == "not_proved" and result.obligation == "visible_record"
    rho = reference_state(STATES)
    instrument = oracle.evolve(program, rho, observed=("b0",))
    # The record is independent of the input (each half of the ideal output), so the
    # criterion would prove a decoupled record; but the contract has no classical output.
    half = {k: v / 2 for k, v in oracle.ideal(rho, ADDRESS, TARGET, TABLE).items()}
    assert instrument == {(0,): half, (1,): half}
    leak = loader(uncompute="measure_z", correction="none")
    leaked = oracle.evolve(leak, rho, observed=("b0",))
    assert set(leaked) == {(0,), (1,)} and leaked[(0,)] != leaked[(1,)]  # reveals [a == 0]


def test_discarded_scratch_is_outside_the_contract_not_a_checker_bug():
    """Incompleteness relative to a garbage-tolerant contract (not the #144 one).

    Ancilla 6 ends in the input-independent state |1>. All quantum outputs are retained in
    the #144 contract, so the refusal is right; tracing that wire would give the ideal channel.
    """
    program = loader(extra_event=True, extra=(HOp("x", (6,)),))
    result = check_hmr_table_xor(program, contract(clean=(5, 6), width=7))
    assert result.obligation == "permutation"
    assert result.witness["output"]["clean"] != 0
    x, y = result.witness["pair"]
    assert oracle.forgotten(program, oracle.unit(x, y)) != oracle.ideal(
        oracle.unit(x, y), ADDRESS, TARGET, TABLE)
    rho = reference_state(STATES)
    traced = oracle.trace_wires(oracle.forgotten(program, rho), (6,))
    assert traced == oracle.ideal(rho, ADDRESS, TARGET, TABLE)


# ----------------------------------------------------------------- decision agreement


def _random_program(rng: random.Random) -> HybridProgram:
    """Wires: address 0, target 1, borrowed 2, clean ancilla 3; biased towards loaders."""
    p = HybridProgram(3, 1)
    slots: list[str] = []
    for _ in range(rng.randint(1, 4)):
        block = rng.randrange(6)
        if block == 0:  # table core
            rng.choice([lambda: p.cx(0, 1), lambda: p.x(1), lambda: None])()
        elif block == 1:  # borrowed toggle trick, sometimes incomplete
            p.cx(2, 1).cx(0, 2).cx(2, 1)
            if rng.random() < 0.8:
                p.cx(0, 2)
        elif block == 2:  # compute junk into the ancilla
            rng.choice([lambda: p.cx(0, 3), lambda: p.ccx(0, 2, 3), lambda: p.x(3),
                        lambda: p.x(0).cx(0, 3).x(0)])()
        elif block == 3:  # uncompute the ancilla
            slot = f"b{len(slots)}"
            kind = rng.randrange(4)
            if kind == 0:
                p.hmr(3, slot)
            elif kind == 1:
                p.measure_z(3, slot).x(3, condition=slot)
            elif kind == 2:
                p.reset(3)
                continue
            else:
                p.hmr(3, slot)
                p.cx(0, 1, condition=slot)
            slots.append(slot)
        elif block == 4 and slots:  # a phase correction on some event
            slot = rng.choice(slots)
            cond = rng.choice([slot, "!" + slot])
            kind, wires = rng.choice([("z", (0,)), ("neg", ()), ("z", (2,)), ("cz", (0, 2)),
                                      ("z", (3,))])
            p.ops.append(HOp(kind, wires, condition=cond))
        elif block == 5:
            rng.choice([lambda: p.z(0), lambda: p.cz(0, 2), lambda: p.neg(), lambda: None])()
    if rng.random() < 0.7:  # make sure the ancilla is usually returned clean
        p.hmr(3, f"b{len(slots)}")
        slots.append(f"b{len(slots)}")
        if rng.random() < 0.5:
            p.z(0, condition=slots[-1])
    return p


def test_checker_decides_exactly_what_the_dense_oracle_decides():
    """The criterion is necessary as well as sufficient for this contract.

    400 random programs x 12 contracts (4 tables, 3 legal sets): the checker proves
    exactly the cases where the oracle's channel equals the ideal one on every legal
    coherence, and each refusal's witness pair is a real difference.
    """
    rng = random.Random(144)
    data_states = range(1 << 3)
    seen: Counter[str | None] = Counter()
    for _ in range(400):
        program = _random_program(rng)
        images = {(x, y): oracle.forgotten(program, oracle.unit(x, y))
                  for x, y in product(data_states, repeat=2)}
        for row0, row1 in product((0, 1), repeat=2):
            for legal in ((0,), (1,), (0, 1)):
                spec = HmrTableContract(width=4, address_wires=(0,), target_wires=(1,),
                                        clean_wires=(3,), borrowed_wires=(2,),
                                        table=(row0, row1), legal_addresses=legal)
                states = spec.legal_inputs()
                same = all(images[x, y] == {(spec.ideal(x), spec.ideal(y)): Fraction(1)}
                           for x, y in product(states, repeat=2))
                result = check_hmr_table_xor(program, spec)
                assert result.status in {"equivalent", "not_proved"}
                assert result.equivalent == same, (program.ops, spec, result)
                if not same:
                    x, y = result.witness["pair"]
                    assert images[x, y] != {(spec.ideal(x), spec.ideal(y)): Fraction(1)}
                seen[result.obligation] += 1
    assert sum(seen.values()) == 400 * 12
    assert seen[None] >= 1000 and seen["permutation"] >= 1000, seen
    assert seen["branch_phase"] >= 100 and seen["branch_support"] >= 5, seen


# ------------------------------------------------------------------ boundaries and caps


def test_caps_give_inconclusive_never_a_proof():
    program, spec = and_uncompute_example()
    assert check_hmr_table_xor(program, spec, max_inputs=10).status == "inconclusive"
    assert check_hmr_table_xor(program, spec, max_branches=1).status == "inconclusive"
    assert check_hmr_table_xor(program, spec, max_steps=50).status == "inconclusive"
    tiny = check_hmr_table_xor(program, spec, budget=Budget(max_seconds=1e-9))
    assert tiny.status == "inconclusive"
    with pytest.raises(ValueError):
        check_hmr_table_xor(program, spec, budget=Budget(max_nodes=10))


def test_unsupported_inputs_are_refused():
    program, spec = and_uncompute_example()
    with pytest.raises(TypeError):
        check_hmr_table_xor(PhaseProgram(5, 1), spec)  # type: ignore[arg-type]
    forged = HybridProgram(5, 1)
    forged.ops.append(HOp("h", (0,)))
    assert check_hmr_table_xor(forged, spec).status == "unsupported"
    undeclared = HmrTableContract(width=6, address_wires=ADDRESS, target_wires=TARGET,
                                  clean_wires=(), borrowed_wires=(4, 5),
                                  table=(0, 1, 3, None), legal_addresses=LEGAL)
    assert check_hmr_table_xor(program, undeclared).status == "unsupported"
    wide = HybridProgram(5, 2)
    assert check_hmr_table_xor(wide, spec).status == "unsupported"


@pytest.mark.parametrize("change", [
    {"table": (0, 1, None, None)},  # a legal row left undefined
    {"table": (0, 1, 3)},  # missing row
    {"table": (0, 1, 4, None)},  # out-of-width row
    {"legal_addresses": (2, 1)},  # unordered
    {"legal_addresses": ()},
    {"clean_wires": (5, 4)},  # alias with borrowed
    {"target_values": (1, 1)},
])
def test_contract_validation(change):
    fields = {"width": 6, "address_wires": ADDRESS, "target_wires": TARGET,
              "clean_wires": (5,), "borrowed_wires": BORROWED, "table": (0, 1, 3, None),
              "legal_addresses": LEGAL}
    fields.update(change)
    with pytest.raises(ValueError):
        HmrTableContract(**fields)


def test_restricted_target_domain():
    program, _ = and_uncompute_example()
    spec = HmrTableContract(width=6, address_wires=ADDRESS, target_wires=TARGET,
                            clean_wires=(5,), borrowed_wires=BORROWED, table=(0, 1, 3, None),
                            legal_addresses=LEGAL, target_values=(0,))
    result = check_hmr_table_xor(program, spec)
    assert result.equivalent and result.checked_inputs == 6
    assert result.to_dict()["contract_sha256"] == spec.sha256 != contract().sha256
