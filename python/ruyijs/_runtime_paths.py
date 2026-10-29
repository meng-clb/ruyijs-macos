"""Locate the runtime for Python 3.10+ clients."""

import os
from pathlib import Path
import platform
import sys


def get_runtime_path():
    """Return the runtime root containing ``dist`` and ``vendor``.

    ``RUYIJS_SHELL`` selects an existing executable and its enclosing runtime
    root. Otherwise prefer a source checkout's ``dist/js`` (or ``dist/js.exe``)
    to the runtime bundled in the installed package. This function never downloads files.
    """
    executable_name = "js.exe" if os.name == "nt" else "js"

    override = os.environ.get("RUYIJS_SHELL")
    if override:
        shell = Path(override).resolve()
        if not shell.is_file():
            raise FileNotFoundError(f"RUYIJS_SHELL does not exist: {shell}")
        return shell.parent.parent

    package = Path(__file__).resolve().parent
    candidates = [package / "_runtime"]
    if package.parent.name == "python":
        candidates.insert(0, package.parent.parent)
    for root in candidates:
        if (root / "dist" / executable_name).is_file():
            return root
        # Also check without extension on Windows or with .exe on non-Windows just in case
        alt_name = "js" if os.name == "nt" else "js.exe"
        if (root / "dist" / alt_name).is_file():
            return root

    searched = ", ".join(str(root / "dist" / executable_name) for root in candidates)
    raise FileNotFoundError(
        f"ruyijs runtime is missing. Install the platform wheel, build the "
        f"source runtime, or set RUYIJS_SHELL to an existing executable. "
        f"Searched: {searched}"
    )
