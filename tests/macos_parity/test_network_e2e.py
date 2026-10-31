"""End-to-end network parity test for macOS native Necko/NSS transport."""

import gzip
import unittest
from ruyijs import Context


class TestNetworkE2E(unittest.TestCase):
    def test_http_get_json(self):
        ctx = Context()
        ctx.eval("""
        globalThis.result = null;
        globalThis.err = null;
        fetch("https://httpbin.org/get?foo=bar").then(r => r.json()).then(data => {
            globalThis.result = data;
        }).catch(e => {
            globalThis.err = e.message;
        });
        """)
        for _ in range(30):
            ctx.advance(200)
            if ctx.eval("globalThis.result") is not None or ctx.eval("globalThis.err") is not None:
                break
        self.assertIsNone(ctx.eval("globalThis.err"))
        res = ctx.eval("globalThis.result")
        self.assertEqual(res.get("args", {}).get("foo"), "bar")

    def test_redirect_302(self):
        ctx = Context()
        ctx.eval("""
        globalThis.resUrl = null;
        fetch("https://httpbin.org/redirect/1").then(r => {
            globalThis.resUrl = r.url;
        });
        """)
        for _ in range(30):
            ctx.advance(200)
            if ctx.eval("globalThis.resUrl") is not None:
                break
        url = ctx.eval("globalThis.resUrl")
        self.assertIn("/get", url)

    def test_gzip_compression_decompressed_cleanly(self):
        ctx = Context()
        ctx.eval("""
        globalThis.gzipped = null;
        fetch("https://httpbin.org/gzip").then(r => r.json()).then(data => {
            globalThis.gzipped = data.gzipped;
        });
        """)
        for _ in range(30):
            ctx.advance(200)
            if ctx.eval("globalThis.gzipped") is not None:
                break
        self.assertTrue(ctx.eval("globalThis.gzipped"))


if __name__ == "__main__":
    unittest.main()
