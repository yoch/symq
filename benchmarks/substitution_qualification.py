"""A small, honest substitution-qualification matrix on the installed SymQ engines.

This is NOT an independent holdout: all QCEC and Qualtran files used here were
previously inspected during SymQ development. Every mutation added to them is
a newly authored synthetic test, not an independently compiled optimization.

Use:
    python -m benchmarks.substitution_qualification --output /tmp/substitutions.json
Each measurement is in a fresh, hard-bounded subprocess. Repetitions are
randomized by a fixed manifest seed; report all unsupported and incomplete
cases. Do not compare unlike semantic theorem types as performance competitors.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .environment import machine, receipt

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "benchmarks/substitution_manifest.json"
QCEC_MANIFEST = ROOT / "benchmarks/corpus/qcec/MANIFEST.json"


def _digest(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _harness_fingerprints() -> dict[str, str]:
    """File identities for the runner, public case manifest and imported corpora."""
    paths = (
        "benchmarks/substitution_qualification.py",
        "benchmarks/substitution_worker.py",
        "benchmarks/substitution_crosscheck.py",
        "benchmarks/substitution_manifest.json",
        "benchmarks/hmr_qualification.py",
        "benchmarks/hmr_qualification_manifest.json",
        "benchmarks/corpus/qcec/MANIFEST.json",
        "benchmarks/corpus/qualtran/gf2mul_mbuc_m1.json",
        "benchmarks/corpus/qualtran/gf2mul_mbuc_m2.json",
    )
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in paths}


def load_manifest(path: Path = MANIFEST) -> dict:
    document = json.loads(path.read_text(encoding="utf-8"))
    if (type(document) is not dict or document.get("schema_version") != 1
            or type(document.get("cases")) is not list
            or not document["cases"]):
        raise ValueError("nonempty version-one substitution manifest required")
    ids = [case.get("id") for case in document["cases"]]
    if any(type(name) is not str or not name for name in ids) or len(ids) != len(set(ids)):
        raise ValueError("manifest case identifiers must be unique nonempty strings")
    allowed = {"classical", "relational", "hybrid", "qualtran", "qcec", "arithmetic"}
    for case in document["cases"]:
        if set(case) != {"id", "family", "scenario", "expected", "provenance", "theorem"}:
            raise ValueError("manifest case schema drift")
        if case["family"] not in allowed:
            raise ValueError(f"unknown manifest family {case['family']}")
        if case["expected"] not in {"proved", "not_proved", "precondition_failed", "unsupported"}:
            raise ValueError("unknown expected result")
        if case["provenance"] not in {
                "synthetic", "existing-qcec-plus-synthetic-rewrite",
                "existing-qualtran-plus-context", "existing-qcec-admissibility",
                "same-repo-independent-algebraic-decompositions"}:
            raise ValueError("unattributed case provenance")
    return document


def _qcec(name: str):
    """Read a source-pinned public QASM and refuse any checksum change."""
    from symq.qasm import parse_qasm
    manifest = json.loads(QCEC_MANIFEST.read_text(encoding="utf-8"))
    source = next((x for x in manifest["circuits"] if x["name"] == name), None)
    if source is None:
        raise ValueError(f"unknown QCEC source {name}")
    path = ROOT / "benchmarks/corpus/qcec" / source["file"]
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != source["sha256"]:
        raise ValueError(f"QCEC source checksum differs for {name}")
    return parse_qasm(raw.decode("utf-8"))


def _classical(case: dict) -> dict:
    from symq import Circuit, Gate
    from symq.labs.classical_transcript import (
        Common,
        Program,
        Slot,
        UnprovedSubstitution,
        digest,
        verify_transcript,
    )

    name = case["scenario"]
    local_id = Program.freeze(Circuit(3))
    controls = Program.freeze(Circuit(3).ccx(0, 1, 2).ccx(0, 1, 2))
    single = Program.freeze(Circuit(3).ccx(0, 1, 2))
    if name == "cancel":
        steps = [Common((Gate("cx", (0, 1)),)),
                 Slot(controls, local_id, (0, 1, 2)),
                 Common((Gate("x", (2,)),))]
        width = 3
    elif name == "dropped_ccx":
        steps = [Slot(single, local_id, (0, 1, 2))]
        width = 3
    elif name == "dirty_restored":
        steps = [Slot(controls, local_id, (0, 1, 2), preserved=(2,))]
        width = 3
    elif name == "dirty_not_restored":
        steps = [Slot(single, single, (0, 1, 2), preserved=(2,))]
        width = 3
    elif name == "connected_71":
        width = 71
        steps = [Common(tuple(Gate("cx", (i, i + 1)) for i in range(70))),
                 Slot(controls, local_id, (10, 11, 12)),
                 Common((Gate("cx", (12, 13)),)),
                 Slot(controls, local_id, (12, 13, 14))]
    elif name in {"qcec_alu1", "qcec_c2"}:
        qcec_name = "alu1_198" if name == "qcec_alu1" else "c2_181"
        qcec = _qcec(qcec_name)
        width = qcec.width
        # Actual pinned QCEC gates are an unchanged COMMON prefix.
        # The appended canceling pair is a synthetic local optimization.
        twice = Program.freeze(Circuit(2).cx(0, 1).cx(0, 1))
        empty = Program.freeze(Circuit(2))
        steps = [Common(tuple(qcec.gates)), Slot(twice, empty, (0, 1))]
    else:
        raise ValueError("unrecognized classical case")

    left, right = [], []
    for step in steps:
        if isinstance(step, Common):
            left.extend(step.gates)
            right.extend(step.gates)
        else:
            for sink, program in ((left, step.reference), (right, step.candidate)):
                sink.extend(Gate(g.name, tuple(step.wires[q] for q in g.qubits))
                            for g in program.gates)
    original, candidate = Circuit(width, left), Circuit(width, right)
    small_oracle = None
    if width <= 6:
        small_oracle = all(
            original.run(x) == candidate.run(x) for x in range(1 << width)
        )
    try:
        proof = verify_transcript(
            original, candidate, steps,
            reference_sha256=digest(Program.freeze(original)),
            candidate_sha256=digest(Program.freeze(candidate)),
            backend="sparse",
        )
        outcome = "proved" if proof.equivalent else "not_proved"
        facts = {"global_width": proof.global_width, "local_slots": proof.slots,
                 "unique_lemmas": proof.unique_lemmas}
    except UnprovedSubstitution as exc:
        outcome = "not_proved"
        facts = {"unproved_slot": exc.slot, "local_cut_witness": exc.witness}
    if small_oracle is False and outcome == "proved":
        raise RuntimeError("positive local transcript contradicts exhaustive global oracle")
    return {"outcome": outcome, "facts": facts,
            "global_exhaustive_oracle": small_oracle,
            "source": name}


def _polynomial_multiply_reference(n: int, modulus: int, a: int, b: int) -> int:
    """Separate plain integer convolution and remainder oracle, no circuit simulation."""
    raw = 0
    for i in range(n):
        if a >> i & 1:
            for j in range(n):
                if b >> j & 1:
                    raw ^= 1 << (i + j)
    while raw.bit_length() > n:
        raw ^= modulus << (raw.bit_length() - n - 1)
    return raw


def _arithmetic_pair(scenario: str):
    """Build the same full reversible pair for exact local and external checks.

    Two independent *bilinear decompositions* inside the same SymQ codebase,
    with the same genuine nontrivial common prefix and suffix. This is not
    independently developed or compiled third-party source code.
    """
    from symq import Circuit
    from symq.generators.gf2n import multiplier

    scenarios = {
        "gf2_n2_schoolbook_karatsuba": (2, "schoolbook", "karatsuba", False),
        "gf2_n3_schoolbook_karatsuba": (3, "schoolbook", "karatsuba", False),
        "gf2_n3_schoolbook_rank_floor": (3, "schoolbook", "rank_floor", False),
        "gf2_n4_karatsuba_rank_floor": (4, "karatsuba", "rank_floor", False),
        "gf2_n3_mutant": (3, "schoolbook", "karatsuba", True),
        "gf2_n4_mutant": (4, "karatsuba", "rank_floor", True),
    }
    n, method_a, method_b, mutant = scenarios[scenario]
    reference = multiplier(n, method_a)
    replacement = multiplier(n, method_b)
    if reference.gates == replacement.gates:
        raise RuntimeError("two structurally different decompositions required")
    if mutant:
        replacement.x(2 * n)
    width = 3 * n
    prefix = Circuit(width).cx(0, n)
    suffix = Circuit(width).cx(2 * n, 0)
    original = Circuit(width, prefix.gates + reference.gates + suffix.gates)
    candidate = Circuit(width, prefix.gates + replacement.gates + suffix.gates)
    return (n, method_a, method_b, mutant, reference, replacement,
            prefix, suffix, original, candidate)


def _arithmetic(case: dict) -> dict:
    """Distinct GF(2^n) bilinear decompositions, sharing the *same* generator library.

    This is a more meaningful algorithmic pair than self-cancelling gates,
    but it is NOT independent external compiler output or a new holdout.
    The expected arithmetic is checked against a separate integer oracle.
    """
    from symq.generators.gf2n import MODULI
    from symq.labs.classical_transcript import (
        Common,
        Program,
        Slot,
        UnprovedSubstitution,
        digest,
        verify_transcript,
    )

    (n, method_a, method_b, mutant, reference, replacement,
     prefix, suffix, left, right) = _arithmetic_pair(case["scenario"])
    width = 3 * n
    slot = Slot(
        Program.freeze(reference), Program.freeze(replacement),
        tuple(range(width)), preserved=tuple(range(2 * n)),
    )
    steps = (
        Common(tuple(prefix.gates)), slot, Common(tuple(suffix.gates)),
    )
    # Exhaustively inspect both implementations against plain polynomial
    # arithmetic, not against one another, for every 3n-bit input (<= 12 bits).
    oracle_agrees = True
    mutant_differs = False
    modulus = MODULI[n]
    mask = (1 << n) - 1
    for x in range(1 << width):
        cut = prefix.run(x)
        a, b, z = cut & mask, (cut >> n) & mask, (cut >> (2 * n)) & mask
        product = _polynomial_multiply_reference(n, modulus, a, b)
        expected_cut = a | (b << n) | ((z ^ product) << (2 * n))
        expected = suffix.run(expected_cut)
        got_left, got_right = left.run(x), right.run(x)
        if got_left != expected:
            raise RuntimeError("the source circuit disagrees with the independent GF integer oracle")
        if got_right != expected:
            if not mutant:
                raise RuntimeError("candidate circuit disagrees with independent GF integer oracle")
            mutant_differs = True
        oracle_agrees = oracle_agrees and got_left == got_right
    if mutant and (oracle_agrees or not mutant_differs):
        raise RuntimeError("declared mutant did not change the full reversible function")
    if not mutant and not oracle_agrees:
        raise RuntimeError("distinct bilinear decompositions differ on the legal full domain")

    source_hash, candidate_hash = digest(Program.freeze(left)), digest(Program.freeze(right))
    try:
        proof = verify_transcript(
            left, right, steps, reference_sha256=source_hash,
            candidate_sha256=candidate_hash, backend="sparse",
        )
        outcome = "proved" if proof.equivalent else "not_proved"
        facts = {"local_slots": proof.slots, "unique_lemmas": proof.unique_lemmas}
    except UnprovedSubstitution as exc:
        outcome = "not_proved"
        facts = {"local_cut_witness": exc.witness, "unproved_slot": exc.slot}
    if outcome == "proved" and not oracle_agrees:
        raise RuntimeError("SymQ certified a false arithmetic rewrite")
    facts.update({
        "degree": n, "modulus": modulus, "reference_method": method_a,
        "candidate_method": method_b, "independent_integer_oracle": True,
        "reference_gates": len(reference.gates),
        "candidate_gates": len(replacement.gates),
        "reference_sha256": source_hash, "candidate_sha256": candidate_hash,
        "all_inputs_checked": 1 << width, "mutant": mutant,
    })
    return {"outcome": outcome, "facts": facts,
            "global_exhaustive_oracle": oracle_agrees,
            "source": case["scenario"]}


def _relational(case: dict) -> dict:
    from symq import Circuit
    from symq.sat.assumptions import And, Const, Not, Var
    from symq.sat.composition import (
        Guarantee,
        Interface,
        all_outputs_equal,
        check_composition,
        equality_all,
    )

    scenario = case["scenario"]
    clean = Not(Var("u.2"))
    relation = And(equality_all("u.", "v.", 3), clean)
    prepared = scenario != "unprepared"
    domain = Not(Var("x.2")) if prepared else Const(True)
    prefix = Circuit(3).cx(0, 2).cx(0, 2) if prepared else Circuit(3)
    if scenario in {"prepared", "unprepared"}:
        original = Circuit(3).cx(2, 0)
    elif scenario == "mutated":
        original = Circuit(3).x(0)
    else:
        raise ValueError("unknown relational scenario")
    proof = check_composition(
        prefix_left=prefix, prefix_right=prefix,
        suffix_left=original, suffix_right=Circuit(3),
        interface=Interface(3, domain, relation),
        guarantee=Guarantee(3, clean, all_outputs_equal(3)),
    )
    decisions = [
        {"name":o.name, "actual_sat":o.satisfiable, "expected":o.wanted,
         "timeout":o.timed_out}
        for o in proof.obligations
    ]
    if any(o.satisfiable is None for o in proof.obligations):
        outcome = "inconclusive"
    elif proof.accepted:
        outcome = "proved"
    elif any(o.name in {"domain", "prefix", "interface"} and not o.ok
             for o in proof.obligations):
        outcome = "precondition_failed"
    else:
        outcome = "not_proved"
    if scenario == "prepared" and outcome == "proved":
        # A separate concrete whole-program check over the declared input domain.
        for x in range(8):
            if not x & 4 and original.run(prefix.run(x)) != prefix.run(x):
                raise RuntimeError("SAT proof contradicts concrete input-domain oracle")
    return {"outcome": outcome, "facts": {"obligations": decisions},
            "global_exhaustive_oracle": None, "source": scenario}


def _hybrid(case: dict) -> dict:
    from symq.experimental.hybrid import HOp, HybridProgram
    from symq.labs.channel_composition import (
        ChannelSlot,
        HybridCommon,
        HybridFragment,
        UnprovedSubstitution,
        _map_ops,
        hybrid_digest,
        verify_channel_transcript,
    )

    scenario = case["scenario"]
    observed: tuple[str, ...] = ()
    discarded: tuple[int, ...] = ()
    if scenario.startswith("qualtran_"):
        from benchmarks.hmr_qualification import hybrid
        from benchmarks.hmr_qualification import load_manifest as qualtran_manifest
        from benchmarks.hmr_qualification import programs as qualtran_programs

        origin_id = scenario.removeprefix("qualtran_")
        original_case = next(
            (x for x in qualtran_manifest()["cases"] if x["id"] == origin_id), None
        )
        if original_case is None:
            raise ValueError(f"unknown pinned Qualtran case {origin_id}")
        a, b = (hybrid(p) for p in qualtran_programs(original_case))
        data, ancillas = a.data, a.ancillas
        ref = HybridFragment(a.width, tuple(a.ops))
        cand = HybridFragment(b.width, tuple(b.ops))
        names = set()
        for op in ref.ops + cand.ops:
            names.update(s for s in (op.slot, op.source,
                         op.condition.removeprefix("!") if op.condition else None)
                         if s is not None)
        slot = ChannelSlot(ref, cand, tuple(range(a.width)),
                           tuple((s, s) for s in sorted(names)),
                           clean=tuple(range(data, a.width)),
                           preserved=tuple(range(data)))
        steps = (slot,)
    elif scenario in {"temp_and", "missing_cz", "unprepared", "connected_71"}:
        compute = (HOp("ccx", (0, 1, 3)), HOp("cx", (3, 2)))
        ref = HybridFragment(4, compute + (HOp("ccx", (0, 1, 3)),))
        candidate = compute + (HOp("hmr", (3,), slot="b0"),)
        if scenario != "missing_cz":
            candidate += (HOp("cz", (0, 1), condition="b0"),)
        cand = HybridFragment(4, candidate)
        slot = ChannelSlot(ref, cand, (0, 1, 2, 3),
                           (("b0", "b7"),), clean=(3,))
        if scenario == "unprepared":
            data, ancillas = 4, 0
            steps = (slot,)
        elif scenario == "connected_71":
            data, ancillas = 70, 1
            steps = (
                HybridCommon(tuple(HOp("cx", (i, i + 1)) for i in range(70))),
                HybridCommon((HOp("reset", (3,)),)), slot,
                HybridCommon((HOp("cx", (2, 70)),)),
            )
        else:
            data, ancillas = 3, 1
            steps = (slot,)
    elif scenario == "dirty_phase":
        data, ancillas = 2, 0
        phase = HybridFragment(2, (HOp("cz", (0, 1)),))
        steps = (ChannelSlot(phase, phase, (0, 1), preserved=(1,)),)
    elif scenario == "live_record":
        data, ancillas = 2, 0
        base = (HOp("reset", (1,)), HOp("measure_z", (1,), slot="b0"))
        ref = HybridFragment(2, base)
        cand = HybridFragment(2, base + (HOp("invert", slot="b0"),))
        steps = (
            ChannelSlot(ref, cand, (0, 1), (("b0", "b0"),)),
            HybridCommon((HOp("x", (0,), condition="b0"),)),
        )
    elif scenario == "terminal_trace":
        data, ancillas = 2, 0
        left = HybridFragment(2, (HOp("x", (1,)),))
        right = HybridFragment(2, ())
        steps = (ChannelSlot(left, right, (0, 1), discarded=(1,)),)
        discarded = (1,)
    else:
        raise ValueError("unrecognized hybrid case")

    left, right = [], []
    for step in steps:
        if isinstance(step, HybridCommon):
            left.extend(step.ops)
            right.extend(step.ops)
        else:
            mapping = dict(step.classical_map)
            left.extend(_map_ops(step.reference.ops, step.wires, mapping))
            right.extend(_map_ops(step.candidate.ops, step.wires, mapping))
    a, b = HybridProgram(data, ancillas, left), HybridProgram(data, ancillas, right)
    try:
        proof = verify_channel_transcript(
            a, b, steps, reference_sha256=hybrid_digest(a),
            candidate_sha256=hybrid_digest(b),
            observed_slots=observed, discarded_global=discarded,
        )
        outcome = "proved" if proof.equivalent else "not_proved"
        facts = {"coherent_input_pairs": proof.checked_pairs,
                 "local_lemmas": proof.unique_lemmas,
                 "global_width": proof.global_width}
    except UnprovedSubstitution as exc:
        outcome = "not_proved"
        facts = {"failure": str(exc), "global_width": a.width}
    # Local channel evidence uses the same hybrid semantics/oracle implementation;
    # repeated execution is NOT an independent mathematical implementation.
    return {"outcome": outcome, "facts": facts,
            "global_exhaustive_oracle": None, "source": scenario}


def _execute(case: dict) -> dict:
    if case["family"] == "qcec":
        from symq.circuit import UnsupportedOperation
        try:
            _qcec(case["scenario"])
        except UnsupportedOperation as exc:
            return {"outcome": "unsupported", "facts": {"reason": str(exc)},
                    "source": case["scenario"], "global_exhaustive_oracle": None}
        return {"outcome": "unexpectedly_supported", "facts": {},
                "source": case["scenario"], "global_exhaustive_oracle": None}
    if case["family"] == "classical":
        return _classical(case)
    if case["family"] == "relational":
        return _relational(case)
    if case["family"] == "arithmetic":
        return _arithmetic(case)
    return _hybrid(case)


def _trial(case: dict) -> dict:
    """An importable fresh-worker function, no trust in a saved outcome label."""
    t0, cpu0 = time.perf_counter(), time.process_time()
    observed = _execute(case)
    return {
        **observed,
        "verification_wall_seconds": time.perf_counter() - t0,
        "verification_cpu_seconds": time.process_time() - cpu0,
    }


def run_campaign(*, repetitions: int = 1,
                 selected: tuple[str, ...] = (),
                 wall_seconds: float = 30.0) -> dict:
    from symq.experimental.execution import HardLimits, run_isolated

    from .substitution_worker import substitution_trial

    manifest = load_manifest()
    if type(repetitions) is not int or repetitions < 1:
        raise ValueError("positive repetitions required")
    if type(selected) is not tuple or any(type(s) is not str for s in selected):
        raise ValueError("selected must be a tuple of case IDs")
    available = {item["id"] for item in manifest["cases"]}
    if any(s not in available for s in selected):
        raise ValueError("unknown requested case")
    cases = [case for case in manifest["cases"] if not selected or case["id"] in selected]
    jobs = [(case, rep) for case in cases for rep in range(repetitions)]
    random.Random(manifest["shuffle_seed"]).shuffle(jobs)
    limits = HardLimits(wall_seconds=wall_seconds, cpu_seconds=wall_seconds,
                        memory_bytes=2 * 1024**3)
    before = receipt()
    files_before = _harness_fingerprints()
    rows = []
    start = time.perf_counter()
    for case, rep in jobs:
        worker = run_isolated(substitution_trial, case, limits=limits)
        value = worker.value if worker.status == "completed" else None
        actual = value["outcome"] if value is not None else worker.status
        outcome = ("accepted" if actual == case["expected"] else "mismatch")
        rows.append({
            "case_id": case["id"], "family": case["family"], "theorem": case["theorem"],
            "provenance": case["provenance"], "repetition": rep,
            "expected": case["expected"], "actual": actual, "qualification": outcome,
            "worker_status": worker.status, "worker_reason": worker.reason,
            "worker_exitcode": worker.exitcode, "worker_wall_seconds": worker.wall_seconds,
            "worker_cpu_seconds": worker.cpu_seconds, "worker_peak_rss_bytes": worker.peak_rss_bytes,
            "value": value,
        })
    after = receipt()
    files_after = _harness_fingerprints()
    return {
        "schema_version": 1, "date_utc": datetime.now(UTC).isoformat(),
        "manifest": manifest, "manifest_sha256": _digest(manifest),
        "source_before": before, "source_after": after,
        "harness_fingerprints_before": files_before,
        "harness_fingerprints_after": files_after,
        "source_unchanged": before == after and files_before == files_after,
        "environment": machine(), "repetitions": repetitions,
        "limits": {"wall_seconds": limits.wall_seconds, "cpu_seconds": limits.cpu_seconds,
                   "memory_bytes": limits.memory_bytes},
        "campaign_wall_seconds": time.perf_counter() - start,
        "qualification_counts": dict(Counter(r["qualification"] for r in rows)),
        "case_counts": dict(Counter(r["actual"] for r in rows)),
        "rows": rows,
        "measurement_notes": [
            "Each row is a fresh spawned, hard-bounded worker.",
            "CPU/RSS include Python import and worker setup; verification wall is within the worker.",
            "The classical small-width oracle is independent concrete Circuit.run, but the hybrid",
            "channel proof uses the same implementation as the existing scalar hybrid semantics.",
            "This is an explicitly previously explored corpus; NOT an untouched holdout.",
            "Local failures need not imply a reachable global counterexample.",
            "Different theorem families are not performance-competitor cells.",
            "Missing data and unsupported jobs are counted, never dropped.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--wall-seconds", type=float, default=30)
    args = parser.parse_args()
    report = run_campaign(
        repetitions=args.repetitions, selected=tuple(args.case),
        wall_seconds=args.wall_seconds,
    )
    if not report["source_unchanged"]:
        raise SystemExit("the imported SymQ source changed during the campaign")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    # The source and content digests in the report are inspection receipts,
    # never independently checked semantic certificates.
    args.output.write_text(content, encoding="utf-8")
    digest = hashlib.sha256(content.encode()).hexdigest()
    args.output.with_suffix(args.output.suffix + ".sha256").write_text(
        digest + "  " + args.output.name + "\n", encoding="utf-8"
    )
    errors = report["qualification_counts"].get("mismatch", 0)
    print(f"{len(report['rows'])} trials; mismatched expectations: {errors}; {args.output}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
