"""Reproducible local development campaign; all trials, including failures, survive.

Every timed proof runs in a fresh interpreter. Fixture generation and fresh
canonical replay are separately timed; replay has the same ceiling, a fresh
deadline, and is never hidden in the proof timing. No cross-trial lift cache.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import platform
import random
import resource
import subprocess
import sys
from collections import Counter
from pathlib import Path
from time import perf_counter

from benchmarks.affine_basis_cases import make_case, source_document
from benchmarks.environment import receipt as checkout_receipt
from symq.labs import affine_basis_study as prototype
from symq.labs import affine_phase as core
from symq.resources import Budget

ROOT = Path(__file__).resolve().parents[1]
PINNED_HEAD = "cd315955256dfeebd7beeb67533c2c4ef2122bde"
PINNED_MODULE_SHA256 = "75bb5e45299af18b8264b7ad78ce2fc008d7a69fadf6f6b38ba69334bb1fec91"
RESEARCH_FILES = ("src/symq/labs/affine_basis_study.py", "benchmarks/affine_basis_cases.py",
                  "tests/testkit/affine_basis_oracle.py", "benchmarks/affine_basis.py",
                  "benchmarks/affine_basis_summary.py", "benchmarks/affine_basis_operations.py")


def _reference_class():
    """Load the checkout-only independent oracle without changing sys.path."""
    spec = importlib.util.spec_from_file_location(
        "symq_affine_basis_reference", ROOT / "tests/testkit/affine_basis_oracle.py")
    if spec is None or spec.loader is None:
        raise ImportError("the source-checkout oracle is required")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ExactChannel


ExactChannel = _reference_class()


def source_hashes():
    paths = [ROOT / "src/symq/labs/affine_phase.py"]
    paths.extend(ROOT / name for name in RESEARCH_FILES)
    return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode()).hexdigest()


def cases():
    raw = [
        ("identity_small", {"n": 6}),
        ("identity_medium", {"n": 9}),
        ("identity_dense", {"n": 12}),
        ("partition", {"n": 12, "presentation": "partition"}),
        ("almost_equal", {"n": 12, "presentation": "almost_equal"}),
        ("nonlinear_predicates", {"n": 9, "presentation": "nonlinear"}),
        ("mixed_coordinates", {"n": 12, "mixed_support": True, "seed": 11}),
        ("larger_modulus_small", {"n": 6, "k": 5}),
        ("perturbed_small", {"family": "perturbed", "n": 6}),
        ("perturbed_dense", {"family": "perturbed", "n": 12}),
        ("perturbed_nonlinear", {"family": "perturbed", "n": 9, "presentation": "nonlinear"}),
        ("early_negative", {"family": "single_dense", "n": 12}),
        ("early_negative_large_k", {"family": "single_dense", "n": 6, "k": 8}),
        ("partial_dephasing", {"family": "dephased_identity", "n": 12}),
        ("singleton_fibres", {"family": "singleton", "n": 24, "k": 16}),
        ("measured_dense_predicate", {"family": "invariant_dense", "n": 24, "k": 16}),
        ("grouped_cancellation", {"family": "grouped_zero", "n": 24, "k": 8}),
        ("output_mismatch", {"family": "output_negative", "n": 12}),
        ("dense_expansion_term_cap", {"n": 12, "k": 7}),
        ("short_deadline", {"n": 12, "k": 7}),
        ("cache_evictions", {"n": 9}),
        ("selection_fallback", {"n": 9}),
        ("tiny_reference", {"n": 4, "k": 4, "mixed_support": True, "seed": 37}),
        # Generated variations for the lift-reuse methods: other coefficients and 2-adic
        # valuations (scale), moduli, and kernel directions (mixed/partial supports).
        ("variation_scaled_odd", {"n": 12, "k": 5, "scale": 3}),
        ("variation_scaled_even", {"n": 12, "k": 5, "scale": 6}),
        ("variation_perturbed_scaled", {"family": "perturbed", "n": 12, "k": 5, "scale": 3}),
        ("variation_nonlinear_mixed", {"n": 9, "k": 4, "presentation": "nonlinear",
                                       "mixed_support": True, "seed": 5}),
        ("variation_dephased_mixed", {"family": "dephased_identity", "n": 12, "k": 4,
                                      "mixed_support": True, "seed": 3}),
        ("variation_perturbed_nonlinear_k5", {"family": "perturbed", "n": 9, "k": 5,
                                              "presentation": "nonlinear", "scale": 5}),
        # Adversarial for the factorized method: one dense predicate, invariant along
        # every kernel direction but the last.
        ("variation_near_invariant_dense", {"family": "near_invariant_dense", "n": 16, "k": 6}),
        # Positive with a phase that is constant on fibres but not identically zero.
        ("variation_fibre_constant", {"family": "fibre_constant", "n": 12, "k": 4}),
        ("variation_fibre_constant_mixed", {"family": "fibre_constant", "n": 12, "k": 5,
                                            "mixed_support": True, "seed": 9, "scale": 3}),
    ]
    result = []
    for name, spec in raw:
        row = {"id": name, "spec": spec, "budget": {"max_terms": 100_000, "max_seconds": 2.0},
               "settings": {}, "allow_inconclusive": False}
        if name == "dense_expansion_term_cap":
            row["budget"]["max_terms"] = 1000
            row["allow_inconclusive"] = True
        if name == "short_deadline":
            row["budget"]["max_seconds"] = 0.003
            row["allow_inconclusive"] = True
        if name == "cache_evictions":
            row["settings"] = {"max_cache_entries": 1, "max_cache_terms": 100}
        if name == "selection_fallback":
            row["settings"] = {"max_search_units": 1}
        result.append(row)
    return result


def trial(case_spec, method):
    row = {"case_id": case_spec["id"], "method": method, "qualified": False,
           "worker_source_hashes": source_hashes()}
    started = perf_counter()
    try:
        case = make_case(**case_spec["spec"])
        source = source_document(case)
        row.update(source_sha256=sha(source), expected_status=case.expected,
                   source_generation_seconds=perf_counter() - started)
        budget, settings = Budget(**case_spec["budget"]), prototype.Settings(**case_spec["settings"])
        started = perf_counter()
        result = prototype.run(case.left, case.right, case.dephaser, support=case.support,
                               method=method, budget=budget, settings=settings)
        row.update(result=result, proof_outer_seconds=perf_counter() - started,
                   proof_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        row["construction_and_proof_seconds"] = row["source_generation_seconds"] + row["proof_outer_seconds"]
    except Exception as error:  # noqa: BLE001 - preserve every failed experimental trial
        row.update(error=f"{type(error).__name__}: {error}", failed_stage_seconds=perf_counter() - started)
        return row
    qualified = result["status"] == case.expected
    if result["status"] == "inconclusive":
        qualified = case_spec["allow_inconclusive"] and result["receipt"] is None
    if result["status"] == "equivalent":
        receipt = result["receipt"]
        row["source_binding_valid"] = (type(receipt) is dict
                                       and receipt.get("source_sha256") == row["source_sha256"])
        replayed = False
        started = perf_counter()
        if type(receipt) is dict:
            try:
                replay = core.replay_affine_phase(case.left, case.right, case.dephaser, receipt,
                                                 support=case.support, budget=budget)
                row["replay_status"], row["replay_reason"] = replay.status, replay.reason
                replayed = replay.equivalent and replay.receipt is not None
            except Exception as error:  # noqa: BLE001 - a replay failure must remain in the artifact
                row["replay_error"] = f"{type(error).__name__}: {error}"
        row["replay_seconds"] = perf_counter() - started
        row["proof_and_replay_seconds"] = row["proof_outer_seconds"] + row["replay_seconds"]
        row["construction_proof_replay_seconds"] = row["source_generation_seconds"] + row["proof_and_replay_seconds"]
        qualified = qualified and row["source_binding_valid"] and replayed
    elif result["status"] == "not_proved":
        try:
            witness = result["witness"]
            row["witness_valid"] = (witness is not None
                                    and ExactChannel(case, points=witness).validates_witness(witness))
            qualified = qualified and row["witness_valid"] and result["receipt"] is None
        except Exception as error:  # noqa: BLE001 - keep invalid witness diagnostics
            row["witness_error"] = f"{type(error).__name__}: {error}"
            qualified = False
    if len(case.support.columns) <= 5 and case.dephaser.measurements <= 6:
        try:
            oracle = ExactChannel(case).compare()
            row["oracle"] = oracle
            if result["status"] != "inconclusive":
                qualified = qualified and (result["status"] == "equivalent") == oracle["equivalent"]
        except Exception as error:  # noqa: BLE001 - keep failed independent-oracle trials
            row["oracle_error"] = f"{type(error).__name__}: {error}"
            qualified = False
    row["qualified"] = qualified
    if source_hashes() != row["worker_source_hashes"]:
        row.update(qualified=False, provenance_error="worker source files changed during trial")
    row["final_peak_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return row


def isolated_trial(case, method):
    timeout = 2 * case["budget"]["max_seconds"] + 15
    request = json.dumps({"case": case, "method": method})
    started = perf_counter()
    try:
        process = subprocess.run([sys.executable, "-m", "benchmarks.affine_basis", "--worker"],
                                 input=request, text=True, capture_output=True, cwd=ROOT,
                                 env={**os.environ, "PYTHONHASHSEED": "0"}, timeout=timeout,
                                 check=False)
        row = json.loads(process.stdout)
        if process.returncode != 0:
            row.update(qualified=False, worker_returncode=process.returncode)
        if process.stderr:
            row["worker_stderr"] = process.stderr
    except Exception as error:  # noqa: BLE001 - retain timeout, decode and worker failures alike
        row = {"case_id": case["id"], "method": method, "qualified": False,
               "worker_error": f"{type(error).__name__}: {error}"}
    row["subprocess_wall_seconds"] = perf_counter() - started
    return row


def _version(name):
    """Recorded tool version; an absent optional tool is recorded, never a setup failure."""
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def provenance():
    root = ROOT
    module = root / "src/symq/labs/affine_phase.py"
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    module_sha = hashlib.sha256(module.read_bytes()).hexdigest()
    if module_sha != PINNED_MODULE_SHA256:
        raise ValueError("published baseline identity changed")
    # The byte identity above is the strict check. Lineage is recorded, not required:
    # a squash or rebase merge, or a shallow clone, keeps the bytes but not the commit.
    ancestry = subprocess.run(["git", "merge-base", "--is-ancestor", PINNED_HEAD, head],
                              cwd=root, check=False, capture_output=True)
    lineage = {0: "pinned commit is an ancestor", 1: "pinned commit is not an ancestor"}.get(
        ancestry.returncode, "pinned commit unavailable in this history")
    if Path(core.__file__).resolve() != module.resolve():
        raise ValueError("imported baseline is outside the authenticated checkout")
    result = {"repository": "yoch/symq", "head": head, "baseline_commit": PINNED_HEAD,
              "baseline_lineage": lineage, "module_sha256": module_sha, "checkout_receipt": checkout_receipt(),
              "source_hashes": source_hashes(),
              "research_sha256": {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                                  for name in RESEARCH_FILES},
              "python": sys.version, "platform": platform.platform(), "machine": platform.machine(),
              "cpu_count": os.cpu_count(), "load_average": os.getloadavg(),
              "rss_units": "KiB on Linux; ru_maxrss includes launch/imports and may include inherited fork pages",
              "timer": "time.perf_counter, wall seconds", "replay_budget": "fresh deadline, same ceilings",
              "corpus": "generated development cases; no holdout and no external corpus",
              "versions": {name: _version(name) for name in ("pytest", "ruff")}}
    cpu_info = Path("/proc/cpuinfo")
    if cpu_info.exists():
        result["cpu_model"] = next((line.split(":", 1)[1].strip()
                                    for line in cpu_info.read_text().splitlines()
                                    if line.startswith("model name")), "unknown")
    for name in ("cpu.max", "memory.max"):
        location = Path("/sys/fs/cgroup") / name
        if location.exists():
            result[name] = location.read_text().strip()
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--require-decision", action="store_true",
                        help="fail qualification on every inconclusive result")
    parser.add_argument("--cases", nargs="*")
    parser.add_argument("--methods", nargs="*", choices=prototype.METHODS, default=list(prototype.METHODS))
    args = parser.parse_args(argv)
    if args.worker:
        request = json.loads(sys.stdin.read())
        print(json.dumps(trial(request["case"], request["method"])))
        return 0
    if args.output is None or not 1 <= args.repetitions <= 20 or not args.methods:
        parser.error("output, at least one method and repetitions in 1..20 required")
    specs = cases()
    if args.cases is not None:
        requested = set(args.cases)
        specs = [case for case in specs if case["id"] in requested]
        if {case["id"] for case in specs} != requested or not specs:
            parser.error("unknown/empty case list")
    if args.require_decision:
        for case in specs:
            case["allow_inconclusive"] = False
    document = {"schema": "symq.affine-basis-study/v1",
                "settings": {name: getattr(prototype.Settings(), name) for name, _ in prototype._SETTING_BOUNDS},
                "repetitions": args.repetitions, "methods": args.methods, "cases": specs,
                "trials": [], "qualified": False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    started = perf_counter()
    try:
        document["provenance"] = provenance()
    except Exception as error:  # noqa: BLE001 - retain setup refusals as failed evidence
        document.update(setup_error=f"{type(error).__name__}: {error}",
                        elapsed_seconds=perf_counter() - started)
        args.output.write_text(json.dumps(document, indent=2) + "\n")
        return 1
    for index, case in enumerate(specs):
        for repetition in range(args.repetitions):
            methods = list(args.methods)
            random.Random(371 + 1009 * index + repetition).shuffle(methods)
            for method in methods:
                row = isolated_trial(case, method)
                if row.get("worker_source_hashes") != document["provenance"]["source_hashes"]:
                    row.update(qualified=False, provenance_error="missing/mismatched worker source identity")
                row.update(repetition=repetition, trial_order=len(document["trials"]))
                document["trials"].append(row)
        document["elapsed_seconds"] = perf_counter() - started
        document["qualified"] = all(row["qualified"] for row in document["trials"])
        args.output.write_text(json.dumps(document, indent=2) + "\n")
        subset = [row for row in document["trials"] if row["case_id"] == case["id"]]
        statuses = Counter(row.get("result", {}).get("status", "error") for row in subset)
        print(f"{case['id']}: {dict(statuses)}, qualified={all(row['qualified'] for row in subset)}",
              file=sys.stderr, flush=True)
    return 0 if document["qualified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
