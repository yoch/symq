"""Pilot A: what does the factored/channel criterion actually buy?

Three questions, each with a falsifiable answer:

A1. **Size.** Is the factorised form ``(phi0, g)`` smaller than the expanded ANF ``phi(x, m)``?
    Prediction of the factorisation argument: it should be. Measurement says otherwise, because
    the accepted fragment makes ``phi`` *affine* in ``m``: every monomial carries at most one
    outcome variable, so the expanded ANF is already ``|phi0| + sum_j |g_j|`` monomials.

A2. **Acceptance.** Does the channel criterion accept programs that the strict criterion
    rejects? Prediction: yes, and the count should grow with the number of measurements.

A3. **Usefulness.** Of the programs it newly accepts, how many are legitimately the same channel
    (checked by the density-matrix oracle) -- and how many are ones a user would *want* to
    accept? The second half is a judgement, so the pilot records the shapes of the programs
    rather than only their number.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[4]
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(ROOT / "src"))

import channel
import factored

from symq.phase import PhaseProgram, check_phase_equivalence, phase_semantics


def random_program(rng: random.Random, data: int, ancillas: int, ops: int) -> PhaseProgram:
    program = PhaseProgram(data, ancillas)
    for _ in range(ops):
        kind = rng.choice(["mcx", "mcx", "mcz", "hmr", "mcz_if"])
        if kind == "hmr":
            program.hmr(rng.randrange(program.width))
            continue
        count = rng.randint(1, min(3, program.width))
        qubits = rng.sample(range(program.width), count)
        if kind == "mcz_if" and program.measurements:
            program.mcz_if(rng.randrange(program.measurements), *qubits)
        elif kind == "mcx":
            program.mcx(*qubits)
        else:
            program.mcz(*qubits)
    return program


def size_question() -> list[dict]:
    """A1: compare the two representations on programs with many independent measurements."""
    rows = []
    for count in (2, 4, 8, 16, 32, 64):
        program = PhaseProgram(4, count)
        for index in range(count):
            wire = 4 + index
            program.mcx(index % 3, wire)
            program.hmr(wire)
        form = factored.factor(program)
        expanded = phase_semantics(program).phase
        rows.append({
            "measurements": program.measurements,
            "factored_terms": form.phase_terms(),
            "expanded_terms": len(expanded.terms),
            "ratio": (len(expanded.terms) / form.phase_terms()) if form.phase_terms() else None,
            "max_monomial_degree": expanded.degree,
        })
    return rows


def acceptance_question(trials: int = 300) -> dict:
    """A2: count programs the strict criterion rejects and the channel criterion accepts."""
    rng = random.Random(20261028)
    statistics = {"trials": trials, "strict_accepts": 0, "channel_accepts": 0,
                  "both_accept": 0, "only_channel": 0, "oracle_confirmed_only_channel": 0,
                  "disagreements_with_oracle": 0, "widened_examples": []}
    identity_cache: dict[tuple[int, int], PhaseProgram] = {}
    for _ in range(trials):
        data = rng.randint(1, 2)
        ancillas = rng.randint(1, 2)
        program = random_program(rng, data, ancillas, rng.randint(2, 7))
        key = (data, ancillas)
        if key not in identity_cache:
            identity_cache[key] = PhaseProgram(data, ancillas)
        identity = identity_cache[key]
        strict = check_phase_equivalence(program, identity)
        strict_ok = strict.equivalent and not strict.violations
        verdict = factored.equivalent_channel(program, identity)
        oracle = channel.same_channel(program, identity)
        if verdict.equivalent != oracle:
            statistics["disagreements_with_oracle"] += 1
        statistics["strict_accepts"] += strict_ok
        statistics["channel_accepts"] += verdict.equivalent
        if strict_ok and verdict.equivalent:
            statistics["both_accept"] += 1
        if verdict.equivalent and not strict_ok:
            statistics["only_channel"] += 1
            if oracle:
                statistics["oracle_confirmed_only_channel"] += 1
            if len(statistics["widened_examples"]) < 5:
                statistics["widened_examples"].append({
                    "ops": [f"{op.kind}{list(op.qubits)}"
                            + (f" if m{op.outcome}" if op.outcome is not None else "")
                            for op in program.ops],
                    "strict_violations": list(strict.violations),
                    "oracle_confirms": oracle,
                })
    return statistics


def main() -> int:
    payload = {"size": size_question(), "acceptance": acceptance_question()}
    out = Path(sys.argv[1] if len(sys.argv) > 1 else HERE.parent / "PILOT_A.json")
    out.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload["size"], indent=1))
    acceptance = payload["acceptance"]
    print({k: v for k, v in acceptance.items() if k != "widened_examples"})
    for example in acceptance["widened_examples"][:3]:
        print(" ", example)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
