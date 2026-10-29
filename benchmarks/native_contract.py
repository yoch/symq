"""Reject stale/incompatible benchmark binaries; receipts are provenance, not proofs."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

EXPECTED_ABI = 5
ROOT = Path(__file__).resolve().parents[1]


def native_provenance(*, root=ROOT, module=None):
    if module is None:
        from symq.backends import _zdd as module
    if getattr(module, "ABI_VERSION", None) != EXPECTED_ABI:
        raise RuntimeError(f"incompatible native ABI; this harness requires ABI {EXPECTED_ABI}")
    directory = Path(root) / "src" / "symq" / "backends"
    binary = Path(module.__file__).resolve()
    if binary.parent != directory.resolve():
        raise RuntimeError("native extension was imported from a different source snapshot")
    try:
        receipt = json.loads(Path(str(binary) + ".build.json").read_text())
        source_hash = hashlib.sha256((directory / "_zdd.c").read_bytes()).hexdigest()
        binary_hash = hashlib.sha256(binary.read_bytes()).hexdigest()
        if (receipt["schema"] != "symq/native-build/v1"
                or receipt["source_sha256"] != source_hash
                or receipt["binary_sha256"] != binary_hash):
            raise ValueError("source/binary fingerprint mismatch")
    except (OSError, ValueError, KeyError) as error:
        raise RuntimeError("native build provenance mismatch; rebuild with "
                           "'python tools/build_native.py --require'") from error
    return {**receipt, "abi": EXPECTED_ABI,
            "module": str(binary.relative_to(Path(root).resolve()))}


def unpack_simulation(result, width):
    if type(result) is not tuple or len(result) != 3:
        raise RuntimeError("native result does not match this harness: expected ABI-5 tuple")
    roots, peak, products = result
    if (type(roots) is not list or len(roots) != width
            or any(type(root) is not int or root < 0 for root in roots)
            or (peak is not None and (type(peak) is not int or peak < 0))
            or type(products) is not int or products < 0):
        raise RuntimeError("native result does not match this harness: invalid roots or counters")
    return roots, peak, products
