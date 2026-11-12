"""The public bilinear KMB corpus: provenance checks and exact tower-multiplier rewrites.

The 14 GF(16)/GF(64) multiplier circuits of the Apache-2.0 dataset
``manwithacat/vqcc-bilinear-agent-evaluation`` (James Barlow, 2026; see
``corpus/bilinear_kmb/SOURCE.md``) are decoded and each is proved equal, on every input, to
SymQ's certified tower multiplier in the dataset's polynomial basis, with the total theorem of
``symq.labs.contextual_substitution`` and the exact packed degree-two engine. The proof compares
the two circuits directly, so it does not depend on the tower construction being right.

The corpus is public and its 9/15-Toffoli targets are known: this is a constructive baseline,
not a holdout, not an agent benchmark and not a competition score.

    python -m benchmarks.bilinear_kmb --output report.json [--candidates DIR]
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import struct
import zlib
from pathlib import Path

from benchmarks.environment import machine, receipt
from benchmarks.kmb import decode, encode
from symq.experimental.serialization import save_json
from symq.generators.gf2n import tower_multiplier
from symq.labs.contextual_substitution import SubstitutionContract, check_substitution

DATA_DIR = Path(__file__).with_name("corpus") / "bilinear_kmb"
MANIFEST_SHA256 = "2f48cb3f16f3f6466b394eaa6524d92a19b171a2e25605fd01257ae763f35c85"
PACKED_SHA256 = "8adef29e5e875723e14969cd62114156dcdc4dd3332ee4dc6db7ea6a821694ad"
DATASET_URL = "https://www.kaggle.com/datasets/manwithacat/vqcc-bilinear-agent-evaluation"
PACKED_UNCOMPRESSED_BYTES = 26038


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _corpus_file(name: str) -> Path:
    """A file of the corpus, or a clear error where the corpus is not shipped."""
    path = DATA_DIR / name
    if not path.is_file():
        raise FileNotFoundError(
            f"{path} is missing: the bilinear KMB corpus is kept in the SymQ repository and "
            "left out of the source distribution. Run this from a checkout of "
            "https://github.com/yoch/symq")
    return path


def manifest() -> list[dict]:
    raw = _corpus_file("manifest.json").read_bytes()
    if digest(raw) != MANIFEST_SHA256:
        raise ValueError("corpus manifest SHA-256 mismatch")
    source = json.loads(raw)
    rows = source["instances"]
    if source["schema"] != "bilinear-challenge-v1" or len(rows) != 14:
        raise ValueError("unexpected source dataset schema")
    if len({row["id"] for row in rows}) != 14:
        raise ValueError("duplicate dataset instance")
    return rows


def source_starts() -> dict[str, bytes]:
    """Inflate the 14 *byte-identical* Apache-2.0 public KMB originals.

    The pack is length-prefixed (uint16 name length, UTF-8 name, uint32 byte
    length, exact original bytes). Only this public dataset is mirrored.
    """
    chars = "".join(_corpus_file("starts.zlib.b64").read_text("ascii").split())
    compressed = base64.b64decode(chars, validate=True)
    if digest(compressed) != PACKED_SHA256:
        raise ValueError("source corpus compressed payload SHA-256 mismatch")
    decompressor = zlib.decompressobj()
    raw = decompressor.decompress(compressed, PACKED_UNCOMPRESSED_BYTES + 1)
    raw += decompressor.flush()
    if (not decompressor.eof or decompressor.unused_data
            or len(raw) != PACKED_UNCOMPRESSED_BYTES):
        raise ValueError("bad source corpus archive boundaries")
    result: dict[str, bytes] = {}
    offset = 0
    for _ in range(14):
        if offset + 2 > len(raw):
            raise ValueError("truncated packed fixture")
        name_size = struct.unpack_from("<H", raw, offset)[0]
        offset += 2
        if name_size > 128 or offset + name_size + 4 > len(raw):
            raise ValueError("invalid packed fixture name")
        name = raw[offset:offset + name_size].decode("ascii")
        offset += name_size
        length = struct.unpack_from("<I", raw, offset)[0]
        offset += 4
        if length > 100_000 or offset + length > len(raw) or name in result:
            raise ValueError("invalid packed fixture length or duplicate")
        result[name] = raw[offset:offset + length]
        offset += length
    if offset != len(raw):
        raise ValueError("trailing public fixture bytes")
    rows = manifest()
    if set(result) != {row["kmb"] for row in rows}:
        raise ValueError("source KMB names mismatch")
    for row in rows:
        if digest(result[row["kmb"]]) != row["sha256"]:
            raise ValueError(f"source KMB SHA-256 mismatch: {row['id']}")
    return result


def rewrite(row: dict, source: bytes) -> dict:
    """Prove the tower multiplier equal to one source file and price both."""
    n, modulus = row["width"], row["modulus"]
    original = decode(source)
    if original.width != 3 * n:
        raise ValueError(f"{row['id']}: width {original.width} is not 3n")
    candidate = tower_multiplier(n, modulus=modulus)
    result = check_substitution(original, (0, len(original.gates)), candidate,
                                contract=SubstitutionContract(), engine="packed")
    if not result.equivalent:
        raise AssertionError(f"{row['id']}: tower multiplier not proved ({result.reason})")
    before, after = dict(result.cost.reference_counts), dict(result.cost.candidate_counts)
    return {"id": row["id"], "n": n, "modulus": modulus, "source_sha256": row["sha256"],
            "outcome": result.outcome, "theorem": result.theorem,
            "source_ccx": before.get("ccx", 0), "source_cx": before.get("cx", 0),
            "candidate_ccx": after.get("ccx", 0), "candidate_cx": after.get("cx", 0),
            "candidate_kmb_sha256": digest(encode(candidate)),
            "known_bilinear_target": row["proven_bilinear_target"]}


def run(candidates: Path | None = None) -> dict:
    starts = source_starts()
    rows = [rewrite(row, starts[row["kmb"]]) for row in manifest()]
    if candidates is not None:
        candidates.mkdir(parents=True, exist_ok=True)
        for row in manifest():
            (candidates / row["kmb"]).write_bytes(
                encode(tower_multiplier(row["width"], modulus=row["modulus"])))
    totals = {key: sum(row[key] for row in rows)
              for key in ("source_ccx", "source_cx", "candidate_ccx", "candidate_cx")}
    return {"schema_version": 1, "kind": "symq_bilinear_kmb",
            "source": {"url": DATASET_URL, "license": "Apache-2.0",
                       "manifest_sha256": MANIFEST_SHA256,
                       "status": "public corpus with known targets, not a holdout"},
            "environment": machine(), "receipt": receipt(), "totals": totals, "cases": rows}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, help="write the JSON report here")
    parser.add_argument("--candidates", type=Path, help="write the candidate KMB files here")
    args = parser.parse_args(argv)
    report = run(args.candidates)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        save_json(report, args.output)
    totals = report["totals"]
    print(f"14 rewrites proved: {totals['source_ccx']} -> {totals['candidate_ccx']} CCX, "
          f"{totals['source_cx']} -> {totals['candidate_cx']} CX")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
