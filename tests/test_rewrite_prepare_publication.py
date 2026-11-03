"""Audit #171: write_prepared_rewrite must never replace anything, even under a race.

Deterministic regressions: the competing entry is created *inside* the publication
step (by wrapping the primitive the function uses), not by timing.
"""
from __future__ import annotations

import os

import pytest

from symq.circuit import Circuit
from symq.labs import rewrite_prepare as rp
from symq.labs.contextual_substitution import SubstitutionContract

FILES = {"source.json", "replacement.json", "request.json", "preparation.json"}


def _prepared():
    source = Circuit(4).x(3).ccx(0, 1, 2).cx(2, 3)
    local = Circuit(3).ccx(0, 1, 2)
    prepared = rp.prepare_local_classical(source, local, Circuit(3).ccx(1, 0, 2),
                                          contract=SubstitutionContract())
    assert prepared.ready
    return prepared


def _tmp_leftovers(parent):
    return [p for p in parent.iterdir() if p.name.startswith(".symq-prepare-")]


def _plant(kind, path, tmp_path):
    if kind == "empty_dir":
        path.mkdir()
    elif kind == "nonempty_dir":
        path.mkdir()
        (path / "victim.txt").write_text("keep")
    elif kind == "symlink_dir":
        target = tmp_path / "elsewhere"
        target.mkdir(exist_ok=True)
        path.symlink_to(target)
    elif kind == "dangling_symlink":
        path.symlink_to(tmp_path / "missing-target")
    elif kind == "file":
        path.write_text("keep")


def _intact(kind, path, tmp_path):
    if kind == "empty_dir":
        return path.is_dir() and not any(path.iterdir())
    if kind == "nonempty_dir":
        return sorted(p.name for p in path.iterdir()) == ["victim.txt"]
    if kind in ("symlink_dir", "dangling_symlink"):
        return path.is_symlink() and (kind == "dangling_symlink" or not any(path.iterdir()))
    return path.read_text() == "keep"


KINDS = ["empty_dir", "nonempty_dir", "symlink_dir", "dangling_symlink", "file"]


@pytest.mark.parametrize("kind", KINDS)
def test_preexisting_destination_is_refused_untouched(tmp_path, kind):
    root = tmp_path / "out"
    _plant(kind, root, tmp_path)
    with pytest.raises(FileExistsError):
        rp.write_prepared_rewrite(_prepared(), root)
    assert _intact(kind, root, tmp_path)
    assert not _tmp_leftovers(tmp_path)


@pytest.mark.parametrize("kind", KINDS)
def test_concurrent_creation_at_publication_is_refused_untouched(tmp_path, monkeypatch, kind):
    """Before the fix, a concurrent EMPTY directory was silently replaced (os.rename)."""
    root = tmp_path / "out"
    real_mkdir, real_rename = os.mkdir, os.rename

    def racing_mkdir(path, *args, **kwargs):
        if os.fspath(path) == os.fspath(root):
            _plant(kind, root, tmp_path)
        return real_mkdir(path, *args, **kwargs)

    def racing_rename(src, dst, *args, **kwargs):   # the pre-fix publication primitive
        if os.fspath(dst) == os.fspath(root):
            _plant(kind, root, tmp_path)
        return real_rename(src, dst, *args, **kwargs)

    monkeypatch.setattr(rp.os, "mkdir", racing_mkdir)
    monkeypatch.setattr(rp.os, "rename", racing_rename)
    with pytest.raises(FileExistsError):
        rp.write_prepared_rewrite(_prepared(), root)
    assert _intact(kind, root, tmp_path)
    assert not _tmp_leftovers(tmp_path)


def test_two_writers_racing_one_wins_completely(tmp_path, monkeypatch):
    root = tmp_path / "out"
    real_mkdir = os.mkdir
    state = {"inner": False}

    def racing_mkdir(path, *args, **kwargs):
        if os.fspath(path) == os.fspath(root) and not state["inner"]:
            state["inner"] = True
            rp.write_prepared_rewrite(_prepared(), root)   # the competing writer finishes first
        return real_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(rp.os, "mkdir", racing_mkdir)
    with pytest.raises(FileExistsError):
        rp.write_prepared_rewrite(_prepared(), root)
    assert {p.name for p in root.iterdir()} == FILES
    assert not _tmp_leftovers(tmp_path)


def test_failure_after_claim_removes_only_own_files_and_marker_is_last(tmp_path, monkeypatch):
    root = tmp_path / "out"
    order = []
    real_fsync = os.fsync

    def failing_fsync(fd):
        if not root.exists():          # serialization in the temporary directory
            return real_fsync(fd)
        order.append(len(order))
        if len(order) == 3:
            (root / "foreign.txt").write_text("not ours")
            raise OSError("disk full")
        return real_fsync(fd)

    monkeypatch.setattr(rp.os, "fsync", failing_fsync)
    with pytest.raises(OSError, match="disk full"):
        rp.write_prepared_rewrite(_prepared(), root)
    # Our partial files are gone; the foreign file and therefore the directory remain.
    assert sorted(p.name for p in root.iterdir()) == ["foreign.txt"]
    assert not _tmp_leftovers(tmp_path)


def test_failure_after_claim_without_foreign_content_removes_directory(tmp_path, monkeypatch):
    root = tmp_path / "out"
    real_fsync = os.fsync

    def failing_fsync(fd):
        if root.exists():
            raise OSError("io")
        return real_fsync(fd)

    monkeypatch.setattr(rp.os, "fsync", failing_fsync)
    with pytest.raises(OSError):
        rp.write_prepared_rewrite(_prepared(), root)
    assert not root.exists() and not _tmp_leftovers(tmp_path)


def test_completeness_marker_is_written_last(tmp_path, monkeypatch):
    root = tmp_path / "out"
    written = []
    real_open = open

    def recording_open(path, mode="r", *args, **kwargs):
        if mode == "xb":
            written.append(os.path.basename(path))
        return real_open(path, mode, *args, **kwargs)

    monkeypatch.setattr("builtins.open", recording_open)
    rp.write_prepared_rewrite(_prepared(), root)
    assert written[-1] == "preparation.json" and set(written) == FILES
