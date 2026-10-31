"""Tests for macOS Web Worker and SharedWorker IPC."""

import time
import unittest
from ruyijs import Context


class TestWorkerIPC(unittest.TestCase):
    def test_dedicated_worker_echo(self):
        ctx = Context()
        code = """
        const blob = new Blob([
            'self.onmessage = function(e) { self.postMessage("echo: " + e.data); };'
        ], { type: 'application/javascript' });
        const url = URL.createObjectURL(blob);
        const w = new Worker(url);
        globalThis.received = null;
        w.onmessage = function(e) {
            globalThis.received = e.data;
        };
        w.postMessage("ping-macos-arm64");
        """
        ctx.eval(code)
        for _ in range(10):
            ctx.advance(100)
            if ctx.eval("globalThis.received") is not None:
                break
            time.sleep(0.05)
        self.assertEqual(ctx.eval("globalThis.received"), "echo: ping-macos-arm64")

    def test_worker_bidirectional_numbers(self):
        ctx = Context()
        code = """
        const blob = new Blob([
            'self.onmessage = function(e) { self.postMessage(e.data * 2); };'
        ], { type: 'application/javascript' });
        const url = URL.createObjectURL(blob);
        const w = new Worker(url);
        globalThis.sum = 0;
        w.onmessage = function(e) {
            globalThis.sum += e.data;
        };
        w.postMessage(21);
        """
        ctx.eval(code)
        for _ in range(10):
            ctx.advance(100)
            if ctx.eval("globalThis.sum") != 0:
                break
            time.sleep(0.05)
        self.assertEqual(ctx.eval("globalThis.sum"), 42)


if __name__ == "__main__":
    unittest.main()
