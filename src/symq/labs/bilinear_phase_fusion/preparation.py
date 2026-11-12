"""Constructed boundary witnesses and exact sparse-ANF preparation checking.

A constructed producer is not an extracted application site. Inputs c,A,B are arbitrary; garbage starts
at zero. Only phase-free X/CX/CCX/MCX gates are accepted. Arbitrary dirty garbage,
phases, measurements, modified live inputs and unknown instructions are refused.
"""

from __future__ import annotations

import time

from .checker import Inconclusive, Rejected, _deadline, multiplication_oracle


def emit_source(m: int, modulus: int, bank: int, terms: list[dict] | None = None) -> dict:
    from .compiler import is_irreducible

    if type(m) is not int or not 2 <= m <= 16 or type(bank) is not int or not 1 <= bank <= 128:
        raise ValueError("dimensions")
    if type(modulus) is not int or not is_irreducible(m, modulus):
        raise ValueError("field")
    if terms is None:
        terms = [
            {"a": 1 << i, "b": 1 << j, "output": multiplication_oracle(1 << i, 1 << j, m, modulus)}
            for i in range(m)
            for j in range(m)
        ]
    if type(terms) is not list or len(terms) > 4096:
        raise ValueError("tensor term bound")
    if any(
        type(t) is not dict
        or set(t) != {"a", "b", "output"}
        or any(type(v) is not int or not 0 < v < 1 << m for v in t.values())
        for t in terms
    ):
        raise ValueError("tensor terms")
    live = 1 + m * (bank + 1)
    gates = []
    for j in range(bank):
        for t in terms:
            am = [1 + i for i in range(m) if t["a"] >> i & 1]
            bm = [1 + m + j * m + i for i in range(m) if t["b"] >> i & 1]
            zm = [live + j * m + i for i in range(m) if t["output"] >> i & 1]
            prep = [["cx", [w, am[0]]] for w in am[1:]]
            prep += [["cx", [w, bm[0]]] for w in bm[1:]]
            prep += [["cx", [zm[0], w]] for w in zm[1:]]
            block = prep + [["mcx", [0, am[0], bm[0], zm[0]]]] + list(reversed(prep))
            if len(gates) + len(block) > 200_000:
                raise ValueError("preparation gate bound")
            gates += block
    return {
        "schema": "controlled-product-preparation-v1",
        "field": {"m": m, "modulus": modulus},
        "bank": bank,
        "width": live + m * bank,
        "gates": gates,
    }


def prove_preparation(source: dict, *, seconds: float = 30.0, max_terms: int = 100_000) -> dict:
    deadline = _deadline(seconds)
    if type(max_terms) is not int or max_terms < 0:
        raise Rejected("max_terms must be a nonnegative integer")
    if (
        type(source) is not dict
        or set(source) != {"schema", "field", "bank", "width", "gates"}
        or source["schema"] != "controlled-product-preparation-v1"
    ):
        raise Rejected("preparation schema")
    f = source["field"]
    if type(f) is not dict or set(f) != {"m", "modulus"}:
        raise Rejected("field")
    m, modulus, bank = f["m"], f["modulus"], source["bank"]
    if (
        type(m) is not int
        or not 2 <= m <= 16
        or type(bank) is not int
        or not 1 <= bank <= 128
        or type(modulus) is not int
        or not (1 << m) <= modulus < (1 << (m + 1))
    ):
        raise Rejected("dimensions")
    live = 1 + m * (bank + 1)
    width = live + m * bank
    if (
        type(source["width"]) is not int
        or source["width"] != width
        or type(source["gates"]) is not list
        or len(source["gates"]) > 200_000
    ):
        raise Rejected("width/gates")
    values = [{1 << i} for i in range(live)] + [set() for _ in range(m * bank)]
    for gate in source["gates"]:
        if time.monotonic() > deadline:
            raise Inconclusive("preparation timeout")
        if type(gate) is not list or len(gate) != 2 or type(gate[1]) is not list:
            raise Rejected("gate")
        op, ws = gate
        arity = {"x": 1, "cx": 2, "ccx": 3}
        if (
            type(op) is not str
            or op not in (*arity, "mcx")
            or (op in arity and len(ws) != arity[op])
            or (op == "mcx" and not 2 <= len(ws) <= width)
        ):
            raise Rejected("unsupported preparation gate")
        if any(type(w) is not int or not 0 <= w < width for w in ws) or len(set(ws)) != len(ws):
            raise Rejected("wire/alias")
        expression = {0}
        for c in ws[:-1]:
            if len(expression) * len(values[c]) > max_terms:
                raise Inconclusive("preparation term budget")
            updated = set()
            for x in expression:
                for y in values[c]:
                    v = x | y
                    if v in updated:
                        updated.remove(v)
                    else:
                        updated.add(v)
            expression = updated
        values[ws[-1]].symmetric_difference_update(expression)
        if len(values[ws[-1]]) > max_terms:
            raise Inconclusive("preparation term budget")
    if time.monotonic() >= deadline:
        raise Inconclusive("preparation timeout")
    if values[:live] != [{1 << i} for i in range(live)]:
        raise Rejected("live input changed: stale-operand correction not authorized")
    expected = [set() for _ in range(m * bank)]
    for word in range(bank):
        for i in range(m):
            for k in range(m):
                product = multiplication_oracle(1 << i, 1 << k, m, modulus)
                monomial = 1 | (1 << (1 + i)) | (1 << (1 + m + word * m + k))
                for bit in range(m):
                    if product >> bit & 1:
                        expected[word * m + bit].add(monomial)
    if time.monotonic() >= deadline:
        raise Inconclusive("preparation timeout")
    if values[live:] != expected:
        raise Rejected("garbage relation c*(A*B_j) not established")
    return {
        "theorem": "clean_preparation_graph",
        "arbitrary_live_bits": live,
        "zero_prepared_garbage_bits": m * bank,
        "gates_checked": len(source["gates"]),
        "application_site_extracted": False,
    }


def to_symq(source: dict):
    """Convert a checked, closed preparation into a reversible Circuit."""
    prove_preparation(source)
    from symq import Circuit

    circuit = Circuit(source["width"])
    for op, wires in source["gates"]:
        circuit.append(op, *wires)
    return circuit
