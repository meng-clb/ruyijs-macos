#!/usr/bin/env python3
"""Build a self-contained macOS wheel from the local Firefox donor artifacts."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import tomllib
import zipfile

from macos_runtime import NECKO_DIRS, NECKO_FILES, donor_bin


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_RUNTIME = (
    "dist/js",
    "dist/libmozglue.dylib",
    "dist/libruyijs_client.dylib",
)
GITHUB_BLOB_LIMIT = 100 * 1024 * 1024


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def verify_inputs(donor: Path) -> None:
    for name in REQUIRED_RUNTIME:
        if not (ROOT / name).is_file():
            raise FileNotFoundError(f"missing runtime file: {ROOT / name}")
    for name in NECKO_FILES:
        if not (donor / name).is_file():
            raise FileNotFoundError(f"missing Firefox donor file: {donor / name}")
    for name in NECKO_DIRS:
        if not (donor / name).is_dir():
            raise FileNotFoundError(f"missing Firefox donor directory: {donor / name}")


def verify_wheel(wheel: Path) -> None:
    if wheel.stat().st_size > GITHUB_BLOB_LIMIT:
        raise ValueError(f"wheel exceeds GitHub's 100 MiB Git file limit: {wheel.stat().st_size}")
    required = {
        "ruyijs/_runtime/dist/js",
        "ruyijs/_runtime/dist/libmozglue.dylib",
        "ruyijs/_runtime/dist/libruyijs_client.dylib",
        "ruyijs/_runtime/dist/necko/xpcshell",
        "ruyijs/_runtime/dist/necko/XUL",
        "ruyijs/_runtime/dist/necko/libnss3.dylib",
        "ruyijs/_runtime/dist/necko/necko_fetch.js",
        "necko/core_client.py",
        "necko/closed_route.py",
        "ruyijs_necko/oneshot.py",
    }
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        missing = required - names
        if missing:
            raise ValueError(f"wheel is missing: {sorted(missing)}")
        for entry in archive.infolist():
            if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError(f"wheel contains a symlink: {entry.filename}")
        metadata = next((name for name in names if name.endswith(".dist-info/METADATA")), None)
        if metadata is None:
            raise ValueError("wheel has no package metadata")
        description = archive.read(metadata).decode("utf-8")
        for package in ("h2", "cryptography", "backports.zstd", "publicsuffixlist"):
            if f"Requires-Dist: {package}" not in description:
                raise ValueError(f"wheel does not declare {package}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xpcshell", type=Path,
                        help="Firefox donor xpcshell; defaults to dist/necko/xpcshell")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "wheels",
                        help="repository directory for the installable wheel")
    args = parser.parse_args()
    if sys.platform != "darwin" or platform.machine().lower() not in ("arm64", "aarch64"):
        parser.error("the macOS wheel must be built on macOS arm64")
    if args.xpcshell is not None:
        if not args.xpcshell.is_file():
            parser.error(f"xpcshell does not exist: {args.xpcshell}")
        donor = args.xpcshell.resolve().parent
    else:
        donor = donor_bin(ROOT)
    verify_inputs(donor)
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    expected = f"ruyijs-{version}-py3-none-macosx_26_0_arm64.whl"
    environment = os.environ.copy()
    environment["RUYIJS_XPCSHELL"] = str(donor / "xpcshell")
    # Wheel ZIP timestamps otherwise change on every build and duplicate Git blobs.
    environment.setdefault("SOURCE_DATE_EPOCH", "315532800")
    with tempfile.TemporaryDirectory(prefix="ruyijs-wheel-") as temporary:
        staging = Path(temporary)
        command = [sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-cache-dir",
                   "--wheel-dir", str(staging), str(ROOT)]
        subprocess.run(command, cwd=ROOT, env=environment, check=True)
        wheel = staging / expected
        if not wheel.is_file():
            raise FileNotFoundError(f"expected wheel was not produced: {expected}")
        verify_wheel(wheel)
        output = args.output_dir.resolve()
        output.mkdir(parents=True, exist_ok=True)
        target = output / expected
        pending = output / (expected + ".tmp")
        shutil.copy2(wheel, pending)
        pending.replace(target)
    checksum = f"{sha256(target)}  {target.name}\n"
    manifest = target.parent / "SHA256SUMS"
    pending_manifest = target.parent / "SHA256SUMS.tmp"
    pending_manifest.write_text(checksum, encoding="utf-8")
    pending_manifest.replace(manifest)
    print(f"wheel: {target}")
    print(f"size: {target.stat().st_size}")
    print(f"sha256: {checksum.split()[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
