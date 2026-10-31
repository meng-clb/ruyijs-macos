#!/usr/bin/env python3
"""Build and verify the native macOS Necko/NSS transport runtime.

Usage:
  python3 tools/build_macos_necko.py [--firefox-src DIR] [--donor-obj DIR]
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Build macOS Necko/NSS runtime for ruyijs")
    parser.add_argument("--firefox-src", default="/Users/ameng/Desktop/firefox-src/firefox-159.0",
                        help="Firefox source directory")
    parser.add_argument("--donor-obj", default="/Users/ameng/Desktop/firefox-src/firefox-159.0/obj-js-standalone",
                        help="Firefox standalone js objdir")
    parser.add_argument("--necko-obj", default="/Users/ameng/Desktop/firefox-src/firefox-159.0/obj-necko",
                        help="Firefox browser necko objdir")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    necko_dist_bin = Path(args.necko_obj) / "dist" / "bin"
    xpcshell = necko_dist_bin / "xpcshell"
    xul = necko_dist_bin / "XUL"

    print("=== Step 1: Checking Necko/NSS donor binaries ===")
    if not xpcshell.is_file() or not xul.is_file():
        print(f"Building Necko binaries in {args.firefox_src}...")
        subprocess.run(["./mach", "build"], cwd=args.firefox_src, check=True)
    assert xpcshell.is_file() and xul.is_file(), "xpcshell or XUL missing after build"
    print(f"Found xpcshell: {xpcshell} ({xpcshell.stat().st_size} bytes)")
    print(f"Found XUL: {xul} ({xul.stat().st_size} bytes)")

    print("\n=== Step 2: Preparing dist/necko symlink ===")
    dist_necko = root / "dist" / "necko"
    dist_necko.parent.mkdir(parents=True, exist_ok=True)
    if dist_necko.is_symlink() or dist_necko.is_file():
        dist_necko.unlink()
    dist_necko.symlink_to(necko_dist_bin)
    print(f"Linked {dist_necko} -> {necko_dist_bin}")

    print("\n=== Step 3: Bootstrapping macOS helper venv ===")
    bootstrap = root / "tools" / "bootstrap_macos_helper.py"
    subprocess.run([sys.executable, str(bootstrap)], cwd=root, check=True)

    print("\n=== Step 4: Compiling ruyijs native shell ===")
    build_py = root / "tools" / "build.py"
    subprocess.run([sys.executable, "-B", str(build_py), "--donor-obj", args.donor_obj], cwd=root, check=True)

    print("\n=== All macOS Necko runtime components built and ready ===")


if __name__ == "__main__":
    main()
