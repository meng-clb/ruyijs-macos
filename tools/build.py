"""Build only a local standalone shell; the Firefox donor remains read-only."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
from donor import Donor
from generate import generate
from client import build_client
from native import Native
from provenance import digest, inventory, save_hash_cache, verify_unchanged, write_if_changed
import product_sources
import geometry_fonts
import binding_order
import sanitizer_data
import compression_native
import urlpattern_native
import image_native


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    # Local donor and Firefox paths come from arguments or environment, never
    # from a machine-specific default.
    parser.add_argument("--donor-obj", default=os.environ.get("RUYIJS_DONOR_OBJ"),
                        help="SpiderMonkey standalone obj dir (env RUYIJS_DONOR_OBJ)")
    parser.add_argument("--toolchain-bin", help="explicit independent LLVM bin")
    parser.add_argument("--vs-root", help="explicit VS root with VC and Windows Kits")
    parser.add_argument("--runtime-dll-dir", help="matching MSVC CRT redistributable")
    parser.add_argument("--firefox-font-prefs", default=os.environ.get("RUYIJS_FIREFOX_FONT_PREFS"),
                        help="browser build dist/bin/greprefs.js (env RUYIJS_FIREFOX_FONT_PREFS; "
                             "default: tools/generated/firefox_font_prefs.h)")
    parser.add_argument("--firefox-bindings", default=os.environ.get("RUYIJS_FIREFOX_BINDINGS"),
                        help="generated Firefox dom/bindings directory (prototype member order; "
                             "env RUYIJS_FIREFOX_BINDINGS; default: tools/generated)")
    parser.add_argument("--pristine", action="store_true", help="relink donor objects only")
    parser.add_argument("--prepare-only", action="store_true", help="generate and record inputs")
    parser.add_argument("--no-incremental", action="store_true",
                        help="recompile all local translation units")
    parser.add_argument("--reuse-objects", action="store_true",
                        help="reuse every existing local object without recompiling")
    parser.add_argument("--jobs", type=int, choices=range(1, 129), default=min(os.cpu_count() or 4, 128),
                        help="independent compiler processes (default: CPU count)")
    args = parser.parse_args()
    if not args.donor_obj:
        parser.error("--donor-obj (or RUYIJS_DONOR_OBJ) is required")
    return args


def local_directory(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"build output is outside ruyijs: {path}")
    path.mkdir(parents=True, exist_ok=True)
    return path


def main():
    args = arguments()
    root = Path(__file__).resolve().parents[1]
    mode = "pristine" if args.pristine else "runtime"
    directory = local_directory(root, "build/" + mode)
    destination = local_directory(root, os.environ.get("RUYIJS_DESTINATION", "dist/pristine" if args.pristine else "dist"))
    artifacts = local_directory(root, "artifacts")
    report_path = artifacts / f"build-{mode}.json"
    report = {"mode": mode, "status": "started", "commands": []}
    native = None
    try:
        donor = Donor(args.donor_obj)
        native = Native(donor, root, directory, args)
        objects = donor.objects()
        inputs = donor.source_inputs() + objects + donor.libraries()
        js_bin = donor.obj / ("dist/bin/js.exe" if donor.os_arch == "WINNT" else "dist/bin/js")
        mozglue_bin = donor.obj / ("dist/bin/mozglue.dll" if donor.os_arch == "WINNT" else "dist/bin/libmozglue.dylib")
        inputs += [js_bin, mozglue_bin]
        inputs += list((root / "tools").glob("*.py"))
        sources = []
        if not args.pristine:
            unit, source_inputs = generate(donor, root, directory)
            sources = [(unit, "shell0"), *product_sources.sources(root)]
            # Both inputs come from a full Firefox browser build. Without one,
            # use the headers recorded from Firefox 159 in tools/generated.
            recorded = root / "tools/generated"
            font_unit, font_inputs = geometry_fonts.prepare(
                donor, directory, args.firefox_font_prefs, recorded / "firefox_font_prefs.h")
            if args.firefox_bindings:
                inputs += binding_order.prepare(args.firefox_bindings, directory)
            else:
                order = directory / "firefox_binding_order.h"
                write_if_changed(order, (recorded / "firefox_binding_order.h").read_text("utf-8"), "utf-8")
                inputs += [recorded / "firefox_binding_order.h", order]
            inputs += sanitizer_data.prepare(donor.src, directory)
            sources.append(font_unit)
            inputs += font_inputs
            inputs += source_inputs + product_sources.inputs(root)
            if (root / "profiles/firefox-environment.json").is_file():
                profile_inputs = product_sources.profile(root, directory)
                # The header is generated inside build/runtime and is an output
                # of this invocation. Verify the source profile, not its
                # rewritten output timestamp, as a donor input.
                inputs += [path for path in profile_inputs
                           if path != directory / "firefox_environment_profile.h"]
            inputs += [unit, directory / "js.cpp", directory / "runtime_assets.h"]
            inputs += list((root / "python").rglob("*.py"))
            # Documentation is recorded when present; a public checkout omits
            # internal design notes, and they never affect the compiled output.
            inputs += [path for path in (root / "README.md", root / "ARCHITECTURE.md")
                       if path.is_file()]
            inputs += list((root / "docs").rglob("*.md"))
            inputs += [path for path in (root / "vendor/compression-native").rglob("*") if path.is_file()]
            inputs += [path for path in (root / "vendor/image-native").rglob("*") if path.is_file()]
        report.update(donor=str(donor.obj), source=str(donor.src),
                      executable=str(destination / ("js.exe" if donor.os_arch == "WINNT" else "js")),
                      inputs=inventory(inputs),
                      compiler=native.compiler(), linker=native.linker(),
                      include=native.env.get("INCLUDE", ""),
                      library_paths=donor.libpaths(args.vs_root),
                      runtime_dll_dir=args.runtime_dll_dir)
        if args.prepare_only:
            report["status"] = "prepared"
            return 0
        native.check_tools(compile_needed=bool(sources))
        if sources:
            obj_ext = ".obj" if donor.os_arch == "WINNT" else ".o"
            original = donor.shell / ("Unified_cpp_js_src_shell0" + obj_ext)
            if objects.count(original) != 1:
                raise ValueError("shell0 object must occur once in donor list")
            objects.remove(original)
            def compile_unit(unit):
                source, name = unit
                return native.compile(source, name,
                        exceptions=product_sources.needs_exceptions(source))
            with ThreadPoolExecutor(max_workers=args.jobs) as pool:
                objects += list(pool.map(compile_unit, sources))
        executable = destination / os.environ.get("RUYIJS_OUTPUT_NAME", "js.exe" if donor.os_arch == "WINNT" else "js")
        if not args.pristine:
            if native.is_darwin:
                comp_libs = compression_native.build(native)
                objects += [p for p in comp_libs if "zlib" not in p.name]
                img_libs = image_native.build(native)
                objects += [p for p in img_libs if "color" not in p.name]
            else:
                objects += compression_native.build(native)
                objects += urlpattern_native.build(native)
                objects += image_native.build(native)
            report["imageCodecs"] = json.loads((directory / "image-native/build.json").read_text("utf-8"))
            report["compressionCodecs"] = json.loads(
                (directory / "compression-native/build.json").read_text("utf-8"))
        linked = native.link(objects, executable)
        deployed = native.deploy(destination)
        if sources:
            # The residency proof reads the whole executable; reuse it while unchanged.
            residency = directory / "residency.json"
            stamp = [executable.stat().st_size, executable.stat().st_mtime_ns]
            previous = json.loads(residency.read_text("utf-8")) if residency.is_file() else {}
            if linked or previous.get("stamp") != stamp:
                previous = {"stamp": stamp,
                            "domains": product_sources.residency(root, executable)}
                residency.write_text(json.dumps(previous), "utf-8")
            report["residency"] = previous["domains"]
        if not args.pristine:
            report["client"] = build_client(native, destination)
            # Deploy the one owned source to the existing Necko transport path.
            # The Necko Python runtime ships with releases, not the source tree;
            # a checkout without it still builds js.exe and skips this deploy.
            oneshot_source = root / "src/resource_network/necko_oneshot.py"
            oneshot = root / "vendor/necko-derived/python/Lib/site-packages/ruyijs_necko/oneshot.py"
            if oneshot.parent.is_dir():
                oneshot.write_bytes(oneshot_source.read_bytes())
                deployed.append(oneshot)
                report["networkHelper"] = {"source": str(oneshot_source), "deployed": str(oneshot),
                                           "sha256": digest(oneshot)}
            else:
                report["networkHelper"] = {"source": str(oneshot_source), "deployed": None}
        report["incremental"] = native.incremental
        verify_unchanged(report["inputs"], rehash=True)
        version = subprocess.run([str(executable), "--version"], cwd=destination,
                                 env=native.env, text=True, capture_output=True,
                                 timeout=30, check=True)
        report.update(status="built", version=version.stdout.strip(),
                      sha256=digest(executable), deployed=inventory(deployed),
                      toolchain_versions=native.versions)
        print(version.stdout.strip())
        print(executable)
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        report.update(status="failed", error=str(error))
        print(str(error), file=sys.stderr)
        return 1
    finally:
        save_hash_cache()
        if native:
            report["commands"] = native.commands
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Evidence: {report_path}")


if __name__ == "__main__":
    raise SystemExit(main())
