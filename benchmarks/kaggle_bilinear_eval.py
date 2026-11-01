"""Source-pinned Kaggle public *open-set* bilinear KMB qualification.

Original benchmark and circuit bytes: James Barlow (Apache-2.0),
https://www.kaggle.com/datasets/manwithacat/vqcc-bilinear-agent-evaluation
The independently implemented tower-factor construction follows the
mathematical approach in Polytof, ZIB-IOL/polytof (MIT), commit
0dcac107d15adc34dc646242d222f21ae7d32699.

This is not an agent discovery/generalization benchmark, an official Kaggle
submission, or a proof of optimality outside the bilinear CCX model.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import platform
import struct
import sys
import zlib
from pathlib import Path

from benchmarks.kaggle_bilinear_kmb import encode, parse, pivot_fanout, simulate
from benchmarks.kaggle_bilinear_towers import build_terms

DATA_DIR = Path(__file__).with_name("corpus") / "kaggle_bilinear"
MANIFEST_SHA256 = "2f48cb3f16f3f6466b394eaa6524d92a19b171a2e25605fd01257ae763f35c85"
PACKED_SHA256 = "8adef29e5e875723e14969cd62114156dcdc4dd3332ee4dc6db7ea6a821694ad"
ARCHIVE_SHA256 = "635f4e9117c012adcf4038e29403373fe2aaf3ef2782e89e796ce1ac96e821dc"
DATASET_URL = "https://www.kaggle.com/datasets/manwithacat/vqcc-bilinear-agent-evaluation"
PACKED_UNCOMPRESSED_BYTES = 26038


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def manifest() -> list[dict]:
    raw = (DATA_DIR / "manifest.json").read_bytes()
    if digest(raw) != MANIFEST_SHA256:
        raise ValueError("upstream dataset manifest SHA-256 mismatch")
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
    chars = "".join((DATA_DIR / "starts.zlib.b64").read_text("ascii").split())
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


def independent_product(a: int, b: int, n: int, modulus: int) -> int:
    """Polynomial convolution and long division, independent of tower model."""
    coeff = 0
    for i in range(n):
        for j in range(n):
            if ((a >> i) & (b >> j) & 1):
                coeff ^= 1 << (i + j)
    for degree in range(2 * n - 2, n - 1, -1):
        if (coeff >> degree) & 1:
            coeff ^= modulus << (degree - n)
    return coeff


def verify_tensor(n: int, modulus: int, terms: list[tuple[int, int, int]]) -> None:
    for i in range(n):
        for j in range(n):
            got = 0
            for am, bm, out in terms:
                if (am >> i) & (bm >> j) & 1:
                    got ^= out
            expected = independent_product(1 << i, 1 << j, n, modulus)
            if got != expected:
                raise ValueError(f"GF({1 << n}) tensor mismatch: basis ({i},{j})")


def candidate(n: int, modulus: int) -> tuple[bytes, list[tuple[int, int, int]]]:
    if (n, modulus) not in ((4, 0x13), (6, 0x49)):
        raise ValueError("no certified candidate for this field representation")
    terms, _generator = build_terms(n, modulus)
    verify_tensor(n, modulus, terms)
    ops = pivot_fanout(n, terms)
    raw = encode(ops, n)
    width, parsed = parse(raw)
    if width != 3 * n or parsed != ops:
        raise ValueError("candidate KMB byte round-trip mismatch")
    if sum(op[0] == 49 for op in ops) != (9 if n == 4 else 15):
        raise ValueError("unexpected bilinear CCX target")
    return raw, terms


def run(*, candidate_dir: Path | None = None, check_all_basis: bool = True) -> dict:
    rows = manifest()
    original = source_starts()
    models = {(n, mod): candidate(n, mod) for n, mod in ((4, 19), (6, 73))}
    report = []
    for row in rows:
        n, mod = row["width"], row["modulus"]
        source = original[row["kmb"]]
        width, original_ops = parse(source)
        raw, _terms = models[(n, mod)]
        width2, candidate_ops = parse(raw)
        if width != 3 * n or width2 != width:
            raise ValueError("source and candidate have different register layouts")
        before = sum(op[0] == 49 for op in original_ops)
        after = sum(op[0] == 49 for op in candidate_ops)
        if before != row["start_ccx"] or after != row["proven_bilinear_target"]:
            raise ValueError("incorrect original/candidate gate counts")
        if check_all_basis:
            # Every possible operand pair, with two different (possibly dirty)
            # output words. Coupled with a separate full-state candidate test.
            for a in range(1 << n):
                for b in range(1 << n):
                    product = independent_product(a, b, n, mod)
                    for t in (0, (1 << n) - 1):
                        x = a | (b << n) | (t << (2 * n))
                        expect = a | (b << n) | ((t ^ product) << (2 * n))
                        if simulate(original_ops, x) != expect:
                            raise ValueError(f"original circuit invalid: {row['id']}")
                        if simulate(candidate_ops, x) != expect:
                            raise ValueError(f"candidate circuit invalid: {row['id']}")
        output_file = row["id"] + ".kmb"
        if candidate_dir is not None:
            candidate_dir.mkdir(parents=True, exist_ok=True)
            (candidate_dir / output_file).write_bytes(raw)
        report.append({
            "id": row["id"], "modulus": mod, "width": n,
            "source_sha256": digest(source), "candidate_sha256": digest(raw),
            "source_ccx": before, "candidate_ccx": after,
            "source_cx": sum(op[0] == 33 for op in original_ops),
            "candidate_cx": sum(op[0] == 33 for op in candidate_ops),
            "saved_ccx": before - after, "target_reached": before > after,
            "candidate_file": output_file, "mode": "exact_bilinear_dirty_target",
        })
    if not all(row["target_reached"] for row in report):
        raise ValueError("at least one source was not improved")
    return {
        "schema": "symq-public-kaggle-bilinear-v1", "dataset_url": DATASET_URL,
        "source_author": "James Barlow", "license": "Apache-2.0 (declared in dataset README)",
        "archive_sha256": ARCHIVE_SHA256, "manifest_sha256": MANIFEST_SHA256,
        "field_models": [
            {"n": n, "modulus": mod, "candidate_sha256": digest(models[(n, mod)][0]),
             "rank": len(models[(n, mod)][1])} for n, mod in ((4, 19), (6, 73))
        ],
        "open_set_not_holdout": True, "known_optimum_not_agent_discovery": True,
        "not_official_competition_score": True,
        "case_count": len(report), "target_reached_count": sum(x["target_reached"] for x in report),
        "ccx_before": sum(x["source_ccx"] for x in report),
        "ccx_after": sum(x["candidate_ccx"] for x in report),
        "cases": report,
        "environment": {"python": sys.version.split()[0], "platform": platform.platform()},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--candidate-dir", type=Path)
    args = parser.parse_args()
    result = run(candidate_dir=args.candidate_dir)
    payload = (json.dumps(result, indent=2, sort_keys=True) + "\n").encode("utf-8")
    args.output.write_bytes(payload)
    args.output.with_name(args.output.name + ".sha256").write_text(digest(payload) + "\n")
    print(f"{result['target_reached_count']}/{result['case_count']} target reaches; "
          f"CCX {result['ccx_before']} -> {result['ccx_after']}")


if __name__ == "__main__":
    main()
