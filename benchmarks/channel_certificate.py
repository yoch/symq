"""Bounded development reproduction for one-copy sign/HMR certificates.

No speedup claim, untouched holdout or native-engine comparison. Results are
written only to the requested output artifact, never back into the corpus.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import time
from dataclasses import asdict
from pathlib import Path

import symq
from symq.hashing import canonical_json, canonical_sha256
from symq.kickmix import load_kmx
from symq.labs.channel_certificate import (
    CertificateLimits,
    discover_certificate,
    verify_certificate,
)
from symq.labs.qualtran import load_qualtran_fixture
from symq.phase import PhaseProgram
from symq.resources import Budget

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_FIXTURE_BLOBS = {
    "benchmarks/corpus/kickmix/inc8.kmx": "0604339b577f47d5cc63de0a89088863e1e8a935",
    "benchmarks/corpus/qualtran/gf2mul_mbuc_m1.json": "65ddd0635f42eb01e03ceffdd2ed13b9f2134571",
    "benchmarks/corpus/qualtran/gf2mul_mbuc_m2.json": "4bddfc240a3221372e04af5af70f4b13dee4bbd5",
}


def _authenticate_fixtures() -> dict[str, str]:
    """Bind the already exposed development corpus before interpreting any program."""
    hashes = {}
    for path, expected in PUBLIC_FIXTURE_BLOBS.items():
        raw = (ROOT / path).read_bytes()
        actual = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        if actual != expected:
            raise ValueError(f"public fixture differs from the pinned Git blob: {path}")
        hashes[path] = hashlib.sha256(raw).hexdigest()
    return hashes


def _program(data: int, functions: list[tuple[int, ...]], phase: tuple[int, ...] = ()):
    program = PhaseProgram(data, 1)
    for function in functions:
        for term in function:
            controls = tuple(q for q in range(data) if term >> q & 1)
            program.mcx(*controls, data)
        program.hmr(data)
    for term in phase:
        program.mcz(*(q for q in range(data) if term >> q & 1))
    return program


def _cases():
    for family in ("redundant", "nonlinear_relabel"):
        for count in (3, 5, 8, 12):
            data = 2 * count + 1  # a coherent spectator remains
            features = [(3 << (2 * i),) for i in range(count)]
            right_features = list(features)
            if family == "redundant":
                right_features.extend((features[i][0] | features[j][0],)
                                      for i in range(count) for j in range(i + 1, count))
            else:
                right_features[-1] = (features[-1][0], features[0][0] | features[1][0])
            yield (f"{family}-{count}", "constructed development family", "equivalent",
                   _program(data, features),
                   _program(data, right_features, (features[0][0] | features[1][0],)))
    inc = load_kmx(ROOT / "benchmarks/corpus/kickmix/inc8.kmx").to_phase_program(range(8))
    reference = PhaseProgram(8, inc.ancillas)
    for target in reversed(range(8)):
        reference.mcx(*range(target), target)
    public = [("inc8", reference, inc)]
    for degree in (1, 2):
        path = ROOT / f"benchmarks/corpus/qualtran/gf2mul_mbuc_m{degree}.json"
        public.append((f"qualtran_m{degree}", *load_qualtran_fixture(path).programs()))
    for name, left, right in public:
        yield name, "previously exposed public development fixture", "equivalent", left, right
        mutant = PhaseProgram(right.data, right.ancillas, list(right.ops))
        index = max(i for i, op in enumerate(mutant.ops) if op.kind == "mcz_if")
        del mutant.ops[index]
        yield (name + "-missing-feedback", "mutated public development fixture", "not_proved",
               left, mutant)


def _git(*arguments: str) -> str | None:
    try:
        result = subprocess.run(["git", *arguments], cwd=ROOT, text=True,
                                capture_output=True, check=False, timeout=5)
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _program_sha(program: PhaseProgram) -> str:
    return canonical_sha256({
        "grammar": "sign-hmr/affine-outcomes/full-channel/v1",
        "data": program.data, "ancillas": program.ancillas,
        "ops": [[op.kind, list(op.qubits), op.outcome] for op in program.ops],
    })


def run(repetitions: int = 3) -> dict:
    if type(repetitions) is not int or not 1 <= repetitions <= 100:
        raise ValueError("repetitions must be an integer in 1..100")
    fixture_hashes = _authenticate_fixtures()
    budget = Budget(max_terms=20_000, max_seconds=5)
    limits = CertificateLimits()
    records = []
    for name, provenance, expected, left, right in _cases():
        trials = []
        for _ in range(repetitions):
            started = time.perf_counter()
            result = discover_certificate(left, right, budget=budget, limits=limits)
            elapsed = time.perf_counter() - started
            row = {"outcome": result.outcome, "reason": result.reason,
                   "full_call_wall_seconds": elapsed, "certificate_bytes": None,
                   "selected_features": None, "fresh_check_outcome": None}
            if result.certificate is not None:
                document = result.certificate.to_dict()
                row.update({
                    "certificate_bytes": len(canonical_json(document)),
                    "selected_features": len(result.certificate.left_selectors),
                    "left_sha256": result.certificate.left_sha256,
                    "right_sha256": result.certificate.right_sha256,
                    "fresh_check_outcome": verify_certificate(
                        left, right, document, budget=budget, limits=limits).outcome,
                })
            trials.append(row)
        records.append({
            "id": name, "provenance": provenance, "expected_search_outcome": expected,
            "data_qubits": left.data, "ancillas": left.ancillas,
            "left_events": left.measurements, "right_events": right.measurements,
            "left_sha256": _program_sha(left), "right_sha256": _program_sha(right),
            "trials": trials,
        })
    package = Path(symq.__file__).resolve().parent
    source_hashes = {str(path.relative_to(package)): hashlib.sha256(path.read_bytes()).hexdigest()
                     for path in sorted(package.rglob("*.py"))}
    qualification_passed = all(
        trial["outcome"] == record["expected_search_outcome"]
        and (trial["outcome"] != "equivalent" or trial["fresh_check_outcome"] == "equivalent")
        for record in records for trial in record["trials"]
    )
    return {
        "kind": "symq_channel_certificate_development_reproduction", "schema_version": 1,
        "git_head": _git("rev-parse", "HEAD"),
        "working_tree_status": _git("status", "--porcelain"),
        "python": platform.python_version(), "python_compiler": platform.python_compiler(),
        "platform": platform.platform(), "machine": platform.machine(),
        "package_python_source_sha256": source_hashes,
        "benchmark_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "fixture_sha256": fixture_hashes,
        "fixture_git_blob_sha1": PUBLIC_FIXTURE_BLOBS,
        "qualification_passed": qualification_passed,
        "budget": asdict(budget), "limits": asdict(limits), "repetitions": repetitions,
        "records": records,
        "limitations": [
            "Development data only; no untouched holdout or speedup claim.",
            "No external or native-engine timing comparison; memory/RSS is not measured.",
            "Public corrected fixtures have empty signatures and do not show nonlinear benefit.",
            "not_proved is failure of this search/certificate, not channel inequivalence.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run(args.repetitions)
    encoded = json.dumps(report, sort_keys=True, indent=2) + "\n"
    if args.output is None:
        print(encoded, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    return 0 if report["qualification_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
