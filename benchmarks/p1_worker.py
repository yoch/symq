"""Isolated worker for the fixed public P1 comparative pilot.

Use only source-pinned development cases; no implicit theorem conversion:
classical full permutation is compared to QCEC up to global phase
(which agrees for permutation unitaries); HMR full coherent channel is
compared to a separately implemented exact hybrid Kraus oracle.
"""
from __future__ import annotations

import hashlib
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _program_digest(value, theorem: str) -> str:
    if theorem == "classical":
        from symq.labs.classical_transcript import Program, digest

        return digest(Program.freeze(value))
    from symq.experimental.api import program_hash

    return program_hash(value)


def _kmb_source(case: dict):
    from benchmarks.kaggle_bilinear_eval import manifest, source_starts
    from benchmarks.kaggle_bilinear_kmb import parse
    from symq.circuit import Circuit

    row = next((r for r in manifest() if r["id"] == case["fixture"]), None)
    if row is None or (row["width"], row["modulus"]) not in ((4, 0x13), (6, 0x49)):
        raise ValueError("case fixture or field modulus differs from pinned public corpus")
    raw = source_starts()[row["kmb"]]
    if hashlib.sha256(raw).hexdigest() != row["sha256"]:
        raise ValueError("public KMB source SHA-256 mismatch")
    width, ops = parse(raw)
    if width != 3 * row["width"]:
        raise ValueError("unexpected KMB registers")
    circuit = Circuit(width)
    for kind, a, b, target in ops:
        if kind == 33:
            circuit.cx(a, b)
        elif kind == 34:
            circuit.cx(a, b).cx(b, a).cx(a, b)
        elif kind == 49:
            circuit.ccx(a, b, target)
        else:
            raise ValueError("unsupported KMB gate")
    return circuit, row, {"source_sha256": row["sha256"], "format": "public_KMB_v2",
                          "origin": "James Barlow Kaggle bilinear (Apache-2.0 declared)"}


def _qcec_source(case: dict):
    from symq.corpus import load_corpus
    from symq.qasm import parse_qasm

    manifest = ROOT / "benchmarks/corpus/qcec/MANIFEST.json"
    corpus = load_corpus(manifest)
    entry = next((e for e in corpus.entries if e.name == case["fixture"]), None)
    if entry is None or entry.split != "dev" or not entry.supported:
        raise ValueError("QCEC pilot may read supported upstream DEV cases only")
    raw = entry.path.read_bytes()
    if len(raw) != entry.bytes or hashlib.sha256(raw).hexdigest() != entry.sha256:
        raise ValueError("original QCEC circuit bytes or SHA-256 changed")
    circuit = parse_qasm(raw.decode("utf-8"))
    if circuit.width != entry.width or len(circuit.gates) != entry.gates:
        raise ValueError("upstream QCEC parsed circuit metadata changed")
    return circuit, {"source_sha256": entry.sha256, "format": "QASM",
                     "origin": "MQT QCEC original public corpus (MIT)", "split": entry.split}


def _synthetic_source(case: dict):
    from symq.circuit import Circuit

    if case["fixture"] == "borrowed":
        source = Circuit(5).ccx(0, 1, 4).ccx(0, 1, 4)
        if case["scenario"] == "missing_uncompute":
            source = Circuit(5, source.gates[:-1])
        candidate = Circuit(5)
    elif case["fixture"] == "uncompute":
        source = (Circuit(6).ccx(0, 1, 5).ccx(2, 3, 5)
                  .ccx(2, 3, 5).ccx(0, 1, 5))
        if case["scenario"] == "missing_uncompute":
            source = Circuit(6, source.gates[:-1])
        candidate = Circuit(6)
    else:
        raise ValueError("unknown synthetic family")
    return source, candidate, {"origin": "independent synthetic compute/uncompute",
                               "source_status": "synthetic_not_real_compiler"}


def build_case(case: dict):
    """Construct exactly the same pair for every eligible backend."""
    from symq.generators import equivalent_variant, gf2n

    if case["family"] == "kmb":
        original, row, provenance = _kmb_source(case)
        candidate = gf2n.tower_multiplier(row["width"], modulus=row["modulus"])
        if case["scenario"] == "flip_candidate_target":
            candidate.x(2 * row["width"])
        elif case["scenario"] != "rewrite":
            raise ValueError("unknown public KMB scenario")
        return original, candidate, provenance
    if case["family"] == "qcec":
        original, provenance = _qcec_source(case)
        if case["scenario"] == "commuting_variant":
            candidate = equivalent_variant(
                original, random.Random(case["seed"]), steps=12, max_controls=2
            )
        elif case["scenario"] == "final_x_mutant":
            from symq.circuit import Circuit

            candidate = Circuit(original.width, list(original.gates)).x(0)
        else:
            raise ValueError("unknown QCEC derivative")
        return original, candidate, {
            **provenance, "candidate_provenance": "synthetic_commute_cancel_or_x_mutant",
        }
    if case["family"] == "synthetic":
        return _synthetic_source(case)
    if case["family"] == "qualtran":
        from benchmarks.hmr_qualification import load_manifest, programs

        manifest = load_manifest()
        item = next((i for i in manifest["cases"] if i["id"] == case["fixture"]), None)
        if item is None or item["theorem"] != "full_channel":
            raise ValueError("HMR public fixture/correct theorem is absent")
        if item["expected"] != case["expected"] or item["mutation"] != case["scenario"]:
            raise ValueError("predeclared HMR mutation/outcome mismatch")
        left, right = programs(item)
        return left, right, {
            "source_sha256": manifest["fixture_sha256"][
                f"benchmarks/corpus/qualtran/gf2mul_mbuc_m{item['degree']}.json"
            ],
            "format": "normalized_qualtran_decomposition",
            "origin": "Qualtran GF2MulMBUC, commit 638777fac4379bc62e2a1e4a52cf1a1753895d48 (Apache-2.0)",
            "source_status": "previously_explored_public_qualification",
        }
    raise ValueError("unknown P1 fixture family")


