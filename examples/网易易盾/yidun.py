"""网易易盾智能无感验证（dun.163.com 控制台登录页）：ruyijs+necko 原生环境点击“点击完成验证”拿到 validate。

python yidun.py
python yidun.py --proxy http://127.0.0.1:7890 --output yidun.json
python yidun.py --direct

流程（与 Firefox trace jscall-detail-desktop-20261022-115900 一致）：控制台 dun.163.com/dashboard#/login/ ->
登录 iframe id.zhiqi.163.com/sdk-login（/s/ngt、/auth/urs）-> 易盾 load.min.js -> c.dun.163.com/api/v2/getconf ->
ir-sdk.dun.163.com/v4/j/up（设备指纹）-> /api/v3/get（type 5 智能无感）-> 鼠标移到并点击“点击完成验证” ->
/api/v3/check。trace 中这次 check 判为 false 并降级为滑块拼图（type 2）后才通过；ruyijs 中智能检测直接通过。
脚本不注入任何脚本、不替换浏览器 API、不拼 check 参数；鼠标移动与点击都是可信的 pointer/mouse 事件。
退出码 0 表示 /api/v3/check HTTP 200、组件提示“验证成功”且 iframe 中的 NECaptchaValidate 拿到了 validate。
若易盾降级为滑块拼图，脚本以 fallback="slide" 失败退出（未实现拼图求解）。
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

URL = "https://dun.163.com/dashboard#/login/"
FRAME = "document.querySelector('iframe[src*=\"id.zhiqi.163.com/sdk-login\"]')"
DOC = FRAME + ".contentDocument"
BUTTON = DOC + ".querySelector('.yidun_intelli-text')"
STATE = """(()=>{const f=%s;const d=f&&f.contentDocument;if(!d)return {frame:false};const q=s=>d.querySelector(s);
  const box=e=>{if(!e)return null;const b=e.getBoundingClientRect();return [b.left,b.top,b.width,b.height]};
  const v=q('input[name=NECaptchaValidate]');const root=q('.yidun');
  return {frame:true,frameBox:box(f),button:box(q('.yidun_intelli-control')),label:(q('.yidun_intelli-text')||{}).textContent||null,
    tips:(q('.yidun_tips__text')||{}).textContent||null,cls:root?String(root.className):null,
    slide:!!(q('.yidun_bg-img')&&q('.yidun_bg-img').getAttribute('src')),validate:v?v.value:null}})()""" % FRAME


def auto_proxy():
    for name in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        if os.environ.get(name):
            return os.environ[name]
    try:
        with socket.create_connection(("127.0.0.1", 7890), timeout=.3):
            return "http://127.0.0.1:7890"
    except OSError:
        return None


def run(args, report):
    deadline = monotonic() + args.timeout
    with Context(proxy=report["proxy"] or None, timeout=args.timeout) as context:
        def call(method, *values, **kwargs):
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise TimeoutError("等待页面超时")
            context.timeout = remaining
            return method(*values, **kwargs)

        def advance(ms=250):
            try:
                call(context.advance, ms, max_tasks=500)
            except JSError as error:
                entry = {"name": error.name, "message": error.message[:300]}
                if entry not in report["scriptErrors"] and len(report["scriptErrors"]) < 10:
                    report["scriptErrors"].append(entry)

        def requests(host, part):
            return [r for r in call(context.net_log)
                    if urlsplit(r["url"]).netloc == host and part in urlsplit(r["url"]).path]

        def mouse(kind, x, y):
            # Coordinates are the iframe's own viewport (the events are created in its realm).
            init = dict(clientX=x, clientY=y, screenX=x + 700, screenY=y + 330, buttons=0, button=0,
                        bubbles=True, cancelable=True, composed=True)
            call(context.dispatch_input, "pointer" + kind[5:], target=DOC + ".body", pointerId=1,
                 pointerType="mouse", isPrimary=True, pressure=0, **init)
            call(context.dispatch_input, kind, target=DOC + ".body", **init)

        call(context.configure_clock, "system")
        call(context.navigate, URL)
        state = None
        while True:  # 登录 iframe 中的易盾组件就绪（getconf + get 已完成）
            advance()
            state = call(context.eval, STATE)
            if state["frame"] and state["button"] and requests("c.dun.163.com", "/api/v3/get"):
                break
        for _ in range(12):
            advance()
        report["captchaType"] = "smart"
        # 读一会儿页面，再把鼠标从输入框附近移到按钮上（trace：按下前有 pointermove/mousemove）。
        bx, by, bw, bh = call(context.eval, STATE)["button"]
        tx, ty = bx + bw * random.uniform(.2, .5), by + bh * random.uniform(.3, .7)
        px, py = tx + random.uniform(60, 140), ty - random.uniform(70, 120)
        for i in range(1, 19):
            q = i / 18
            e = q * q * (3 - 2 * q)
            mouse("mousemove", round(px + (tx - px) * e), round(py + (ty - py) * e))
            advance(random.choice((16, 16, 17, 24)))
        advance(random.randint(200, 400))
        call(context.click, BUTTON)
        while True:
            advance()
            state = call(context.eval, STATE)
            if state["validate"] or state["slide"]:
                break
        for _ in range(6):
            advance()
        state = call(context.eval, STATE)
        checks = requests("c.dun.163.com", "/api/v3/check")
        report["checkStatuses"] = [r["status"] for r in checks]
        report["tips"] = state["tips"]
        report["validateLength"] = len(state["validate"] or "")
        if state["slide"] and not state["validate"]:
            report["fallback"] = "slide"
        report["loginFlow"] = {path: [r["status"] for r in requests("id.zhiqi.163.com", path)]
                               for path in ("/sdk-login", "/s/ngt", "/auth/urs")}
        report["passed"] = (bool(state["validate"]) and checks and all(r["status"] == 200 for r in checks)
                            and state["tips"] == "验证成功" and "fallback" not in report)
        context.timeout = min(5, max(1, deadline - monotonic()))


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    proxy = parser.add_mutually_exclusive_group()
    proxy.add_argument("--proxy", help="HTTP(S) 代理，默认环境变量/本机 7890/直连")
    proxy.add_argument("--direct", action="store_true", help="直接连接")
    parser.add_argument("--timeout", type=float, default=120, help="总期限，秒")
    parser.add_argument("--output", type=Path, help="将 JSON 结果同时写入此文件")
    args = parser.parse_args()
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout 必须是正有限数")
    report = {"passed": False, "transport": "ruyijs-page-parameters+necko-fetch", "proxy": None if args.direct else (args.proxy or auto_proxy()), "scriptErrors": []}
    started = monotonic()
    try:
        run(args, report)
    except Exception as error:
        report.update(passed=False, error=type(error).__name__ + ": " + str(error))
    report["elapsedSeconds"] = round(monotonic() - started, 3)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", "utf-8")
    print(text)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
