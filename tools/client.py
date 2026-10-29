"""Build the transport-only C ABI DLL, without any SpiderMonkey linkage."""

import ctypes
import os
import shutil
import subprocess

from provenance import digest


def build_client(native, destination):
    if native.is_darwin:
        include = destination / "include"
        include.mkdir(exist_ok=True)
        shutil.copy2(native.root / "src/client/ruyijs.h", include / "ruyijs.h")
        return {"status": "skipped", "reason": "Darwin client C library skipped for runtime"}
    sources = sorted((native.root / "src/client").glob("*.cpp"))
    if not sources:
        raise ValueError("src/client must contain implementation files")
    objects = []
    # The client is self-contained: any change under src/client rebuilds it.
    newest = max(path.stat().st_mtime_ns for path in (native.root / "src/client").iterdir()
                 if path.is_file())
    for source in sources:
        name = "client_" + source.stem
        output = native.directory / (name + ".obj")
        command = [*native.compiler(), "-MD", "-EHsc", "-W3", "-O2", "-Z7",
                   "-guard:cf", "-c", str(source), "-Fo" + str(output)]
        if not output.is_file() or output.stat().st_mtime_ns < newest:
            native.run(command, name)
        objects.append(output)
    output = destination / "ruyijs_client.dll"
    current = output.is_file() and all(
        path.stat().st_mtime_ns <= output.stat().st_mtime_ns for path in objects)
    flags = ["-DLL", "-OUT:" + str(output), "-MACHINE:X64", "-DEBUG",
             "-OPT:REF,ICF", "-guard:cf", "-PDB:" +
             str(native.directory / "ruyijs_client.pdb"), "-IMPLIB:" +
             str(native.directory / "ruyijs_client.lib")]
    flags += native.donor.libpaths(native.args.vs_root)
    flags += [str(path) for path in objects] + ["kernel32.lib", "bcrypt.lib"]
    response = native.directory / "link-client.rsp"
    response.write_text("\n".join(subprocess.list2cmdline([arg]) for arg in flags),
                        encoding="utf-8")
    if not current:
        native.run([native.linker(), "@" + str(response)], "link-client")
    include = destination / "include"
    include.mkdir(exist_ok=True)
    shutil.copy2(native.root / "src/client/ruyijs.h", include / "ruyijs.h")
    shutil.copy2(native.directory / "ruyijs_client.lib", destination)
    with os.add_dll_directory(str(destination)):
        library = ctypes.WinDLL(str(output))
        exports = ["ruyijs_create", "ruyijs_create_mode", "ruyijs_call",
                   "ruyijs_free", "ruyijs_close",
                   "ruyijs_set_callback", "ruyijs_alloc"]
        for name in exports:
            getattr(library, name)
    return {"path": str(output), "sha256": digest(output), "exports": exports}
