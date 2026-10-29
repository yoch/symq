"""Versioned, immutable contracts for opt-in experimental theorems."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

THEOREMS = frozenset({"full_channel", "reduced_channel", "instrument"})
BACKENDS = frozenset({"zdd", "zdd-native", "zdd-native-wide", "zdd-native-blocks", "hybrid-exact"})


@dataclass(frozen=True)
class VerificationContract:
    theorem: str = "full_channel"
    backend: str = "zdd"
    domain: Any = None
    left_outputs: tuple[int, ...] | None = None
    right_outputs: tuple[int, ...] | None = None
    observed_slots: tuple[str, ...] = ()
    schema_version: int = 1

    def __post_init__(self):
        from .domains import AffineDomain, FullCube, PredicateDomain, PreparedDomain
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError("only experimental contract schema_version 1 is supported")
        if self.theorem not in THEOREMS:
            raise ValueError(f"unknown experimental theorem {self.theorem!r}")
        if self.backend not in BACKENDS:
            raise ValueError(f"unknown experimental backend {self.backend!r}")
        if self.domain is not None and not isinstance(
                self.domain, (FullCube, AffineDomain, PreparedDomain, PredicateDomain)):
            raise TypeError("a closed experimental domain is required")
        for value in (self.left_outputs, self.right_outputs):
            if value is not None and (type(value) is not tuple or
                    any(type(q) is not int or q < 0 for q in value) or len(set(value)) != len(value)):
                raise ValueError("output mappings must be injective tuples of nonnegative wires")
        if self.theorem == "reduced_channel" and (
                self.left_outputs is None or self.right_outputs is None):
            raise ValueError("reduced_channel requires both explicit output mappings")
        if self.theorem != "reduced_channel" and (
                self.left_outputs is not None or self.right_outputs is not None):
            raise ValueError("output mappings are accepted only for reduced_channel")
        if (type(self.observed_slots) is not tuple or
                any(type(s) is not str or not s for s in self.observed_slots) or
                len(set(self.observed_slots)) != len(self.observed_slots)):
            raise ValueError("observed_slots must be an immutable tuple of distinct slot names")
        if self.theorem == "instrument" and not self.observed_slots:
            raise ValueError("instrument requires explicit nonempty observed_slots")
        if self.theorem != "instrument" and self.observed_slots:
            raise ValueError("classical observations require the instrument theorem")

    def to_dict(self):
        return {"schema_version": self.schema_version, "theorem": self.theorem,
                "backend": self.backend,
                "domain": None if self.domain is None else self.domain.to_dict(),
                "left_outputs": None if self.left_outputs is None else list(self.left_outputs),
                "right_outputs": None if self.right_outputs is None else list(self.right_outputs),
                "observed_slots": list(self.observed_slots)}

    @property
    def sha256(self):
        return hashlib.sha256(json.dumps(self.to_dict(), sort_keys=True,
                              separators=(",", ":")).encode()).hexdigest()

    @classmethod
    def from_dict(cls, value):
        from .domains import domain_from_dict
        allowed = {"schema_version", "theorem", "backend", "domain", "left_outputs",
                   "right_outputs", "observed_slots"}
        if type(value) is not dict or set(value) - allowed:
            raise ValueError("unknown or malformed experimental contract fields")
        if value.get("schema_version") != 1:
            raise ValueError("experimental contract schema_version 1 is required")
        fields = dict(value)
        for name in ("left_outputs", "right_outputs", "observed_slots"):
            if name in fields and fields[name] is not None:
                if type(fields[name]) is not list:
                    raise ValueError(f"{name} must be a JSON array")
                fields[name] = tuple(fields[name])
        if fields.get("domain") is not None:
            fields["domain"] = domain_from_dict(fields["domain"])
        return cls(**fields)


@dataclass(frozen=True)
class VerificationResult:
    outcome: str
    theorem: str
    backend: str
    reason: str
    left_sha256: str
    right_sha256: str
    contract_sha256: str
    witness_kind: str | None = None
    witness: tuple[int, int] | None = None
    witness_checked: bool = False
    statistics: tuple[tuple[str, int | float], ...] = ()
    schema_version: int = 1
    proof_kind: str = "engine_decision"
    coefficient_reductions: tuple[Any, ...] = ()

    @property
    def equivalent(self):
        return self.outcome == "equivalent"

    @property
    def certified(self):
        """A decisive exact computation, not an independent proof certificate."""
        return self.equivalent

    def to_dict(self):
        from dataclasses import asdict
        return asdict(self)
