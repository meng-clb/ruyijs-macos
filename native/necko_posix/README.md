# Native Linux standalone Necko adapter

Ported from Starktomy's Linux runtime (pull request #5).

On Linux the shell's HTTP(S) requests go through the same standalone Necko Python
adapter the Windows runtime ships: the `necko` and `ruyijs_necko` packages of the
runtime archive `runtime.json` pins. `tools/build_necko_linux.py` downloads that
archive, checks its SHA-256 and extracts the two packages unchanged into the helper
environment `vendor/necko-derived/python` (not tracked), except for the Linux
patches below; the original file hashes are written to `build/necko/upstream.json`.
`ruyijs_necko/oneshot.py` is `src/resource_network/necko_oneshot.py`, as
`tools/build.py` installs it on Windows and macOS. Mozilla-derived modules retain
their MPL 2.0 notices and license documents. Windows DLLs and the embedded Windows
Python are never loaded on Linux.

The upstream native `necko_core.dll` source was not present in this checkout or
the release archive. `src/` is a new Linux implementation of the ABI consumed by
the upstream Python adapter. It uses POSIX sockets, NSS 3.131/NSPR 4.40 from the
Firefox 159 source tree, and a bounded Brotli decoder (`src/brotli.cpp` over the
Brotli 1.2.0 sources in `vendor/compression-native`). TLS I/O, verification and
certificate decompression use the upstream callbacks. NSS constructs and
processes the TLS records; OpenSSL is not used for the client TLS connection.

The platform changes to the upstream Python, applied as exact text edits by
`tools/build_necko_linux.py` (a changed upstream file fails the build):

- `ruyijs_necko/brotli_native.py` loads the ELF decoder exported by
  `necko/libnecko_core.so` instead of `ruyijs_brotli.dll` on Linux.
- `ruyijs_necko/launch.py` launches resolver helpers with the private Linux
  interpreter rather than `python/python.exe`.
- `ruyijs_necko/connection_lifetime.py` accepts and closes the selector passed
  by the upstream HTTP/3 pump, fixing its cleanup argument mismatch.
- `necko/_http3.py` carries the selected Firefox version into the native bridge,
  which chooses the transport-parameter style from it.

HTTP/2, connection control, strict decoding, request budgets, roots, profile data
and certificate/hostname checks retain the upstream Python implementation.
The C++ runtime retains its resource/Cookie owner and bounded helper session
pool, and starts the helper the way it does on macOS
(`src/resource_network/necko_helper.cpp`).

`quic/` implements the upstream native JSON ABI using Neqo 0.32.0 and nss-rs
0.16.1 from the Firefox donor. `build/necko-quic/neqo-upstream.json` records the
original source hashes; `quic/Cargo.lock` pins dependencies. The build uses local
source copies and two small embedding ports and a per-connection
transport-parameter encoding option to configure the owned NSS socket before the
handshake. The original donor is unchanged. Neqo still implements the QUIC and
HTTP/3 protocols; the bridge owns UDP attachment, bounded calls and output frames.
Firefox 100–159 profiles can use HTTP/3, including NSS-randomized legacy
transport parameter ordering and the older draft version_information ID.
WebTransport uses native Neqo sessions, streams/datagrams, groups/order,
statistics and TLS exporters. The upstream alternative-route race can fall back
to HTTP/2/TCP. This is not a complete Gecko/Necko build. Functional profile
selection does not by itself prove identical ClientHellos to every Windows
Firefox release.

Build with Python 3.14+:

```
python3 tools/build_necko_linux.py --firefox-source /path/to/firefox --http3
```

All generated libraries, source copies and private Python dependencies remain
under this checkout. `build/necko` contains the NSS/NSPR build; the Firefox
source tree is unchanged. Linux wheels include a relocatable private CPython
helper, these adapters and NSS/Neqo (`tools/bundle_linux.py`); build the helper
before packaging.
