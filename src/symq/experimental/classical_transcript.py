"""Deprecated location: this module moved to ``symq.labs.classical_transcript``.

Importing it still works and returns the same module object, with a ``DeprecationWarning``.
"""
import sys
import warnings

from symq.labs import classical_transcript as _module

warnings.warn("symq.experimental.classical_transcript moved to symq.labs.classical_transcript", DeprecationWarning, stacklevel=2)
sys.modules[__name__] = _module
