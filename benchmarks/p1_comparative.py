"""P1 paired public-source *development pilot*; not a confirmatory holdout study.

Same input streams, same decision theorem, randomized paired process order,
independent labels/oracles, hard worker wall/CPU/RSS limits, measured coverage
and explicit failures. Unlike unlike-thesis speed comparisons, HMR channel
pairs are NOT fed to QCEC's unitary-only adapter. PyZX has no vetted adapter
for this corpus and is recorded as NOT RUN rather than a fake failure.

CI runs one coverage smoke repetition. The preregistered 15-pair campaign
is available as an explicit command; do not claim its distributions have
been measured merely because the harness supports them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .environment import machine, receipt
from .p1_worker import ROOT, _program_digest, build_case, worker_trial

MANIFEST = ROOT / "benchmarks/p1_manifest.json"
PINNED_MANIFEST_GIT_BLOB_SHA1 = "fcf3161aa8bae5aa6f5000709fc2210bc1e884e6"
SOURCE_FILES = (
    "benchmarks/p1_manifest.json",
    "benchmarks/p1_worker.py",
    "benchmarks/p1_comparative.py",
    "benchmarks/substitution_crosscheck.py",
    "benchmarks/hmr_qualification.py",
    "benchmarks/hmr_qualification_manifest.json",
    "benchmarks/kaggle_bilinear_eval.py",
    "benchmarks/corpus/kaggle_bilinear/manifest.json",
    "benchmarks/corpus/kaggle_bilinear/starts.zlib.b64",
    "benchmarks/corpus/qcec/MANIFEST.json",
    "benchmarks/corpus/qualtran/gf2mul_mbuc_m1.json",
    "benchmarks/corpus/qualtran/gf2mul_mbuc_m2.json",
)


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _blob_sha1(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def load_manifest(path: Path = MANIFEST) -> dict:
    raw = path.read_bytes()
    if _blob_sha1(raw) != PINNED_MANIFEST_GIT_BLOB_SHA1:
        raise ValueError("P1 manifest differs from pinned Git blob content")
    data = json.loads(raw)
    if (type(data) is not dict or data.get("schema_version") != 1
            or data.get("name") != "symq-p1-comparative-development-pilot-v1"):
        raise ValueError("unexpected P1 manifest schema")
    cases = data["cases"]
    if type(cases) is not list or len(cases) != 13:
        raise ValueError("P1 pilot must have exactly 13 declared cases")
    ids = [case["id"] for case in cases]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate P1 case ID")
    allowed = {"kmb", "qcec", "synthetic", "qualtran"}
    for case in cases:
        keys = {"id", "partition", "family", "fixture", "scenario", "expected", "theorem"}
        if set(case) not in (keys, keys | {"seed"}):
            raise ValueError("unfrozen case fields")
        if (case["partition"] != "development" or case["family"] not in allowed
                or case["expected"] not in ("equivalent", "different")
                or case["theorem"] != ("hmr" if case["family"] == "qualtran" else "classical")):
            raise ValueError("P1 wrong partition, family, outcome or semantic theorem")
        if case["family"] == "qcec" and type(case.get("seed")) is not int:
            raise ValueError("QCEC synthetic derivation needs explicit integer seed")
    seeds = [case["seed"] for case in cases if "seed" in case]
    if len(set(seeds)) != len(seeds):
        raise ValueError("duplicate generator seeds")
    if data["schedule"]["default_repetitions"] != 15:
        raise ValueError("P1 confirmatory protocol must retain the declared 15 pairs")
    if data["theorems"]["hmr"]["backends"] != ["zdd", "hybrid-exact"]:
        raise ValueError("HMR theorem cannot silently change to a unitary comparator")
    if data["theorems"]["classical"]["backends"] != ["sat", "zdd", "qcec"]:
        raise ValueError("classical comparator list must stay explicit")
    return data


def _files() -> dict[str, str]:
    return {name: sha256((ROOT / name).read_bytes()) for name in SOURCE_FILES}


def _oracle_classical(case, left, right) -> dict:
    # The trusted test oracle is separate from the measured SAT/ZDD/QCEC
    # engines. GF16 tests every input, GF64 tests exact basis + seeded dirty
    # states, and synthetics run exhaustive. QCEC-derived positives have a
    # known semantics-preserving rewrite grammar and deterministic samples.
    if case["family"] == "qcec":
        rng = random.Random(case["seed"] + 100000)
        states = [0, 1, (1 << left.width) - 1]
        states += [rng.getrandbits(left.width) for _ in range(64)]
        rationale = ("proven commuting swaps / self-inverse gate pairs + sampled replay"
                     if case["expected"] == "equivalent"
                     else "appended X changes the entire full-output permutation")
    elif case["family"] == "kmb":
        n = left.width // 3
        if n == 4:
            states = list(range(1 << 12))
            rationale = "exhaustive all 4096 complete dirty-register basis states"
        else:
            rng = random.Random(406406)
            states = [0, (1 << 18) - 1]
            states += [((1 << i) | (1 << (n + j))) for i in range(n) for j in range(n)]
            states += [rng.getrandbits(left.width) for _ in range(256)]
            rationale = "source-pinned separate GF64 exhaustive tests plus 294 seeded/basis probes"
    else:
        states = list(range(1 << left.width))
        rationale = "exhaustive all synthetic 5/6-wire basis inputs"
    equal = True
    witness = None
    for x in states:
        if left.run(x) != right.run(x):
            equal = False
            witness = x
            break
    if equal != (case["expected"] == "equivalent"):
        raise RuntimeError(f"independent P1 classical oracle label mismatch: {case['id']}")
    return {"case_id": case["id"], "label_validated": True,
            "tested_states": len(states) if witness is None else states.index(witness) + 1,
            "witness": witness, "rationale": rationale, "exhaustive": (
                case["family"] == "synthetic"
                or case["family"] == "kmb" and left.width == 12
            )}


def _oracle_hmr(case: dict) -> dict:
    from benchmarks.hmr_qualification import load_manifest as load_hmr
    from benchmarks.hmr_qualification import oracle_case

    item = next(r for r in load_hmr()["cases"] if r["id"] == case["fixture"])
    oracle = oracle_case(item)
    if not oracle["expected_label_verified"]:
        raise RuntimeError("independent Kraus oracle contradicted qualified HMR source")
    return {"case_id": case["id"], "label_validated": True,
            "tested_input_coherences": oracle["all_coherences_checked"],
            "witness": oracle["first_witness"],
            "diagonals_equal": oracle["diagonals_equal"],
            "rationale": "independent exhaustive Kraus images on all coherent pairs",
            "exhaustive": True}


def preflight(manifest: dict) -> dict:
    identities = {}
    for case in manifest["cases"]:
        left, right, source = build_case(case)
        source_hash = _program_digest(left, case["theorem"])
        candidate_hash = _program_digest(right, case["theorem"])
        oracle = (_oracle_hmr(case) if case["theorem"] == "hmr"
                  else _oracle_classical(case, left, right))
        identities[case["id"]] = {
            "reference_sha256": source_hash,
            "candidate_sha256": candidate_hash,
            "fixture_provenance": source,
            "oracle": oracle,
            "theorem": manifest["theorems"][case["theorem"]]["name"],
            "admissible_backends": list(manifest["theorems"][case["theorem"]]["backends"]),
        }
    return identities


def _quantile(values: list[float], position: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    f = (len(ordered) - 1) * position
    lo, hi = int(f), min(len(ordered) - 1, int(f) + 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (f - lo)


def distribution(values: list[float]) -> dict:
    return {"n": len(values), "median": statistics.median(values) if values else None,
            "p10": _quantile(values, 0.1), "p90": _quantile(values, 0.9)}


def _qualification(row: dict, expected: str) -> str:
    if row["execution_status"] == "error":
        return "error"
    if row["execution_status"] != "completed":
        reason = (row["execution_reason"] or "").lower()
        return "timeout" if "deadline" in reason or "wall" in reason else "inconclusive"
    if row["actual"] == "unsupported":
        return "unsupported"
    if row["actual"] == "inconclusive":
        return "inconclusive"
    if row["actual"] not in {"equivalent", "different"} or row["actual"] != expected:
        return "incorrect_decision"
    value = row["value"]
    detail = value.get("detail", {})
    if (row["actual"] == "different" and row["engine"] != "qcec"
            and not detail.get("witness_replayed")):
        return "invalid_witness"
    return "matched"


def summarize(rows: list[dict], cases: list[dict]) -> list[dict]:
    output = []
    for case in cases:
        matches = [r for r in rows if r["case_id"] == case["id"]]
        backends = sorted({r["engine"] for r in matches})
        by_backend = {}
        for b in backends:
            trials = [r for r in matches if r["engine"] == b]
            accepted = [r for r in trials if r["qualification"] == "matched"]
            by_backend[b] = {
                "eligible_trials": len(trials),
                "qualifications": dict(Counter(r["qualification"] for r in trials)),
                "engine_import_wall_seconds": distribution([
                    r["value"]["engine_import_wall_seconds"] for r in accepted
                ]),
                "decision_wall_seconds": distribution([
                    r["value"]["decision_wall_seconds"] for r in accepted
                ]),
                "whole_worker_wall_seconds": distribution([
                    r["worker_wall_seconds"] for r in trials
                ]),
                "whole_worker_cpu_seconds": distribution([
                    r["worker_cpu_seconds"] for r in trials
                    if r["worker_cpu_seconds"] is not None
                ]),
                "whole_worker_peak_rss_bytes": distribution([
                    r["worker_peak_rss_bytes"] for r in trials
                    if r["worker_peak_rss_bytes"] is not None
                ]),
            }
        eligibility = {
            "pyzx": "not_run_unqualified_same_theorem_adapter" if case["theorem"] == "classical"
                    else "not_applicable_to_measured_feedback_channel",
        }
        if case["theorem"] == "hmr":
            eligibility["qcec"] = "not_applicable_unitary_adapter_cannot_prove_hmr"
        paired = []
        reference, comparator = (
            ("sat", "qcec") if case["theorem"] == "classical"
            else ("zdd", "hybrid-exact")
        )
        for rep in sorted({r["repetition"] for r in matches}):
            group = {r["engine"]: r for r in matches if r["repetition"] == rep}
            if (reference in group and comparator in group
                    and group[reference]["qualification"] == "matched"
                    and group[comparator]["qualification"] == "matched"):
                a, b = group[reference]["value"]["decision_wall_seconds"], (
                    group[comparator]["value"]["decision_wall_seconds"]
                )
                if b > 0:
                    paired.append(a / b)
        output.append({
            "case_id": case["id"], "theorem": case["theorem"],
            "expected": case["expected"], "backends": by_backend,
            "excluded_comparators": eligibility,
            "ratio_title": f"{reference} / {comparator} decision wall seconds",
            "paired_ratio_only_matched": distribution(paired),
            "pairing_note": "Exploratory: only complete matched decisions on the same case/rep",
        })
    return output


def run_campaign(*, repetitions: int | None = None,
                 wall_seconds: float | None = None,
                 cases: list[str] | None = None) -> dict:
    from symq.experimental.execution import HardLimits, run_isolated
    from symq.external import versions as external_versions

    manifest = load_manifest()
    repetitions = (manifest["schedule"]["default_repetitions"]
                   if repetitions is None else repetitions)
    if type(repetitions) is not int or not 1 <= repetitions <= 30:
        raise ValueError("P1 repetitions must be an integer from 1 to 30")
    limits = manifest["resources"]
    wall = limits["worker_wall_seconds"] if wall_seconds is None else wall_seconds
    if type(wall) not in (int, float) or not math.isfinite(wall) or not 0 < wall <= 60:
        raise ValueError("P1 worker wall deadline must be finite in 0..60 seconds")
    hard = HardLimits(wall_seconds=wall, cpu_seconds=min(limits["worker_cpu_seconds"], wall),
                      memory_bytes=limits["worker_memory_bytes"])
    before, source_before = receipt(), _files()
    selected = [
        c for c in manifest["cases"] if cases is None or c["id"] in cases
    ]
    if not selected or (cases is not None and set(cases) != {c["id"] for c in selected}):
        raise ValueError("P1 case filter must name declared development cases")
    # Preflight ALL registered sources and independent oracles before any
    # timing, so a wrong expected label never becomes a measured 'failure'.
    identities = preflight(manifest)
    rng = random.Random(manifest["schedule"]["shuffle_seed"])
    pairs = [(case, rep) for case in selected for rep in range(repetitions)]
    rng.shuffle(pairs)
    rows = []
    for pair_id, (case, rep) in enumerate(pairs):
        engines = list(manifest["theorems"][case["theorem"]]["backends"])
        rng.shuffle(engines)
        for order, engine in enumerate(engines):
            exact = identities[case["id"]]
            result = run_isolated(
                worker_trial, case, engine, min(wall, limits["decision_seconds"]),
                exact["reference_sha256"], exact["candidate_sha256"], limits=hard,
            )
            value = result.value if result.status == "completed" else None
            actual = value["outcome"] if value is not None else result.status
            row = {
                "case_id": case["id"], "family": case["family"],
                "theorem": manifest["theorems"][case["theorem"]]["name"],
                "expected": case["expected"], "actual": actual,
                "repetition": rep, "pair_index": pair_id, "backend_order": order,
                "engine": engine, "execution_status": result.status,
                "execution_reason": result.reason, "worker_exitcode": result.exitcode,
                "worker_wall_seconds": result.wall_seconds,
                "worker_cpu_seconds": result.cpu_seconds,
                "worker_peak_rss_bytes": result.peak_rss_bytes,
                "value": value,
            }
            row["qualification"] = _qualification(row, case["expected"])
            rows.append(row)
    # Whole source hashes from every completed trial must be identical,
    # irrespective of engine or trial order; otherwise do not compare times.
    for row in rows:
        if row["value"] is not None:
            want = identities[row["case_id"]]
            got = row["value"]
            if (got["reference_sha256"], got["candidate_sha256"]) != (
                    want["reference_sha256"], want["candidate_sha256"]):
                raise RuntimeError("different source/candidate streams entered paired cells")
    after, source_after = receipt(), _files()
    counts = Counter(row["qualification"] for row in rows)
    outcome_counts = Counter(row["actual"] for row in rows)
    return {
        "schema_version": 1, "created_utc": datetime.now(timezone.utc).isoformat(),
        "kind": "symq-p1-public-development-comparative-pilot",
        "source_before": before, "source_after": after,
        "source_fingerprints_before": source_before,
        "source_fingerprints_after": source_after,
        "source_unchanged": before == after and source_before == source_after,
        "manifest_git_blob_sha1": PINNED_MANIFEST_GIT_BLOB_SHA1,
        "manifest_sha256": sha256(MANIFEST.read_bytes()),
        "manifest": manifest, "environment": machine(),
        "external_versions": external_versions(), "repetitions": repetitions,
        "campaign_type": "single-repetition-smoke" if repetitions == 1
                         else "exploratory_paired_repetitions",
        "limits": {"wall_seconds": hard.wall_seconds, "cpu_seconds": hard.cpu_seconds,
                   "memory_bytes": hard.memory_bytes,
                   "inner_decision_seconds": min(wall, limits["decision_seconds"])},
        "fixtures": identities,
        "eligible_trials": len(rows),
        "qualification_counts": dict(counts), "outcome_counts": dict(outcome_counts),
        "summary": summarize(rows, selected), "rows": rows,
        "notes": [
            "Every trial uses a fresh isolated spawn with hard wall/CPU/RSS limits.",
            "Case and backend order are randomized reproducibly with a pinned seed.",
            "QCEC is an independent full-unitary baseline ONLY for all-input reversible permutations.",
            "HMR full coherent-channel comparisons use the distinct exact hybrid Kraus oracle.",
            "MQT QCEC and PyZX are not incorrectly passed HMR programs.",
            "PyZX is NOT RUN on classical cases pending a vetted equivalent-theorem adapter.",
            "Whole-worker time/CPU/RSS includes imports, conversion and source creation.",
            "Cold backend import is measured as a separate stage, still included in whole-worker wall/CPU/RSS.",
            "Public decision wall/CPU includes checker-specific conversion but excludes cold backend imports.",
            "Ratios are descriptive, paired only for correct decisive results and without statistical claims.",
            "All exposed KMB, Qualtran and legacy QCEC dev cases are development; NO new blind holdout.",
            "Timeout/unsupported/error are observable incomplete coverage, never non-equivalence.",
            "Do not claim general competitor superiority from this selected pilot.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repetitions", type=int)
    parser.add_argument("--wall-seconds", type=float)
    parser.add_argument("--case", action="append", dest="cases")
    args = parser.parse_args()
    report = run_campaign(repetitions=args.repetitions, wall_seconds=args.wall_seconds,
                          cases=args.cases)
    if not report["source_unchanged"]:
        raise SystemExit("P1 source/binary or campaign harness changed during run")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    args.output.write_text(raw, encoding="utf-8")
    args.output.with_name(args.output.name + ".sha256").write_text(
        sha256(raw.encode()) + "  " + args.output.name + "\n", encoding="ascii"
    )
    errors = sum(report["qualification_counts"].get(kind, 0)
                 for kind in ("incorrect_decision", "invalid_witness", "error"))
    print(json.dumps({
        "eligible_trials": report["eligible_trials"],
        "qualifications": report["qualification_counts"],
        "manifest_sha256": report["manifest_sha256"],
        "source_unchanged": report["source_unchanged"],
        "complete_paired_repetitions": report["repetitions"],
        "kind": report["campaign_type"],
    }, sort_keys=True))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
