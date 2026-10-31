"""腾讯天御验证码（cloud.tencent.cn/product/captcha 体验区）：ruyijs+necko 原生环境完成「无感验证」与「滑块拼图」。

python tianyu.py
python tianyu.py --mode slide --proxy http://127.0.0.1:7890 --output tianyu.json
python tianyu.py --direct

流程（与 Firefox trace jscall-detail-desktop-20261022-155307 一致）：产品页 -> TJCaptcha.js -> tgJCap.js ->
cap_union_prehandle -> tdc.js（设备信息）-> cap_union_new_verify。
- 无感验证（#noFeel_click，aid 198550928，subcapclass 1001）：点击按钮，verify 直接返回 errorCode 0 与 ticket。
- 滑块拼图（#captcha_click，aid 192962660，subcapclass 2401）：弹出拼图（背景 672x390，精灵图里的拼图块
  120x120），把滑块拖到缺口处松开，verify 的答案是拼图块在 672 宽坐标系下的位置。trace 中第一次被拒
  （errorCode 50）、刷新后第二次通过；本脚本被拒时同样等待新拼图后重试，最多 --attempts 次。

缺口位置由求解端自己"看图"：另开一个 ruyijs Context（同源 turing.captcha.qcloud.com）取回背景与精灵图，用
ImageDecoder 解码；拼图块的形状取自精灵图的透明通道，缺口是背景上同形状的变暗区域，在拼图块所在的那几行
横向滑动，取"形状内平均亮度 - 形状外一圈平均亮度"最小的位置。拖动按真实时间进行（快速滑到缺口前，慢慢靠上，
停一下再松开）。挑战页面不注入脚本、不替换浏览器 API、不生成 verify 参数；鼠标事件都是可信的 pointer/mouse 事件。
退出码 0 表示所选模式都显示「验证成功」且没有腾讯验证码脚本异常。
"""
import argparse
import base64
import json
import math
import os
from pathlib import Path
import random
import re
import socket
import sys
from time import monotonic

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
if (ROOT / "dist" / "js.exe").is_file() or os.environ.get("RUYIJS_SHELL"):
    sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "examples" / "google"))
from google_search import NeckoSession
from ruyijs import Context, JSError

URL = "https://cloud.tencent.cn/product/captcha"
P = "tencent-captcha-dy__"
LAST = "(()=>{const l=document.querySelectorAll('.%s');return l[l.length-1]})()"
SLIDER = LAST % (P + "slider-block")
STATE = """(()=>{const last=c=>{const l=document.querySelectorAll('.%s'+c);return l[l.length-1]||null};
  const fg=last('fg-item'),bg=last('verify-bg-img'),sl=last('slider-block'),speed=last('verify-speed'),err=last('verify-error-text');
  const url=e=>{const m=e&&(e.getAttribute('style')||'').match(/url\\(([^)]+)\\)/);return m?m[1]:null};
  const box=e=>{if(!e)return null;const b=e.getBoundingClientRect();return [b.left,b.top,b.width,b.height]};
  const shown=e=>{const b=e.getBoundingClientRect();return b.width>0&&b.height>0};
  const toast=[...document.querySelectorAll('body *')].some(e=>e.childElementCount===0&&e.textContent.trim()==='验证成功'&&e.getBoundingClientRect().width>0);
  return {fg:url(fg),bg:url(bg),fgStyle:fg?fg.getAttribute('style'):null,bgWidth:bg?bg.getBoundingClientRect().width:0,
    slider:box(sl),speed:speed&&shown(speed)?speed.textContent.trim():'',error:err&&shown(err)?err.textContent.trim():'',toast}})()""" % P
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
        self.context.load_page("https://turing.captcha.qcloud.com/", "<!doctype html><title>solver</title>")

    def rgba(self, url, kind):
        c = self.context
        status, _, payload, _ = self.necko.send("GET", url, [("Accept", "image/*")])
        if status < 200 or status >= 300:
            raise RuntimeError("图片请求 HTTP %s: %s" % (status, url))
        encoded = base64.b64encode(payload).decode("ascii")
        c.eval("window.__img=null;(%s)(%s,%s).then(v=>{__img=v},e=>{__img=String(e)});0"
               % (DECODE, json.dumps(encoded), json.dumps(kind)))
        value = None
        for _ in range(400):
            c.advance(25)
            value = c.eval("__img")
            if value is not None:
                break
        if not isinstance(value, list):
            raise RuntimeError("图片解码失败: %s %s" % (url[:80], value))
        return value[0], value[1], base64.b64decode(value[2])

    def close(self):
        self.context.close()
        self.necko.close()


