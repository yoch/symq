"""Build the optional native ZDD core.

The extension is compiled in place with the platform C compiler. It is optional by default:
if no compiler or Python headers are found, the wheel stays pure Python and
``symq.backends.zdd_native`` is unavailable.
Set ``SYMQ_REQUIRE_NATIVE=1`` to mandate the native backend and fail the build if it cannot be built.
Set ``SYMQ_SKIP_NATIVE=1`` to skip native compilation entirely.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

try:
    from hatchling.builders.hooks.plugin.interface import BuildHookInterface
except ImportError:
    class BuildHookInterface:  # type: ignore[no-redef]
        """Fallback interface when hatchling is not installed in the current environment."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.root = args[1] if len(args) > 1 else Path.cwd()

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tools.build_native import build_extension, is_native_required


class BuildHook(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict) -> None:
        if os.environ.get("SYMQ_SKIP_NATIVE"):
            print("[symq] SYMQ_SKIP_NATIVE is active; skipping native core build.", file=sys.stderr)
            return

        required = is_native_required()
        built = build_extension(self.root, quiet=False, require=required)
        if built is not None:
            # ``*.so`` is ignored by git, and hatchling only ships tracked files, so the
            # compiled core has to be declared as a build artifact.
            build_data["pure_python"] = False
            build_data["infer_tag"] = True
            build_data["artifacts"] = [
                str(built.relative_to(self.root)) if built.is_relative_to(self.root) else str(built)
            ]
        else:
            print(
                "[symq] Native core was not built; continuing in pure-Python mode.\n"
                "       (Set SYMQ_REQUIRE_NATIVE=1 to enforce native backend compilation.)",
                file=sys.stderr,
            )
