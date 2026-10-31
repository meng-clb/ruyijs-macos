"""数美滑动验证码（www.ishumei.com 注册页）：ruyijs+necko 原生环境完成拼图滑动并通过 fverify。

python shumei.py
python shumei.py --proxy http://127.0.0.1:7890 --output shumei.json
python shumei.py --direct

流程（与 Firefox trace jscall-detail-desktop-20261022-130216 一致）：注册页 -> smcp.min.js -> ca/v1/conf ->
fp.min.js 设备指纹（fp-it.portal101.cn/deviceprofile/v4）-> captcha-sdk.min.js -> ca/v1/register（拼图 bg 600x300 +
fg 90x300）-> 鼠标移到滑块上（悬停显示拼图）、按下、拖动、松开 -> ca/v2/fverify。trace 中第一次 REJECT，刷新后第二次 PASS；
本脚本被拒时同样等待组件刷新后重试，最多 --attempts 次。

缺口位置由求解端自己"看图"：另开一个 ruyijs Context（同源 castatic.fengkongcloud.cn）取回 bg/fg，用 ImageDecoder
解码，把拼图块的形状在它自己那几行上横向滑动，取"形状内亮度 - 外圈亮度"最大的位置（缺口是一层半透明白色）。
拖动按真实时间进行（SDK 每 100 ms 采样一次指针）：约 0.5 s 快速滑到缺口前，约 0.8 s 慢慢靠上，读取页面上
拼图块的位置对准后停一会儿再松开，整体约 2 s，与 trace 中通过的那次相当。
挑战页面不注入脚本、不替换浏览器 API、不生成 fverify 参数；鼠标事件都是可信的 pointer/mouse 事件。
退出码 0 表示某次 fverify 返回 riskLevel PASS（滑轨显示 slide_success“验证成功”）且没有数美脚本异常。
"""
import argparse
import base64
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
sys.path.insert(0, str(ROOT / "examples" / "google"))
from google_search import NeckoSession
from ruyijs import Context, JSError

URL = ("https://www.ishumei.com/account/register.html?crmSource="
       "%E9%A6%96%E9%A1%B5-%E8%8F%9C%E5%8D%95%E6%A0%8F%E5%85%8D%E8%B4%B9%E8%AF%95%E7%94%A8")
Q = "document.querySelector('[id$=\"shumei_captcha_%s\"]')"
BUTTON, ICON = Q % "slide_btn", Q % "slide_btn" + ".querySelector('i')"
STATE = """(()=>{const q=s=>document.querySelector('[id$="shumei_captcha_'+s+'"]');
  const box=e=>{if(!e)return null;const b=e.getBoundingClientRect();return [b.left,b.top,b.width,b.height]};
  const w=q('wrapper'),bg=q('loaded_img_bg'),fg=q('img_loaded_fg_wrapper');
  const t=q('slide_wrapper');
  return {ready:!!w,cls:t?String(t.className):'',button:box(q('slide_btn')),track:box(t),
    bg:bg&&bg.getAttribute('src'),fg:(q('loaded_img_fg')||{}).src||null,bgWidth:bg?bg.offsetWidth:0,
    fgLeft:fg?parseFloat(fg.style.left||'0'):null,tips:(q('slide_tips')||{}).textContent||null}})()"""
DECODE = """(async (b64, type) => { const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
  const image = (await new ImageDecoder({data: bytes, type}).decode()).image;
  const out = new Uint8Array(image.allocationSize({format: 'RGBA'})); await image.copyTo(out, {format: 'RGBA'});
  let s = ''; for (let i = 0; i < out.length; i += 8192) s += String.fromCharCode.apply(null, out.subarray(i, i + 8192));
  return [image.codedWidth, image.codedHeight, btoa(s)]; })"""


def auto_proxy():
    for name in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        if os.environ.get(name):
            return os.environ[name]
    try:
        with socket.create_connection(("127.0.0.1", 7890), timeout=.3):
            return "http://127.0.0.1:7890"
    except OSError:
        return None


