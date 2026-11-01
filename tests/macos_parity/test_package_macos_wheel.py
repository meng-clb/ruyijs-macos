"""The checked-in wheel builder must reject incomplete native runtimes."""

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import package_macos_wheel as package
from macos_runtime import NSS_FILES


class TestWheelInputs(unittest.TestCase):
    def test_missing_quic_library_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in package.REQUIRED_RUNTIME:
                if name.endswith("libnecko_quic.dylib"):
                    continue
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            with patch.object(package, "ROOT", root):
                with self.assertRaisesRegex(FileNotFoundError, "libnecko_quic.dylib"):
                    package.verify_inputs(root / "absent-donor")

    def test_no_xpcshell_build_uses_staged_nss(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in package.REQUIRED_RUNTIME:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            for name in NSS_FILES:
                (root / "dist" / "necko_tls" / name).touch()
            with patch.object(package, "ROOT", root):
                package.verify_inputs(root / "absent-donor")


if __name__ == "__main__":
    unittest.main()
