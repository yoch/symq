"""Deprecated location: this module moved to ``symq.labs.rename``.

Importing it still works and returns the same module object, with a ``DeprecationWarning``.
"""
import sys
import warnings

from symq.labs import rename as _module

warnings.warn("symq.experimental.rename moved to symq.labs.rename", DeprecationWarning, stacklevel=2)
sys.modules[__name__] = _module
