"""Prepare native Linux inputs from an unmodified SpiderMonkey build.

Writes the generated shell units, profile, sanitizer and binding tables beside
`sources.cmake`, the unit/object lists CMakeLists.txt compiles and links. The
units are product_sources.sources() for Linux: the Linux font, crypto and codec
units replace the DirectWrite/Core Text, CNG/CommonCrypto and WIC/ImageIO ones.
`foreign.cmake` holds the frozen libavif, dav1d and libyuv units that
tools/image_native.py, and the Brotli units that tools/compression_native.py,
compile on Windows and macOS.
"""
import argparse
from pathlib import Path

from donor import Donor
import compression_native
from generate import generate
import image_native
import product_sources
import sanitizer_data
from provenance import write_if_changed


def cmake_list(name, values):
    return "set(" + name + "\n" + "".join('  "' + str(value).replace('\\', '/') + '"\n'
                                          for value in values) + ")\n"


def object_libraries(name, units):
    """One CMake object library per flag set of (source, flags) units, listed in
    ${name}_TARGETS."""
    groups = {}
    for path, flags in units:
        groups.setdefault(tuple(flags), []).append(path)
    output, targets = "", []
    for index, (flags, paths) in enumerate(groups.items()):
        target = name + str(index)
        targets.append(target)
        output += cmake_list(target + "_SOURCES", paths) + cmake_list(target + "_FLAGS", flags)
        output += ("add_library(" + target + " OBJECT ${" + target + "_SOURCES})\n"
                   "target_compile_options(" + target + " PRIVATE ${" + target + "_FLAGS})\n")
    return output + "set(" + name + "_TARGETS " + " ".join(targets) + ")\n"


def foreign_cmake(root):
    """The portable vendor/ C and C++ units: image_native.portable_units() (dav1d's
    bit-depth templates twice, at 8 and at 16 bits) and compression_native's Brotli."""
    image = root / "vendor/image-native"
    image_native.frozen_inputs(image)
    compression = root / "vendor/compression-native"
    compression_native.frozen_inputs(compression)
    brotli = [(compression / "brotli" / unit, compression_native.brotli_flags(compression))
              for unit in compression_native.brotli_units(compression)]
    return (object_libraries("ruyijs_image_native", [(path, flags) for path, _, flags in
                                                     image_native.portable_units(image, False)]) +
            object_libraries("ruyijs_cs_brotli", brotli))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--donor-obj", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    donor = Donor(args.donor_obj)
    if donor.os_arch != "Linux":
        parser.error("a Linux SpiderMonkey donor build is required")
    directory = args.output.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    shell, _ = generate(donor, root, directory)
    product_sources.profile(root, directory)
    sanitizer_data.prepare(donor.src, directory)
    for header in (root / "tools/generated").glob("*.h"):
        write_if_changed(directory / header.name, header.read_text(encoding="utf-8"), encoding="utf-8")
    sources = [shell] + [path for path, _ in product_sources.sources(root)]
    objects = [path for path in donor.objects() if path.name != "Unified_cpp_js_src_shell0.o"]
    output = cmake_list("RUYIJS_SOURCES", sources)
    output += cmake_list("DONOR_OBJECTS", objects)
    output += cmake_list("DONOR_LIBRARIES", donor.libraries())
    output += cmake_list("DONOR_LINK_FLAGS", donor.flags("COMPUTED_LDFLAGS") + donor.flags("OS_LIBS"))
    output += cmake_list("DONOR_SOURCE", [donor.src])
    write_if_changed(directory / "sources.cmake", output, encoding="utf-8")
    write_if_changed(directory / "foreign.cmake", foreign_cmake(root), encoding="utf-8")
    print(f"Prepared {len(sources)} Linux translation units")


if __name__ == "__main__":
    main()