def _classical_verdict(left, right, backend: str, seconds: float) -> tuple[str, dict]:
    from symq import Budget

    if backend == "sat":
        from symq.sat import check_sat_equivalence

        decision = check_sat_equivalence(left, right, budget=Budget(max_seconds=seconds))
        return decision.outcome, {
            "solver": decision.solver,
            "witness": decision.witness,
            "witness_replayed": bool(decision.witness_checked),
            "clauses": decision.clauses, "variables": decision.variables,
        }
    if backend in ("zdd", "zdd-native"):
        from symq import check_equivalence

        decision = check_equivalence(left, right, backend=backend,
                                     budget=Budget(max_seconds=seconds))
        replayed = (decision.witness is not None
                    and left.run(decision.witness) != right.run(decision.witness))
        return "equivalent" if decision.equivalent else "different", {
            "witness": decision.witness, "witness_replayed": replayed,
            "backend": decision.backend,
        }
    if backend == "qcec":
        # The adapter disables QCEC's probabilistic simulation checker.
        from symq.external.qcec import qcec_check

        result = qcec_check(left, right, timeout=seconds)
        return ("equivalent" if result.equivalent is True else
                "different" if result.equivalent is False else "inconclusive"), {
                    "criterion": result.verdict, "check_seconds": result.check_seconds,
                    "preprocessing_seconds": result.preprocessing_seconds,
                    "witness": None, "witness_replayed": False,
                }
    raise ValueError("backend not eligible for full classical permutation theorem")


def _hmr_verdict(left, right, backend: str, seconds: float) -> tuple[str, dict]:
    from symq.experimental import VerificationContract, replay, verify
    from symq.resources import Budget

    if backend == "hybrid-exact":
        from benchmarks.hmr_qualification import hybrid

        left, right = hybrid(left), hybrid(right)
    elif backend not in ("zdd", "zdd-native"):
        raise ValueError("not an eligible HMR coherent-channel backend")
    contract = VerificationContract(theorem="full_channel", backend=backend)
    result = verify(left, right, contract, budget=Budget(max_seconds=seconds))
    replayed = False
    if result.outcome == "different":
        replayed = replay(result, left, right, contract,
                          budget=Budget(max_seconds=seconds)).witness_checked
    return result.outcome, {
        "witness": result.witness,
        "witness_replayed": replayed,
        "witness_kind": result.witness_kind,
        "checked_coherences": dict(result.statistics).get("checked_pairs"),
        "backend": backend,
    }


def worker_trial(
    case: dict, engine: str, seconds: float,
    expected_left_sha256: str, expected_right_sha256: str,
) -> dict:
    """Complete staged worker, timed inside a fresh hard-bounded process."""
    import time

    from symq.errors import ResourceLimitExceeded, SatUnavailable, UnsupportedOperation

    wall0, cpu0 = time.perf_counter(), time.process_time()
    left, right, provenance = build_case(case)
    left_sha = _program_digest(left, case["theorem"])
    right_sha = _program_digest(right, case["theorem"])
    if (left_sha, right_sha) != (expected_left_sha256, expected_right_sha256):
        raise RuntimeError("source/candidate snapshot mismatch across verifier workers")
    built = time.perf_counter()
    cpu_built = time.process_time()

    try:
        if case["theorem"] == "classical":
            outcome, detail = _classical_verdict(left, right, engine, seconds)
        else:
            outcome, detail = _hmr_verdict(left, right, engine, seconds)
    except (ImportError, SatUnavailable, UnsupportedOperation) as exc:
        outcome, detail = "unsupported", {"reason": f"{type(exc).__name__}: {exc}"}
    except ResourceLimitExceeded as exc:
        outcome, detail = "inconclusive", {"reason": str(exc)}

    done = time.perf_counter()
    return {
        "outcome": outcome, "detail": detail,
        "theorem": case["theorem"], "engine": engine,
        "reference_sha256": left_sha, "candidate_sha256": right_sha,
        "source_provenance": provenance,
        "width": left.width if case["theorem"] == "classical" else left.data,
        "materialization_wall_seconds": built - wall0,
        "materialization_cpu_seconds": cpu_built - cpu0,
        "decision_wall_seconds": done - built,
        "decision_cpu_seconds": time.process_time() - cpu_built,
        "worker_inside_wall_seconds": done - wall0,
        "worker_inside_cpu_seconds": time.process_time() - cpu0,
    }
