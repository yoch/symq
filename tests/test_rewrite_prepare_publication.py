"""Audit #171: write_prepared_rewrite must never replace anything, even under a race.

Deterministic regressions: the competing entry is created *inside* the publication
step (by wrapping the primitive the function uses), not by timing.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys

import pytest

from symq.circuit import Circuit
from symq.labs import rewrite_prepare as rp
from symq.labs.contextual_substitution import SubstitutionContract
from symq.labs.rewrite_request import load_request_files, request_to_dict

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
    planted = []   # plant once: pathlib.mkdir itself calls os.mkdir on Python >= 3.11

    def plant_once(path):
        if os.fspath(path) == os.fspath(root) and not planted:
            planted.append(True)
            _plant(kind, root, tmp_path)

    def racing_mkdir(path, *args, **kwargs):
        plant_once(path)
        return real_mkdir(path, *args, **kwargs)

    def racing_rename(src, dst, *args, **kwargs):   # the pre-fix publication primitive
        plant_once(dst)
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


# --- Intermediate states (audit #171, finalization): the marker is advisory. ---
# Publication is no-replace, not atomic visibility. Every state a crash or a
# concurrent reader can observe is a prefix of PUBLICATION_ORDER, the last
# file possibly truncated. The proof loader must refuse it or read exactly the
# complete inputs; it must never prove anything else.


def _final(tmp_path):
    root = tmp_path / "final"
    rp.write_prepared_rewrite(_prepared(), root)
    return {name: (root / name).read_bytes() for name in rp.PUBLICATION_ORDER}


def _cuts(blob):
    return sorted({0, 1, len(blob) // 3, len(blob) // 2, len(blob) - 2, len(blob) - 1})


def _states(final):
    """(label, {name: bytes}) for every complete prefix and truncated next file."""
    order = rp.PUBLICATION_ORDER
    for done in range(len(order) + 1):
        complete = {name: final[name] for name in order[:done]}
        yield f"{done}-complete", complete
        if done < len(order):
            name = order[done]
            for cut in _cuts(final[name]):
                yield f"{done}-complete+{name}[:{cut}]", {**complete, name: final[name][:cut]}


def test_publication_order_puts_the_request_after_its_inputs():
    order = rp.PUBLICATION_ORDER
    assert order.index("request.json") > max(order.index("source.json"), order.index("replacement.json"))
    assert order[-1] == "preparation.json"


def test_every_intermediate_state_is_refused_or_reads_the_complete_inputs(tmp_path):
    final = _final(tmp_path)
    expected = {key: hashlib.sha256(final[f"{key}.json"]).hexdigest()
                for key in ("source", "replacement")}
    reference, _digests, _paths = load_request_files(tmp_path / "final" / "request.json")
    loaded = refused = 0
    for index, (label, files) in enumerate(_states(final)):
        state = tmp_path / f"state{index}"
        state.mkdir()
        for name, blob in files.items():
            (state / name).write_bytes(blob)
        try:
            _request, digests, _paths = load_request_files(state / "request.json")
        except (ValueError, OSError):
            refused += 1
            continue
        loaded += 1
        # Only complete proof inputs may load. The single exception is a request.json
        # missing just its trailing newline: the very same JSON document.
        request_bytes = files["request.json"]
        assert request_bytes == final["request.json"] or final["request.json"] == request_bytes + b"\n", label
        assert {k: digests[k] for k in expected} == expected, label
        assert request_to_dict(_request) == request_to_dict(reference), label
    assert loaded and refused


def _cli(*args, cwd):
    run = subprocess.run([sys.executable, "-m", "symq", *args], cwd=cwd,
                         capture_output=True, text=True, check=False, timeout=120)
    return run.returncode, json.loads(run.stdout)


@pytest.mark.sat
def test_cli_on_states_without_marker(tmp_path):
    final = _final(tmp_path)
    # Crash before request.json: no entry point, refused as invalid input.
    early = tmp_path / "early"
    early.mkdir()
    for name in ("source.json", "replacement.json"):
        (early / name).write_bytes(final[name])
    code, out = _cli("rewrite", "request.json", cwd=early)
    assert code == 3 and out["result"]["outcome"] == "invalid" and out["application"] != "applied"
    # Truncated request.json: refused.
    torn = tmp_path / "torn"
    torn.mkdir()
    for name in ("source.json", "replacement.json"):
        (torn / name).write_bytes(final[name])
    (torn / "request.json").write_bytes(final["request.json"][:-5])
    code, out = _cli("rewrite", "request.json", cwd=torn)
    assert code == 3 and out["result"]["outcome"] == "invalid"
    # All proof inputs complete but no marker yet: the proof is the same as on the
    # finished directory, because it is computed from those very bytes.
    late = tmp_path / "late"
    late.mkdir()
    for name in ("source.json", "replacement.json", "request.json"):
        (late / name).write_bytes(final[name])
    done = tmp_path / "done"
    done.mkdir()
    for name, blob in final.items():
        (done / name).write_bytes(blob)
    code_late, out_late = _cli("rewrite", "request.json", cwd=late)
    code_done, out_done = _cli("rewrite", "request.json", cwd=done)
    assert code_late == code_done == 0
    assert out_late["result"] == out_done["result"] and out_late["application"] == "applied"


def test_preparation_never_authorizes_and_records_the_emitted_hashes(tmp_path):
    root = tmp_path / "out"
    record = rp.write_prepared_rewrite(_prepared(), root)
    marker = json.loads((root / "preparation.json").read_text())
    assert marker["status"] == "ready_for_proof" and marker["proved"] is False
    assert marker["candidate_authorized"] is False and marker["proof_status"] == "unproved"
    for name, digest in marker["files"].items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest
    assert record["files"] == marker["files"]


def test_input_symlink_leaving_the_directory_is_refused(tmp_path):
    final = _final(tmp_path)
    outside = tmp_path / "outside.json"
    outside.write_bytes(final["source.json"])
    state = tmp_path / "linked"
    state.mkdir()
    for name in ("replacement.json", "request.json"):
        (state / name).write_bytes(final[name])
    (state / "source.json").symlink_to(outside)
    with pytest.raises(ValueError, match="inside the request directory"):
        load_request_files(state / "request.json")
