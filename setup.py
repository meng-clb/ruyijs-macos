"""Build a platform wheel containing the unchanged standalone runtime."""
from pathlib import Path
import platform
import shutil
import sys

from setuptools import Distribution, setup
from setuptools.command.bdist_wheel import bdist_wheel
from setuptools.command.build_py import build_py

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
from wheel_runtime import obtain_runtime, validate, digest

# Captured third-party responses and cookies used only for offline replay stay out of the wheel.
EXAMPLES_EXCLUDED = shutil.ignore_patterns("__pycache__", "*.pyc", "fixture", "interstitial_fixture",
                                           "replay.py", "interstitial.py", "interstitial_solve.py")


class PlatformDistribution(Distribution):
    def has_ext_modules(self):
        return True


class BuildPython(build_py):
    def get_outputs(self, include_bytecode=True):
        outputs = list(super().get_outputs(include_bytecode=include_bytecode))
        examples = Path(self.build_lib) / "ruyijs/examples"
        if examples.exists():
            outputs.extend(str(path) for path in examples.rglob("*") if path.is_file())
        return sorted(set(outputs))

    def run(self):
        if sys.platform not in ("win32", "darwin") or platform.machine().lower() not in ("amd64", "x86_64", "arm64", "aarch64"):
            raise RuntimeError("ruyijs requires Windows x64 or macOS and a 64-bit Python installation")
        if sys.maxsize <= 2 ** 32:
            raise RuntimeError("ruyijs requires 64-bit Python")
        super().run()
        runtime = obtain_runtime(Path(__file__).resolve().parent)
        target = Path(self.build_lib) / "ruyijs/_runtime"
        if target.exists():
            validate(target)
            if digest(target / "SHA256SUMS") != digest(runtime / "SHA256SUMS"):
                raise ValueError(f"Build directory contains another runtime version: {target}")
        else:
            shutil.copytree(runtime, target)
        examples = Path(self.build_lib) / "ruyijs/examples"
        if examples.exists():
            shutil.rmtree(examples)
        shutil.copytree(Path(__file__).resolve().parent / "examples", examples, ignore=EXAMPLES_EXCLUDED)
        registry = Path(__file__).resolve().parent / "python/ruyijs/examples"
        shutil.copytree(registry, examples, dirs_exist_ok=True)
        readme = examples / "DataDome/README.md"
        if readme.is_file():
            readme.write_text(
                "> The installed package includes only the live `solve.py` "
                "(`python -m ruyijs.examples datadome`).\n"
                "> Offline replay and device-check scripts and their captured data are not distributed.\n\n"
                + readme.read_text(encoding="utf-8"), encoding="utf-8")


class PlatformWheel(bdist_wheel):
    def finalize_options(self):
        super().finalize_options()
        self.root_is_pure = False
        self.plat_name = "win_amd64"

    def get_tag(self):
        return "py3", "none", "win_amd64"


setup(distclass=PlatformDistribution,
      cmdclass={"build_py": BuildPython, "bdist_wheel": PlatformWheel})
