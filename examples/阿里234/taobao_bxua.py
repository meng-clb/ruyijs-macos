"""用 ruyijs 原生环境加载淘宝登录页，让 fireyejs 在真 Firefox 引擎里自然生成 bx-ua token。

python taobao_bxua.py
python taobao_bxua.py --proxy http://127.0.0.1:7890
python taobao_bxua.py --direct --output result.json

闭环路径：不做任何逆向，让 fireyejs 原件在真 SpiderMonkey + Necko 里跑，token 自然出来。
fireyejs 的自完整性校验、37 台 JSVMP、字节码 VM 全部不需要碰——引擎级真实性是 ruyijs 免费给的。

系列：[[01 反混淆]] → [[02 反编译]] → [[03 算法还原]] → [[04 魔改浏览器追指纹]] → 本脚本（闭环）

仅依赖 Python 标准库、项目 python/ruyijs 和 dist/js.exe。
退出码 0 表示成功提取 bx-ua token（234! 开头、长度合理）；1 表示失败。
"""
import argparse
import json
import math
import os
from pathlib import Path
import random
import socket
import sys
from time import monotonic
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
if (ROOT / "dist" / "js.exe").is_file() or os.environ.get("RUYIJS_SHELL"):
    sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context, JSError

# ── 目标 ──────────────────────────────────────────────
LOGIN_URL = "https://login.taobao.com/member/login.jhtml"

# ── 指纹配置（Firefox 158 on Windows 10，与 google 示例同级别）──
PROFILE = json.loads(r"""
{
 "navigator": {
  "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:158.0) Gecko/20100101 Firefox/158.0",
  "platform": "Win32",
  "appCodeName": "Mozilla",
  "appName": "Netscape",
  "appVersion": "5.0 (Windows)",
  "product": "Gecko",
  "productSub": "20100101",
  "vendor": "",
  "vendorSub": "",
  "language": "zh-CN",
  "languages": ["zh-CN", "zh", "en-US", "en"],
  "hardwareConcurrency": 8,
  "maxTouchPoints": 0,
  "cookieEnabled": true,
  "webdriver": false,
  "oscpu": "Windows NT 10.0; Win64; x64",
  "buildID": "20181001000000",
  "doNotTrack": "unspecified",
  "pdfViewerEnabled": true,
  "onLine": true,
  "globalPrivacyControl": false
 },
 "screen": {
  "width": 1920, "height": 1080,
  "availWidth": 1920, "availHeight": 1032,
  "availLeft": 0, "availTop": 0,
  "colorDepth": 24, "pixelDepth": 24
 },
 "viewport": {
  "width": 1440, "height": 900, "devicePixelRatio": 1
 },
 "locale": {
  "timezone": "Asia/Shanghai"
 },
 "webgl": {
  "vendor": "Mozilla",
  "renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0), or similar",
  "version": "WebGL 1.0",
  "glslVersion": "WebGL GLSL ES 1.0",
  "unmaskedVendor": "Google Inc. (NVIDIA)",
  "unmaskedRenderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0), or similar",
  "version2": "WebGL 2.0",
  "glslVersion2": "WebGL GLSL ES 3.00",
  "attributes": {
   "alpha": true, "antialias": true, "depth": true,
   "failIfMajorPerformanceCaveat": false, "powerPreference": "default",
   "premultipliedAlpha": true, "preserveDrawingBuffer": false, "stencil": false
  },
  "extensions": [
   "ANGLE_instanced_arrays", "EXT_blend_minmax", "EXT_color_buffer_half_float",
   "EXT_float_blend", "EXT_frag_depth", "EXT_shader_texture_lod", "EXT_sRGB",
   "EXT_texture_compression_bptc", "EXT_texture_compression_rgtc",
   "EXT_texture_filter_anisotropic", "OES_element_index_uint",
   "OES_standard_derivatives", "OES_texture_float", "OES_texture_float_linear",
   "OES_texture_half_float", "OES_texture_half_float_linear",
   "OES_vertex_array_object", "WEBGL_color_buffer_float",
   "WEBGL_compressed_texture_s3tc", "WEBGL_compressed_texture_s3tc_srgb",
   "WEBGL_debug_renderer_info", "WEBGL_debug_shaders",
   "WEBGL_depth_texture", "WEBGL_draw_buffers", "WEBGL_lose_context"
  ],
  "limits": {}
 },
 "canvas": {
  "mode": "pixel", "seed": 1, "strength": 1,
  "density": 64, "preserveAlpha": true,
  "preserveWhitePoint": true, "pngMetadata": true
 },
 "audio": {
  "sampleRate": 48000, "baseLatency": 0, "maxChannelCount": 2
 },
 "speech": {
  "voices": [
   "Microsoft Huihui - Chinese (Simplified, PRC)",
   "Microsoft Kangkang - Chinese (Simplified, PRC)",
   "Microsoft Yaoyao - Chinese (Simplified, PRC)"
  ],
  "langs": ["zh-CN", "zh-CN", "zh-CN"],
  "default": ""
 }
}
""")

