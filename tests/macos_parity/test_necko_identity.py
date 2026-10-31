"""Verify native Firefox Necko/NSS stack identity on macOS arm64.

Ensures no curl_cffi or external mock library is in use.
"""

import os
import subprocess
import unittest
from pathlib import Path
from ruyijs import Context


class TestNeckoIdentity(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[2]

    def test_no_curl_cffi_imported_or_present(self):
        """Ensure curl_cffi is completely banished from ruyijs repository and runtime."""
        # 1. Grep python/ and src/ for curl_cffi
        res = subprocess.run(
            ["grep", "-rnw", "--include=*.py", "--include=*.cpp", "--include=*.h", "curl_cffi", str(self.root / "python"), str(self.root / "src")],
            capture_output=True, text=True
        )
        self.assertEqual(res.stdout.strip(), "", f"Forbidden curl_cffi found in code:\n{res.stdout}")

        # 2. Check vendor/necko-derived/python
        helper_site = self.root / "vendor/necko-derived/python"
        curl_cffi_dirs = list(helper_site.glob("**/curl_cffi*"))
        self.assertEqual(len(curl_cffi_dirs), 0, f"curl_cffi directory found in helper venv: {curl_cffi_dirs}")

    def test_xpcshell_donor_binary_validity(self):
        """Verify xpcshell executable is arm64 Mach-O and runnable."""
        xpcshell = os.environ.get("RUYIJS_XPCSHELL") or "/Users/ameng/Desktop/firefox-src/firefox-159.0/obj-necko/dist/bin/xpcshell"
        self.assertTrue(os.path.isfile(xpcshell), f"xpcshell missing at {xpcshell}")

        res = subprocess.run(["file", xpcshell], capture_output=True, text=True)
        self.assertIn("Mach-O 64-bit", res.stdout)
        self.assertIn("arm64", res.stdout)

    def test_native_fetch_headers_and_status(self):
        """Perform real HTTP fetch and verify response matches Firefox Necko."""
        ctx = Context()
        code = """
        globalThis.resp = null;
        globalThis.error = null;
        fetch("https://httpbin.org/get").then(r => r.json()).then(data => {
            globalThis.resp = data;
        }).catch(e => {
            globalThis.error = e.message;
        });
        """
        ctx.eval(code)
        # Advance loop for response
        for _ in range(30):
            ctx.advance(200)
            if ctx.eval("globalThis.resp") is not None or ctx.eval("globalThis.error") is not None:
                break

        err = ctx.eval("globalThis.error")
        self.assertIsNone(err, f"Fetch failed with error: {err}")

        resp = ctx.eval("globalThis.resp")
        self.assertIsNotNone(resp, "Fetch did not return response")
        headers = resp.get("headers", {})
        ua = headers.get("User-Agent", "")
        self.assertIn("Firefox/159.0", ua, f"Unexpected User-Agent: {ua}")


if __name__ == "__main__":
    unittest.main()
