"""Frozen public Qualtran qualification, with separate semantics and cost receipts.

This deliberately reuses previously explored m=1/2 fixtures. It is not a new
blind holdout, an external-tool comparison or a large-multiplier scaling claim.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import random
import statistics
import subprocess
import sys
import sysconfig
import time
from collections import Counter
from dataclasses import asdict
from importlib import metadata
from pathlib import Path

MANIFEST_SHA256 = "42a8b1ff796877b8b11fc7641709d3a869d915ec3a0e8a838d0608292c1472c8"
ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "benchmarks/hmr_qualification_manifest.json"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def load_manifest(path=MANIFEST):
    manifest = json.loads(Path(path).read_text())
    if digest(manifest) != MANIFEST_SHA256:
        raise ValueError("HMR qualification manifest differs from the frozen protocol")
    for name, expected in manifest["fixture_sha256"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"public fixture changed: {name}")
    return manifest


def programs(case):
    from symq.experimental.importers import parse_phase_stream
    from symq.experimental.qualtran import load_qualtran_fixture
    from symq.phase import PhaseProgram

    degree = case["degree"]
    fixture = load_qualtran_fixture(ROOT / f"benchmarks/corpus/qualtran/gf2mul_mbuc_m{degree}.json")
    reference, candidate = fixture.programs()
    mutation = case["mutation"]
    if mutation == "missing_correction":
        correction = next(i for i, op in enumerate(candidate.ops) if op.kind == "mcz_if")
        candidate = PhaseProgram(candidate.data, candidate.ancillas,
                                 candidate.ops[:correction] + candidate.ops[correction + 1:])
    elif mutation != "none":
        preparer, cleanup = fixture.preparer, fixture.cleanup
        if mutation == "wrong_event":
            cleanup = cleanup.replace("CZ q0 q2 if b0", "CZ q0 q2 if b1")
        elif mutation == "wrong_parity":
            cleanup = cleanup.replace("OXOR b2 b1", "OXOR b2 b0")
        elif mutation == "wrong_bits":
            preparer = preparer.replace("q0", "TEMP").replace("q1", "q0").replace("TEMP", "q1")
        else:
            raise ValueError("unknown frozen mutation")
        candidate = parse_phase_stream(preparer + "\n" + cleanup, data=2 * degree,
                                       ancillas=degree).program
    return reference, candidate


def contract_for(case, backend):
    from symq.experimental import VerificationContract

    options = {}
    if case["theorem"] == "reduced_channel":
        options = {"left_outputs": tuple(range(2 * case["degree"])),
                   "right_outputs": tuple(range(2 * case["degree"]))}
    return VerificationContract(case["theorem"], backend, **options)


def hybrid(program):
    """Lossless lowering to the independently implemented exact Kraus oracle."""
    from symq.experimental.hybrid import HybridProgram

    result = HybridProgram(program.data, program.ancillas)
    for op in program.ops:
        if op.kind == "mcx":
            if len(op.qubits) == 1:
                result.x(*op.qubits)
            else:
                result.mcx(*op.qubits)
        elif op.kind in {"mcz", "mcz_if"}:
            kwargs = {} if op.kind == "mcz" else {"condition": f"b{op.outcome}"}
            getattr(result, {1: "z", 2: "cz", 3: "ccz"}[len(op.qubits)])(*op.qubits, **kwargs)
        elif op.kind == "hmr":
            result.hmr(op.qubits[0], f"b{op.outcome}")
        else:
            raise ValueError(f"oracle lowering refuses {op.kind}")
    return result


def _trace(image, outputs):
    from fractions import Fraction

    discarded = ~sum(1 << q for q in outputs)
    result = {}
    for (a, b), value in image.items():
        if (a ^ b) & discarded:
            continue
        row = sum(((a >> q) & 1) << i for i, q in enumerate(outputs))
        col = sum(((b >> q) & 1) << i for i, q in enumerate(outputs))
        result[row, col] = result.get((row, col), Fraction()) + value
    return {key: value for key, value in result.items() if value}


def oracle_case(case):
    from symq.experimental.hybrid import coherence_image

    left, right = (hybrid(p) for p in programs(case))
    equal, diagonals, first, pairs = True, True, None, 0
    for x in range(1 << left.data):
        for y in range(1 << left.data):
            a, b = coherence_image(left, x, y), coherence_image(right, x, y)
            if case["theorem"] == "reduced_channel":
                keep = tuple(range(left.data))
                a, b = _trace(a, keep), _trace(b, keep)
            pairs += 1
            if a != b:
                equal = False
                if first is None:
                    first = [x, y]
                if x == y:
                    diagonals = False
    expected = case["expected"] == "equivalent"
    return {"case_id": case["id"], "all_coherences_checked": pairs,
            "equivalent": equal, "diagonals_equal": diagonals,
            "first_witness": first, "expected_label_verified": equal == expected}


def semantic_matrix():
    from symq.experimental import inspect
    from symq.experimental.hybrid import same_instrument
    from symq.experimental.importers import parse_phase_stream
    from symq.experimental.qualtran import load_qualtran_fixture
    from symq.phase import PhaseProgram, check_phase_equivalence

    manifest = load_manifest()
    records = [oracle_case(case) for case in manifest["cases"]]
    if any(not record["expected_label_verified"] for record in records):
        raise RuntimeError("independent oracle disagrees with a preregistered label")
    branches, instruments, preparation = [], [], []
    for degree in (1, 2):
        case = next(c for c in manifest["cases"] if c["degree"] == degree and c["mutation"] == "none")
        left, right = programs(case)
        branch = check_phase_equivalence(left, right)
        branches.append({"degree": degree, "strict_O1_O2": asdict(branch)})
        # A derived instrument control observes raw measurement events in the
        # normalized embedding, not the upstream fixture's discarded outputs.
        a, b = hybrid(left), hybrid(right)
        slots = tuple(f"b{j}" for j in range(degree))
        for j, slot in enumerate(slots):
            a.hmr(a.data + j, slot)
        instrument = same_instrument(a, b, observed_slots=slots)
        instruments.append({"degree": degree, "derived_normalized_record_control": True,
                            "result": asdict(instrument)})
        fixture = load_qualtran_fixture(ROOT / f"benchmarks/corpus/qualtran/gf2mul_mbuc_m{degree}.json")
        raw = parse_phase_stream(fixture.cleanup, data=2 * degree, ancillas=degree).program
        from symq.experimental import VerificationContract, verify
        refusal = verify(PhaseProgram(2 * degree, degree), raw,
                         VerificationContract(backend="zdd"))
        preparation.append({"degree": degree, "unprepared_cleanup_counterexample": refusal.to_dict()})
    boundaries = []
    for data in (32, 33, 36, 64, 65):
        connected = PhaseProgram(data)
        for q in range(data - 1):
            connected.cx(q, q + 1)
        for backend in ("zdd-native", "zdd-native-wide", "zdd-native-blocks"):
            boundaries.append({"data": data, "source": "synthetic_static_boundary_control",
                               "backend": backend,
                               "inspection": asdict(inspect(connected, connected, engine=backend))})
    from symq.experimental import VerificationContract, verify
    from symq.experimental.hybrid import HybridProgram, same_channel

    observed = HybridProgram(1).hmr(0, "b0")
    flipped = HybridProgram(1).hmr(0, "b0").invert("b0")
    record_control = {"source": "synthetic theorem counterexample",
                      "forgotten_channel": asdict(same_channel(observed, flipped)),
                      "observed_instrument": asdict(same_instrument(observed, flipped,
                                                                    observed_slots=("b0",)))}
    erased_a = PhaseProgram(1, 1).cx(0, 1)
    erased_b = PhaseProgram(1, 1).cx(0, 1).x(1)
    trace_control = {"source": "synthetic theorem counterexample",
                     "full": verify(erased_a, erased_b, VerificationContract()).to_dict(),
                     "reduced": verify(erased_a, erased_b, VerificationContract(
                         "reduced_channel", "zdd", left_outputs=(0,), right_outputs=(0,))).to_dict()}
    nonunitary = PhaseProgram(1, 1).cx(0, 1)
    nonunitary.hmr(1)
    branch_control = {"source": "synthetic theorem counterexample",
                      "strict_branch": asdict(check_phase_equivalence(nonunitary, nonunitary)),
                      "channel": verify(nonunitary, nonunitary, VerificationContract()).to_dict()}
    return {"oracle_cases": records, "restricted_branch": branches,
            "derived_instruments": instruments, "missing_preparation": preparation,
            "static_connected_width_controls": boundaries,
            "public_gadget_connected_composition": composition_control(),
            "channel_not_instrument": record_control, "reduced_not_full": trace_control,
            "channel_not_strict_branch": branch_control}


def composition_control():
    """Public m=1 gadget in a declared synthetic, connected 65-wire context."""
    from dataclasses import replace

    from symq.experimental.composition import (
        ChannelSlot,
        HybridCommon,
        HybridFragment,
        UnprovedSubstitution,
        hybrid_digest,
        verify_channel_transcript,
    )
    from symq.experimental.hybrid import HOp, HybridProgram
    from symq.resources import Budget

    case = load_manifest()["cases"][0]
    a, b = (hybrid(p) for p in programs(case))
    left, right = HybridFragment(a.width, tuple(a.ops)), HybridFragment(b.width, tuple(b.ops))
    prefix = HybridCommon(tuple(HOp("cx", (q, q + 1)) for q in range(63)))
    slots = [ChannelSlot(left, right, (0, 1, 64), (("b0", "b0"),), clean=(2,), preserved=(0, 1)),
             ChannelSlot(left, right, (32, 33, 64), (("b0", "b1"),), clean=(2,), preserved=(0, 1))]
    suffix = HybridCommon((HOp("cx", (63, 0)),))
    steps = [prefix, slots[0], slots[1], suffix]

    def streams(steps):
        aa, bb = [], []
        for step in steps:
            if type(step) is HybridCommon:
                aa.extend(step.ops)
                bb.extend(step.ops)
                continue
            for output, fragment in ((aa, step.reference), (bb, step.candidate)):
                table = dict(step.classical_map)
                for op in fragment.ops:
                    output.append(replace(op, wires=tuple(step.wires[q] for q in op.wires),
                                          slot=table.get(op.slot),
                                          condition=table.get(op.condition)))
        return HybridProgram(64, 1, aa), HybridProgram(64, 1, bb)

    def check(steps):
        aa, bb = streams(steps)
        return verify_channel_transcript(aa, bb, steps,
                                         reference_sha256=hybrid_digest(aa),
                                         candidate_sha256=hybrid_digest(bb),
                                         budget=Budget(max_seconds=10))

    proof = check(steps)
    dirty = [prefix, HybridCommon((HOp("cx", (0, 64)),)), *steps[1:]]
    missing = replace(slots[0], candidate=replace(right, ops=right.ops[:-1]))
    rejected = {}
    for name, mutant_steps in (("dirty_clean_ancilla_claim", dirty),
                               ("missing_local_feedback", [prefix, missing, *steps[2:]])):
        try:
            check(mutant_steps)
        except UnprovedSubstitution as exc:
            rejected[name] = str(exc)
        else:
            raise RuntimeError(f"composition accepted discriminating mutant: {name}")
    return {"provenance": "synthetic connected context containing exact public-derived m1 gadgets",
            "global_data": 64, "global_physical_width": 65, "proof": asdict(proof),
            "mutants_rejected": rejected,
            "meaning": "All local coherences and clean-cut facts checked; no dense global enumeration or independent certificate."}


def snapshot():
    import symq
    from symq.backends import _zdd

    package = Path(symq.__file__).resolve()
    module = Path(_zdd.__file__).resolve()
    if package != ROOT / "src/symq/__init__.py" or not module.is_relative_to(ROOT / "src"):
        raise RuntimeError("worker imported a different checkout or native extension")
    files = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "src/symq").rglob("*")
                   if p.is_file() and p.suffix in {".py", ".c"})
    files += ["benchmarks/hmr_qualification.py", "benchmarks/hmr_qualification_manifest.json",
              "tools/build_native.py", "pyproject.toml", "hatch_build.py"]
    files += list(load_manifest()["fixture_sha256"])
    return {"head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "sources": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in files},
            "native_sha256": hashlib.sha256(module.read_bytes()).hexdigest(),
            "native_module": module.relative_to(ROOT).as_posix(), "abi": _zdd.ABI_VERSION}


def _trial(case, backend, frozen):
    from symq.experimental import replay, verify
    from symq.resources import Budget

    if snapshot() != frozen:
        raise RuntimeError("worker source/native provenance mismatch")
    materialize = time.perf_counter()
    left, right = programs(case)
    contract = contract_for(case, backend)
    materialize = time.perf_counter() - materialize
    started, cpu_started = time.perf_counter(), time.process_time()
    result = verify(left, right, contract, budget=Budget(max_seconds=50, max_nodes=2_000_000))
    seconds, cpu = time.perf_counter() - started, time.process_time() - cpu_started
    replayed, replay_seconds, oracle_witness_checked = None, 0.0, None
    if result.outcome == "different":
        started = time.perf_counter()
        replayed = replay(result, left, right, contract, budget=Budget(max_seconds=5)).witness_checked
        from symq.experimental.hybrid import coherence_image
        x, y = result.witness
        a, b = coherence_image(hybrid(left), x, y), coherence_image(hybrid(right), x, y)
        if case["theorem"] == "reduced_channel":
            a, b = _trace(a, contract.left_outputs), _trace(b, contract.right_outputs)
        oracle_witness_checked = a != b
        replay_seconds = time.perf_counter() - started
    if snapshot() != frozen:
        raise RuntimeError("worker changed during measurement")
    return {"result": result.to_dict(), "input_materialization_seconds": materialize,
            "public_verify_wall_seconds": seconds, "public_verify_cpu_seconds": cpu,
            "additional_replay_seconds": replay_seconds, "additional_replay_checked": replayed,
            "independent_kraus_witness_checked": oracle_witness_checked}


def distribution(values):
    if not values:
        return {"n": 0, "median": None, "p10": None, "p90": None}
    ordered = sorted(values)
    return {"n": len(values), "median": statistics.median(values),
            "p10": ordered[int((len(values) - 1) * 0.1)],
            "p90": ordered[int((len(values) - 1) * 0.9)]}


def summarise(rows, cases):
    output = []
    for case in cases:
        selected = [r for r in rows if r["case_id"] == case["id"]]
        ratios = []
        for repetition in range(15):
            pair = {r["backend"]: r for r in selected if r["repetition"] == repetition}
            if set(pair) == {"zdd", "zdd-native"} and all(r["qualified"] for r in pair.values()):
                ratios.append(pair["zdd"]["value"]["public_verify_wall_seconds"] /
                              pair["zdd-native"]["value"]["public_verify_wall_seconds"])
        backends = {}
        for backend in ("zdd", "zdd-native"):
            valid = [r for r in selected if r["backend"] == backend and r["qualified"]]
            backends[backend] = {"eligible": 15, "completed_and_verified": len(valid),
                                 "public_verify_wall_seconds": distribution([
                                     r["value"]["public_verify_wall_seconds"] for r in valid]),
                                 "public_verify_cpu_seconds": distribution([
                                     r["value"]["public_verify_cpu_seconds"] for r in valid]),
                                 "whole_worker_peak_rss_bytes": distribution([
                                     r["peak_rss_bytes"] for r in valid])}
        output.append({"case_id": case["id"], "backends": backends,
                       "paired_python_over_native": distribution(ratios)})
    return output


def build_receipt():
    """Build the frozen sources with fixed flags and record the actual binary."""
    subprocess.run(["git", "diff", "--exit-code", "HEAD", "--", "src", "tools/build_native.py",
                    "benchmarks/hmr_qualification.py", "benchmarks/hmr_qualification_manifest.json"],
                   cwd=ROOT, check=True, capture_output=True)
    subprocess.run(["git", "ls-files", "--error-unmatch", "benchmarks/hmr_qualification.py",
                    "benchmarks/hmr_qualification_manifest.json"], cwd=ROOT,
                   check=True, capture_output=True)
    flags = ["-O3", "-std=c11", "-fPIC", "-shared", "-fno-strict-aliasing"]
    completed = subprocess.run([sys.executable, "tools/build_native.py", "--require"],
                               cwd=ROOT, env=dict(os.environ, CC="cc", CFLAGS="", LDFLAGS=""),
                               text=True, capture_output=True, check=True)
    return {"schema_version": 1, "frozen": snapshot(),
            "compiler": subprocess.check_output(["cc", "--version"], text=True).splitlines()[0],
            "compiler_flags": flags, "python_headers": sysconfig.get_paths()["include"],
            "command": [sys.executable, "tools/build_native.py", "--require"],
            "controlled_environment": {"CC": "cc", "CFLAGS": "", "LDFLAGS": ""},
            "build_output": completed.stderr.strip()}


def run_campaign(receipt_path):
    import resource

    from symq.experimental.execution import HardLimits, run_isolated

    manifest = load_manifest()
    if subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"],
                               cwd=ROOT, text=True).strip():
        raise RuntimeError("freeze a clean source commit before measurement")
    frozen = snapshot()
    receipt = json.loads(Path(receipt_path).read_text())
    if receipt["frozen"] != frozen:
        raise RuntimeError("build receipt does not match the frozen sources/native binary")
    if frozen["abi"] != 5:
        raise RuntimeError("qualification requires the current ABI 5 native extension")
    matrix = semantic_matrix()
    jobs = [(case, repetition) for case in manifest["cases"] for repetition in range(15)]
    rng = random.Random(manifest["shuffle_seed"])
    rng.shuffle(jobs)
    rows = []
    started = time.perf_counter()
    for pair_index, (case, repetition) in enumerate(jobs):
        backends = list(manifest["backends"])
        rng.shuffle(backends)
        for backend_order, backend in enumerate(backends):
            usage = resource.getrusage(resource.RUSAGE_CHILDREN)
            cpu_before = usage.ru_utime + usage.ru_stime
            isolated = run_isolated(_trial, case, backend, frozen, limits=HardLimits(**manifest["limits"]))
            usage = resource.getrusage(resource.RUSAGE_CHILDREN)
            reaped_cpu = usage.ru_utime + usage.ru_stime - cpu_before
            value = isolated.value if isolated.status == "completed" else None
            outcome = value["result"]["outcome"] if value else isolated.status
            qualified = outcome == case["expected"] and (
                outcome != "different" or value["additional_replay_checked"] is True and
                value["independent_kraus_witness_checked"] is True)
            rows.append({"case_id": case["id"], "backend": backend, "repetition": repetition,
                         "pair_index": pair_index, "backend_order": backend_order,
                         "outcome": outcome, "qualified": qualified, "value": value,
                         "execution_status": isolated.status, "execution_reason": isolated.reason,
                         "process_wall_seconds": isolated.wall_seconds,
                         "whole_reaped_worker_cpu_seconds": reaped_cpu if isolated.exitcode is not None else None,
                         "worker_cpu_before_response_encoding_seconds": isolated.cpu_seconds,
                         "peak_rss_bytes": isolated.peak_rss_bytes, "exitcode": isolated.exitcode})
    if snapshot() != frozen:
        raise RuntimeError("campaign source/native snapshot changed")
    return {"schema_version": 1, "protocol_sha256": MANIFEST_SHA256,
            "frozen": frozen, "manifest": manifest, "semantic_matrix": matrix,
            "environment": {"python": platform.python_version(), "platform": platform.platform(),
                            "cpu_affinity": sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None,
                            "versions": {n: metadata.version(n) for n in ("pytest", "symq")},
                            "native_build": receipt},
            "campaign_wall_seconds": time.perf_counter() - started,
            "counts": dict(Counter(r["outcome"] for r in rows)),
            "unqualified": sum(not r["qualified"] for r in rows),
            "rows": rows, "summary": summarise(rows, manifest["cases"]),
            "scope": "Previously explored two-size single-family public qualification; no cross-family confidence or stable promotion."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--semantic-only", action="store_true")
    parser.add_argument("--build-native", action="store_true")
    parser.add_argument("--build-receipt", type=Path)
    args = parser.parse_args()
    if args.semantic_only:
        result = semantic_matrix()
    elif args.build_native:
        result = build_receipt()
    elif args.build_receipt is None:
        parser.error("a --build-receipt matching the frozen source is required")
    else:
        result = run_campaign(args.build_receipt)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")


if __name__ == "__main__":
    main()
