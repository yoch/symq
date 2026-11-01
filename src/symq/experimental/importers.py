"""Deprecated location: this module moved to ``symq.labs.importers``.

Importing it still works and returns the same module object, with a ``DeprecationWarning``.
"""
import sys
import warnings

from symq.labs import importers as _module

warnings.warn("symq.experimental.importers moved to symq.labs.importers", DeprecationWarning, stacklevel=2)
sys.modules[__name__] = _module
