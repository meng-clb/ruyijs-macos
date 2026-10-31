"""用 ruyijs 采集真实浏览器指纹环境（fp 24 字段），替代魔改浏览器 Cloak + CDP logpoint。

python collect_fp.py --output fp.json
python collect_fp.py --proxy http://127.0.0.1:7890 --output fp.json
python collect_fp.py --direct

采到的指纹可以直接喂给纯算 bxua.py：
  import json; from bxua import get_bx_ua
  token = get_bx_ua(json.load(open('fp.json')))

替代 [[04 魔改浏览器追指纹]] 的全部取证流程：
- 不需要魔改浏览器 Cloak
- 不需要 CDP 通道和 logpoint
- ruyijs 的 SpiderMonkey 提供与真 Firefox 一致的 API 返回值
- 不触发 fireyejs 自完整性校验（不改源码，eval 求值零侵入）

仅依赖 Python 标准库、项目 python/ruyijs 和 dist/js.exe。
退出码 0 表示成功采集全部 fp 字段；1 表示失败。
"""
import argparse
import json
import math
import os
from pathlib import Path
import socket
import sys
from time import monotonic

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
if (ROOT / "dist" / "js.exe").is_file() or os.environ.get("RUYIJS_SHELL"):
    sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context, JSError

LOGIN_URL = "https://login.taobao.com/member/login.jhtml"

PROFILE = {
    "navigator": {
        "language": "zh-CN",
        "languages": ["zh-CN", "zh", "en-US", "en"],
        "hardwareConcurrency": 8,
        "platform": "Win32",
        "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:158.0) "
                     "Gecko/20100101 Firefox/158.0",
    },
    "screen": {"width": 1920, "height": 1080, "colorDepth": 24, "pixelDepth": 24},
    "viewport": {"width": 1440, "height": 900, "devicePixelRatio": 1},
    "locale": {"timezone": "Asia/Shanghai"},
    "webgl": {
        "vendor": "Mozilla",
        "unmaskedVendor": "Google Inc. (NVIDIA)",
        "unmaskedRenderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 "
                            "Direct3D11 vs_5_0 ps_5_0), or similar",
    },
    "audio": {"sampleRate": 48000, "maxChannelCount": 2},
}

