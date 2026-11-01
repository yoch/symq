"""Classical contextual rewrite of a public KMB multiplier, qualified through the command line.

The source is ``gf16-07.kmb`` from James Barlow's public VQCC bilinear dataset (Apache 2.0 per the
dataset page, see ``benchmarks/corpus/bilinear_kmb/SOURCE.md``): a GF(16) multiplier modulo
``0x13`` on three dirty 4-bit registers. It is read from the corpus, which checks its SHA-256
against the manifest, decoded by the strict reader of ``benchmarks/kmb.py``, and compared on all
4,096 states of its 12 wires with the independent field arithmetic of
``tests/testkit/field_oracle.py``.

It is then placed in a real 13-wire context, unchanged from the original P0 of #128: a prefix
``cx(0,12) cx(0,12) cx(1,7)``, the decoded circuit, and a suffix ``cx(11,0) cx(10,2)``. Wire 12 is
an ancilla declared 0 on input and clean at the cut. The replacement is SymQ's 9-product tower
multiplier in the same basis. The versioned files under
``benchmarks/corpus/bilinear_kmb/rewrite/gf16-07-context/`` are the source, the replacement and a
``symq_rewrite_request`` with the exact span, the contract and the declared weights
``ccx = mcx = 32`` (other operations 1).

``--output-dir`` qualifies the case as a user would, through ``symq rewrite --isolate`` and
``symq replay`` after the inputs are deleted, with the ``classical`` SAT theorem. It requires:
- every precondition, restoration and output-equality obligation passed, and a negative declared
  weighted delta;
- the candidate, taken from a fresh replay, equal to the source on all 4,096 legal states;
- three refusals: an unprepared ancilla (``precondition_failed``), a corrupted replacement
  (``not_proved``), and an edited report (``symq replay`` exits 3).

The dataset was explored during development: this is not a holdout, and the weights are not a
hardware cost. The classical theorem says nothing about phases or superpositions.

    python -m benchmarks.rewrite_kmb_context --output-dir evidence/kmb-context-cli
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from benchmarks.bilinear_kmb import DATASET_URL, manifest, source_starts
from benchmarks.environment import machine, receipt
from benchmarks.kmb import decode
from benchmarks.rewrite_cli import (
    INPUTS,
    MEMORY_MIB,
    TIMEOUT_SECONDS,
    cli,
    cli_expectations,
    dump,
    qualify,
    require,
    rewrite,
)
from symq.circuit import Circuit
from symq.experimental.serialization import save_json
from symq.generators.gf2n import tower_multiplier
from symq.labs.rewrite_request import replayed_candidate
from tests.testkit.field_oracle import multiplier_output

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "benchmarks" / "corpus" / "bilinear_kmb" / "rewrite"
CASE = "gf16-07-context"
PUBLIC_ID = "gf16-07"
KMB_SHA256 = "636c554e783c83daf74e40b4e1ae2885473fcf4f348a1736f5b65360c82f0f8c"
N, MODULUS, WIDTH, ANCILLA = 4, 0x13, 13, 12
OBLIGATIONS = ("domain", "prefix", "interface", "suffix", "restore_original", "restore_candidate")


def public_source() -> Circuit:
    """The decoded ``gf16-07.kmb``, after its SHA-256 and field are checked."""
    row = next(r for r in manifest() if r["id"] == PUBLIC_ID)
    if (row["sha256"], row["width"], row["modulus"]) != (KMB_SHA256, N, MODULUS):
        raise ValueError("the public KMB manifest does not describe gf16-07 as pinned")
    raw = source_starts()[row["kmb"]]  # checks every file's SHA-256 against the manifest
    if hashlib.sha256(raw).hexdigest() != KMB_SHA256:
        raise ValueError("gf16-07.kmb differs from its pinned SHA-256")
    circuit = decode(raw)
    if circuit.width != 3 * N:
        raise ValueError("gf16-07.kmb is not a 12-wire multiplier")
    return circuit


def oracle_states(circuit: Circuit) -> int:
    """States on which the circuit equals the independent field arithmetic (all, or raise)."""
    for state in range(1 << (3 * N)):
        if circuit.run(state) != multiplier_output(N, state, MODULUS):
            raise AssertionError(f"gf16-07 differs from GF(16) mod 0x13 on state {state}")
    return 1 << (3 * N)


def context() -> tuple[Circuit, Circuit, tuple[int, int]]:
    """The 13-wire source, the replacement and the exact span of the public block."""
    original = public_source()
    prefix = Circuit(WIDTH).cx(0, ANCILLA).cx(0, ANCILLA).cx(1, 7)
    suffix = Circuit(WIDTH).cx(11, 0).cx(10, 2)
    source = Circuit(WIDTH, [*prefix.gates, *original.gates, *suffix.gates])
    replacement = Circuit(WIDTH, list(tower_multiplier(N, modulus=MODULUS).gates))
    return source, replacement, (len(prefix.gates), len(prefix.gates) + len(original.gates))


def case_files() -> dict[str, str]:
    source, replacement, span = context()
    request = {
        "schema_version": 1, "kind": "symq_rewrite_request", "theorem": "classical",
        "source": "source.json", "replacement": "replacement.json", "span": list(span),
        "contract": {"initial_constants": [[ANCILLA, 0]], "clean_at_cut": [ANCILLA],
                     "restored_at_cut": [], "cut_assumption": None},
        "weights": {"by_kind": [["ccx", 32], ["mcx", 32]], "unit": "declared_units",
                    "default": 1},
        "require_saving": False,
    }
    return {"source.json": dump(source.to_dict()),
            "replacement.json": dump(replacement.to_dict()),
            "request.json": dump(request)}


def provenance_manifest() -> dict:
    return {"schema_version": 1, "dataset": DATASET_URL, "author": "James Barlow",
            "license": "Apache-2.0 (dataset page licence field)", "id": PUBLIC_ID,
            "kmb_sha256": KMB_SHA256, "field": {"n": N, "modulus": hex(MODULUS)},
            "status": "public development case, not a holdout",
            "generated_by": "python -m benchmarks.rewrite_kmb_context --export",
            "files_sha256": {f"{CASE}/{name}": hashlib.sha256(text.encode()).hexdigest()
                             for name, text in case_files().items()}}


def export(directory: Path) -> None:
    destination = directory / CASE
    destination.mkdir(parents=True, exist_ok=True)
    for name, text in case_files().items():
        (destination / name).write_text(text, encoding="utf-8")
    (directory / "MANIFEST.json").write_text(dump(provenance_manifest()), encoding="utf-8")


def _negative(name: str, work: Path, edit) -> dict:
    """A copy of the case with one input edited, proved through the CLI; it must be refused."""
    work.mkdir(parents=True, exist_ok=True)
    for file in INPUTS:
        shutil.copyfile(CORPUS / CASE / file, work / file)
    edit(work)
    code, out, report = rewrite(work)
    return {"case": name, "rewrite_exit_code": code, "outcome": out["result"]["outcome"],
            "candidate_exported": report["candidate"] is not None}


def _without_initial_constant(work: Path) -> None:
    request = json.loads((work / "request.json").read_text())
    request["contract"]["initial_constants"] = []
    (work / "request.json").write_text(dump(request))


def _without_one_toffoli(work: Path) -> None:
    replacement = json.loads((work / "replacement.json").read_text())
    gates = replacement["gates"]
    gates.pop(next(i for i, (name, _) in enumerate(gates) if name == "ccx"))
    (work / "replacement.json").write_text(dump(replacement))


def _edited_reports(report_path: Path, work: Path) -> list[dict]:
    """The proved report with one stored field contradicted; ``symq replay`` must exit 3."""
    work.mkdir(parents=True, exist_ok=True)
    proved = json.loads(report_path.read_text())
    edits = {"outcome turned negative": lambda r: r["result"].update(outcome="not_proved"),
             "candidate removed": lambda r: r.update(candidate=None),
             "obligation edited": lambda r: r["result"]["obligations"][0].update(
                 status="failed")}
    rows = []
    for name, edit in edits.items():
        edited = json.loads(json.dumps(proved))
        edit(edited)
        (work / "edited.json").write_text(json.dumps(edited))
        code, _ = cli("replay", "edited.json", cwd=work, allowed=(0, 2, 3))
        rows.append({"case": f"report: {name}", "replay_exit_code": code})
    return rows


def run(output_dir: Path) -> dict:
    """Qualify the versioned case through the CLI; write ``summary.json`` in ``output_dir``."""
    expected = provenance_manifest()
    if json.loads((CORPUS / "MANIFEST.json").read_text()) != expected:
        raise AssertionError("the versioned KMB rewrite files do not match a fresh export")
    for path, digest in expected["files_sha256"].items():
        if hashlib.sha256((CORPUS / path).read_bytes()).hexdigest() != digest:
            raise AssertionError(f"versioned file changed: {path}")
    source_states = oracle_states(public_source())

    work = output_dir / CASE
    row = qualify(CORPUS / CASE, work)
    report = json.loads((work / "report.json").read_text())
    obligations = {o["name"]: o["status"] for o in report["result"]["obligations"]}
    candidate = replayed_candidate(report)
    source, _, _ = context()
    legal = [state for state in range(1 << WIDTH) if not state >> ANCILLA & 1]
    agreeing = sum(candidate is not None and candidate.run(x) == source.run(x) for x in legal)
    proved_inputs = {key: expected["files_sha256"][f"{CASE}/{key}.json"]
                     for key in ("source", "replacement", "request")}
    require(CASE, {
        **cli_expectations(row, proved=True),
        "versioned files proved": row["input_file_sha256"] == proved_inputs,
        "every SAT obligation passed": obligations == dict.fromkeys(OBLIGATIONS, "passed"),
        "negative declared weighted delta": row["cost"]["weighted_delta"] < 0,
        "candidate equals the source on every legal state": agreeing == len(legal),
    })

    negatives = [
        _negative("unprepared ancilla", output_dir / "negative-unprepared-ancilla",
                  _without_initial_constant),
        _negative("corrupted replacement", output_dir / "negative-corrupted-replacement",
                  _without_one_toffoli),
    ]
    expected_refusals = {"unprepared ancilla": "precondition_failed",
                         "corrupted replacement": "not_proved"}
    for negative in negatives:
        require(negative["case"], {
            "refused with exit 2": negative["rewrite_exit_code"] == 2,
            "expected outcome": negative["outcome"] == expected_refusals[negative["case"]],
            "no candidate": not negative["candidate_exported"],
        })
    edited = _edited_reports(work / "report.json", output_dir / "negative-edited-report")
    for negative in edited:
        require(negative["case"], {"replay exits 3": negative["replay_exit_code"] == 3})

    summary = {"schema_version": 1, "kind": "symq_rewrite_kmb_context_cli",
               "source": {key: expected[key] for key in
                          ("dataset", "author", "license", "id", "kmb_sha256", "field",
                           "status")},
               "versioned_files_sha256": expected["files_sha256"],
               "independent_oracle_states": source_states,
               "context": {"width": WIDTH, "ancilla": ANCILLA,
                           "span": json.loads((CORPUS / CASE / "request.json").read_text())
                           ["span"]},
               "limits": {"wall_seconds": TIMEOUT_SECONDS, "memory_mib": MEMORY_MIB},
               "case": {**row, "obligations": obligations, "legal_states_checked": len(legal),
                        "legal_states_agreeing": agreeing},
               "negatives": negatives + edited,
               "environment": machine(), "receipt": receipt()}
    save_json(summary, output_dir / "summary.json")
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--output-dir", type=Path,
                        help="qualify the versioned case through the CLI and keep the reports")
    action.add_argument("--export", type=Path, help="regenerate the versioned case files")
    args = parser.parse_args(argv)
    if args.export:
        export(args.export)
        return 0
    args.output_dir.mkdir(parents=True, exist_ok=True)
    result = run(args.output_dir)
    case = result["case"]
    print(f"{CASE}: exit {case['rewrite_exit_code']} {case['outcome']}, replay exit "
          f"{case['replay_exit_code']}, weighted delta {case['cost']['weighted_delta']}, "
          f"{case['legal_states_agreeing']}/{case['legal_states_checked']} legal states, "
          f"oracle {result['independent_oracle_states']} states")
    for negative in result["negatives"]:
        print(f"  refused: {negative['case']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
