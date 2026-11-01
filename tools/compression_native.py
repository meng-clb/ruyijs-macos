"""Offline source-owned CompressionStream codecs; no mutable Firefox objects."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# zlib-rs's C ABI under a private prefix, as libz-rs-sys's build script would set it.
ZLIB_ENV = {'LIBZ_RS_SYS_PREFIX': 'RUYIJS_CS_Z_', 'CARGO_PKG_VERSION': '0.6.3',
            'CARGO_PKG_VERSION_MAJOR': '0', 'CARGO_PKG_VERSION_MINOR': '6'}


def frozen_inputs(source):
    """SHA-256 of each vendor/compression-native file, checked against manifest.json."""
    manifest = json.loads((source / 'manifest.json').read_text('utf8'))
    inputs = {row['path']: digest(source / row['path']) for row in manifest['files']}
    if any(inputs[row['path']] != row['sha256'] for row in manifest['files']):
        raise ValueError('Compression dependency source differs from frozen manifest')
    return inputs


def zlib_rlibs(base, source, directory):
    """The rustc commands (with log names) that build zlib-rs and its C ABI under
    ZLIB_ENV, and the two rlibs they write, C ABI first."""
    def features(*names):
        return [item for name in names for item in ('--cfg', 'feature="' + name + '"')]
    rlib = directory / 'libzlib_rs.rlib'
    abi = directory / 'libz_rs_sys.rlib'
    commands = [
        ([*base, '--crate-name=zlib_rs', '--crate-type=rlib',
          *features('std', 'rust-allocator', 'c-allocator', '__internal-api', 'avx512', 'vpclmulqdq'),
          str(source / 'zlib-rs/src/lib.rs'), '-o', str(rlib)], 'rust_zlib'),
        ([*base, '--crate-name=libz_rs_sys', '--crate-type=rlib',
          *features('std', 'rust-allocator', 'custom-prefix', 'export-symbols'),
          '--extern', 'zlib_rs=' + str(rlib), str(source / 'libz-rs-sys/src/lib.rs'),
          '-o', str(abi)], 'rust_c_abi')]
    return commands, [abi, rlib]


def brotli_units(source):
    """Exact moz.build source inventory; separate TUs retain upstream semantics."""
    return re.findall(r"'((?:common|dec|enc)/[^']+\.c)'",
                      (source / 'brotli/moz.build').read_text('utf8'))


def brotli_flags(source):
    return ['-DBROTLI_BUILD_PORTABLE', '-I' + str(source / 'brotli/include')]


def build(native):
    source = native.root / 'vendor/compression-native'
    directory = native.directory / 'compression-native'
    directory.mkdir(parents=True, exist_ok=True)
    inputs = frozen_inputs(source)
    # Rust static libraries share the donor's standard runtime. A PATH compiler
    # can embed a second std version with colliding unmangled personality symbols.
    rustc = native.donor.substs['RUSTC']
    if isinstance(rustc, list):
        rustc = rustc[0]
    if not Path(rustc).is_file():
        raise RuntimeError('The configured donor rustc is required: ' + rustc)
    compiler = native.compiler()[0]
    librarian, lib_prefix = native.librarian()
    tools = {path: subprocess.run([path, '--version'], capture_output=True,
             text=True, check=True).stdout for path in (rustc, compiler)}
    identity = {'sources': inputs, 'tools': tools, 'builder': digest(__file__),
                'rustcSHA256': digest(rustc),
                'compilerSHA256': digest(compiler), 'librarianSHA256': digest(librarian),
                'donorConfigSHA256': digest(native.donor.config_path),
                'include': native.env.get('INCLUDE'),
                'prefix': 'RUYIJS_CS_Z_', 'crt': 'dynamic',
                'target': native.donor.rust_target}
    signature = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    stamp = directory / 'build.json'
    libs = [native.static_library(directory, 'ruyijs_cs_zlib'),
            native.static_library(directory, 'ruyijs_cs_brotli')]
    if stamp.is_file():
        old = json.loads(stamp.read_text('utf8'))
        if not native.incremental['disabled'] and old.get('signature') == signature and all(
                p.is_file() and digest(p) == old['outputs'].get(p.name) for p in libs):
            return libs
    report = {'signature': signature, 'identity': identity, 'commands': [], 'outputs': {}}
    env = native.env.copy()
    env.update(ZLIB_ENV)

    def run(command, name):
        report['commands'].append(command)
        completed = subprocess.run(command, cwd=directory, env=env,
                                   capture_output=True, text=True)
        (directory / (name + '.log')).write_text(completed.stdout + completed.stderr, 'utf8')
        if completed.returncode:
            raise RuntimeError(name + ': ' + (completed.stdout + completed.stderr)[-10000:])

    base = native.rustc_base(rustc, '2021')
    commands, rlibs = zlib_rlibs(base, source, directory)
    for command, name in commands:
        run(command, name)
    # One Rust std/global allocator already belongs to donor jsrust. Rlibs emit
    # library code without a new executable-level allocator shim; archive only
    # our two crates and let that original runtime satisfy their dependencies.
    run(native.archive(libs[0], rlibs), 'archive_zlib')
    units = brotli_units(source)
    objects = []
    for unit in units:
        output = directory / (unit.replace('/', '_')[:-2] + native.donor.object_suffix)
        run(native.compile_foreign(source / 'brotli' / unit, output, brotli_flags(source)), output.stem)
        objects.append(str(output))
    run(native.archive(libs[1], objects), 'archive_brotli')
    if any(digest(source / name) != checksum for name, checksum in inputs.items()):
        raise ValueError('Compression source changed during dependency build')
    report['outputs'] = {path.name: digest(path) for path in libs}
    report['compiledBrotliUnits'] = units
    stamp.write_text(json.dumps(report, indent=2) + '\n', 'utf8')
    return libs


if __name__ == '__main__':
    import argparse
    from donor import Donor
    from native import Native
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--donor-obj', required=True)
    parser.add_argument('--toolchain-bin', required=True)
    parser.add_argument('--vs-root')
    parser.add_argument('--output', default='artifacts/native-four/compression/dependency-build')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    directory = (root / args.output).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    owner = Native(Donor(args.donor_obj), root, directory, args)
    print(json.dumps({'libraries': [str(path) for path in build(owner)]}))
