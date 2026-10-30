"""Public SymQ demo: exact classical equivalence and coherent HMR channels.

No optional native compiler, QCEC, PolyBoRi or external corpus is required.
Install the package with python -m pip install -e ., then run
python /path/to/symq/examples/public_demo.py from any working directory.
"""
from __future__ import annotations

import json

from symq import Budget, Circuit, check_equivalence, make_algebra, simulate
from symq.experimental import VerificationContract, replay, verify
from symq.phase import PhaseProgram


def run_demo() -> dict:
    """Produce a checked, JSON-serializable example; never infer a wider theorem."""
    zero = Circuit(3)
    cancelling = Circuit(3).ccx(0, 1, 2).ccx(0, 1, 2)
    mutant = Circuit(3).ccx(0, 1, 2)

    eq = check_equivalence(zero, cancelling, backend="sparse", budget=Budget(max_seconds=5))
    neq = check_equivalence(zero, mutant, backend="sparse", budget=Budget(max_seconds=5))
    assert eq.equivalent and not neq.equivalent and neq.witness is not None
    assert zero.run(neq.witness) != mutant.run(neq.witness)

    algebra = make_algebra("zdd", width=mutant.width)
    outputs = simulate(mutant, algebra)
    target_anf = algebra.to_anf(outputs[2])
    assert target_anf.degree == 2

    # These input/data widths and the X-basis HMR grammar are intentionally tiny.
    # A prepared ancilla is reset after X-basis measurement; a conditional CZ
    # cancels the measurement-dependent phase on every input coherence.
    reference = PhaseProgram(2, 1)
    repaired = PhaseProgram(2, 1).ccx(0, 1, 2)
    event = repaired.hmr(2)
    repaired.cz_if(event, 0, 1)

    broken = PhaseProgram(2, 1).ccx(0, 1, 2)
    broken.hmr(2)  # deliberately omit the conditional phase correction

    contract = VerificationContract(theorem="full_channel", backend="zdd")
    good = verify(reference, repaired, contract, budget=Budget(max_seconds=10))
    bad = verify(reference, broken, contract, budget=Budget(max_seconds=10))
    assert good.equivalent and bad.outcome == "different" and bad.witness is not None
    replayed = replay(bad, reference, broken, contract, budget=Budget(max_seconds=10))
    assert replayed.witness_checked

    return {
        "classical": {
            "theorem": "full Boolean reversible equivalence",
            "equivalent": eq.equivalent,
            "mutant_equivalent": neq.equivalent,
            "counterexample_input": neq.witness,
            "target_anf_degree": target_anf.degree,
        },
        "hmr": {
            "theorem": "outcome-forgotten full coherent channel",
            "backend": "zdd (pure Python)",
            "equivalent": good.equivalent,
            "uncorrected_outcome": bad.outcome,
            "coherence_witness": list(bad.witness),
            "witness_replayed": replayed.witness_checked,
        },
        "limitations": "One 3-wire reversible circuit and one 2-data/1-ancilla HMR gadget; no general quantum or performance claim.",
    }


def main() -> None:
    print(json.dumps(run_demo(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
