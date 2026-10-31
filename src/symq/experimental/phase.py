"""Deprecated location: this module moved to ``symq.labs.dyadic_phase``.

Importing it still works and returns the same module object, with a ``DeprecationWarning``.
"""
import sys
import warnings

from symq.labs import dyadic_phase as _module

warnings.warn("symq.experimental.phase moved to symq.labs.dyadic_phase", DeprecationWarning, stacklevel=2)
sys.modules[__name__] = _module
