"""Small robustness guarantees: atomic outputs and one-shot iterables."""
from __future__ import annotations

import pytest

from symq._io import atomic_write_text


def test_atomic_write_replaces_completely(tmp_path):
    target = tmp_path / "receipt.json"
    atomic_write_text(target, "first\n")
    atomic_write_text(target, "second\n")
    assert target.read_text() == "second\n"
    assert [p.name for p in tmp_path.iterdir()] == ["receipt.json"]


def test_an_interrupted_write_leaves_the_previous_file(tmp_path, monkeypatch):
    import os

    target = tmp_path / "receipt.json"
    atomic_write_text(target, "kept\n")

    def fail(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError, match="disk full"):
        atomic_write_text(target, "lost\n")
    assert target.read_text() == "kept\n"
    assert [p.name for p in tmp_path.iterdir()] == ["receipt.json"]


def test_reachable_union_accepts_a_generator():
    from symq import Circuit, make_algebra, simulate

    algebra = make_algebra("zdd", 3)
    outputs = simulate(Circuit(3).ccx(0, 1, 2), algebra)
    from_list = algebra.reachable_union(list(outputs))
    from_generator = algebra.reachable_union(value for value in outputs)
    assert from_generator == from_list and from_list["roots"] == 3
