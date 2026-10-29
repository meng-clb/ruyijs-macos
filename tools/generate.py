"""Deterministic shell hooks; generated files retain the donor MPL header."""

import re
from provenance import write_if_changed


def replace_once(source, old, new):
    count = source.count(old)
    if count != 1:
        raise ValueError(f"expected one shell hook, found {count}: {old!r}")
    return source.replace(old, new, 1)


def generate(donor, root, directory):
    original = donor.src / "js/src/shell/js.cpp"
    source = original.read_text(encoding="utf-8")
    source = replace_once(source, "/* JS shell. */",
                          '/* JS shell. */\n#include "runtime/runtime.h"\n'
                          '#include "runtime/exception_capture.h"\n'
                          '#include "runtime/arguments.h"')
    source = replace_once(source, "  sArgc = argc;",
                          "  ruyijs::Arguments productArguments;\n"
                          "  if (!productArguments.Prepare(&argc, &argv)) return 1;\n"
                          "  sArgc = argc;")
    source = replace_once(
        source, "!ProcessArgs(cx, op)",
        '!(op->getStringOption("ruyijs-worker") ? '
        'ruyijs::RunWorker(cx, op, RunShellJobs) : '
        'op->getBoolOption("ruyijs-runtime") || '
        'op->getStringOption("ruyijs-rpc") ? '
        'ruyijs::Run(cx, op, RunShellJobs) : ProcessArgs(cx, op))')
    hook = '!op.addBoolOption(\'i\', "shell", "Enter prompt after running code")'
    options = ('!op.addBoolOption(\'\\0\', "ruyijs-runtime", '
               '"Run in the ruyijs page realm") ||\n      '
               '!op.addStringOption(\'\\0\', "ruyijs-rpc", "PIPE", '
               '"Serve ruyijs requests over a private pipe") ||\n      '
               '!op.addStringOption(\'\\0\', "ruyijs-environment", "JSON_FILE", '
               '"Configure the ruyijs environment before page execution") ||\n      '
               '!op.addStringOption(\'\\0\', "ruyijs-mode", "MODE", '
               '"Context mode; debug enables the API monitor") ||\n      '
               '!op.addStringOption(\'\\0\', "ruyijs-worker", "PIPE", '
               '"Run as a ruyijs worker connected to a private pipe") ||\n      '
               '!op.addStringOption(\'\\0\', "ruyijs-worker-kind", "KIND", '
               '"Worker global kind: dedicated (default), service or shared") ||\n      ')
    source = replace_once(source, hook, options + hook)
    source = replace_once(
        source, "js::shell::AutoReportException::~AutoReportException() {",
        "js::shell::AutoReportException::~AutoReportException() {\n"
        "  if (ruyijs::CaptureShellException(cx)) return;")
    # The test shell always exposes FinalizationRegistry.prototype.cleanupSome;
    # Firefox ships javascript.options.experimental.weakrefs.expose_cleanupSome
    # off, so the product modes keep the browser default.
    source = replace_once(
        source, "  JS::Prefs::setAtStartup_experimental_weakrefs_expose_cleanupSome(true);",
        "  JS::Prefs::setAtStartup_experimental_weakrefs_expose_cleanupSome(\n"
        "      !(op.getBoolOption(\"ruyijs-runtime\") || op.getStringOption(\"ruyijs-rpc\") ||\n"
        "        op.getStringOption(\"ruyijs-worker\")));")
    rejection = ("static void ForwardingPromiseRejectionTrackerCallback(\n"
                 "    JSContext* cx, bool mutedErrors, JS::HandleObject promise,\n"
                 "    JS::PromiseRejectionHandlingState state, void* data) {")
    source = replace_once(
        source, rejection, rejection + "\n"
        "  if (ruyijs::CapturePromiseRejection(cx, promise, state)) return;")
    generated_js = directory / "js.cpp"
    # ``newline="\n"`` is rejected by the Windows text layer (EINVAL).  The
    # generated source already uses LF, so disable translation explicitly.
    write_if_changed(generated_js, source, newline="")
    unified = donor.shell / "Unified_cpp_js_src_shell0.cpp"
    includes = []

    def resolve_include(match):
        path = (donor.shell / match[1]).resolve()
        includes.append(path)
        if path == original.resolve():
            path = generated_js
        return f'#include "{path.as_posix()}"'

    unit = re.sub(r'^#include "([^"]+\.cpp)"', resolve_include,
                  unified.read_text(encoding="utf-8"), flags=re.MULTILINE)
    if includes.count(original.resolve()) != 1:
        raise ValueError("the unified shell must include js.cpp exactly once")
    generated_unit = directory / unified.name
    write_if_changed(generated_unit, unit, newline="")
    codec_path = root / "src/runtime/codec.js"
    codec = codec_path.read_text(encoding="utf-8")
    delimiter = "RUYIJS_CODEC"
    if f'){delimiter}"' in codec:
        raise ValueError("codec collides with its C++ raw-string delimiter")
    header = ('// Generated from src/runtime/codec.js. Do not edit.\n'
              '#pragma once\nnamespace ruyijs {\n'
              f'inline constexpr char kCodecSource[] = R"{delimiter}('
              f'{codec}){delimiter}";\n}}\n')
    write_if_changed(directory / "runtime_assets.h", header)
    return generated_unit, includes + [codec_path]
