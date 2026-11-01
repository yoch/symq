"""Deprecated location: this module moved to ``symq.labs.proof_graph``.

Importing it still works and returns the same module object, with a ``DeprecationWarning``.
"""
import sys
import warnings

from symq.labs import proof_graph as _module

warnings.warn("symq.experimental.proof_graph moved to symq.labs.proof_graph", DeprecationWarning, stacklevel=2)
sys.modules[__name__] = _module
