"""Shared cases for the HMR table-loader contract: tests and qualification harness.

Test-only (``tests/testkit``). Builders only: no checker logic. The verdicts are
compared with the independent dense oracle in ``table_channel_oracle``.
"""
from __future__ import annotations

import random

from symq.experimental.hybrid import HOp, HybridProgram
from symq.labs.hmr_table_contract import HmrTableContract
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


def random_program(rng: random.Random) -> HybridProgram:
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
