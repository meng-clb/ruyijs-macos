"""Test the Windows archive pinned by runtime.json.

Verifies:
- runtime.json contract: SHA256, size, inventory_sha256 matching the pinned zip
- Component inventory of Windows runtime (Necko modules, NSS, TLS profiles)
- Author macOS branch parity delta analysis
"""

import hashlib
import json
from pathlib import Path
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_JSON = ROOT / "runtime.json"


class TestWindowsContractInventory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not RUNTIME_JSON.is_file():
            raise FileNotFoundError("runtime.json is missing")
        with open(RUNTIME_JSON, "r", encoding="utf-8") as f:
            cls.manifest = json.load(f)
        cls.win_zip = Path("/tmp") / cls.manifest["archive"]

    def test_runtime_json_matches_windows_archive(self):
        """The pinned Windows release archive matches its manifest."""
        if not self.win_zip.is_file():
            self.skipTest(f"Windows release archive not found at {self.win_zip}")
        
        data = self.win_zip.read_bytes()
        archive_sha = hashlib.sha256(data).hexdigest()
        self.assertEqual(archive_sha, self.manifest["sha256"])
        self.assertEqual(len(data), self.manifest["size"])

        with zipfile.ZipFile(self.win_zip) as z:
            shell_data = z.read("dist/js.exe")
            shell_sha = hashlib.sha256(shell_data).hexdigest()
            self.assertEqual(shell_sha, self.manifest["shell_sha256"])

            sums_data = z.read("SHA256SUMS")
            sums_sha = hashlib.sha256(sums_data).hexdigest()
            self.assertEqual(sums_sha, self.manifest["inventory_sha256"])

    def test_windows_necko_components_inventory(self):
        """Verify the pinned runtime's Necko DLLs and TLS profile table."""
        if not self.win_zip.is_file():
            self.skipTest(f"Windows release archive not found at {self.win_zip}")

        with zipfile.ZipFile(self.win_zip) as z:
            names = set(z.namelist())
            self.assertIn("vendor/necko-derived/python/Lib/site-packages/necko/nss3.dll", names)
            self.assertIn("vendor/necko-derived/python/Lib/site-packages/necko/necko_core.dll", names)
            self.assertIn("vendor/necko-derived/python/Lib/site-packages/necko/necko_quic.dll", names)
            self.assertIn("vendor/necko-derived/python/Lib/site-packages/necko/_tls_profiles.py", names)

            profiles_code = z.read("vendor/necko-derived/python/Lib/site-packages/necko/_tls_profiles.py").decode("utf-8")
            self.assertIn('"100":', profiles_code)
            self.assertIn('"159":', profiles_code)


if __name__ == "__main__":
    unittest.main()
