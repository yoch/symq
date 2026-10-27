"""Import the MQT QCEC ``test/circuits/original`` corpus at a pinned commit.

Every file is checked against the Git blob SHA-1 listed in the upstream tree at that commit
before it is written. The DEV/holdout split is the one recorded in the 27 Oct 2026 handoff
(5 circuits used to tune the ``auto_zdd`` threshold, 6 held out); every other circuit of the
directory goes to the ``extension`` split, which must never be used for tuning.

Usage: python benchmarks/import_qcec.py [--commit SHA] [--out benchmarks/corpus/qcec]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from symq import UnsupportedOperation
from symq.corpus import git_blob_sha1, sha256_hex
from symq.qasm import parse_qasm

REPOSITORY = "munich-quantum-toolkit/qcec"
COMMIT = "98d6784176bfeb6ef923d4d0220e8d486dc1982f"
DIRECTORY = "test/circuits/original"
DEV = ("c2_181", "mod5adder_306", "rd73_312", "rd84_313", "sym9_317")
HOLDOUT = ("5xp1_194", "alu1_198", "dk27_225", "cm150a_210", "pcler8_248", "mlp4_245")


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "symq-corpus-import"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def describe(name: str, data: bytes) -> dict:
    text = data.decode("utf-8")
    try:
        circuit = parse_qasm(text)
    except UnsupportedOperation as error:
        width = int(re.search(r"qubit\s*\[(\d+)\]|qreg\s+\w+\[(\d+)\]", text).group(1))
        statements = [s for s in re.sub(r"//[^\n]*", "", text).split(";") if s.strip()]
        return {"status": "unsupported", "reason": str(error), "width": width,
                "gates": len(statements) - 3, "controls_histogram": {}}
    histogram = Counter(len(g.qubits) - 1 for g in circuit.gates)
    return {"status": "supported", "width": circuit.width, "gates": len(circuit.gates),
            "controls_histogram": {str(k): histogram[k] for k in sorted(histogram)}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", default=COMMIT)
    parser.add_argument("--out", type=Path, default=Path(__file__).parent / "corpus" / "qcec")
    args = parser.parse_args()
    tree = json.loads(fetch(
        f"https://api.github.com/repos/{REPOSITORY}/git/trees/{args.commit}?recursive=1"))
    if tree.get("truncated"):
        raise SystemExit("upstream tree listing truncated")
    blobs = {e["path"]: e["sha"] for e in tree["tree"] if e["type"] == "blob"}
    raw = f"https://raw.githubusercontent.com/{REPOSITORY}/{args.commit}/"
    args.out.mkdir(parents=True, exist_ok=True)

    license_data = fetch(raw + "LICENSE")
    if git_blob_sha1(license_data) != blobs["LICENSE"]:
        raise SystemExit("LICENSE does not match upstream blob")
    (args.out / "LICENSE_QCEC.txt").write_bytes(license_data)

    circuits = []
    paths = sorted(p for p in blobs if p.startswith(DIRECTORY + "/") and p.endswith(".qasm"))
    for upstream_path in paths:
        data = fetch(raw + upstream_path)
        if git_blob_sha1(data) != blobs[upstream_path]:
            raise SystemExit(f"{upstream_path} does not match upstream blob")
        file = Path(upstream_path).name
        name = file.removesuffix(".qasm")
        (args.out / file).write_bytes(data)
        split = "dev" if name in DEV else "holdout" if name in HOLDOUT else "extension"
        circuits.append({"name": name, "file": file, "upstream_path": upstream_path,
                         "split": split, "git_blob_sha1": blobs[upstream_path],
                         "sha256": sha256_hex(data), "bytes": len(data), **describe(name, data)})
        print(f"{name:16s} {split:9s} {circuits[-1]['status']}", file=sys.stderr)
    missing = set(DEV + HOLDOUT) - {c["name"] for c in circuits}
    if missing:
        raise SystemExit(f"split circuits missing upstream: {sorted(missing)}")

    manifest = {
        "source": {
            "repository": f"https://github.com/{REPOSITORY}",
            "commit": args.commit,
            "directory": DIRECTORY,
            "license": "MIT",
            "license_file": "LICENSE_QCEC.txt",
            "license_git_blob_sha1": blobs["LICENSE"],
            "retrieved_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        "split_policy": (
            "dev and holdout reproduce the 27 Oct 2026 handoff split (dev tuned the auto_zdd "
            "threshold, holdout is reserved). extension holds the remaining circuits of the "
            "directory and must not be used for tuning. Inputs are fully symbolic (full_input)."
        ),
        "circuits": circuits,
    }
    (args.out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