def gap_x(bg, sprite, piece):
    """缺口在背景中的横向位置（背景像素坐标，即拼图块外框左缘）。

    piece = (精灵图中的 x, y, 边长, 拼图块在背景中的 y)。缺口是同形状的变暗区域（带白色描边）。"""
    bw, bh, bp = bg
    sw, _, sp = sprite
    px, py, size, y = piece
    inside = [(x, yy) for yy in range(size) for x in range(size) if sp[((py + yy) * sw + px + x) * 4 + 3] > 128]
    solid = set(inside)
    ring = set()
    for x, yy in inside:
        for dx in range(-3, 4):
            for dy in range(-3, 4):
                if (x + dx, yy + dy) not in solid and 0 <= yy + dy < size and 0 <= x + dx < size:
                    ring.add((x + dx, yy + dy))
    ring = sorted(ring)
    light = lambda x, yy: (bp[(yy * bw + x) * 4] * 30 + bp[(yy * bw + x) * 4 + 1] * 59 + bp[(yy * bw + x) * 4 + 2] * 11) // 100
    inside, ring = inside[::2], ring[::2]
    if y + size > bh:
        return 0
    # The band's brightness once, then a coarse scan (4 px) refined around its best offset.
    band = {(x, yy): light(x, y + yy) for yy in range(size) for x in range(bw)}

    def score(offset):
        a = sum(band[offset + x, yy] for x, yy in inside) / len(inside)
        b = sum(band[offset + x, yy] for x, yy in ring) / len(ring)
        return a - b
    last = bw - size - 1
    coarse = min(range(0, last + 1, 4), key=score)
    return min(range(max(0, coarse - 4), min(last, coarse + 4) + 1), key=score)


