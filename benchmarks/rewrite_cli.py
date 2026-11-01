"""Shared steps of the external rewrite qualifications that go through the command line.

Both public P0 paths (the classical KMB context and the coherent Qualtran cases) are qualified
the way a user would run them: versioned ``source.json``, ``replacement.json`` and
``request.json`` are copied into a fresh directory, ``symq rewrite --isolate`` proves the request
under hard wall-clock and memory limits, the input files are deleted, and ``symq replay`` reproves
the self-contained report alone.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import symq

INPUTS = ("source.json", "replacement.json", "request.json")
TIMEOUT_SECONDS, MEMORY_MIB = 45, 2048


def dump(value: dict) -> str:
    """The canonical text of a versioned JSON file."""
    return json.dumps(value, sort_keys=True, indent=2) + "\n"


def cli(*args: str, cwd: Path, allowed: tuple[int, ...] = (0, 2)) -> tuple[int, dict]:
    """Run ``python -m symq`` with the imported package; refuse an unexpected exit code."""
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(
        [str(Path(symq.__file__).resolve().parents[1]), os.environ.get("PYTHONPATH", "")]))
    done = subprocess.run([sys.executable, "-m", "symq", *args], cwd=cwd, env=env,
                          capture_output=True, text=True, timeout=4 * TIMEOUT_SECONDS,
                          check=False)
    try:
        output = json.loads(done.stdout) if done.stdout.strip() else {}
    except json.JSONDecodeError:
        output = {}
    if done.returncode not in allowed:
        raise AssertionError(f"symq {args[0]} exited {done.returncode}: {done.stderr.strip()}")
    return done.returncode, output


def rewrite(work: Path) -> tuple[int, dict, dict]:
    """``symq rewrite request.json --isolate`` in ``work``: exit code, printed output, report."""
    code, out = cli("rewrite", "request.json", "--isolate", "--timeout", str(TIMEOUT_SECONDS),
                    "--memory-mib", str(MEMORY_MIB), "--report", "report.json", cwd=work)
    return code, out, json.loads((work / "report.json").read_text())


def qualify(case_dir: Path, work: Path) -> dict:
    """Copy one versioned case, prove it with the CLI, delete its inputs and replay the report."""
    work.mkdir(parents=True, exist_ok=True)
    for file in INPUTS:
        shutil.copyfile(case_dir / file, work / file)
    code, out, report = rewrite(work)
    for file in INPUTS:
        (work / file).unlink()  # the replay must stand on the report alone
    replay_code, replayed = cli("replay", "report.json", "--timeout", str(TIMEOUT_SECONDS),
                                cwd=work)
    return {
        "input_file_sha256": report["provenance"]["input_file_sha256"],
        "rewrite_exit_code": code, "outcome": out["result"]["outcome"],
        "theorem": out["result"]["theorem"], "application": report["application"],
        "candidate_exported": report["candidate"] is not None,
        "cost": report["result"]["cost"], "execution": report["provenance"].get("execution"),
        "replay_exit_code": replay_code, "replay": replayed.get("replay"),
        "replayed_outcome": replayed.get("result", {}).get("outcome"),
        "inputs_deleted_before_replay": not any((work / f).exists() for f in INPUTS),
    }


def cli_expectations(row: dict, *, proved: bool, refused_outcome: str = "not_proved") -> dict:
    """The checks every CLI-qualified case shares, by name."""
    return {
        "rewrite exit code": row["rewrite_exit_code"] == (0 if proved else 2),
        "outcome": row["outcome"] == ("equivalent" if proved else refused_outcome),
        "candidate only when proved": row["candidate_exported"] == proved,
        "application": row["application"] == ("applied" if proved else "not_proved"),
        "isolated execution": (row["execution"] or {}).get("status") == "completed",
        "replay after deleting inputs": (row["inputs_deleted_before_replay"]
                                         and row["replay_exit_code"] == row["rewrite_exit_code"]
                                         and row["replayed_outcome"] == row["outcome"]
                                         and (row["replay"] or {}).get("reverified") is True),
    }


def require(name: str, expectations: dict) -> None:
    failed = [check for check, ok in expectations.items() if not ok]
    if failed:
        raise AssertionError(f"{name}: " + ", ".join(failed))