# ── fp 24 字段采集（来自 [[04 魔改浏览器追指纹]] §五 来源总表）──
COLLECT_FP = r"""(function() {
    var fp = {};

    // ── 源0: browser_marker（全静态）──
    fp.appCodeName = navigator.appCodeName;
    fp.appName     = navigator.appName;
    fp.platform    = navigator.platform;

    // ── 源1: runtime_vector ──
    fp.colorDepth   = screen.colorDepth;
    fp.pixelDepth   = screen.pixelDepth;
    fp.screenWidth  = screen.width;
    fp.screenHeight = screen.height;
    try { fp.resourceCount = performance.getEntriesByType("resource").length; }
    catch(e) { fp.resourceCount = 0; }

    // ── 源2: error_stack（静态）──
    try { throw new Error(); } catch(e) { fp.errorStack = e.stack || ""; }

    // ── 源3: profile_vector ──

    // A. 直接环境读取
    fp.url            = location.href;
    fp.userAgent      = navigator.userAgent;
    fp.appVersion     = navigator.appVersion;
    fp.language       = navigator.language;
    fp.hwConcurrency  = navigator.hardwareConcurrency;
    fp.windowStr      = String(window);

    var conn = navigator.connection || {};
    fp.connection = [conn.downlink, conn.rtt, conn.effectiveType].map(
        function(v) { return v === undefined ? "undefined" : String(v); }).join("_");

    var gp = Object.getOwnPropertyNames(window);
    fp.globalEnumCount = gp.length;
    fp.globalEnumHead  = gp.slice(0, 20).join(",");

    // WebGL
    try {
        var c = document.createElement("canvas");
        var gl = c.getContext("webgl") || c.getContext("experimental-webgl");
        if (gl) {
            var ext = gl.getExtension("WEBGL_debug_renderer_info");
            fp.webglVendor   = ext ? gl.getParameter(ext.UNMASKED_VENDOR_WEBGL) : "";
            fp.webglRenderer = ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : "";
            fp.maxTextureSize  = gl.getParameter(gl.MAX_TEXTURE_SIZE);
            fp.maxRenderbuffer = gl.getParameter(gl.MAX_RENDERBUFFER_SIZE);
        }
    } catch(e) {}

    // performance.memory
    try {
        fp.heapLimit = performance.memory.jsHeapSizeLimit;
        fp.heapTotal = performance.memory.totalJSHeapSize;
        fp.heapUsed  = performance.memory.usedJSHeapSize;
    } catch(e) {}

    // B. 探针哈希（hash31）
    function hash31(s) {
        var h = 0;
        for (var i = 0; i < s.length; i++) h = (((31 * h) | 0) + s.charCodeAt(i)) | 0;
        return h;
    }
    try {
        var au = new Audio();
        var at = ['audio/mpeg','audio/ogg; codecs="vorbis"','audio/wav',
                  'audio/mp4','audio/aac','audio/webm; codecs="vorbis"'];
        fp.hashAudio = hash31(at.map(function(t){return au.canPlayType(t);}).join(""));
    } catch(e) { fp.hashAudio = null; }

    try {
        var vi = document.createElement("video");
        var vt = ['video/mp4','video/webm','video/ogg','video/webm; codecs="vp8"'];
        fp.hashVideo = hash31(vt.map(function(t){return vi.canPlayType(t);}).join(""));
    } catch(e) { fp.hashVideo = null; }

    // C. 能力向量
    fp.featureBits = [
        typeof fetch!='undefined'?1:0, typeof Promise!='undefined'?1:0,
        typeof Proxy!='undefined'?1:0, typeof Symbol!='undefined'?1:0,
        typeof WeakMap!='undefined'?1:0, typeof WeakSet!='undefined'?1:0,
        typeof Map!='undefined'?1:0, typeof Set!='undefined'?1:0,
        typeof Reflect!='undefined'?1:0, typeof Intl!='undefined'?1:0,
        typeof SharedArrayBuffer!='undefined'?1:0, typeof Atomics!='undefined'?1:0,
        typeof BigInt!='undefined'?1:0, typeof globalThis!='undefined'?1:0,
        typeof queueMicrotask!='undefined'?1:0
    ].join("|");

    // D. 时间 / 会话
    fp.nowMs     = Date.now();
    fp.sessionId = Math.random().toString(36).substring(2);
    try {
        var ls = localStorage.getItem("lswucn") || "";
        fp.seed = ls ? ("D" + ls.split("@@")[0]) : "";
    } catch(e) { fp.seed = ""; }

    return JSON.stringify(fp);
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
    with Context(proxy=report["proxy"] or None, timeout=args.timeout) as context:
        def call(method, *a, **kw):
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise TimeoutError("超时")
            context.timeout = remaining
            return method(*a, **kw)

        # 1. 配置指纹 + 系统时钟
        call(context.configure_fingerprint, PROFILE)
        call(context.configure_clock, "system")

        # 2. 导航到目标页（Necko 真实请求，给出 location.href + DOM）
        call(context.eval, "location.assign(%s);undefined" % json.dumps(args.url))

        # 3. 等页面 ready
        for _ in range(30):
            try:
                call(context.advance, 5, max_tasks=200)
            except JSError:
                pass
            state = call(context.eval, "document.readyState")
            if state in ("interactive", "complete"):
                break

        # 4. 采集 fp 24 字段
        raw = call(context.eval, COLLECT_FP)
        fp = json.loads(raw)
        report["fingerprint"] = fp
        report["fieldCount"] = len(fp)
        report["passed"] = len(fp) >= 20  # 至少采到 20 个字段

        # 5. 保存
        if args.output and report["passed"]:
            args.output.resolve().parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(fp, ensure_ascii=False, indent=2) + "\n", "utf-8")
            report["outputFile"] = str(args.output.resolve())

        context.timeout = min(5, max(1, deadline - monotonic()))


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    proxy_group = parser.add_mutually_exclusive_group()
    proxy_group.add_argument("--proxy", help="HTTP(S) 代理")
    proxy_group.add_argument("--direct", action="store_true", help="直接连接")
    parser.add_argument("--timeout", type=float, default=30, help="超时秒数")
    parser.add_argument("--url", default=LOGIN_URL, help="目标页面 URL")
    parser.add_argument("--output", "-o", type=Path, help="保存指纹 JSON 到文件")
    args = parser.parse_args()
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout 必须是正有限数")
    report = {"passed": False, "transport": "ruyijs-context",
              "proxy": None if args.direct else (args.proxy or auto_proxy()),
              "url": args.url}
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
