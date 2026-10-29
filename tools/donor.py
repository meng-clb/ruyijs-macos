"""Read a configured standalone SpiderMonkey build without invoking make."""

import json
import re
import shlex
from pathlib import Path


class Donor:
    def __init__(self, objdir):
        self.obj = Path(objdir).resolve()
        self.config_path = self.obj / "config.status.json"
        self.config = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.substs = self.config["substs"]
        self.src = Path(self.config["topsrcdir"]).resolve()
        self.shell = self.obj / "js/src/shell"
        self.backend_path = self.shell / "backend.mk"
        self.backend = self.backend_path.read_text(encoding="utf-8")
        if str(self.substs.get("JS_STANDALONE")) != "1":
            raise ValueError("donor requires JS_STANDALONE=1")
        self.os_arch = str(self.substs.get("OS_ARCH"))
        if self.os_arch == "WINNT":
            if "x86_64" not in str(self.substs.get("target", "")):
                raise ValueError("donor must target x86_64 Windows")
            if "-MD" not in self.flags("COMPUTED_CXXFLAGS"):
                raise ValueError("donor must use the shared MSVC CRT (-MD)")
        elif self.os_arch == "Darwin":
            target = str(self.substs.get("target", ""))
            if "darwin" not in target:
                raise ValueError("donor must target Darwin")
        else:
            raise ValueError(f"unsupported donor OS_ARCH: {self.os_arch}")

    def values(self, variable):
        pattern = rf"^{re.escape(variable)}\s*(?:\+=|:=|=)\s*(.*)$"
        return re.findall(pattern, self.backend, re.MULTILINE)

    def flags(self, variable):
        # shlex is slow and the donor configuration is fixed for the process.
        cache = self.__dict__.setdefault("_flags", {})
        if variable not in cache:
            cache[variable] = shlex.split(" ".join(self.values(variable)))
        return list(cache[variable])

    def expand(self, text):
        for variable, value in (("DEPTH", self.obj), ("topobjdir", self.obj),
                                ("topsrcdir", self.src)):
            text = text.replace(f"$({variable})", value.as_posix())
        if "$(" in text:
            raise ValueError(f"unresolved make variable: {text}")
        return text

    def libraries(self):
        return [Path(self.expand(item)).resolve()
                for key in ("STATIC_LIBS", "SHARED_LIBS")
                for item in self.flags(key)]

    def js_list_path(self):
        p = self.shell / "js_exe.list"
        return p if p.is_file() else (self.shell / "js.list")

    def objects(self):
        text = self.js_list_path().read_text(encoding="utf-8")
        return [(self.shell / line.strip().strip('"')).resolve()
                for line in text.splitlines() if line.strip()]

    def libpaths(self, vs_root=None):
        result = []
        for value in self.substs.get("HOST_LINKER_LIBPATHS", []):
            path = value.split(":", 1)[1].strip("'\"")
            result.append("-LIBPATH:" + self.remap_vs(path, vs_root))
        return result

    def include(self, vs_root=None):
        raw = self.substs.get("INCLUDE", "")
        if not raw: return ""
        return ";".join(self.remap_vs(path, vs_root) for path in raw.split(";") if path)

    @staticmethod
    def remap_vs(path, vs_root):
        marker = "/.mozbuild/vs/"
        if vs_root is None:
            return path
        normalized = path.replace("\\", "/")
        if marker not in normalized:
            raise ValueError(f"unexpected VS path: {path}")
        return (Path(vs_root) / normalized.split(marker, 1)[1]).as_posix()

    def source_inputs(self):
        return [self.config_path, self.backend_path, self.js_list_path(),
                self.shell / "Unified_cpp_js_src_shell0.cpp",
                self.obj / "js/src/js-confdefs.h", self.src / "js/src/shell/js.cpp"]
