"""Deprecated location: this module moved to ``symq.labs.qcec_adapter``.

Importing it still works and returns the same module object, with a ``DeprecationWarning``.
"""
import sys
import warnings

from symq.labs import qcec_adapter as _module

warnings.warn("symq.experimental.qcec moved to symq.labs.qcec_adapter", DeprecationWarning, stacklevel=2)
sys.modules[__name__] = _module
