"""Development-only, stdlib-only audit of concrete SymQ graph snapshots.

This is NOT a certified implementation and is never imported by the SymQ
runtime. It exposes a narrow, inspectable representation for later refinement
against the already proved typed acyclic Lean DAG semantics.
"""
from __future__ import annotations

import hashlib
import json


class InvalidGraphSnapshot(ValueError):
    """The supplied Python graph violates the restricted formal input contract."""


def _number(value, label):
    if type(value) is not int:
        raise InvalidGraphSnapshot(f"{label} must be a plain integer")
    return value


def validate_graph_shape(nodes, variables, unique, root, *, max_nodes=100000):
    """Return a canonical graph/CNF document only for exact well-formed inputs.

    The independent checks deliberately reject unsupported node kinds, forward
    or zero references, reused source names, stale caches, malformed physical
    constant conventions and noncanonical signed XOR child records. In a future
    certified route, this snapshot should be reconstructed by a typed parser,
    rather than trusted merely because a Python function returned it.
    """
    if type(max_nodes) is not int or max_nodes < 2:
        raise ValueError("positive max_nodes required")
    if type(nodes) is not list or not 2 <= len(nodes) <= max_nodes + 1:
        raise InvalidGraphSnapshot("graph node list missing or over limit")
    if nodes[0] is not None or nodes[1] != ("one",) or type(nodes[1]) is not tuple:
        raise InvalidGraphSnapshot("node 1 must be the unique true constant")
    if type(variables) is not dict or type(unique) is not dict:
        raise InvalidGraphSnapshot("physical input mapping and node cache required")

    seen_inputs, seen_nodes, records = {}, {}, []
    clauses = [[1]]
    for physical, key in enumerate(nodes[2:], start=2):
        if type(key) is not tuple or not key:
            raise InvalidGraphSnapshot(f"malformed node at {physical}")
        if key[0] == "var":
            if len(key) != 2:
                raise InvalidGraphSnapshot("input record arity")
            source = _number(key[1], "source index")
            if source < 0 or source in seen_inputs:
                raise InvalidGraphSnapshot("duplicate/negative logical source index")
            seen_inputs[source] = physical
            records.append(["input", physical, source])
        elif key[0] in ("and", "xor"):
            if len(key) != 3:
                raise InvalidGraphSnapshot("gate record arity")
            a, b = _number(key[1], "left edge"), _number(key[2], "right edge")
            if not a or not b or abs(a) >= physical or abs(b) >= physical:
                raise InvalidGraphSnapshot("zero, forward or self-referential gate edge")
            if a > b:
                raise InvalidGraphSnapshot("noncanonical gate input order")
            if key[0] == "xor" and (a < 0 or b < 0):
                raise InvalidGraphSnapshot("XOR sign must be carried by the node reference")
            if key[0] == "and":
                clauses.extend([[-physical, a], [-physical, b], [physical, -a, -b]])
            else:
                clauses.extend([[-a, -b, -physical], [a, b, -physical],
                                [a, -b, physical], [-a, b, physical]])
            records.append([key[0], physical, a, b])
        else:
            raise InvalidGraphSnapshot("unknown graph gate grammar")
        if key in seen_nodes:
            raise InvalidGraphSnapshot("node key repeated outside canonical unique table")
        seen_nodes[key] = physical
    if variables != seen_inputs or unique != seen_nodes:
        raise InvalidGraphSnapshot("input map or canonical hash-cons cache disagrees")
    signed_root = _number(root, "root edge")
    if not signed_root or abs(signed_root) >= len(nodes):
        raise InvalidGraphSnapshot("root is zero or outside graph")
    # A SAT assumption is a different API field from the registered clauses.
    document = {
        "schema": "symq-formal-graph-v1",
        "constant": 1,
        "nodes": records,
        "inputs": [[k, v] for k, v in sorted(seen_inputs.items())],
        "clauses": clauses,
        "assumption": signed_root,
    }
    payload = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return document, hashlib.sha256(payload.encode("ascii")).hexdigest()


def evaluate_snapshot(document, assignment):
    """Independent scalar semantics for a previously checked graph document."""
    if type(assignment) is not int or assignment < 0:
        raise ValueError("nonnegative integer source assignment required")
    values = {1: True}
    for node in document["nodes"]:
        kind, physical = node[:2]
        if kind == "input":
            values[physical] = bool((assignment >> node[2]) & 1)
        else:
            a, b = node[2:]
            x = values[abs(a)] if a > 0 else not values[abs(a)]
            y = values[abs(b)] if b > 0 else not values[abs(b)]
            values[physical] = x and y if kind == "and" else x != y
    root = document["assumption"]
    return values[abs(root)] if root > 0 else not values[abs(root)]
