<div align="center">

# 🦊 ruyiJS

### Run any site's JavaScript from Python — with the real Firefox engine.

**A new-generation, minimalist browser purpose-built for AI-driven automation.**<br>
The authentic Firefox JavaScript engine and networking stack, with no window and no renderer —<br>
made for web scraping, JS reverse engineering, data collection, and getting past bot checks.

[![PyPI](https://img.shields.io/pypi/v/ruyijs?label=pypi&color=111111&logo=pypi&logoColor=white)](https://pypi.org/project/ruyijs/) [![macOS](https://img.shields.io/badge/macOS-Apple%20Silicon%20%7C%20Intel-000000?logo=apple&logoColor=white)](https://github.com/meng-clb/ruyijs-macos) [![Python](https://img.shields.io/badge/Python-%E2%89%A53.10-111111?logo=python&logoColor=white)](https://pypi.org/project/ruyijs/) [![License](https://img.shields.io/badge/license-Source%20Available-111111)](LICENSE) [![Windows](https://img.shields.io/badge/Windows%20x64-0078D4?logo=windows&logoColor=white)](https://pypi.org/project/ruyijs/) [![LinuxDO](https://img.shields.io/badge/LinuxDO-community-FFB003?logo=discourse&logoColor=white)](https://linux.do/t/topic/3078486)

<sub>Sponsored by</sub>

<a href="https://www.fastaitoken.com"><img src="assets/sponsor-fastaitoken.png" height="42" alt="FastAIToken"></a>

**[Install](#-installation)** &nbsp;·&nbsp; **[Features](#-features)** &nbsp;·&nbsp; **[Verification systems](#-verification-systems-it-defeats)** &nbsp;·&nbsp; **[Examples](#-examples)** &nbsp;·&nbsp; **[FAQ](#-faq--troubleshooting)** &nbsp;·&nbsp; **[Contact](#-contact)** &nbsp;·&nbsp; **[LinuxDO](https://linux.do/t/topic/3078486)** &nbsp;·&nbsp; **English** · [简体中文](README.zh-CN.md)

> **⚠️ Disclaimer:** This project is for researching next-generation AI browsers. Any form of brute-force reverse engineering is strictly rejected. The source code is fully open-source. Unauthorized commercial use is prohibited.

<br>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/architecture-dark.svg">
  <img src="assets/architecture.svg" width="880" alt="ruyiJS architecture: your Python code drives a ruyiJS Context — an isolated process holding the SpiderMonkey JS engine, 38 browser contexts, and the Necko network stack — which talks to the target site.">
</picture>

</div>

<br>

## Is ruyiJS for you?

Headless Chrome and Playwright hand you a whole browser: a GPU-rendering, window-managing, memory-hungry process that anti-bot vendors have spent years learning to detect. ruyiJS takes the opposite path — it embeds only the Firefox internals that matter for automation and leaves the rest behind:

- **The real engine, not an impersonation.** Genuine SpiderMonkey (Firefox 159) and the Necko network stack execute a site's JavaScript, challenges, signatures, and fingerprints exactly as Firefox would.
- **Truly headless.** No window, no layout, no renderer. A pure JavaScript + Web API environment that starts fast and stays light.
- **Isolated and reproducible.** Each `Context` is its own process with a persistent JavaScript world and its own proxy, so sessions never leak into each other.
- **Offline when you need it.** Serve scripts and responses yourself and replay a whole captured flow with no network.

If you scrape, reverse-engineer web JavaScript, or collect data behind a challenge, it's for you. If a plain HTTP client already gets your pages, you don't need it.

Runs on **Windows x64** with **Python 3.10+** (verified on Python 3.14). The wheel bundles the pinned native runtime, so there's nothing else to download.

## 🍎 macOS Native Quickstart (Apple Silicon & Intel)

This repository is a **full native macOS port** (Apple Silicon M1/M2/M3/M4 & Intel x86_64):
- **Native Engine**: Pinned Firefox 159 SpiderMonkey runtime (`dist/js` and `libmozglue.dylib`);
- **Native Network Worker**: Embedded Go concurrent network worker `dist/ghostfox-worker` with automatic transparent decompression (gzip/deflate) and HTTP/HTTPS proxy support;
- **Fully Validated**: 100% pass on CreepJS (all 23 fingerprint sections), 100% automated bypass on DataDome plv2 + plv3 interstitial challenge.

### 1. Installation on macOS
Clone this repository and install the Python SDK in editable mode:
```sh
git clone https://github.com/meng-clb/ruyijs-macos.git
cd ruyijs-macos
pip install -e .
```

### 2. Python Quickstart
```python
from ruyijs import Context

with Context() as ctx:
    # Basic JS execution
    print(ctx.eval("1 + 1"))  # 2

    # DOM manipulation
    ctx.eval('document.body.innerHTML = "<h1>Hello macOS ruyiJS</h1>"')
    print(ctx.eval('document.querySelector("h1").textContent'))

    # Network requests (async fetch)
    ctx.eval("""
        (async () => {
            const resp = await fetch('https://httpbin.org/get');
            window.data = await resp.json();
        })();
    """)
    ctx.advance(200)  # advance event loop to complete network task
    print(ctx.eval("window.data.url"))
```

### 3. Running Production Examples
```sh
# Run CreepJS full fingerprint verification (0 failures, ~3s)
python examples/creepjs/creepjs.py --direct

# Run DataDome interstitial device-check (Mouser)
python examples/DataDome/datadome.py --direct

# Run Akamai BM3 verification
python examples/akamai/akamai.py --direct
```

## 📦 Installation (Windows x64)

```sh
python -m pip install ruyijs
```

**Requirements:** Python 3.10+ on Windows x64 (64-bit). Verified on Python 3.10 – 3.14.

The wheel ships the SHA256-pinned SpiderMonkey + Necko runtime (~42 MB). Local scripts run offline right after install — no browser download, no external dependencies.

To upgrade:
```sh
python -m pip install --upgrade ruyijs
```

To verify the installation:
```python
import ruyijs
print(ruyijs.__version__)   # 0.1.6
```

## 🚀 Quick start

**1 · Open a context and run JavaScript.** Variables and functions persist across `eval` calls within the same context.

```python
from ruyijs import Context

with Context() as context:
    context.eval("let count = 40")
    print(context.eval("count += 2"))        # 42
    print(context.eval("navigator.userAgent"))
```

**3 · Point it at a real target.** Configure the environment, load the page, and let the site's own JavaScript mint whatever token it demands.

```python
with Context(proxy="http://127.0.0.1:7890") as context:
    context.configure_fingerprint({
        "navigator": {"language": "zh-CN", "hardwareConcurrency": 8},
        "locale": {"timezone": "Asia/Shanghai"},
    })
    context.load_page("https://target.example/", html)
    token = context.eval("window.__sign(payload)")   # run the page's signer
    print(token)
```

## 🏗️ How it fits together

```
Python  ──►  ruyiJS Context (isolated process)  ──►  Target site
                 ├─ SpiderMonkey — Firefox 159 JS engine
                 ├─ 38 browser contexts — DOM · Canvas · Workers · iframes · …
                 └─ Necko — HTTP/1.1 · 2 · 3, per-context proxy
```

Your Python code drives a `Context`. Inside it, the genuine SpiderMonkey engine runs the page's scripts against a real DOM and 38 bounded browser subsystems, while in-page `fetch`/XHR ride the Necko transport. The implementation lives under [`src/`](src) (domain, application, and every browser subsystem) and [`python/ruyijs/`](python/ruyijs) (the binding).

## ✨ Features

### Run a site's JavaScript

Execute scripts in a persistent context, load real HTML with iframes and classic scripts, and query the resulting DOM. References to live JS objects come back as `JSObject` / `JSFunction` you can call from Python.

| Capability | How |
| :-- | :-- |
| Execute JS, keep state | `context.eval(src)` — variables and functions persist |
| Get a callable back | `context.eval(src, to_py=False)` → `JSFunction` |
| Load a page | `context.load_page(url, html)` — relative URLs resolve against `url` |
| Top-level navigation | `context.navigate(url)` — no Referer, `Sec-Fetch-Site: none` |
| Query the DOM | `context.eval("document.querySelector('#x').textContent")` |

```python
with Context() as context:
    context.set("config", {"offset": 2})
    add = context.eval("(value) => value + config.offset", to_py=False)
    print(add(40))  # 42
```

### Configure the browser environment

Set Navigator, Screen, viewport, timezone, and locale through one validated profile surface. Commit it before the first page script runs.

```python
with Context() as context:
    context.configure_fingerprint({
        "navigator": {"language": "zh-CN", "hardwareConcurrency": 8},
        "screen": {"width": 1920, "height": 1080},
        "viewport": {"width": 1280, "height": 720},
        "locale": {"timezone": "Asia/Shanghai"},
    })
    print(context.eval("[navigator.language, screen.width]"))  # ['zh-CN', 1920]
```

### Native network over Necko

In-page `fetch` and XHR ride real HTTP/1.1, 2, and 3, through a proxy scoped to the context. Serve responses yourself with `put_resource()` to replay an entire captured flow offline. Inspect every request with `net_log()`.

### Native TLS fingerprint — switchable across Firefox 100 – 159

The network stack is Firefox's own **Necko + NSS** (the same TLS library real Firefox uses). The TLS ClientHello — cipher suites, extensions, ALPN, key shares, and their ordering — is produced by the real NSS library, not an emulation, so bot-detection systems that inspect TLS cannot distinguish ruyiJS traffic from a genuine Firefox session.

The Necko transport can **freely switch between Firefox 100 – 159 TLS profiles**. Each profile reproduces that version's exact ClientHello, giving you a different JA3 / JA4 fingerprint on the wire — useful for rotating browser identities, evading per-version blocks, or testing how a site reacts to different Firefox releases.

```python
with Context(proxy="http://127.0.0.1:7890", timeout=30) as context:
    context.load_page("https://example.com/", "")
    context.eval("globalThis.r = null; fetch('/api').then(x => x.json()).then(v => r = v)")
    context.advance(25)               # drive the event loop until it settles
    print(context.eval("r"))
```

### Python ↔ JavaScript bridge

Pass data in with `set()`, get callable JS functions out, and expose Python functions to the running script. Workers, Service Workers, and iframes are included.

```python
with Context() as context:
    context.expose(lambda a, b: a + b, "add")
    print(context.eval("add(20, 22)"))  # 42
```

### Deterministic clock

Drive timers with a logical clock for perfectly reproducible runs, or use the system clock for live work. The host advances time explicitly.

```python
with Context() as context:
    context.configure_clock("logical", epoch_ms=1700000000000)
    context.eval("globalThis.result = 0; setTimeout(() => { result = 42 }, 10)")
    context.advance(10)
    print(context.eval("result"))  # 42
```

### Errors and logs

JavaScript exceptions surface as `JSError` with name, message, and stack. `console_log()` and `net_log()` return the captured console and network records.

```python
from ruyijs import Context, JSError

with Context(timeout=10) as context:
    try:
        context.eval("throw new TypeError('bad input')", filename="demo.js")
    except JSError as error:
        print(error.name, error.message)  # TypeError bad input
        print(error.stack)
```

## 🛡️ Verification systems it defeats

Each example drives the site's own JavaScript to produce the parameters it demands, then completes the flow end to end. All ship runnable in the package: `python -m ruyijs.examples <name>`.

| System | Category | Example |
| :-- | :-- | :-- |
| **Akamai Bot Manager 3.x** | sensor_data + sbsd challenge | `akamai` |
| **DataDome** | Interstitial device-check (plv2 + plv3) | `datadome` |
| **CreepJS** | Fingerprint audit — passes every section | `creepjs` |

> 🔒 **Strictly prohibited for any unlawful use.** ruyiJS is provided **solely for research into a new generation of AI browsers.** Live results depend on current network conditions and each site's present responses.

## 🧪 Examples

Examples ship inside the package — no need to clone the repo:

```sh
python -m ruyijs.examples                      # list every example and its install path
python -m ruyijs.examples akamai               # Akamai Bot Manager 3.x
python -m ruyijs.examples datadome             # DataDome interstitial device-check
python -m ruyijs.examples creepjs              # CreepJS fingerprint audit
```

Every example supports `--direct` (direct connection) and `--proxy http://127.0.0.1:7890`. Add `--help` after a name for all options, and `--output result.json` to save results. Each example directory ships its own README.

## 📚 Documentation & API

| | |
| :-- | :-- |
| **`Context.eval` / `set` / `expose`** | Execute JS, pass data in, expose Python callbacks |
| **`load_page` / `navigate` / `put_resource`** | Load HTML, top-level navigation, serve resources offline |
| **`configure_fingerprint` / `configure_environment`** | Navigator, Screen, viewport, timezone, locale |
| **`configure_clock` / `advance` / `tick`** | Logical vs. system clock, drive the event loop |
| **`JSError` / `console_log` / `net_log`** | Errors as exceptions, console and network records |
| **`JSObject` / `JSFunction` / `get_runtime_path`** | Live JS handles, bundled-runtime path |

## 📏 Scope & limitations

ruyiJS provides JavaScript execution and a broad Web API environment on **Windows x64**. It has **no browser window and no full page layout or rendering** — it is a tool for automation, analysis, and research. Use it in compliance with the terms of service of any site you interact with and with applicable law.

**Related:** [**ruyiHttp**](https://gitee.com/losenine888/ruyiHttp) — a Requests-style Python HTTP library built on Firefox's native networking components.

## ❓ FAQ / Troubleshooting

<details>
<summary><b>What Python versions are supported?</b></summary>

Python 3.10 and above on Windows x64 (64-bit). Tested up to Python 3.14.
</details>

<details>
<summary><b>Does it work on macOS or Linux?</b></summary>

**Fully supported on macOS natively!** This repository (`ruyijs-macos`) is dedicated to macOS native Apple Silicon (arm64) and Intel (x86_64) platforms, featuring complete native Clang runtime builds, POSIX IPC, and transparent network decompression.
</details>

<details>
<summary><b>Do I need to download a browser?</b></summary>

No. The wheel bundles the pinned SpiderMonkey + Necko runtime. Everything works offline right after `pip install ruyijs`.
</details>

<details>
<summary><b>Context hangs or doesn't respond</b></summary>

- Make sure you use the `with` statement (`with Context() as ctx:`) so the process is cleaned up properly.
- If using a proxy, verify it is reachable: `context = Context(proxy="http://127.0.0.1:7890")`.
- Increase the timeout: `Context(timeout=60)`.
- On Wine, upgrade to ≥ 0.1.5 which fixes a known navigate deadlock.
</details>

<details>
<summary><b>JSError: script error</b></summary>

The site's JavaScript threw an exception. Inspect `error.name`, `error.message`, and `error.stack` to locate the cause. If the page relies on APIs not yet implemented, the stack trace will point to the missing call.
</details>

<details>
<summary><b>How do I use a proxy?</b></summary>

```python
with Context(proxy="http://127.0.0.1:7890") as ctx:
    ctx.navigate("https://example.com/")
```

HTTP, HTTPS, and SOCKS5 proxies are supported per-context.
</details>

<details>
<summary><b>How do I run examples?</b></summary>

```sh
python -m ruyijs.examples              # list all examples
python -m ruyijs.examples akamai --proxy http://127.0.0.1:7890
python -m ruyijs.examples creepjs
```
</details>

## 💬 Contact

Questions, permission requests, commercial licensing, or just to talk shop — add the author on WeChat, or scan to join the discussion group.

<table>
<tr>
<td align="center"><img src="assets/wechat-qr.jpg" alt="WeChat QR — 如意" width="220"><br><b>WeChat:</b> 如意</td>
<td align="center"><img src="assets/wechat-group-qr.jpg" alt="Group — AI 浏览器交流群" width="220"><br><b>Group:</b> AI 浏览器交流群</td>
</tr>
</table>

> The group QR refreshes periodically; if it has expired, add the author on WeChat (如意) for an invite.

## 📄 License

Licensed under the **[ff-ruyijs Source Available License v1.0](LICENSE)**.

- ✅ Free for personal learning, research, and non-commercial use
- ✅ Modifications **must be open-sourced** when distributed
- ❌ Commercial use **requires written authorization** from the author

To request a commercial license, contact via WeChat (ID: **如意**) or open an issue on [GitHub](https://github.com/cutetailbud/ff-ruyijs).

See [`NOTICE`](NOTICE) for third-party attributions.

If ff-ruyijs saved you from reimplementing a browser, a ⭐ helps others find it.
