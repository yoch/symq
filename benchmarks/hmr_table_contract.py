"""Development qualification of the HMR table-loader contract (issue #144, ``symq.labs``).

Every checker verdict is compared with the independent dense cq-state oracle in
``tests/testkit/table_channel_oracle.py``. The cohort is synthetic and public:

* the AND/HMR example loader (expected ``equivalent``, full channel checked with a
  borrowed wire entangled with a reference qubit);
* the controlled mutations (expected ``not_proved`` with a named obligation; the
  oracle must confirm a channel difference at the reported witness);
* input-admissibility attacks from the review of #157 (forged empty domain,
  deceptive operation name, expired or unsupported inherited budget), which must
  never be certified;
* a seeded random differential: the checker must prove exactly the cases where the
  oracle's channel equals the ideal one on every legal coherence.

No holdout, scaling or speed claim. The JSON is written before a nonzero exit.
Run: ``python -m benchmarks.hmr_table_contract --output evidence/hmr-table-contract.json``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import time
from collections import Counter
from fractions import Fraction
from itertools import product
from pathlib import Path

from benchmarks.environment import machine, receipt
from symq.experimental.hybrid import HOp, HybridProgram
from symq.labs.hmr_table_contract import (
    HmrTableContract,
    and_uncompute_example,
    check_hmr_table_xor,
)
from symq.resources import Budget, VerificationSession
from tests.testkit import table_channel_oracle as oracle
from tests.testkit.hmr_table_cases import (
    ADDRESS,
    MUTATIONS,
    TABLE,
    TARGET,
    channel_matches,
    contract,
    loader,
    random_program,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ("src/symq/labs/hmr_table_contract.py", "benchmarks/hmr_table_contract.py",
           "tests/testkit/table_channel_oracle.py", "tests/testkit/hmr_table_cases.py")


class _Deceptive(str):
    def __hash__(self):
        return hash("x")

    def __eq__(self, other):
        return other == "x"


def _row(name: str, kind: str, expected: str, run) -> dict:
    row: dict = {"case": name, "kind": kind, "expected": expected, "passed": False}
    started = time.perf_counter()
    try:
        row.update(run())
    except Exception as error:  # noqa: BLE001 - a failure is evidence, never lost
        row["error"] = f"{type(error).__name__}: {error}"
        row["observed"] = "raised"
    row["seconds"] = time.perf_counter() - started
    row["passed"] = row.get("observed") == expected and row.get("oracle_ok", True)
    return row


def _example() -> dict:
    program, spec = and_uncompute_example()
    result = check_hmr_table_xor(program, spec)
    return {"observed": result.status, "result": result.to_dict(),
            "oracle_ok": channel_matches(program)}


def _mutation(name: str) -> dict:
    options, _obligation = MUTATIONS[name]
    program = loader(**options)
    clean = (5, 6) if options.get("extra_event") else (5,)
    spec = contract(clean=clean, width=program.width)
    result = check_hmr_table_xor(program, spec)
    observed = f"{result.status}:{result.obligation}"
    ok = not channel_matches(program)
    if result.status == "not_proved":
        x, y = result.witness["pair"]
        ok &= (oracle.forgotten(program, oracle.unit(x, y))
               != oracle.ideal(oracle.unit(x, y), ADDRESS, TARGET, TABLE))
    return {"observed": observed, "result": result.to_dict(), "oracle_ok": ok}


def _refused(call) -> dict:
    try:
        result = call()
    except (ValueError, TypeError) as error:
        return {"observed": "refused", "reason": f"{type(error).__name__}: {error}"}
    return {"observed": "refused" if result.status != "equivalent" else "equivalent",
            "status": result.status, "result": result.to_dict()}


def _forged_empty_domain():
    spec = HmrTableContract(2, (0,), (1,), (), (), (0, 0), (0, 1))
    object.__setattr__(spec, "legal_addresses", ())
    return check_hmr_table_xor(HybridProgram(2), spec)


def _deceptive_name():
    op = HOp("x", (1,))
    object.__setattr__(op, "kind", _Deceptive("h"))
    program = HybridProgram(2)
    program.ops.append(op)
    return check_hmr_table_xor(program, HmrTableContract(2, (0,), (1,), (), (), (1, 1), (0, 1)))


def _expired_budget():
    spec = HmrTableContract(2, (0,), (1,), (), (), (0, 0), (0, 1))
    return check_hmr_table_xor(HybridProgram(2), spec, budget=Budget(max_seconds=1e-12))


def _inherited_max_nodes():
    spec = HmrTableContract(2, (0,), (1,), (), (), (0, 0), (0, 1))
    with VerificationSession(Budget(max_nodes=1)):
        return check_hmr_table_xor(HybridProgram(2), spec)


def _differential(seed: int, programs: int) -> dict:
    rng = random.Random(seed)
    counts: Counter = Counter()
    disagreements = []
    for index in range(programs):
        program = random_program(rng)
        images = {(x, y): oracle.forgotten(program, oracle.unit(x, y))
                  for x, y in product(range(1 << 3), repeat=2)}
        for row0, row1 in product((0, 1), repeat=2):
            for legal in ((0,), (1,), (0, 1)):
                spec = HmrTableContract(4, (0,), (1,), (3,), (2,), (row0, row1), legal)
                states = spec.legal_inputs()
                same = all(images[x, y] == {(spec.ideal(x), spec.ideal(y)): Fraction(1)}
                           for x, y in product(states, repeat=2))
                result = check_hmr_table_xor(program, spec)
                agree = result.equivalent == same
                if agree and not same:
                    x, y = result.witness["pair"]
                    agree = images[x, y] != {(spec.ideal(x), spec.ideal(y)): Fraction(1)}
                counts[result.obligation or result.status] += 1
                if not agree:
                    disagreements.append({"program": index, "table": [row0, row1],
                                          "legal": list(legal), "status": result.status})
    total = sum(counts.values())
    return {"observed": "agree" if not disagreements and total == programs * 12 else "disagree",
            "cases": total, "counts": dict(counts), "disagreements": disagreements[:20]}


def run(*, seed: int = 144, programs: int = 400) -> dict:
    rows = [_row("and_uncompute_example", "positive", "equivalent", _example)]
    for name in sorted(MUTATIONS):
        obligation = MUTATIONS[name][1]
        rows.append(_row(name, "mutation", f"not_proved:{obligation}",
                         lambda name=name: _mutation(name)))
    for name, call in (("forged empty legal domain", _forged_empty_domain),
                       ("deceptive operation name", _deceptive_name),
                       ("expired deadline, empty stream", _expired_budget),
                       ("inherited max_nodes", _inherited_max_nodes)):
        rows.append(_row(name, "admissibility", "refused", lambda call=call: _refused(call)))
    rows.append(_row("random differential", "differential", "agree",
                     lambda: _differential(seed, programs)))
    return {
        "schema_version": 1, "kind": "symq_hmr_table_contract_qualification",
        "scope": "synthetic public development cohort; no holdout or speed claim",
        "seed": seed, "programs": programs, "machine": machine(), "source": receipt(),
        "source_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                          for name in SOURCES},
        "rows": rows, "passed": all(row["passed"] for row in rows),
        "failed": [row["case"] for row in rows if not row["passed"]],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=144)
    parser.add_argument("--programs", type=int, default=400)
    args = parser.parse_args(argv)
    try:
        report = run(seed=args.seed, programs=args.programs)
    except Exception as error:  # noqa: BLE001 - setup failures are written too
        report = {"schema_version": 1, "kind": "symq_hmr_table_contract_qualification",
                  "passed": False, "setup_error": f"{type(error).__name__}: {error}"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"passed": report["passed"], "failed": report.get("failed")}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
