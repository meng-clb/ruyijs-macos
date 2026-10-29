<div align="center">

# 🦊 ruyiJS

### 在 Python 里跑任意站点的 JavaScript —— 用真正的 Firefox 引擎。

**新一代、专为 AI 驱动打造的极简浏览器。**<br>
原生的 Firefox JavaScript 引擎与网络栈，没有窗口、没有渲染器 ——<br>
专为网页抓取、JS 逆向、数据采集与绕过人机验证而生。

[![PyPI](https://img.shields.io/pypi/v/ruyijs?label=pypi&color=111111&logo=pypi&logoColor=white)](https://pypi.org/project/ruyijs/) [![macOS](https://img.shields.io/badge/macOS-Apple%20Silicon%20%7C%20Intel-000000?logo=apple&logoColor=white)](https://github.com/meng-clb/ruyijs-macos) [![Python](https://img.shields.io/badge/Python-%E2%89%A53.10-111111?logo=python&logoColor=white)](https://pypi.org/project/ruyijs/) [![License](https://img.shields.io/badge/license-Source%20Available-111111)](LICENSE) [![Windows](https://img.shields.io/badge/Windows%20x64-0078D4?logo=windows&logoColor=white)](https://pypi.org/project/ruyijs/) [![LinuxDO](https://img.shields.io/badge/LinuxDO-社区-FFB003?logo=discourse&logoColor=white)](https://linux.do/t/topic/3078486)

<sub>赞助商</sub>

<a href="https://www.fastaitoken.com"><img src="assets/sponsor-fastaitoken.png" height="42" alt="FastAIToken"></a>

**[安装](#-安装)** &nbsp;·&nbsp; **[功能](#-功能)** &nbsp;·&nbsp; **[攻克的验证系统](#-攻克的验证系统)** &nbsp;·&nbsp; **[示例](#-运行示例)** &nbsp;·&nbsp; **[FAQ](#-常见问题)** &nbsp;·&nbsp; **[联系](#-联系方式)** &nbsp;·&nbsp; **[LinuxDO](https://linux.do/t/topic/3078486)** &nbsp;·&nbsp; [English](README.md) · **简体中文**

> **⚠️ 声明：** 本项目用于研究新一代 AI 浏览器，拒绝任何形式的暴力逆向破解。源码全部开源，禁止未经授权的商业化用途。

<br>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/architecture-dark.svg">
  <img src="assets/architecture.svg" width="880" alt="ruyiJS 架构：你的 Python 代码驱动一个 ruyiJS Context —— 独立进程，内含 SpiderMonkey JS 引擎、38 个浏览器上下文与 Necko 网络栈 —— 再与目标站点通信。">
</picture>

</div>

<br>

## ruyiJS 适合你吗？

Headless Chrome 和 Playwright 给你的是一整个浏览器：一个负责 GPU 渲染、管理窗口、吃内存的进程，而反爬厂商已经花了多年时间学习如何识别它。ruyiJS 走的是相反的路 —— 只嵌入与自动化真正相关的 Firefox 内核，其余一概不要：

- **原生引擎，而非模仿。** 货真价实的 SpiderMonkey（Firefox 159）与 Necko 网络栈，会像 Firefox 一样原样执行站点的 JavaScript、challenge、签名与指纹。
- **真正无头。** 没有窗口、没有布局、没有渲染器。纯 JavaScript + Web API 环境，启动快、占用低。
- **隔离且可复现。** 每个 `Context` 都是独立进程，拥有持续保存的 JavaScript 世界与自己的代理，会话之间互不干扰。
- **需要时可离线。** 自己提供脚本与响应，无网络也能复跑整条已捕获的流程。

如果你做网页抓取、逆向 Web JavaScript，或采集 challenge 背后的数据，它就适合你。如果普通 HTTP 客户端已经能拿到页面，那就不需要它。

运行于 **Windows x64**，需要 **Python 3.10+**（已在 Python 3.14 下验证）。wheel 内置锁定版原生运行时，无需再下载任何东西。

## 🍎 macOS 原生使用指南 (Apple Silicon & Intel)

本项目已实现 **macOS 原生架构完整移植**（原生支持 Apple Silicon M1/M2/M3/M4 系列与 Intel x86_64）：
- **原生引擎**：基于 Firefox 159 原生编译的 SpiderMonkey 运行时（`dist/js` 与 `libmozglue.dylib`）；
- **原生网络 Worker**：集成 Go 编写的高性能并发 `dist/ghostfox-worker`，支持自动透明解压 gzip/deflate 与 HTTP/HTTPS 代理；
- **全量测试通过**：实测 CreepJS 23 项指纹检测 0 失败通过、DataDome plv2+plv3 字节码 VM 挑战 100% 自动穿透。

### 1. 快速安装 (macOS 源码模式)
在 macOS 上克隆本仓库后，直接以 editable 模式安装 Python SDK：
```sh
git clone https://github.com/meng-clb/ruyijs-macos.git
cd ruyijs-macos
pip install -e .
```

### 2. Python 快速上手
```python
from ruyijs import Context

# 启动原生沙箱环境
with Context() as ctx:
    # 基础 JS 计算
    print(ctx.eval("1 + 1"))  # 2

    # 完整 DOM 渲染
    ctx.eval('document.body.innerHTML = "<h1>Hello macOS ruyiJS</h1>"')
    print(ctx.eval('document.querySelector("h1").textContent'))

    # 网络抓取 (异步 fetch)
    ctx.eval("""
        (async () => {
            const resp = await fetch('https://httpbin.org/get');
            window.data = await resp.json();
        })();
    """)
    ctx.advance(200)  # 推进事件循环完成网络请求
    print(ctx.eval("window.data.url"))
```

### 3. 运行实战案例
```sh
# 运行 CreepJS 全量指纹测试 (23 项全通过，耗时约 3 秒)
python examples/creepjs/creepjs.py --direct

# 运行 DataDome 双层人机防护挑战 (全自动过检测拿 200 首页)
python examples/DataDome/datadome.py --direct

# 运行 Akamai BM3 挑战
python examples/akamai/akamai.py --direct
```

## 📦 安装 (Windows x64)

```sh
python -m pip install ruyijs
```

**系统要求：** Windows x64（64 位）+ Python 3.10+，已在 Python 3.10 – 3.14 下验证。

wheel 内置 SHA256 锁定的 SpiderMonkey + Necko 运行时（约 42 MB），安装后即可离线运行，无需下载浏览器，无外部依赖。

升级：
```sh
python -m pip install --upgrade ruyijs
```

验证安装：
```python
import ruyijs
print(ruyijs.__version__)   # 0.1.6
```

## 🚀 快速开始

**1 · 打开上下文，执行 JavaScript。** 同一上下文内，变量和函数在多次 `eval` 之间保留。

```python
from ruyijs import Context

with Context() as context:
    context.eval("let count = 40")
    print(context.eval("count += 2"))        # 42
    print(context.eval("navigator.userAgent"))
```

**3 · 对准真实目标。** 配置环境、加载页面，让站点自身的 JavaScript 去生成它所需的 token。

```python
with Context(proxy="http://127.0.0.1:7890") as context:
    context.configure_fingerprint({
        "navigator": {"language": "zh-CN", "hardwareConcurrency": 8},
        "locale": {"timezone": "Asia/Shanghai"},
    })
    context.load_page("https://target.example/", html)
    token = context.eval("window.__sign(payload)")   # 调用页面自己的签名函数
    print(token)
```

## 🏗️ 整体结构

```
Python  ──►  ruyiJS Context（独立进程）  ──►  目标站点
                 ├─ SpiderMonkey —— Firefox 159 JS 引擎
                 ├─ 38 个浏览器上下文 —— DOM · Canvas · Worker · iframe · …
                 └─ Necko —— HTTP/1.1 · 2 · 3，按上下文独立代理
```

你的 Python 代码驱动一个 `Context`。在其中，原生 SpiderMonkey 引擎针对真实 DOM 与 38 个受限浏览器子系统运行页面脚本，页面内的 `fetch`/XHR 走 Necko 传输。实现代码位于 [`src/`](src)（领域层、应用层与各浏览器子系统）与 [`python/ruyijs/`](python/ruyijs)（Python 绑定）。

## ✨ 功能

### 运行站点的 JavaScript

在持续保存的上下文中执行脚本，加载含 iframe 与经典脚本的真实 HTML，并查询生成的 DOM。对存活 JS 对象的引用会作为可从 Python 调用的 `JSObject` / `JSFunction` 返回。

| 功能 | 用法 |
| :-- | :-- |
| 执行 JS 并保留状态 | `context.eval(src)` —— 变量和函数持续保留 |
| 取回可调用对象 | `context.eval(src, to_py=False)` → `JSFunction` |
| 加载页面 | `context.load_page(url, html)` —— 相对地址按 `url` 解析 |
| 顶层导航 | `context.navigate(url)` —— 无 Referer，`Sec-Fetch-Site: none` |
| 查询 DOM | `context.eval("document.querySelector('#x').textContent")` |

```python
with Context() as context:
    context.set("config", {"offset": 2})
    add = context.eval("(value) => value + config.offset", to_py=False)
    print(add(40))  # 42
```

### 配置浏览器环境

通过一套带校验的 profile 接口设置 Navigator、Screen、视口、时区与区域。请在首个页面脚本运行前提交。

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

### 基于 Necko 的原生网络

页面内 `fetch` 与 XHR 走真实 HTTP/1.1、2、3，并通过按上下文隔离的代理。用 `put_resource()` 自行提供响应即可离线复跑整条已捕获的流程。用 `net_log()` 查看每一次请求。

### 原生 TLS 指纹 —— 自由切换 Firefox 100 – 159

网络栈使用 Firefox 自身的 **Necko + NSS**（与真实 Firefox 完全一致的 TLS 库）。TLS ClientHello 中的密码套件、扩展、ALPN、密钥共享及其排列顺序均由真实 NSS 库生成，而非模拟，基于 TLS 指纹检测的反爬系统无法区分 ruyiJS 与真实 Firefox 的流量。

Necko 传输层可**自由切换 Firefox 100 – 159 的 TLS 配置**，每个版本均精确复现该版本的 ClientHello，在线上呈现不同的 JA3 / JA4 指纹——可用于轮换浏览器身份、规避按版本封禁，或测试站点对不同 Firefox 版本的反应。

```python
with Context(proxy="http://127.0.0.1:7890", timeout=30) as context:
    context.load_page("https://example.com/", "")
    context.eval("globalThis.r = null; fetch('/api').then(x => x.json()).then(v => r = v)")
    context.advance(25)               # 推进事件循环直到稳定
    print(context.eval("r"))
```

### Python ↔ JavaScript 互通

用 `set()` 传入数据，取回可调用的 JS 函数，并把 Python 函数暴露给运行中的脚本。含 Worker、Service Worker 与 iframe。

```python
with Context() as context:
    context.expose(lambda a, b: a + b, "add")
    print(context.eval("add(20, 22)"))  # 42
```

### 确定性时钟

用逻辑时钟驱动定时器以获得完全可复现的运行，或用系统时钟进行实时作业。时间由宿主显式推进。

```python
with Context() as context:
    context.configure_clock("logical", epoch_ms=1700000000000)
    context.eval("globalThis.result = 0; setTimeout(() => { result = 42 }, 10)")
    context.advance(10)
    print(context.eval("result"))  # 42
```

### 错误与日志

JavaScript 异常会作为带 name、message、stack 的 `JSError` 抛出。`console_log()` 与 `net_log()` 返回已捕获的 console 和网络记录。

```python
from ruyijs import Context, JSError

with Context(timeout=10) as context:
    try:
        context.eval("throw new TypeError('bad input')", filename="demo.js")
    except JSError as error:
        print(error.name, error.message)  # TypeError bad input
        print(error.stack)
```

## 🛡️ 攻克的验证系统

每个示例都驱动站点自身的 JavaScript 生成其所需参数，再端到端完成流程。全部随包可运行：`python -m ruyijs.examples <名称>`。

| 系统 | 类型 | 示例 |
| :-- | :-- | :-- |
| **Akamai Bot Manager 3.x** | sensor_data + sbsd 挑战 | `akamai` |
| **DataDome** | interstitial device-check（plv2 + plv3） | `datadome` |
| **CreepJS** | 指纹审计 —— 全部项目通过 | `creepjs` |

> 🔒 **严禁用于任何非法用途，仅用于研究新时代 AI 浏览器。** 线上结果取决于当前网络状况与各站点的实时响应。

## 🧪 运行示例

示例随包安装，无需下载仓库：

```sh
python -m ruyijs.examples                      # 列出全部示例及其安装路径
python -m ruyijs.examples akamai               # Akamai Bot Manager 3.x
python -m ruyijs.examples datadome             # DataDome interstitial device-check
python -m ruyijs.examples creepjs              # CreepJS 指纹审计
```

示例均支持 `--direct`（直连）和 `--proxy http://127.0.0.1:7890`，在名称后加 `--help` 查看全部参数，`--output result.json` 可保存结果。各示例目录内附 README。

## 📚 文档与 API

| | |
| :-- | :-- |
| **`Context.eval` / `set` / `expose`** | 执行 JS、传入数据、暴露 Python 回调 |
| **`load_page` / `navigate` / `put_resource`** | 加载 HTML、顶层导航、离线提供资源 |
| **`configure_fingerprint` / `configure_environment`** | Navigator、Screen、视口、时区、区域 |
| **`configure_clock` / `advance` / `tick`** | 逻辑时钟 vs 系统时钟，推进事件循环 |
| **`JSError` / `console_log` / `net_log`** | 异常、console 与网络记录 |
| **`JSObject` / `JSFunction` / `get_runtime_path`** | 存活 JS 句柄、内置运行时路径 |

## 📏 使用范围与限制

ruyiJS 提供 **Windows x64** 上的 JavaScript 执行及广泛的 Web API 环境，**不含浏览器窗口，也没有完整的页面布局与渲染** —— 它是面向自动化、分析与研究的工具。请在遵守目标站点服务条款与适用法律的前提下使用。

**相关项目：** [**ruyiHttp**](https://gitee.com/losenine888/ruyiHttp) —— 基于 Firefox 原生网络组件的 Requests 风格 Python 请求库。

## ❓ 常见问题

<details>
<summary><b>支持哪些 Python 版本？</b></summary>

Windows x64（64 位）上的 Python 3.10 及以上版本，已测试至 Python 3.14。
</details>

<details>
<summary><b>支持 macOS 或 Linux 吗？</b></summary>

**macOS 原生全面支持！** 本仓库 `ruyijs-macos` 专门针对 macOS（Apple Silicon arm64 及 Intel x86_64）进行了系统级移植重构，修复了系统符号链接、IPC 通信、Apple Silicon SVE 特性以及网络透明解压。
</details>

<details>
<summary><b>需要下载浏览器吗？</b></summary>

不需要。wheel 内置了锁定版 SpiderMonkey + Necko 运行时，`pip install ruyijs` 后即可离线运行。
</details>

<details>
<summary><b>Context 卡住无响应</b></summary>

- 确保使用 `with` 语句（`with Context() as ctx:`），以正确清理进程。
- 如果使用代理，请检查代理是否可达：`Context(proxy="http://127.0.0.1:7890")`。
- 增大超时：`Context(timeout=60)`。
- 在 Wine 上运行请升级至 ≥ 0.1.5，该版本修复了已知的 navigate 死锁。
</details>

<details>
<summary><b>JSError: 脚本报错</b></summary>

站点的 JavaScript 抛出了异常。检查 `error.name`、`error.message` 和 `error.stack` 定位原因。如果页面依赖尚未实现的 API，堆栈中会指向缺失的调用。
</details>

<details>
<summary><b>如何使用代理？</b></summary>

```python
with Context(proxy="http://127.0.0.1:7890") as ctx:
    ctx.navigate("https://example.com/")
```

支持 HTTP、HTTPS、SOCKS5 代理，按上下文隔离。
</details>

<details>
<summary><b>如何运行示例？</b></summary>

```sh
python -m ruyijs.examples              # 列出全部示例
python -m ruyijs.examples akamai --proxy http://127.0.0.1:7890
python -m ruyijs.examples creepjs
```
</details>

## 💬 联系方式

二次分发、商业授权、技术交流，欢迎添加作者微信，或扫码加入交流群。

<table>
<tr>
<td align="center"><img src="assets/wechat-qr.jpg" alt="微信 — 如意" width="220"><br><b>微信：</b>如意</td>
<td align="center"><img src="assets/wechat-group-qr.jpg" alt="交流群 — AI 浏览器过检测交流群" width="220"><br><b>交流群：</b>AI 浏览器过检测交流群</td>
</tr>
</table>

> 群二维码会定期刷新；如已过期，请添加作者微信（如意）邀请入群。

## 📄 许可证

基于 **[ff-ruyijs Source Available License v1.0](LICENSE)** 发布。

- ✅ 个人学习、学术研究、非商业用途可自由使用
- ✅ 修改后分发**必须开源**完整源码
- ❌ 商业用途**必须取得作者书面授权**

商业授权请添加作者微信（**如意**）或在 [GitHub](https://github.com/cutetailbud/ff-ruyijs) 提交 issue。

第三方声明见 [`NOTICE`](NOTICE)。

如果 ff-ruyijs 帮你省下了重写一个浏览器的功夫，点个 ⭐ 能让更多人发现它。
