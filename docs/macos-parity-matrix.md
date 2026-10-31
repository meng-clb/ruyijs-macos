# macOS 与 Windows v0.2.1 功能对等矩阵

本文档根据 Windows v0.2.1 实际发版产物（`ruyijs-runtime-0.2.1-win-amd64.zip`）与源码实现对照，记录所有功能领域、协议契约与 macOS 对应实现状态。

## 1. 核心运行时与架构

| 模块 / 特性 | Windows v0.2.1 行为 | macOS 对应实现 | 状态 | 验证方法 |
| --- | --- | --- | --- | --- |
| JS 引擎 (SpiderMonkey) | Firefox 159 C159.0 standalone (x64) | Firefox 159 C159.0 standalone (arm64) | Pass | `js --version` |
| 进程模型 | 单主进程 + RPC 管道 (`dist/js.exe`) | 单主进程 + RPC 管道 (`dist/js`) | Pass | `ruyijs.Context().eval(...)` |
| Python 绑定层 | `ruyijs.Context` 同步 IPC 控制层 | 同一套 Python 代码，兼容 Unix 管道 | Pass | 单元测试 & examples |
| C ABI 客户端 | `libruyijs_client.dll` | `libruyijs_client.dylib` | 待完善安装路径 | C ABI 测试 |

## 2. 异步网络协议栈 (Necko / NSS)

| 协议 / 能力 | Windows v0.2.1 行为 | 原作者 macOS 路径 | 本机现状与实施路径 | 状态 |
| --- | --- | --- | --- | --- |
| HTTP/1.1 | Python oneshot + `necko_core.dll` (NSS) | `xpcshell` + `necko_fetch.js` | 移植 author xpcshell + Necko 原生适配 | 待构建 xpcshell |
| HTTP/2 | hyper-h2 + `necko_core.dll` (NSS 3.131) | `xpcshell` 原生 `nsIHttpChannel` h2 | 移植 author xpcshell + Necko 原生适配 | 待构建 xpcshell |
| HTTP/3 / QUIC | `necko_quic.dll` + neqo | donor xpcshell (无 socket process 时降级) | 依 Windows 基线对等 | 待验证 |
| TLS Profiles (100–159) | `necko/_tls_profiles.py` 映射 | Firefox 159 NSS 默认 ClientHello | 移植对应 profile 逻辑 | 待验证 |
| 证书与根证书验证 | NSS 3.131 证书链校验 | Firefox 159 NSS 证书链校验 | 同步由 NSS 处理 | 待验证 |
| WebTransport | C++ 接口骨架 (依赖 HTTP/3 会话) | 同源 C++ 接口骨架 | 依 Windows 会话基线处理 | 待验证 |

## 3. Web Workers 多进程 IPC

| Worker 类型 | Windows v0.2.1 行为 | macOS 当前状态 | 目标修复实现 | 状态 |
| --- | --- | --- | --- | --- |
| Dedicated Worker | Windows Overlapped Named Pipe | `PipeIo` 为空桩 (返回 Failed) | 移植 author 非阻塞 Unix Socket + `poll` | 待迁移 |
| Shared Worker | Windows Overlapped Named Pipe | 空桩无法启动 | 移植 author 非阻塞 Unix Socket + `poll` | 待迁移 |
| Service Worker | Windows Overlapped Named Pipe | 空桩无法启动 | 移植 author 非阻塞 Unix Socket + `poll` | 待迁移 |

## 4. 平台相关渲染与原生库

| 领域 / 特性 | Windows v0.2.1 行为 | macOS 对应实现 | 状态 |
| --- | --- | --- | --- |
| Canvas 2D 文本测量 | DirectWrite 字体量度 | Core Text / 跨平台 fallback | Pass |
| Canvas 2D 路径绘制 | DirectWrite Skia 轮廓 | Core Text `CTFontCreatePathForGlyph` | 待迁移 author 完整实现 |
| 图像编解码 (PNG/JPEG/GIF) | Windows WIC | macOS ImageIO | 待迁移 author 完整实现 |
| WebCrypto 加密摘要 | Windows CNG | CommonCrypto / Security.framework | 待迁移 author 完整实现 |
