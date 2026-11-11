"""Build the optional native ZDD core.

The extension is compiled in place with the platform C compiler. It is optional by default:
if no compiler or Python headers are found, the wheel stays pure Python and
``symq.backends.zdd_native`` is unavailable.
Set ``SYMQ_REQUIRE_NATIVE=1`` to mandate the native backend and fail the build if it cannot be built.
Set ``SYMQ_SKIP_NATIVE=1`` to skip native compilation entirely (setting both is an error).
"""
from __future__ import annotations

import sys
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface
from hatchling.metadata.plugin.interface import MetadataHookInterface

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tools.build_native import build_extension, native_mode
from tools.pypi_readme import absolute_links, release_ref


class MetadataHook(MetadataHookInterface):
    """The long description: ``README.md`` with its relative links made absolute.

    PyPI renders the description away from the repository, where a relative link is dead. The
    links point to the tag of the version being built (see ``tools/pypi_readme.py``).
    """

    PLUGIN_NAME = "custom"

    def update(self, metadata: dict) -> None:
        text = (Path(self.root) / "README.md").read_text(encoding="utf-8")
        metadata["readme"] = {
            "content-type": "text/markdown",
            "text": absolute_links(text, release_ref(metadata["version"])),
        }


class BuildHook(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict) -> None:
        mode = native_mode()
        if mode == "skip":
            print("[symq] SYMQ_SKIP_NATIVE is active; skipping native core build.", file=sys.stderr)
            return

        built = build_extension(self.root, quiet=False, require=mode == "require")
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
