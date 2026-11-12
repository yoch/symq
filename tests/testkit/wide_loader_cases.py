"""Synthetic table loaders with 12 to 16 address bits, and their mutants (lot 4 qualification).

Each target bit of the table is the XOR of a few terms over the address bits ``a``: a single
bit ``a[i]``, or a product ``a[i] a[k]``. A single bit is copied with ``cx``. A product is
computed into the clean ancilla with ``ccx``, copied with ``cx``, then uncomputed by HMR:
the measurement leaves the phase ``(-1)^(b a[i] a[k])``, which ``cz(a[i], a[k])``
conditioned on the outcome ``b`` cancels. Every term uses only the low ``n - 1`` address
bits, and the address domain is ``0 <= a < upper`` with ``upper > 2**(n - 1)``: every
combination of the low bits is admitted, so each mutant below changes the channel on
admitted inputs, and its expected status is known by construction.

Mutants, each applied to the first product term:

- ``missing_phase``: the ``cz`` correction is dropped (branch phase left behind);
- ``wrong_target``: the product is copied into another target bit;
- ``dirty_ancilla``: the HMR uncomputation and its correction are dropped;
- ``wrong_address``: the product is computed from another address bit;
- ``uncontrolled_measurement``: address bit 0 is measured in Z at the end.

Generated from a seed; the development and holdout seed ranges are disjoint and declared
by the tests that use them. No fixture comes from outside this repository.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from symq.experimental.hybrid import HybridProgram
from symq.experimental.serialization import program_to_dict
from symq.experimental.table_xor import PredicateValues
from symq.labs.shared_table import SharedTable

MUTANTS = ("missing_phase", "wrong_target", "dirty_ancilla", "wrong_address",
           "uncontrolled_measurement")


@dataclass(frozen=True)
class Case:
    address_bits: int
    target_bits: int
    terms: tuple[tuple[tuple[int, ...], ...], ...]
    """``terms[j]``: the address-bit tuples (one or two bits) whose products XOR into target j."""
    upper: int
    mutant: str | None

    @property
    def expected(self) -> str:
        return "equivalent" if self.mutant is None else "not_proved"

    def row(self, address: int) -> int:
        word = 0
        for j, products in enumerate(self.terms):
            bit = 0
            for bits in products:
                bit ^= all(address >> i & 1 for i in bits)
            word |= bit << j
        return word

    def source(self) -> dict:
        n, t = self.address_bits, self.target_bits
        ancilla = n + t
        program = HybridProgram(n + t, 1)
        first_product = True
        slot = 0
        for j, products in enumerate(self.terms):
            target = n + j
            for bits in products:
                if len(bits) == 1:
                    program.cx(bits[0], target)
                    continue
                i, k = bits
                mutate = self.mutant if first_product else None
                first_product = False
                compute_k = (k + 1) % (n - 1) if mutate == "wrong_address" else k
                if compute_k == i:
                    compute_k = (k + 2) % (n - 1)
                program.ccx(i, compute_k, ancilla)
                copy_to = n + (j + 1) % t if mutate == "wrong_target" else target
                program.cx(ancilla, copy_to)
                if mutate == "dirty_ancilla":
                    continue
                name = f"b{slot}"
                slot += 1
                program.hmr(ancilla, name)
                if mutate != "missing_phase":
                    program.cz(i, compute_k, condition=name)
        if self.mutant == "uncontrolled_measurement":
            program.measure_z(0, f"b{slot}")
        return program_to_dict(program)

    def contract(self) -> dict:
        n, t = self.address_bits, self.target_bits
        table = SharedTable.from_rows([self.row(a) for a in range(1 << n)], address_bits=n,
                                      target_bits=t)
        return {"kind": "symq_shared_affine_table_contract", "schema_version": 3,
                "width": n + t + 1, "address_wires": list(range(n)),
                "target_wires": list(range(n, n + t)), "clean_wires": [n + t],
                "borrowed_wires": [], "table": table.to_dict(),
                "address_domain": PredicateValues.below(n, self.upper).to_dict(),
                "target_space": {"kind": "affine_image", "offset": 0,
                                 "columns": [1 << j for j in range(t)]},
                "bit_order": "lsb_first", "records": "forgotten", "outputs": "all_retained"}


def case(address_bits: int, seed: int, mutant: str | None = None, *, target_bits: int = 3,
         terms_per_target: int = 3) -> Case:
    """A loader for ``address_bits`` in 4..16 with at least one product term."""
    if not 4 <= address_bits <= 16 or (mutant is not None and mutant not in MUTANTS):
        raise ValueError("4..16 address bits and a known mutant required")
    rng = random.Random(f"wide-loader/{address_bits}/{seed}")
    low = address_bits - 1
    terms = []
    for j in range(target_bits):
        products = []
        for _ in range(terms_per_target):
            if rng.random() < 0.5:
                products.append((rng.randrange(low),))
            else:
                products.append(tuple(rng.sample(range(low), 2)))
        if j == 0 and all(len(p) == 1 for p in products):
            products[0] = tuple(rng.sample(range(low), 2))
        terms.append(tuple(products))
    upper = rng.randrange((1 << low) + 1, (1 << address_bits) + 1)
    return Case(address_bits, target_bits, tuple(terms), upper, mutant)
