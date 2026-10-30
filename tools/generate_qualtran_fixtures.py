"""Regenerate real GF2MulMBUC imports using the pinned optional Qualtran build.

Install in an isolated environment:
  pip install 'qualtran @ git+https://github.com/quantumlib/Qualtran.git@638777fac4379bc62e2a1e4a52cf1a1753895d48'
  PYTHONPATH=src python tools/generate_qualtran_fixtures.py

This traverses live CompositeBloq soquet connections, including Parity and
classical CZ controls. It does not reconstruct an algorithm from its formulas.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path

from symq.circuit import UnsupportedOperation
from symq.experimental.qualtran import (
    QUALTRAN_COMMIT,
    QUALTRAN_SOURCE,
    QUALTRAN_SOURCE_SHA256,
    fixture_digest,
)


class Compiler:
    def __init__(self, degree, *, cleanup):
        self.degree = degree
        self.cleanup = cleanup
        self.lines = []
        self.next_bit = 0
        self.allocations = 0
        self.consumed = set()
        self.trace = []

    def bit(self):
        result = f"b{self.next_bit}"
        self.next_bit += 1
        return result

    def compile(self, bloq, inputs):
        import numpy as np
        from qualtran import LeftDangle

        cb = bloq.decompose_bloq()
        values = {}

        def resolve(soq):
            if isinstance(soq, np.ndarray):
                return tuple(resolve(s) for s in soq)
            if soq.binst == LeftDangle:
                return inputs[soq.reg.name]
            return values[soq]

        def bind(soq, value):
            if isinstance(soq, np.ndarray):
                if len(soq) != len(value):
                    raise UnsupportedOperation("Qualtran output shape mismatch")
                for s, v in zip(soq, value):
                    bind(s, v)
            else:
                values[soq] = value

        for instance, incoming, outgoing in cb.iter_bloqsoqs():
            current = instance.bloq
            name = type(current).__name__
            args = {key: resolve(value) for key, value in incoming.items()}
            self.trace.append({"type": name, "inputs": args})
            if name == "Split":
                out = {"reg": tuple((q,) for q in args["reg"])}
            elif name == "Join":
                out = {"reg": tuple(q for bundle in args["reg"] for q in bundle)}
            elif name == "Allocate":
                if self.cleanup or self.allocations or int(current.dtype.num_qubits) != self.degree:
                    raise UnsupportedOperation("unexpected Qualtran allocation")
                self.allocations += 1
                out = {"reg": tuple(reversed(range(2 * self.degree, 3 * self.degree)))}
            elif name == "GF2ShiftRight":
                out = self.compile(current, args)
            elif name in {"CNOT", "Toffoli"}:
                ctrl = args["ctrl"]
                wires = ((ctrl[0],) if name == "CNOT" else tuple(q[0] for q in ctrl))
                wires += (args["target"][0],)
                if self.consumed.intersection(wires):
                    raise UnsupportedOperation("quantum use after MeasureX consumption")
                self.lines.append(("CX" if name == "CNOT" else "CCX") + " " +
                                  " ".join(f"q{q}" for q in wires))
                out = args
            elif name == "MeasureX":
                q = args["q"][0]
                if not self.cleanup or q < 2 * self.degree or q in self.consumed:
                    raise UnsupportedOperation("MeasureX must consume each result wire once")
                self.consumed.add(q)
                bit = self.bit()
                self.lines.append(f"HMR q{q} {bit}")
                out = {"c": bit}
            elif name == "Parity":
                bit = self.bit()
                self.lines.append(f"BIT_STORE0 {bit}")
                for source in args["x"]:
                    self.lines.append(f"OXOR {bit} {source}")
                out = {**args, "parity": bit}
            elif name == "ClassicallyControlled":
                from qualtran import CBit
                if (type(current.subbloq).__name__ != "CZ"
                        or current.ctrl_spec.qdtypes != (CBit(),)
                        or len(current.ctrl_spec.cvs) != 1
                        or int(current.ctrl_spec.cvs[0]) != 1):
                    raise UnsupportedOperation("only one-bit classical positive CZ control")
                wires = (args["q1"][0], args["q2"][0])
                if self.consumed.intersection(wires):
                    raise UnsupportedOperation("quantum use after MeasureX consumption")
                self.lines.append(f"CZ q{wires[0]} q{wires[1]} if {args['ctrl']}")
                out = args
            elif name == "Discard":
                from qualtran import CBit
                if any(reg.dtype != CBit() for reg in current.signature.lefts()):
                    raise UnsupportedOperation("only classical discard is supported")
                out = {}
            else:
                raise UnsupportedOperation(f"unsupported actual Qualtran bloq {name}")
            for register, soq in zip(current.signature.rights(), outgoing):
                bind(soq, out[register.name])
        return {key: resolve(soq) for key, soq in cb.final_soqs().items()}

    def align(self, outputs, expected):
        current = [q for name in expected for q in outputs[name]]
        desired = [q for name in expected for q in expected[name]]
        if sorted(current) != sorted(desired):
            raise UnsupportedOperation("unexpected Qualtran quantum output interface")
        for i, wire in enumerate(desired):
            if current[i] != wire:
                other = current[i]
                self.lines.append(f"SWAP q{other} q{wire}")
                current = [wire if q == other else other if q == wire else q for q in current]


def generate(degree):
    import qualtran.bloqs.gf_arithmetic.gf2_multiplication as source_module
    from qualtran.bloqs.gf_arithmetic.gf2_multiplication import GF2MulMBUC, GF2Multiplication

    if hashlib.sha256(Path(source_module.__file__).read_bytes()).hexdigest() != QUALTRAN_SOURCE_SHA256:
        raise UnsupportedOperation("installed Qualtran source differs from pinned public source")

    inputs = {"x": tuple(reversed(range(degree))),
              "y": tuple(reversed(range(degree, 2 * degree)))}
    full = {**inputs, "result": tuple(reversed(range(2 * degree, 3 * degree)))}
    prep = Compiler(degree, cleanup=False)
    prep.align(prep.compile(GF2Multiplication(degree), inputs), full)
    clean = Compiler(degree, cleanup=True)
    clean.align(clean.compile(GF2MulMBUC(degree), full), inputs)
    if clean.consumed != set(range(2 * degree, 3 * degree)):
        raise UnsupportedOperation("incomplete MeasureX consumption/zero embedding")
    preparer, cleanup = "\n".join(prep.lines), "\n".join(clean.lines)
    trace = json.dumps({"preparer": prep.trace, "cleanup": clean.trace}, sort_keys=True)
    return {
        "schema_version": 1, "degree": degree, "preparer": preparer, "cleanup": cleanup,
        "contract": {
            "data": 2 * degree, "zero_ancillas": degree,
            "precondition": "result register prepared by imported GF2Multiplication",
            "comparison": "full channel on all data coherences after preparation",
            "embedding": "consumed MeasureX wires are returned as terminal |0> wires by HMR",
            "classical_outputs": "discarded",
        },
        "provenance": {
            "repository": "https://github.com/quantumlib/Qualtran", "commit": QUALTRAN_COMMIT,
            "source": QUALTRAN_SOURCE, "license": "Apache-2.0",
            "source_sha256": hashlib.sha256(Path(source_module.__file__).read_bytes()).hexdigest(),
            "normalized_sha256": fixture_digest(preparer, cleanup),
            "decomposition_trace_sha256": hashlib.sha256(trace.encode()).hexdigest(),
            "decomposition_trace": json.loads(trace),
            "qualtran_version": importlib.metadata.version("qualtran"),
            "python_version": platform.python_version(),
            "generator": "tools/generate_qualtran_fixtures.py",
            "preparer_bloq": "GF2Multiplication", "cleanup_bloq": "GF2MulMBUC",
            "register_bit_order": "wire q_i is polynomial coefficient i within each register",
        },
    }


def main():
    distribution = importlib.metadata.distribution("qualtran")
    direct = json.loads(distribution.read_text("direct_url.json") or "{}")
    if direct.get("vcs_info", {}).get("commit_id") != QUALTRAN_COMMIT:
        raise SystemExit("Install the exact pinned Qualtran git commit before regeneration")
    destination = Path(__file__).resolve().parents[1] / "benchmarks/corpus/qualtran"
    destination.mkdir(parents=True, exist_ok=True)
    for degree in (1, 2):
        payload = generate(degree)
        (destination / f"gf2mul_mbuc_m{degree}.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n")
        print(f"generated actual GF2MulMBUC degree={degree} {payload['provenance']['normalized_sha256']}")


if __name__ == "__main__":
    main()
