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
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import symq
from benchmarks.environment import machine, receipt
from benchmarks.hmr_qualification import hybrid, load_manifest, programs
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
INPUTS = ("source.json", "replacement.json", "request.json")
TIMEOUT_SECONDS, MEMORY_MIB = 45, 2048


def identifier(degree: int, mutant: bool) -> str:
    return f"m{degree}-full-" + ("missing_correction" if mutant else "none")


def _dump(value: dict) -> str:
    return json.dumps(value, sort_keys=True, indent=2) + "\n"


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
    return {"source.json": _dump(program_to_dict(source)),
            "replacement.json": _dump(fragment_to_dict(fragment)),
            "request.json": _dump(request)}


def provenance_manifest() -> dict:
    manifest = load_manifest()
    files = {}
    for degree, mutant in CASES:
        for name, text in case_files(degree, mutant).items():
            files[f"{identifier(degree, mutant)}/{name}"] = hashlib.sha256(
                text.encode()).hexdigest()
    return {"schema_version": 1, "source": UPSTREAM, "upstream_commit": UPSTREAM_COMMIT,
            "license": "Apache-2.0",
            "fixture_sha256": {name: digest for name, digest in manifest["fixture_sha256"].items()
                               if "qualtran" in name},
            "status": "previously explored development fixtures, not a holdout",
            "generated_by": "python -m benchmarks.rewrite_qualtran_hmr --export",
            "files_sha256": files}


def export(directory: Path) -> None:
    for degree, mutant in CASES:
        destination = directory / identifier(degree, mutant)
        destination.mkdir(parents=True, exist_ok=True)
        for name, text in case_files(degree, mutant).items():
            (destination / name).write_text(text, encoding="utf-8")
    (directory / "MANIFEST.json").write_text(_dump(provenance_manifest()), encoding="utf-8")


def _cli(*args: str, cwd: Path) -> tuple[int, dict]:
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(
        [str(Path(symq.__file__).resolve().parents[1]), os.environ.get("PYTHONPATH", "")]))
    done = subprocess.run([sys.executable, "-m", "symq", *args], cwd=cwd, env=env,
                          capture_output=True, text=True, timeout=4 * TIMEOUT_SECONDS,
                          check=False)
    try:
        output = json.loads(done.stdout) if done.stdout.strip() else {}
    except json.JSONDecodeError:
        output = {}
    if done.returncode not in (0, 2):
        raise AssertionError(f"symq {args[0]} failed ({done.returncode}): {done.stderr.strip()}")
    return done.returncode, output


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
    work.mkdir(parents=True, exist_ok=True)
    for file in INPUTS:
        shutil.copyfile(CORPUS / name / file, work / file)
    oracle = _oracle(work)
    code, out = _cli("rewrite", "request.json", "--isolate", "--timeout", str(TIMEOUT_SECONDS),
                     "--memory-mib", str(MEMORY_MIB), "--report", "report.json", cwd=work)
    report = json.loads((work / "report.json").read_text())
    for file in INPUTS:
        (work / file).unlink()  # the replay must stand on the report alone
    replay_code, replayed = _cli("replay", "report.json", "--timeout", str(TIMEOUT_SECONDS),
                                 cwd=work)
    return {
        "id": name, "degree": degree, "mutant": mutant,
        "input_file_sha256": report["provenance"]["input_file_sha256"],
        "rewrite_exit_code": code, "outcome": out["result"]["outcome"],
        "theorem": out["result"]["theorem"], "application": report["application"],
        "candidate_exported": report["candidate"] is not None,
        "cost": report["result"]["cost"], "execution": report["provenance"].get("execution"),
        "replay_exit_code": replay_code, "replay": replayed.get("replay"),
        "replayed_outcome": replayed.get("result", {}).get("outcome"),
        "inputs_deleted_before_replay": not any((work / f).exists() for f in INPUTS),
        "independent_oracle": oracle,
    }


def check(row: dict) -> None:
    """The preregistered outcome of one case; raises on any disagreement."""
    valid = not row["mutant"]
    oracle = row["independent_oracle"]
    expectations = {
        "rewrite exit code": row["rewrite_exit_code"] == (0 if valid else 2),
        "outcome": row["outcome"] == ("equivalent" if valid else "not_proved"),
        "candidate only when proved": row["candidate_exported"] == valid,
        "application": row["application"] == ("applied" if valid else "not_proved"),
        "isolated execution": (row["execution"] or {}).get("status") == "completed",
        "replay after deleting inputs": (row["inputs_deleted_before_replay"]
                                         and row["replay_exit_code"] == row["rewrite_exit_code"]
                                         and row["replayed_outcome"] == row["outcome"]
                                         and (row["replay"] or {}).get("reverified") is True),
        "independent oracle agrees": (oracle["differing"] == 0) == valid,
        "mutant differs only off the diagonal": valid or not oracle["diagonal_differs"],
    }
    failed = [name for name, ok in expectations.items() if not ok]
    if failed:
        raise AssertionError(f"{row['id']}: " + ", ".join(failed))


def run(output_dir: Path) -> dict:
    """Qualify the four versioned cases through the CLI; write ``summary.json`` there."""
    expected = provenance_manifest()
    committed = json.loads((CORPUS / "MANIFEST.json").read_text())
    if committed != expected:
        raise AssertionError("the versioned Qualtran rewrite files do not match a fresh export")
    for path, digest in expected["files_sha256"].items():
        if hashlib.sha256((CORPUS / path).read_bytes()).hexdigest() != digest:
            raise AssertionError(f"versioned file changed: {path}")
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
