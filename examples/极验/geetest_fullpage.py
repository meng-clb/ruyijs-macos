"""极验 v3 一键通过模式（demos.geetest.com/fullpage.html）：ruyijs+necko 原生环境完成验证并提交登录。

python geetest_fullpage.py
python geetest_fullpage.py --proxy http://127.0.0.1:7890 --output geetest.json
python geetest_fullpage.py --direct

流程（与 Firefox trace jscall-detail-desktop-20261022-114517 一致）：页面 register-fullpage 取 challenge ->
gettype/get.php 加载 fullpage.js -> 点击“点击按钮进行验证” -> ajax.php 判定：
  * result=success：一键通过；
  * result=slide（trace 中即为此分支）：加载 slide.js 与拼图，像人一样拖动滑块 -> ajax.php 返回 validate。
最后点击“提交”，页面 POST gt/validate-fullpage 做服务端二次校验。

缺口位置由求解端自己“看图”得到：在一个独立的 ruyijs Context（同源 static.geetest.com）里取回 bg/fullbg/slice，
用 ImageDecoder 解码，按 slide.js 的条带还原表（trace 中 52 次 getImageData/putImageData）还原两张图，取差异最左列。
挑战页面本身不注入任何脚本，不替换浏览器 API，不拼 w 参数。
退出码 0 表示 ajax.php 给出 validate（或一键通过）、validate-fullpage 为 HTTP 200、页面未重置验证码
（服务端校验失败时 demo 会 captchaObj.reset()），并且页面弹出了一次结果提示。
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

URL = "https://demos.geetest.com/fullpage.html"
RADAR = "document.querySelector('.geetest_radar_tip')"
BUTTON = "document.querySelector('.geetest_slider_button')"
SUBMIT = "document.querySelector('#btn')"
# slide.7.9.3 的还原：源图 312x160 的 52 条 10x80 条带 (sx, sy) -> 显示图 260x160 的 (dx, dy)。
RESTORE = json.loads(Path(__file__).with_name("restore_map.json").read_text("utf-8"))
STATE = """(()=>{const q=s=>document.querySelector(s),t=e=>e?e.textContent.trim():null,r=e=>{if(!e)return null;const b=e.getBoundingClientRect();return [b.left,b.top,b.width,b.height]};
  return {ready:document.readyState,radar:t(q('.geetest_radar_tip_content')),success:!!q('.geetest_success_radar_tip'),
    successText:t(q('.geetest_success_radar_tip_content')),panel:!!q('.geetest_panel_box.geetest_panelshowslide')||!!q('.geetest_slider_button'),
    button:r(q('.geetest_slider_button')),radarBox:r(q('.geetest_radar_tip')),submit:r(q('#btn')),
    sliderTip:t(q('.geetest_slider_tip')),result:t(q('.geetest_result_content'))}})()"""
DECODE = """(async (b64, type) => { const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
  const image = (await new ImageDecoder({data: bytes, type}).decode()).image;
  const out = new Uint8Array(image.allocationSize({format: 'RGBA'}));
  await image.copyTo(out, {format: 'RGBA'});
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


class Images:
    """A separate ruyijs Context used only as the solver's eyes: fetch + decode the puzzle images."""

    def __init__(self, proxy, timeout):
        self.context = Context(proxy=proxy or None, timeout=timeout)
        self.necko = NeckoSession(proxy)
        self.context.load_page("https://static.geetest.com/", "<!doctype html><title>solver</title>")

    def rgba(self, url):
        c = self.context
        status, _, payload, _ = self.necko.send("GET", url, [("Accept", "image/*")])
        if status < 200 or status >= 300:
            raise RuntimeError("图片请求 HTTP %s: %s" % (status, url))
        encoded = base64.b64encode(payload).decode("ascii")
        c.eval("window.__img = null;(%s)(%s,%s).then(v=>{__img=v},e=>{__img=String(e)});0"
               % (DECODE, json.dumps(encoded), json.dumps("image/png" if url.endswith(".png") else "image/jpeg")))
        for _ in range(200):
            c.advance(50)
            value = c.eval("__img")
            if value is not None:
                break
        if not isinstance(value, list):
            raise RuntimeError("图片解码失败: %s %s" % (url, value))
        width, height, data = value
        return width, height, base64.b64decode(data)

    def close(self):
        self.context.close()
        self.necko.close()


def restore(width, pixels):
    """按 slide.js 的条带表把 312x160 原图还原为 260x160。"""
    out = bytearray(260 * 160 * 4)
    for sx, sy, dx, dy in RESTORE:
        for row in range(80):
            src = ((sy + row) * width + sx) * 4
            dst = ((dy + row) * 260 + dx) * 4
            out[dst:dst + 40] = pixels[src:src + 40]
    return out


def gap_left(bg, full):
    """bg 与 fullbg 差异显著的最左列（连续 3 列每列至少 6 个像素差异）。"""
    counts = []
    for x in range(260):
        n = 0
        for y in range(160):
            i = (y * 260 + x) * 4
            if abs(bg[i] - full[i]) + abs(bg[i + 1] - full[i + 1]) + abs(bg[i + 2] - full[i + 2]) > 80:
                n += 1
        counts.append(n)
    for x in range(260 - 3):
        if all(counts[x + k] >= 6 for k in range(3)):
            return x
    raise RuntimeError("未找到缺口")


def opaque_left(width, height, pixels):
    for x in range(width):
        if any(pixels[(y * width + x) * 4 + 3] > 128 for y in range(height)):
            return x
    return 0


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
                entry = {"name": error.name, "message": error.message[:300]}
                if entry not in report["scriptErrors"] and len(report["scriptErrors"]) < 10:
                    report["scriptErrors"].append(entry)

        def state():
            return call(context.eval, STATE)

        def requests(part):
            return [r for r in call(context.net_log) if part in urlsplit(r["url"]).path]

        def mouse(kind, x, y, buttons, target):
            init = dict(clientX=x, clientY=y, screenX=x + 8, screenY=y + 120, buttons=buttons, button=0,
                        bubbles=True, cancelable=True, composed=True)
            pointer = {"mousedown": "pointerdown", "mousemove": "pointermove", "mouseup": "pointerup"}[kind]
            call(context.dispatch_input, pointer, target=target, pointerId=1, pointerType="mouse", isPrimary=True,
                 pressure=0.5 if buttons else 0, **init)
            call(context.dispatch_input, kind, target=target, **init)

        call(context.configure_clock, "system")
        call(context.navigate, URL)
        while True:  # 组件就绪：雷达按钮显示“点击按钮进行验证”
            advance()
            s = state()
            if s["radarBox"] and s["ready"] == "complete" and requests("/get.php"):
                break
        for _ in range(8):
            advance()
        # 读者先看一会儿页面，再把鼠标移向按钮并点击（trace：按下前有 pointermove/mousemove）。
        rx, ry, rw, rh = state()["radarBox"]
        tx, ty = rx + rw * random.uniform(.3, .7), ry + rh * random.uniform(.3, .7)
        px, py = tx + random.uniform(150, 260), ty + random.uniform(80, 160)
        for i in range(1, 21):
            q = i / 20
            e = q * q * (3 - 2 * q)
            mouse("mousemove", round(px + (tx - px) * e), round(py + (ty - py) * e), 0, "document.body")
            advance(16)
        call(context.click, RADAR)
        result = None
        while result is None:
            advance()
            s = state()
            if s["success"] and s["successText"]:
                result = "success"
            elif s["panel"] and s["button"] and requests("/pictures/"):
                result = "slide"
        report["firstCheck"] = result
        if result == "slide":
            for _ in range(10):
                advance()
            urls = [r["url"] for r in call(context.net_log) if "/pictures/gt/" in r["url"]]
            bg = next(u for u in reversed(urls) if "/bg/" in u)
            slice_ = next(u for u in reversed(urls) if "/slice/" in u)
            full = next(u for u in reversed(urls) if "/bg/" not in u and "/slice/" not in u and u.endswith(".jpg"))
            eyes = Images(proxy, 60)
            try:
                bw, _, bgp = eyes.rgba(bg)
                fw, _, fullp = eyes.rgba(full)
                sw, sh, slp = eyes.rgba(slice_)
            finally:
                eyes.close()
            left = gap_left(restore(bw, bgp), restore(fw, fullp))
            distance = left - opaque_left(sw, sh, slp)
            report["slide"] = {"gapLeft": left, "distance": distance}
            bx, by, bw_, bh = state()["button"]
            x, y = round(bx + bw_ / 2 + random.uniform(-6, 6)), round(by + bh / 2 + random.uniform(-6, 6))
            # 移到滑块上、按下、按 trace 的时长（约 1~3 秒）拖动：先快后慢，末端微调回拉。
            for i in range(1, 13):
                mouse("mousemove", x - 60 + i * 5, y + 24 - i * 2, 0, BUTTON)
                advance(16)
            advance(random.randint(250, 450))
            mouse("mousedown", x, y, 1, BUTTON)
            advance(random.randint(90, 160))
            overshoot = random.uniform(2, 5)
            moves = random.randint(35, 50)
            cy = y
            for i in range(1, moves + 1):
                q = i / moves
                e = 1 - (1 - q) ** 3
                cy += random.choice((0, 0, 0, 1)) if i < moves * .6 else 0
                mouse("mousemove", round(x + (distance + overshoot) * e), cy, 1, BUTTON)
                advance(random.choice((16, 16, 17, 24, 33)))
            for k in range(1, 4):
                mouse("mousemove", round(x + distance + overshoot * (1 - k / 3)), cy, 1, BUTTON)
                advance(random.randint(40, 90))
            advance(random.randint(120, 260))
            mouse("mouseup", round(x + distance), cy, 0, BUTTON)
            while True:
                advance()
                s = state()
                if s["success"] and s["successText"]:
                    break
                ajax = [r for r in requests("/ajax.php")]
                if len(ajax) >= 2 and s["radar"] and not s["panel"]:
                    break
            report["slideResult"] = s["successText"] or s["sliderTip"]
        for _ in range(6):
            advance()
        before = state()
        report["captchaPassed"] = bool(before["success"])
        call(context.click, SUBMIT)
        while not requests("/gt/validate-fullpage"):
            advance()
        for _ in range(12):
            advance()
        after = state()
        validate = requests("/gt/validate-fullpage")
        report["validateStatuses"] = [r["status"] for r in validate]
        report["ajaxStatuses"] = [r["status"] for r in requests("/ajax.php")]
        report["widgetAfterSubmit"] = after["successText"] if after["success"] else after["radar"]
        report["passed"] = (report["captchaPassed"] and validate and all(r["status"] == 200 for r in validate)
                            and after["success"] and not report["scriptErrors"])
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