class Eyes:
    """A separate ruyijs Context that only fetches and decodes the puzzle images (same origin)."""

    def __init__(self, proxy):
        self.context = Context(proxy=proxy or None, timeout=60)
        self.necko = NeckoSession(proxy)
        self.context.load_page("https://castatic.fengkongcloud.cn/", "<!doctype html><title>solver</title>")

    def rgba(self, url):
        c = self.context
        status, _, payload, _ = self.necko.send("GET", url, [("Accept", "image/*")])
        if status < 200 or status >= 300:
            raise RuntimeError("图片请求 HTTP %s: %s" % (status, url))
        encoded = base64.b64encode(payload).decode("ascii")
        c.eval("window.__img=null;(%s)(%s,%s).then(v=>{__img=v},e=>{__img=String(e)});0"
               % (DECODE, json.dumps(encoded), json.dumps("image/png" if url.endswith(".png") else "image/jpeg")))
        for _ in range(400):
            c.advance(25)
            value = c.eval("__img")
            if value is not None:
                break
        if not isinstance(value, list):
            raise RuntimeError("图片解码失败: %s %s" % (url, value))
        return value[0], value[1], base64.b64decode(value[2])

    def close(self):
        self.context.close()
        self.necko.close()


def _gray(p, i):
    return (p[i * 4] * 30 + p[i * 4 + 1] * 59 + p[i * 4 + 2] * 11) // 100


def gap_x(bg, fg):
    """拼图块在背景中的横向位置（背景像素坐标，即拼图条带左缘）。

    缺口是原图上盖了一层半透明白色，形状和高度与拼图块相同（背景里还有一个高度不同的假缺口）。
    把拼图块的形状放在它自己的那几行上横向滑动，取"形状内平均亮度 - 形状外一圈平均亮度"最大的位置。"""
    bw, bh, bp = bg
    fw, fh, fp = fg
    opaque = lambda x, y: 0 <= x < fw and 0 <= y < fh and fp[(y * fw + x) * 4 + 3] > 128
    inside = [(x, y) for y in range(fh) for x in range(fw) if opaque(x, y)]
    near = set()
    for x, y in inside:
        for dx in range(-3, 4):
            for dy in range(-3, 4):
                if not opaque(x + dx, y + dy) and 0 <= y + dy < fh:
                    near.add((x + dx, y + dy))
    ring = sorted(near)
    light = [_gray(bp, i) for i in range(bw * bh)]
    xs = [x for x, _ in inside] + [x for x, _ in ring]
    lo, hi = -min(xs), bw - 1 - max(xs)
    best, at = None, 0
    for offset in range(lo, hi + 1):
        a = sum(light[y * bw + offset + x] for x, y in inside[::2]) / len(inside[::2])
        b = sum(light[y * bw + offset + x] for x, y in ring[::2]) / len(ring[::2])
        if best is None or a - b > best:
            best, at = a - b, offset
    return at