# ── JS 探针 ───────────────────────────────────────────
READ_STATE = """(function() {
    var baxia = window.__baxia__ || window.AWSC || {};
    var mod = baxia.getFYModule || baxia;
    return {
        url: location.href,
        title: document.title,
        ready: document.readyState,
        nodes: document.getElementsByTagName('*').length,
        hasBaxia: typeof window.__baxia__ !== 'undefined',
        hasAWSC: typeof window.AWSC !== 'undefined',
        hasFY: !!(mod && mod.getFYToken),
        cookie: document.cookie.substring(0, 200)
    };
})()"""

GET_TOKEN = """(function() {
    var baxia = window.__baxia__ || window.AWSC;
    if (!baxia) return {error: 'no __baxia__/AWSC'};
    var mod = baxia.getFYModule || baxia;
    if (!mod || !mod.getFYToken) return {error: 'no getFYToken'};
    try {
        var token = mod.getFYToken({});
        return {token: token, length: token.length, prefix: token.substring(0, 10)};
    } catch(e) {
        return {error: e.name + ': ' + e.message};
    }
})()"""


def auto_proxy():
    for name in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        if os.environ.get(name):
            return os.environ[name]
    try:
        with socket.create_connection(("127.0.0.1", 7890), timeout=0.3):
            return "http://127.0.0.1:7890"
    except OSError:
        return None


def run(args, report):
    deadline = monotonic() + args.timeout
    profile = json.loads(json.dumps(PROFILE))
    profile["canvas"]["seed"] = random.randint(1, 2**53 - 1)

    with Context(proxy=report["proxy"] or None, timeout=args.timeout) as context:
        def call(method, *values, **kwargs):
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise TimeoutError("超时")
            context.timeout = remaining
            return method(*values, **kwargs)

        def advance():
            try:
                call(context.advance, 250, max_tasks=500)
            except JSError as error:
                entry = {"name": error.name, "message": error.message, "stack": error.stack}
                if entry not in report["scriptErrors"] and len(report["scriptErrors"]) < 10:
                    report["scriptErrors"].append(entry)

        # 1. 配置指纹（真 Firefox 158 级别）+ 系统时钟
        call(context.configure_fingerprint, profile)
        call(context.configure_clock, "system")

        # 2. 导航到登录页（Necko 发真实请求拉页面和所有脚本，包括 fireyejs）
        call(context.eval, "location.assign(" + json.dumps(LOGIN_URL) + ");undefined")

        # 3. 等待 fireyejs 加载并初始化
        #    fireyejs 通过 <script> 标签加载后挂到 window.__baxia__
        while True:
            advance()
            state = call(context.eval, READ_STATE)
            report["pageState"] = state
            if state.get("hasFY"):
                break

        # 4. 调用 getFYToken 生成 bx-ua
        result = call(context.eval, GET_TOKEN)
        report["tokenResult"] = result

        if "error" in result:
            report["passed"] = False
            report["error"] = "getFYToken 失败: " + result["error"]
        else:
            token = result["token"]
            report.update(
                passed=bool(token and token.startswith("234!") and len(token) > 50),
                token=token,
                tokenLength=len(token),
                prefix=token[:10] if token else "",
                is234=token.startswith("234!") if token else False,
            )
            if not report["passed"] and token:
                report["error"] = f"token 结构异常: 长度={len(token)}, 前缀={token[:10]}"

        # 5. 附加诊断信息
        report["cookieNames"] = call(context.eval, """document.cookie.split(';')
          .map(x=>x.trim().split('=')[0]).filter(Boolean)""")
        net = call(context.net_log)
        report["networkRequests"] = len(net)
        report["fireyeRequests"] = [
            {"url": r["url"], "status": r.get("status")}
            for r in net if "fireyejs" in r.get("url", "") or "AWSC" in r.get("url", "")
        ]
        report["consoleLines"] = len(call(context.console_log))

        if args.output and report.get("token"):
            args.output.resolve().parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")
            report["outputFile"] = str(args.output.resolve())

        context.timeout = min(5, max(1, deadline - monotonic()))


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    proxy = parser.add_mutually_exclusive_group()
    proxy.add_argument("--proxy", help="HTTP(S) 代理，默认环境变量/本机 7890/直连")
    proxy.add_argument("--direct", action="store_true", help="直接连接")
    parser.add_argument("--timeout", type=float, default=45, help="总期限，秒")
    parser.add_argument("--output", "-o", type=Path, help="保存完整 JSON 报告到文件")
    args = parser.parse_args()
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout 必须是正有限数")
    report = {"passed": False, "transport": "ruyijs-context+necko",
              "proxy": None if args.direct else (args.proxy or auto_proxy()),
              "scriptErrors": []}
    started = monotonic()
    try:
        run(args, report)
    except Exception as error:
        report.update(passed=False, error=type(error).__name__ + ": " + str(error))
    report["elapsedSeconds"] = round(monotonic() - started, 3)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