def px(style, name):
    m = re.search(r"(?:^|;)\s*%s:\s*(-?[0-9.]+)px(?:\s+(-?[0-9.]+)px)?" % re.escape(name), style)
    return (float(m.group(1)), float(m.group(2) or 0)) if m else (0.0, 0.0)


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
            return [r for r in call(context.net_log) if "/cap_union_new_verify" in r["url"]]

        def mouse(kind, x, y, buttons, target):
            init = dict(clientX=x, clientY=y, screenX=x + 8, screenY=y + 120, buttons=buttons, button=0,
                        bubbles=True, cancelable=True, composed=True)
            pointer = {"mousedown": "pointerdown", "mousemove": "pointermove", "mouseup": "pointerup"}[kind]
            call(context.dispatch_input, pointer, target=target, pointerId=1, pointerType="mouse", isPrimary=True,
                 pressure=0.5 if buttons else 0, **init)
            call(context.dispatch_input, kind, target=target, **init)

        def click(button):
            target = "document.getElementById(%s)" % json.dumps(button)
            box = call(context.eval, "(()=>{const b=%s.getBoundingClientRect();return [b.left,b.top,b.width,b.height]})()" % target)
            x, y = round(box[0] + box[2] / 2), round(box[1] + box[3] / 2)
            mouse("mousemove", x, y, 0, target)
            advance(random.randint(80, 160))
            mouse("mousedown", x, y, 1, target)
            advance(random.randint(60, 120))
            mouse("mouseup", x, y, 0, target)
            call(context.dispatch_input, "click", target=target, clientX=x, clientY=y, button=0, bubbles=True, cancelable=True)

        def load(button):
            # Wait for the new document (not the previous one) to show the button and
            # the captcha SDK (TJCaptcha.js defines TencentCaptcha) to be ready.
            call(context.eval, "window.__previous=1;0")
            call(context.navigate, URL)
            ready = "!window.__previous&&!!document.getElementById(%s)&&typeof TencentCaptcha=='function'" % json.dumps(button)
            while not call(context.eval, ready):
                advance(100)
            advance(300)

        call(context.configure_clock, "system")
        if args.mode in ("all", "nofeel"):
            load("noFeel_click")
            sent = len(verifies())
            click("noFeel_click")
            while len(verifies()) <= sent:
                advance()
            for _ in range(4):
                advance()
            s = state()
            report["nofeel"] = {"status": verifies()[-1]["status"], "passed": "验证成功" in s["speed"] or s["toast"]}
        if args.mode in ("all", "slide"):
            eyes = Eyes(proxy)  # its own process starts while the page loads
            load("captcha_click")
            click("captcha_click")
            while not (state()["fg"] and state()["slider"]):
                advance()
            advance(250); advance(250)
            report["slide"] = {"attempts": [], "passed": False}
            try:
                last_bg = None
                for _ in range(args.attempts):
                    s = state()
                    last_bg = s["bg"]
                    sent = len(verifies())
                    style = s["fgStyle"]
                    scale = (s["bgWidth"] or 330) / 672
                    pos_x, pos_y = px(style, "background-position")
                    size = round(px(style, "width")[0] / scale)
                    left0, top = px(style, "left")[0], px(style, "top")[0]
                    piece = (round(-pos_x / scale), round(-pos_y / scale), size, round(top / scale))
                    bg, sprite = eyes.rgba(s["bg"], "image/jpeg"), eyes.rgba(s["fg"], "image/png")
                    target = gap_x(bg, sprite, piece)
                    goal = target * scale  # the piece's displayed left at the gap
                    bx, by, bw, bh = s["slider"]
                    x, y = round(bx + bw / 2 + random.uniform(-5, 5)), round(by + bh / 2 + random.uniform(-4, 4))
                    hx, hy = x - random.uniform(80, 160), y + random.uniform(30, 80)
                    for i in range(1, 13):  # approach the slider
                        q = i / 12
                        e = q * q * (3 - 2 * q)
                        mouse("mousemove", round(hx + (x - hx) * e), round(hy + (y - hy) * e), 0, SLIDER)
                        advance(random.choice((16, 17, 24, 33)))
                    advance(random.randint(200, 500))
                    mouse("mousedown", x, y, 1, SLIDER)
                    advance(random.randint(90, 160))
                    # Real-time drag: a fast run to a few px short of the gap, a slow approach, a short hold.
                    distance = goal - left0
                    short = random.uniform(6, 14)
                    fast, slow = random.uniform(.45, .7), random.uniform(.5, .8)
                    cx, cy, moves, began = x, y, 0, monotonic()
                    while True:
                        t = monotonic() - began
                        if t >= fast + slow:
                            break
                        if t < fast:
                            q = t / fast
                            cx = x + (distance - short) * (1 - (1 - q) ** 2)
                            cy = y + round(random.uniform(0, 4) * q)
                        else:
                            cx = x + distance - short * (1 - (t - fast) / slow)
                        mouse("mousemove", round(cx), cy, 1, SLIDER)
                        advance(16)
                        moves += 1
                    for _ in range(4):  # land on the gap, reading the piece's position
                        left = px(state()["fgStyle"], "left")[0]
                        if abs(goal - left) < 0.6:
                            break
                        cx += goal - left
                        mouse("mousemove", round(cx), cy, 1, SLIDER)
                        advance(16)
                        moves += 1
                    released = px(state()["fgStyle"], "left")[0]
                    advance(random.randint(200, 400))
                    mouse("mouseup", round(cx), cy, 0, SLIDER)
                    while len(verifies()) <= sent:
                        advance()
                    for _ in range(4):
                        advance()
                    s = state()
                    passed = "验证成功" in s["speed"] or s["toast"]
                    report["slide"]["attempts"].append({"gapX": target, "goal": round(goal, 1), "releasedAt": round(released, 1),
                                                        "moves": moves, "status": verifies()[-1]["status"],
                                                        "error": s["error"] or None, "passed": passed})
                    if passed:
                        report["slide"]["passed"] = True
                        break
                    for _ in range(16):  # 被拒：等待组件刷新出新拼图
                        advance()
                        s = state()
                        if s["bg"] and s["bg"] != last_bg and s["slider"]:
                            break
            finally:
                eyes.close()
        tencent = [e for e in report["scriptErrors"] if "captcha.qcloud.com" in e["stack"] or "captcha.gtimg.com" in e["stack"]]
        report["passed"] = all(report[m]["passed"] for m in ("nofeel", "slide") if m in report) and not tencent
        context.timeout = min(5, max(1, deadline - monotonic()))


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    proxy = parser.add_mutually_exclusive_group()
    proxy.add_argument("--proxy", help="HTTP(S) 代理，默认环境变量/本机 7890/直连")
    proxy.add_argument("--direct", action="store_true", help="直接连接")
    parser.add_argument("--mode", choices=("all", "nofeel", "slide"), default="all", help="验证模式，默认两种都做")
    parser.add_argument("--attempts", type=int, default=3, help="滑块被拒时最多尝试的次数")
    parser.add_argument("--timeout", type=float, default=90, help="总期限，秒")
    parser.add_argument("--output", type=Path, help="将 JSON 结果同时写入此文件")
    args = parser.parse_args()
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout 必须是正有限数")
    report = {"passed": False, "transport": "ruyijs-parameters+necko", "proxy": None if args.direct else (args.proxy or auto_proxy()), "scriptErrors": []}
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
