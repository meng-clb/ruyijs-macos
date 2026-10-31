# 阿里 234 — 淘宝 bx-ua (fireyejs) 闭环

用 ruyijs 跑通淘宝登录页的 bx-ua token 生成全流程。

## 背景

淘宝登录页加载 `fireyejs/1.234.37/fireyejs.js`，它是一个 **37 台嵌套 JSVMP** 字节码虚拟机，
带控制流平坦化、位判定树分发器和自完整性校验（`Hn.toString()` 随机窗口塞进 token 明文）。
生成的 `bx-ua` token 格式：`234!` + 乱序 base64(打包字节流)。

传统逆向路线需要四层工作：反混淆 → 符号执行反编译 → 纯算还原 → 魔改浏览器取指纹。
ruyijs 提供了 **引擎级真实性**（真 SpiderMonkey Firefox 158 + Necko 网络栈），
fireyejs 在里面跑和在真 Firefox 里跑一样——不需要碰任何一层逆向。

## 两个脚本

### `taobao_bxua.py` — 直跑 token（推荐）

```sh
python taobao_bxua.py
python taobao_bxua.py --proxy http://127.0.0.1:7890
python taobao_bxua.py --direct --output result.json
```

加载淘宝登录页 → 等 fireyejs 初始化 → 调 `getFYToken({})` → 拿到 `234!` 开头的 token。
自完整性校验、JSVMP、字节码 VM 全部不需要碰。

### `collect_fp.py` — 采集指纹（纯算辅助）

```sh
python collect_fp.py --output fp.json
python collect_fp.py --proxy http://127.0.0.1:7890 --output fp.json
```

替代魔改浏览器 Cloak + CDP logpoint 的全部取证流程。
采集 fp 24 字段（navigator、screen、WebGL、hash31 探针、能力向量…），
输出 JSON 直接喂给纯算 `bxua.py`：

```python
import json
from bxua import get_bx_ua
token = get_bx_ua(json.load(open('fp.json')))
```

## 为什么能跑通

| 问题 | ruyijs 怎么解决 |
|---|---|
| 自完整性校验 | 不改源码、不插桩、`eval` 只读求值 —— `Hn.toString()` 与原件逐字节相同 |
| JSVMP 字节码 VM | 引擎原生执行，字节码在真 SpiderMonkey 里跑 |
| navigator/WebGL/Canvas 指纹 | `configure_fingerprint` 配置 38 个浏览器上下文的完整 profile |
| Necko 网络栈 | 真 HTTP/1.1·2·3，与目标服务器通信跟真 Firefox 一模一样 |
| Cookie / localStorage | Context 自带持久化 JS 世界，session 不泄漏 |
