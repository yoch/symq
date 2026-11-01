"""Coherent rewrites on the public Qualtran GF2MulMBUC decompositions (m = 1, 2), through the CLI.

Four cases: for m = 1 and m = 2, the measurement-based uncompute that Qualtran publishes, and a
mutant without its conditional phase correction. Each replaces the reference decomposition
inside a synthetic one-gate prefix and suffix.

The cases are versioned files under ``benchmarks/corpus/qualtran/rewrite/<case>/``:
``source.json`` (the hybrid program), ``replacement.json`` (the fragment) and ``request.json``
(the span, the physical contract and the declared weights). ``--export`` regenerates them from
the Qualtran fixtures, whose SHA-256 are checked against the provenance manifest first; a test
checks the committed files are byte-identical to a fresh export.

``--output-dir`` qualifies every case through the command line, as a user would:

1. copy the three versioned files into a fresh directory;
2. ``symq rewrite request.json --isolate`` (hard wall-clock and memory limits) writes the report;
   the two valid rewrites must exit 0, the two mutants 2, and a failure carries no candidate;
3. delete the three input files and run ``symq replay`` on the report alone, which must reprove
   it and agree (``reverified``);
4. compare the source and the rewritten program on every data coherence ``|x><y|`` with the
   independent Kraus-trajectory oracle of ``tests/testkit/kraus_oracle.py``, which shares no
   code with the checker. The mutants must differ, and only off the diagonal.

The fixtures were already explored during development: this is not a holdout. Costs use the
declared proxy ``ccx = 12, hmr = 0, cz = 2`` (other operations 1); they are not a T-count, a
hardware cost or any competition score.

    python -m benchmarks.rewrite_qualtran_hmr --output-dir evidence/qualtran-hmr-cli
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from benchmarks.environment import machine, receipt
from benchmarks.hmr_qualification import hybrid, load_manifest, programs
from benchmarks.rewrite_cli import (
    MEMORY_MIB,
    TIMEOUT_SECONDS,
    cli_expectations,
    dump,
    files_sha256,
    qualify,
    require,
    verify_versioned,
    write_versioned,
)
from symq.experimental.hybrid import HOp, HybridProgram
from symq.experimental.serialization import program_from_dict, program_to_dict, save_json
from symq.labs.channel_composition import HybridFragment
from symq.labs.rewrite_request import fragment_from_dict, fragment_to_dict
from tests.testkit.kraus_oracle import coherence_images

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "benchmarks" / "corpus" / "qualtran" / "rewrite"
UPSTREAM = "https://github.com/quantumlib/Qualtran"
UPSTREAM_COMMIT = "638777fac4379bc62e2a1e4a52cf1a1753895d48"
CASES = tuple((degree, mutant) for degree in (1, 2) for mutant in (False, True))


def identifier(degree: int, mutant: bool) -> str:
    return f"m{degree}-full-" + ("missing_correction" if mutant else "none")


def case_files(degree: int, mutant: bool) -> dict[str, str]:
    """The three input files of one case, from the authenticated Qualtran fixture."""
    manifest = load_manifest()  # raises if a fixture's SHA-256 differs from the manifest
    case = next(c for c in manifest["cases"] if c["id"] == identifier(degree, mutant))
    reference, candidate = (hybrid(p) for p in programs(case))
    prefix, suffix = [HOp("cx", (0, 1))], [HOp("cx", (0, 1))]
    source = HybridProgram(reference.data, reference.ancillas,
                           prefix + list(reference.ops) + suffix)
    fragment = HybridFragment(reference.width, tuple(candidate.ops))
    request = {
        "schema_version": 1, "kind": "symq_rewrite_request", "theorem": "coherent",
        "source": "source.json", "replacement": "replacement.json",
        "span": [len(prefix), len(prefix) + len(reference.ops)],
        "contract": {"wires": list(range(reference.width)),
                     "clean": list(range(reference.data, reference.width)),
                     "preserved": list(range(reference.data)),
                     "max_local_width": 6, "max_events": 8, "max_branches": 256},
        "weights": {"by_kind": [["ccx", 12], ["cz", 2], ["hmr", 0]],
                    "unit": "illustrative_proxy", "default": 1},
        "require_saving": False,
    }
    return {"source.json": dump(program_to_dict(source)),
            "replacement.json": dump(fragment_to_dict(fragment)),
            "request.json": dump(request)}


def all_case_files() -> dict[str, dict[str, str]]:
    return {identifier(degree, mutant): case_files(degree, mutant) for degree, mutant in CASES}


def provenance_manifest(cases: dict[str, dict[str, str]] | None = None) -> dict:
    manifest = load_manifest()
    return {"schema_version": 1, "source": UPSTREAM, "upstream_commit": UPSTREAM_COMMIT,
            "license": "Apache-2.0",
            "fixture_sha256": {name: digest for name, digest in manifest["fixture_sha256"].items()
                               if "qualtran" in name},
            "status": "previously explored development fixtures, not a holdout",
            "generated_by": "python -m benchmarks.rewrite_qualtran_hmr --export",
            "files_sha256": files_sha256(cases or all_case_files())}


def export(directory: Path) -> None:
    cases = all_case_files()
    write_versioned(directory, cases, provenance_manifest(cases))


def _oracle(directory: Path) -> dict:
    source = program_from_dict(json.loads((directory / "source.json").read_text()))
    fragment = fragment_from_dict(json.loads((directory / "replacement.json").read_text()))
    start, stop = json.loads((directory / "request.json").read_text())["span"]
    rewritten = HybridProgram(source.data, source.ancillas,
                              source.ops[:start] + list(fragment.ops) + source.ops[stop:])
    left, right = coherence_images(source), coherence_images(rewritten)
    differing = [pair for pair in left if left[pair] != right[pair]]
    return {"coherences_checked": len(left), "differing": len(differing),
            "diagonal_differs": any(x == y for x, y in differing)}


def _qualify(degree: int, mutant: bool, work: Path) -> dict:
    name = identifier(degree, mutant)
    return {"id": name, "degree": degree, "mutant": mutant,
            "independent_oracle": _oracle(CORPUS / name), **qualify(CORPUS / name, work)}


def check(row: dict) -> None:
    """The preregistered outcome of one case; raises on any disagreement."""
    valid = not row["mutant"]
    oracle = row["independent_oracle"]
    require(row["id"], {
        **cli_expectations(row, proved=valid),
        "independent oracle agrees": (oracle["differing"] == 0) == valid,
        "mutant differs only off the diagonal": valid or not oracle["diagonal_differs"],
    })


def run(output_dir: Path) -> dict:
    """Qualify the four versioned cases through the CLI; write ``summary.json`` there."""
    expected = provenance_manifest()
    verify_versioned(CORPUS, expected)
    rows = []
    for degree, mutant in CASES:
        row = _qualify(degree, mutant, output_dir / identifier(degree, mutant))
        check(row)
        proved_inputs = {key: expected["files_sha256"][f"{row['id']}/{key}.json"]
                         for key in ("source", "replacement", "request")}
        if row["input_file_sha256"] != proved_inputs:
            raise AssertionError(f"{row['id']}: the CLI did not prove the versioned files")
        rows.append(row)
    summary = {"schema_version": 2, "kind": "symq_rewrite_qualtran_hmr_cli",
               "source": {key: expected[key] for key in
                          ("source", "upstream_commit", "license", "fixture_sha256", "status")},
               "versioned_files_sha256": expected["files_sha256"],
               "limits": {"wall_seconds": TIMEOUT_SECONDS, "memory_mib": MEMORY_MIB},
               "accepted": sum(row["outcome"] == "equivalent" for row in rows),
               "refused": sum(row["outcome"] == "not_proved" for row in rows),
               "environment": machine(), "receipt": receipt(), "cases": rows}
    save_json(summary, output_dir / "summary.json")
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--output-dir", type=Path,
                        help="qualify the versioned cases through the CLI and keep the reports")
    action.add_argument("--export", type=Path, help="regenerate the versioned case files")
    args = parser.parse_args(argv)
    if args.export:
        export(args.export)
        return 0
    args.output_dir.mkdir(parents=True, exist_ok=True)
    result = run(args.output_dir)
    for row in result["cases"]:
        print(f"{row['id']:<26} exit {row['rewrite_exit_code']} {row['outcome']:<11} "
              f"replay exit {row['replay_exit_code']}  weighted delta "
              f"{row['cost']['weighted_delta']:>4}  oracle differing "
              f"{row['independent_oracle']['differing']}"
              f"/{row['independent_oracle']['coherences_checked']}")
    print(f"{result['accepted']} accepted, {result['refused']} refused")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
