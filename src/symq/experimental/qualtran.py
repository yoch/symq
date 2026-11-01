"""Deprecated location: this module moved to ``symq.labs.qualtran``.

Importing it still works and returns the same module object, with a ``DeprecationWarning``.
"""
import sys
import warnings

from symq.labs import qualtran as _module

warnings.warn("symq.experimental.qualtran moved to symq.labs.qualtran", DeprecationWarning, stacklevel=2)
sys.modules[__name__] = _module
