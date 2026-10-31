"""Deprecated location: this module moved to ``symq.labs.cyclotomic``.

Importing it still works and returns the same module object, with a ``DeprecationWarning``.
"""
import sys
import warnings

from symq.labs import cyclotomic as _module

warnings.warn("symq.experimental.cyclotomic moved to symq.labs.cyclotomic", DeprecationWarning, stacklevel=2)
sys.modules[__name__] = _module