def run(args, report):
    deadline = monotonic() + args.timeout
    proxy = report["proxy"]
    with Context(proxy=proxy or None, timeout=args.timeout) as context:
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
                entry = {"name": error.name, "message": error.message[:200], "stack": (error.stack or "")[:200]}
                if not any(e["message"] == entry["message"] for e in report["scriptErrors"]) and len(report["scriptErrors"]) < 10:
                    report["scriptErrors"].append(entry)

        def state():
            return call(context.eval, STATE)

        def verifies():
            return [r for r in call(context.net_log) if urlsplit(r["url"]).path == "/ca/v2/fverify"]

        def mouse(kind, x, y, buttons, target):
            init = dict(clientX=x, clientY=y, screenX=x + 8, screenY=y + 120, buttons=buttons, button=0,
                        bubbles=True, cancelable=True, composed=True)
            pointer = {"mousedown": "pointerdown", "mousemove": "pointermove", "mouseup": "pointerup"}[kind]
            call(context.dispatch_input, pointer, target=target, pointerId=1, pointerType="mouse", isPrimary=True,
                 pressure=0.5 if buttons else 0, **init)
            call(context.dispatch_input, kind, target=target, **init)

        call(context.configure_clock, "system")
        call(context.navigate, URL)
        s = None
        while True:  # 组件与第一张拼图就绪
            advance()
            s = state()
            if s["ready"] and s["bg"] and s["fg"] and s["button"]:
                break
        for _ in range(8):
            advance()
        eyes = Eyes(proxy)
        try:
            for attempt in range(args.attempts):
                s = state()
                sent = len(verifies())
                bg, fg = eyes.rgba(s["bg"]), eyes.rgba(s["fg"])
                target = gap_x(bg, fg)
                bx, by, bw, bh = s["button"]
                x, y = round(bx + bw / 2 + random.uniform(-6, 6)), round(by + bh / 2 + random.uniform(-6, 6))
                # Hover: approach the slider (the puzzle image shows on hover), read the displayed scale.
                px, py = x - random.uniform(120, 200), y + random.uniform(60, 120)
                for i in range(1, 19):
                    q = i / 18
                    e = q * q * (3 - 2 * q)
                    mouse("mousemove", round(px + (x - px) * e), round(py + (y - py) * e), 0, BUTTON)
                    advance(random.choice((16, 17, 24, 33)))
                call(context.dispatch_input, "mouseover", target=BUTTON, clientX=x, clientY=y, bubbles=True)
                advance(random.randint(600, 1200))
                s = state()
                scale = (s["bgWidth"] or 300) / bg[0]
                goal = target * scale  # the piece's displayed left at the gap
                mouse("mousedown", x, y, 1, ICON)
                advance(random.randint(100, 180))
                # Drag like the traced user (PASS: 2.26 s in all). The SDK samples the pointer every 100 ms of
                # real time, so positions follow the wall clock, not the number of dispatched moves: a fast run to
                # a few px short of the gap (~0.5 s), a slow approach (~0.8 s), a short hold, release.
                start_left = state()["fgLeft"] or 0
                distance = goal - start_left
                short = random.uniform(8, 20)
                fast, slow = random.uniform(.45, .65), random.uniform(.6, .9)
                cx, cy, moves, began = x, y, 0, monotonic()
                while True:
                    t = monotonic() - began
                    if t >= fast + slow:
                        break
                    if t < fast:
                        q = t / fast
                        cx = x + (distance - short) * (1 - (1 - q) ** 2)
                        cy = y + round(random.uniform(0, 6) * q)
                    else:
                        cx = x + distance - short * (1 - (t - fast) / slow)
                    mouse("mousemove", round(cx), cy, 1, BUTTON)
                    advance(16)
                    moves += 1
                for _ in range(4):  # land exactly on the gap, reading the piece's position
                    left = state()["fgLeft"] or 0
                    if abs(goal - left) < 0.6:
                        break
                    cx += goal - left
                    mouse("mousemove", round(cx), cy, 1, BUTTON)
                    advance(16)
                    moves += 1
                released_left = state()["fgLeft"]
                advance(random.randint(200, 450))
                mouse("mouseup", round(cx), cy, 0, BUTTON)
                while len(verifies()) <= sent:
                    advance()
                for _ in range(6):
                    advance()
                s = state()
                # 成功时滑轨加上 slide_success、提示变为“验证成功”（fverify 返回 riskLevel PASS）。
                passed = "slide_success" in s["cls"].split()
                report["attempts"].append({"bg": s["bg"][-40:] if s["bg"] else None, "gapX": target, "scale": scale, "goal": round(goal, 1), "releasedAt": released_left,
                                           "moves": moves, "status": verifies()[-1]["status"],
                                           "widget": s["cls"].split()[-1] if s["cls"] else None, "passed": passed})
                if passed:
                    break
                for _ in range(12):  # 被拒：等待组件刷新出新拼图
                    advance()
                    s = state()
                    if s["bg"] and s["bg"] != report.get("lastBg"):
                        break
                report["lastBg"] = s["bg"]
        finally:
            eyes.close()
        report["fverifyStatuses"] = [r["status"] for r in verifies()]
        shumei = [e for e in report["scriptErrors"] if "fengkongcloud" in e["stack"] or "portal101" in e["stack"]]
        report["passed"] = bool(report["attempts"]) and report["attempts"][-1]["passed"] and not shumei
        context.timeout = min(5, max(1, deadline - monotonic()))


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    proxy = parser.add_mutually_exclusive_group()
    proxy.add_argument("--proxy", help="HTTP(S) 代理，默认环境变量/本机 7890/直连")
    proxy.add_argument("--direct", action="store_true", help="直接连接")
    parser.add_argument("--attempts", type=int, default=3, help="被拒时最多尝试的次数")
    parser.add_argument("--timeout", type=float, default=60, help="总期限，秒")
    parser.add_argument("--output", type=Path, help="将 JSON 结果同时写入此文件")
    args = parser.parse_args()
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout 必须是正有限数")
    report = {"passed": False, "transport": "ruyijs-parameters+necko", "proxy": None if args.direct else (args.proxy or auto_proxy()),
              "attempts": [], "scriptErrors": []}
    started = monotonic()
    try:
        run(args, report)
    except Exception as error:
        report.update(passed=False, error=type(error).__name__ + ": " + str(error))
    report.pop("lastBg", None)
    report["elapsedSeconds"] = round(monotonic() - started, 3)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", "utf-8")
    print(text)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
