"""Generate the pre-registered blind corpus ``corpus/blind`` (issue #18, experiment E3).

The corpus is written once and frozen by its manifest *before* any symbolic measurement:
the only checks performed here are concrete executions (the circuits really compute what
their family name says). No family, size or seed below was chosen by looking at a symbolic
backend's behaviour; the sizes are fixed by the width limit of ``zdd-native`` (64 wires)
and by a geometric progression.

Families (all X/CX/CCX/MCX, written as OpenQASM 3):
  adder_n      Cuccaro ripple-carry adder, b <- a + b, carry into z (width 2n + 2);
  cadder_n     the same adder controlled by one extra wire (width 2n + 3);
  mult_n       shift-and-add multiplier p <- a * b with controlled Cuccaro adders (4n + 1);
  incr_n       n-bit incrementer x <- x + 1 with an MCX cascade (width n);
  rand_w_g_k   uniformly random MCX circuits, at most k controls (seeded).

Usage: python benchmarks/generate_blind.py [--check-only]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

from symq.circuit import Circuit
from symq.corpus import git_blob_sha1, sha256_hex
from symq.generators import random_circuit
from symq.qasm import parse_qasm

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "corpus" / "blind"
SEED = "symq-blind-2026-10-27"


def maj(c: Circuit, x: int, y: int, z: int, ctl: tuple[int, ...] = ()) -> None:
    c.mcx(*ctl, z, y)
    c.mcx(*ctl, z, x)
    c.mcx(*ctl, x, y, z)


def uma(c: Circuit, x: int, y: int, z: int, ctl: tuple[int, ...] = ()) -> None:
    c.mcx(*ctl, x, y, z)
    c.mcx(*ctl, z, x)
    c.mcx(*ctl, x, y)


def cuccaro(c: Circuit, a: list[int], b: list[int], carry_in: int, carry_out: int,
            ctl: tuple[int, ...] = ()) -> None:
    """b <- a + b (mod 2^n), carry_out ^= carry; ``carry_in`` must be 0 and is restored."""
    n = len(a)
    maj(c, carry_in, b[0], a[0], ctl)
    for i in range(1, n):
        maj(c, a[i - 1], b[i], a[i], ctl)
    c.mcx(*ctl, a[n - 1], carry_out)
    for i in range(n - 1, 0, -1):
        uma(c, a[i - 1], b[i], a[i], ctl)
    uma(c, carry_in, b[0], a[0], ctl)


def normalise(circuit: Circuit) -> Circuit:
    """Rename every gate after its control count (``mcx`` with 0..2 controls -> x/cx/ccx)."""
    out = Circuit(circuit.width)
    for gate in circuit.gates:
        out.append({1: "x", 2: "cx", 3: "ccx"}.get(len(gate.qubits), "mcx"), *gate.qubits)
    return out


def adder(n: int, controlled: bool = False) -> Circuit:
    # wires: c0, b[0..n-1], a[0..n-1], z, [ctl]
    width = 2 * n + 2 + int(controlled)
    c = Circuit(width)
    b = list(range(1, n + 1))
    a = list(range(n + 1, 2 * n + 1))
    ctl = (2 * n + 2,) if controlled else ()
    cuccaro(c, a, b, 0, 2 * n + 1, ctl)
    return normalise(c)


def multiplier(n: int) -> Circuit:
    # wires: c0, a[0..n-1], b[0..n-1], p[0..2n-1]
    width = 4 * n + 1
    c = Circuit(width)
    a = list(range(1, n + 1))
    b = list(range(n + 1, 2 * n + 1))
    p = list(range(2 * n + 1, 4 * n + 1))
    for j in range(n):
        cuccaro(c, a, p[j:j + n], 0, p[j + n], (b[j],))
    return normalise(c)


def incrementer(n: int) -> Circuit:
    c = Circuit(n)
    for i in range(n - 1, 0, -1):
        c.mcx(*range(i), i)
    c.x(0)
    return normalise(c)


def random_family(width: int, gates: int, controls: int) -> Circuit:
    digest = hashlib.sha256(f"{SEED}/rand/{width}/{gates}/{controls}".encode()).hexdigest()
    rng = random.Random(int(digest[:16], 16))
    return normalise(random_circuit(width, gates, rng, max_controls=controls))


def bits(value: int, wires: list[int]) -> int:
    return sum(((value >> i) & 1) << w for i, w in enumerate(wires))


def read(state: int, wires: list[int]) -> int:
    return sum(((state >> w) & 1) << i for i, w in enumerate(wires))


def check_adder(circuit: Circuit, n: int, controlled: bool, rng: random.Random) -> None:
    b = list(range(1, n + 1))
    a = list(range(n + 1, 2 * n + 1))
    for _ in range(200):
        x, y, z = rng.getrandbits(n), rng.getrandbits(n), rng.getrandbits(1)
        on = rng.getrandbits(1) if controlled else 1
        state = bits(x, a) | bits(y, b) | z << (2 * n + 1)
        if controlled:
            state |= on << (2 * n + 2)
        out = circuit.run(state)
        total = x + y if on else y
        expect = bits(x, a) | bits(total % (1 << n), b) | (z ^ (total >> n)) << (2 * n + 1)
        if controlled:
            expect |= on << (2 * n + 2)
        assert out == expect, (n, controlled, x, y, z, on)


def check_multiplier(circuit: Circuit, n: int, rng: random.Random) -> None:
    a = list(range(1, n + 1))
    b = list(range(n + 1, 2 * n + 1))
    p = list(range(2 * n + 1, 4 * n + 1))
    for _ in range(200):
        x, y = rng.getrandbits(n), rng.getrandbits(n)
        out = circuit.run(bits(x, a) | bits(y, b))
        assert read(out, p) == x * y and read(out, a) == x and read(out, b) == y, (n, x, y)
        assert out & 1 == 0


def check_incrementer(circuit: Circuit, n: int, rng: random.Random) -> None:
    for _ in range(200):
        x = rng.getrandbits(n)
        assert circuit.run(x) == (x + 1) % (1 << n), (n, x)


def to_qasm(circuit: Circuit) -> str:
    lines = ["OPENQASM 3.0;", 'include "stdgates.inc";', f"qubit[{circuit.width}] q;"]
    for gate in circuit.gates:
        operands = ", ".join(f"q[{q}]" for q in gate.qubits)
        k = len(gate.qubits) - 1
        if k <= 2:
            lines.append(f"{('x', 'cx', 'ccx')[k]} {operands};")
        else:
            lines.append(f"ctrl({k}) @ x {operands};")
    return "\n".join(lines) + "\n"


FAMILIES = (
    [("adder", n) for n in (4, 8, 16, 24, 31)]
    + [("cadder", n) for n in (4, 8, 16, 24, 30)]
    + [("mult", n) for n in (2, 3, 4, 5, 6, 8, 10)]
    + [("incr", n) for n in (16, 32, 48, 64)]
    + [("rand", (w, g, k)) for w in (16, 32, 64) for g, k in ((100, 2), (100, 4), (400, 2))]
)


def build(family: str, parameter, rng: random.Random) -> tuple[str, Circuit]:
    if family == "adder":
        circuit = adder(parameter)
        check_adder(circuit, parameter, False, rng)
        return f"adder_{parameter}", circuit
    if family == "cadder":
        circuit = adder(parameter, controlled=True)
        check_adder(circuit, parameter, True, rng)
        return f"cadder_{parameter}", circuit
    if family == "mult":
        circuit = multiplier(parameter)
        check_multiplier(circuit, parameter, rng)
        return f"mult_{parameter}", circuit
    if family == "incr":
        circuit = incrementer(parameter)
        check_incrementer(circuit, parameter, rng)
        return f"incr_{parameter}", circuit
    width, gates, controls = parameter
    return f"rand_{width}_{gates}_{controls}", random_family(width, gates, controls)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check-only", action="store_true",
                        help="regenerate in memory and compare with the frozen files")
    args = parser.parse_args()
    rng = random.Random(SEED)
    entries, problems = [], []
    for family, parameter in FAMILIES:
        name, circuit = build(family, parameter, rng)
        text = to_qasm(circuit)
        parsed = parse_qasm(text)
        assert parsed.width == circuit.width and parsed.gates == circuit.gates, name
        assert circuit.width <= 64, name
        data = text.encode()
        path = TARGET / f"{name}.qasm"
        if args.check_only:
            if not path.is_file() or path.read_bytes() != data:
                problems.append(name)
            continue
        entries.append({
            "name": name, "file": path.name, "family": family, "split": "holdout",
            "git_blob_sha1": git_blob_sha1(data), "sha256": sha256_hex(data),
            "bytes": len(data), "status": "supported", "width": circuit.width,
            "gates": len(circuit.gates),
            "max_controls": max(len(g.qubits) - 1 for g in circuit.gates),
        })
        if not args.check_only:
            TARGET.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    if args.check_only:
        print("ok" if not problems else f"differs: {problems}")
        return 1 if problems else 0
    manifest = {
        "source": {
            "generator": "benchmarks/generate_blind.py",
            "seed": SEED,
            "license": "generated by symq (same license as the repository)",
        },
        "split_policy": (
            "Pre-registered blind corpus for issue #18 (E3). Frozen by this manifest before "
            "any symbolic backend was run on it; only concrete-execution checks of the "
            "arithmetic families were run before freezing. Never use it for tuning. "
            "Every circuit is 'holdout'."
        ),
        "circuits": entries,
    }
    (TARGET / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"{len(entries)} circuits written to {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
