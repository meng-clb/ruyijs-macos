"""The installed macOS wheel must resolve its packaged Necko libraries."""

import os
from pathlib import Path
import unittest
from unittest.mock import patch

from ruyijs._runtime_paths import get_runtime_path
from necko.closed_route import _core_library_path, _quic_library_path
from necko.core_client import library_path
from ruyijs_necko.webtransport_connection import _library_path as webtransport_library_path


@unittest.skipUnless(os.sys.platform == "darwin", "macOS wheel contract")
class TestInstalledNativeLibraries(unittest.TestCase):
    def test_core_and_quic_resolve_without_machine_paths(self):
        root = get_runtime_path() / "dist" / "necko"
        core = root / "libnecko_core.dylib"
        quic = root / "libnecko_quic.dylib"
        self.assertTrue(core.is_file(), f"missing packaged core library: {core}")
        self.assertTrue(quic.is_file(), f"missing packaged QUIC library: {quic}")
        with patch.dict(os.environ, {"NECKO_CORE_LIBRARY": "", "NECKO_QUIC_LIBRARY": ""}):
            self.assertEqual(Path(_core_library_path()).resolve(), core.resolve())
            self.assertEqual(Path(library_path()).resolve(), core.resolve())
            self.assertEqual(Path(_quic_library_path()).resolve(), quic.resolve())
            self.assertEqual(Path(webtransport_library_path()).resolve(), quic.resolve())


if __name__ == "__main__":
    unittest.main()
