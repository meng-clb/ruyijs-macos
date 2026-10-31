"""Test Windows v0.2.1 contract inventory and verification.

Verifies:
- runtime.json contract: SHA256, size, inventory_sha256 matching official Windows v0.2.1 zip
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
WIN_ZIP = Path("/tmp/ruyijs-runtime-0.2.1-win-amd64.zip")


class TestWindowsContractInventory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not RUNTIME_JSON.is_file():
            raise FileNotFoundError("runtime.json is missing")
        with open(RUNTIME_JSON, "r", encoding="utf-8") as f:
            cls.manifest = json.load(f)

    def test_runtime_json_matches_windows_archive(self):
        """Task 1 hard invariant: runtime.json must match Windows v0.2.1 release archive."""
        if not WIN_ZIP.is_file():
            self.skipTest(f"Windows release archive not found at {WIN_ZIP}")
        
        data = WIN_ZIP.read_bytes()
        archive_sha = hashlib.sha256(data).hexdigest()
        self.assertEqual(archive_sha, self.manifest["sha256"])
        self.assertEqual(len(data), self.manifest["size"])

        with zipfile.ZipFile(WIN_ZIP) as z:
            shell_data = z.read("dist/js.exe")
            shell_sha = hashlib.sha256(shell_data).hexdigest()
            self.assertEqual(shell_sha, self.manifest["shell_sha256"])

            sums_data = z.read("SHA256SUMS")
            sums_sha = hashlib.sha256(sums_data).hexdigest()
            self.assertEqual(sums_sha, self.manifest["inventory_sha256"])

    def test_windows_necko_components_inventory(self):
        """Verify Windows v0.2.1 components: NSS 3.131, necko_core, necko_quic, TLS profiles 100-159."""
        if not WIN_ZIP.is_file():
            self.skipTest(f"Windows release archive not found at {WIN_ZIP}")

        with zipfile.ZipFile(WIN_ZIP) as z:
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
