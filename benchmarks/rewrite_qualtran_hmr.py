"""Coherent rewrites on the public Qualtran GF2MulMBUC decompositions (m = 1, 2).

Each case replaces the reference decomposition by its measurement-based uncompute inside a
synthetic one-gate prefix and suffix, and proves it with the ``coherent`` theorem of
``symq rewrite`` (the bounded local channel checker). The whole rewritten program is then
compared with the source on every data coherence ``|x><y|`` by the independent Kraus-trajectory
oracle of ``tests/testkit/kraus_oracle.py``, which does not share the checker's code. A mutant
without the conditional phase correction must be refused although it agrees on the diagonal.

The fixtures were already explored during development: this is not a holdout. Costs use the
declared proxy ``ccx = 12, hmr = 0, cz = 2`` (other operations 1); they are not a T-count, a
hardware cost or any competition score.

    python -m benchmarks.rewrite_qualtran_hmr --output report.json
"""
from __future__ import annotations

import argparse
from pathlib import Path

from benchmarks.environment import machine, receipt
from benchmarks.hmr_qualification import hybrid, load_manifest, programs
from symq.experimental.hybrid import HOp, HybridProgram
from symq.experimental.serialization import save_json
from symq.labs.channel_composition import HybridFragment
from symq.labs.rewrite import Weights
from symq.labs.rewrite_request import HybridFrame, RewriteRequest, replay_report, run_request
from symq.resources import Budget
from tests.testkit.kraus_oracle import coherence_images

UPSTREAM = "https://github.com/quantumlib/Qualtran"
UPSTREAM_COMMIT = "638777fac4379bc62e2a1e4a52cf1a1753895d48"
WEIGHTS = Weights.from_mapping({"ccx": 12, "hmr": 0, "cz": 2}, unit="illustrative_proxy")


def _case(degree: int, mutant: bool) -> dict:
    identifier = f"m{degree}-full-" + ("missing_correction" if mutant else "none")
    manifest = load_manifest()
    case = next(c for c in manifest["cases"] if c["id"] == identifier)
    reference, candidate = (hybrid(p) for p in programs(case))
    prefix, suffix = [HOp("cx", (0, 1))], [HOp("cx", (0, 1))]
    source = HybridProgram(reference.data, reference.ancillas,
                           prefix + list(reference.ops) + suffix)
    rewritten = HybridProgram(reference.data, reference.ancillas,
                              prefix + list(candidate.ops) + suffix)
    request = RewriteRequest(
        "coherent", source, HybridFragment(reference.width, tuple(candidate.ops)),
        (len(prefix), len(prefix) + len(reference.ops)),
        HybridFrame(tuple(range(reference.width)),
                    clean=tuple(range(reference.data, reference.width)),
                    preserved=tuple(range(reference.data))),
        WEIGHTS)
    report = run_request(request, Budget(max_seconds=45))
    fresh = replay_report(report, Budget(max_seconds=45))

    left, right = coherence_images(source), coherence_images(rewritten)
    differing = [pair for pair in left if left[pair] != right[pair]]
    return {
        "id": identifier, "degree": degree, "mutant": mutant,
        "fixture_sha256": manifest["fixture_sha256"][
            f"benchmarks/corpus/qualtran/gf2mul_mbuc_m{degree}.json"],
        "outcome": report["result"]["outcome"], "replayed_outcome": fresh["result"]["outcome"],
        "theorem": report["result"]["theorem"], "application": report["application"],
        "cost": report["result"]["cost"],
        "independent_oracle": {
            "coherences_checked": len(left), "differing": len(differing),
            "diagonal_differs": any(x == y for x, y in differing),
        },
    }


def run() -> dict:
    rows = [_case(degree, mutant) for degree in (1, 2) for mutant in (False, True)]
    for row in rows:
        agree = row["independent_oracle"]["differing"] == 0
        if row["mutant"] == agree or (row["outcome"] == "equivalent") != agree:
            raise AssertionError(f"{row['id']}: checker and independent oracle disagree")
        if row["mutant"] and row["independent_oracle"]["diagonal_differs"]:
            raise AssertionError(f"{row['id']}: the mutant should differ only off-diagonal")
    return {"schema_version": 1, "kind": "symq_rewrite_qualtran_hmr",
            "source": {"url": UPSTREAM, "commit": UPSTREAM_COMMIT, "license": "Apache-2.0",
                       "status": "previously explored development fixture, not a holdout"},
            "environment": machine(), "receipt": receipt(), "cases": rows}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, help="write the JSON report here")
    args = parser.parse_args(argv)
    result = run()
    if args.output:
        save_json(result, args.output)
    for row in result["cases"]:
        print(f"{row['id']:<26} {row['outcome']:<12} {row['application']:<12} "
              f"weighted delta {row['cost']['weighted_delta']:>4}  "
              f"oracle differing {row['independent_oracle']['differing']}"
              f"/{row['independent_oracle']['coherences_checked']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
