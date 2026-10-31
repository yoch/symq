"""Deprecated location: this module moved to ``symq.labs.qasm3``.

Importing it still works and returns the same module object, with a ``DeprecationWarning``.
"""
import sys
import warnings

from symq.labs import qasm3 as _module

warnings.warn("symq.experimental.qasm3 moved to symq.labs.qasm3", DeprecationWarning, stacklevel=2)
sys.modules[__name__] = _module
