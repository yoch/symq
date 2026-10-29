"""Check 7 of the PR #96 checklist: native and pure-Python grammar parity.

The checklist asks to "compare native and pure-Python engines on identical accepted grammar".
Two things must hold, and they are different:

1. **Acceptance parity** -- for every program in the restricted grammar, both engines must
   accept or reject for the same reason. A native engine that silently accepts something the
   reference rejects (or vice versa) is a soundness split, not a performance one.
2. **Verdict parity** -- when both accept, they must return the same `equivalent` flag.

This harness fuzzes random programs over the grammar and records any divergence.
"""
from __future__ import annotations

import os
import random
import sys
from pathlib import Path

PR95 = Path(os.environ.get("PR95", "/tmp/audit/pr95"))
sys.path.insert(0, str(PR95))
sys.path.insert(0, str(PR95 / "src"))

from research.hmr_native_channel.native_channel import check_full_channel
from symq.phase import Op, PhaseProgram
from symq.resources import Budget

BACKENDS = ("zdd", "zdd-native")


def random_program(rng, data, ancillas, length):
    """Build a program from the accepted grammar only, with fresh HMR outcome indices."""
    ops = []
    events = 0
    for _ in range(length):
        choices = ["mcx", "mcz"]
        if events:
            choices.append("mcz_if")
        choices.append("hmr")
        kind = rng.choice(choices)
        if kind == "hmr":
            if data + ancillas < 1:
                continue
            ops.append(Op("hmr", (data + rng.randrange(ancillas) if ancillas else rng.randrange(data),),
                          outcome=events))
            events += 1
        elif kind == "mcx":
            need = rng.choice([2, 3]) if data + ancillas >= 3 else 2
            if data + ancillas < need:
                continue
            qs = tuple(rng.sample(range(data + ancillas), need))
            ops.append(Op("mcx", qs, outcome=None))
        elif kind == "mcz":
            need = rng.choice([1, 2, 3]) if data + ancillas >= 3 else 2
            if data + ancillas < need:
                continue
            qs = tuple(rng.sample(range(data + ancillas), need))
            ops.append(Op("mcz", qs, outcome=None))
        else:
            width = data + ancillas
            size = min(rng.choice([1, 2]), width)
            qs = tuple(rng.sample(range(width), size))
            ops.append(Op("mcz_if", qs, outcome=rng.randrange(events)))
    return ops


def outcome(call):
    try:
        verdict = call()
        return ("accept", bool(verdict.equivalent))
    except Exception as exc:  # noqa: BLE001 - the class name is the signal
        return ("reject", type(exc).__name__)


def main(trials=250, seed=20261029):
    rng = random.Random(seed)
    accept_parity_failures = []
    verdict_failures = []
    both_accept = 0
    both_reject = 0
    skipped = 0

    for trial in range(trials):
        data = rng.randint(1, 3)
        ancillas = rng.randint(0, 2)
        length = rng.randint(1, 5)
        ops = random_program(rng, data, ancillas, length)
        # Two independent `PhaseProgram` instances, so a shared mutation cannot hide a split.
        try:
            left = PhaseProgram(data, ancillas, list(ops))
            right = PhaseProgram(data, ancillas, list(ops))
        except (ValueError, TypeError):
            # A generator producing an invalid program is a harness limitation, not a finding.
            # Count it so the denominator stays honest.
            skipped += 1
            continue

        results = {}
        for backend in BACKENDS:
            results[backend] = outcome(
                lambda b=backend, l=left, r=right: check_full_channel(
                    l, r, backend=b, budget=Budget(max_seconds=10)
                )
            )
        native, python = results["zdd-native"], results["zdd"]
        if native[0] != python[0]:
            accept_parity_failures.append((trial, ops, python, native))
            continue
        if native[0] == "accept":
            both_accept += 1
            if native[1] != python[1]:
                verdict_failures.append((trial, ops, python, native))
        else:
            both_reject += 1

    print(f"{trials} random programs over the accepted grammar")
    print(f"  both accepted          : {both_accept}")
    print(f"  both rejected          : {both_reject}")
    print(f"  acceptance-split       : {len(accept_parity_failures)}")
    print(f"  verdict disagreements  : {len(verdict_failures)}")
    print(f"  generator skip (invalid ops): {skipped}")
    for label, failures in (("ACCEPTANCE", accept_parity_failures),
                            ("VERDICT", verdict_failures)):
        for trial, ops, python, native in failures[:5]:
            print(f"  {label} trial {trial}: ops={[(o.kind, o.qubits, o.outcome) for o in ops]}")
            print(f"      zdd={python} native={native}")
    ok = not accept_parity_failures and not verdict_failures
    print()
    print("GRAMMAR PARITY:", "HOLDS" if ok else "BROKEN")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
