"""Build the optional native ZDD core.

The extension is compiled in place with the platform C compiler. It is optional: if no
compiler or Python headers are found, the wheel stays pure Python and
``symq.backends.zdd_native`` is unavailable, which the backend registration handles.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tools.build_native import build_extension


class BuildHook(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict) -> None:
        if os.environ.get("SYMQ_SKIP_NATIVE"):
            return
        built = build_extension(self.root, quiet=True)
        if built is not None:
            # ``*.so`` is ignored by git, and hatchling only ships tracked files, so the
            # compiled core has to be declared as a build artifact.
            build_data["pure_python"] = False
            build_data["infer_tag"] = True
            build_data["artifacts"] = [
                str(built.relative_to(self.root)) if built.is_relative_to(self.root) else str(built)
            ]
