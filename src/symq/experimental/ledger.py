"""Deprecated location: this module moved to ``symq.labs.ledger``.

Importing it still works and returns the same module object, with a ``DeprecationWarning``.
"""
import sys
import warnings

from symq.labs import ledger as _module

warnings.warn("symq.experimental.ledger moved to symq.labs.ledger", DeprecationWarning, stacklevel=2)
sys.modules[__name__] = _module
