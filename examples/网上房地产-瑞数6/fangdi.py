"""使用 ruyijs 原生环境通过挑战，再验证同一会话能取得房地产首页。

python fangdi.py
python fangdi.py --proxy http://127.0.0.1:7890 --html fangdi_home.html
python fangdi.py --direct

仅依赖 Python 标准库、项目 python/ruyijs 和 dist/js.exe。
退出码 0 表示最终首页 HTTP 200、标题正确且有链接；页面脚本异常单独列出。
"""
import argparse
from html.parser import HTMLParser
import json
import math
import os
from pathlib import Path
import socket
import sys
from time import monotonic
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
if (ROOT / "dist" / "js.exe").is_file() or os.environ.get("RUYIJS_SHELL"):
    sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context, JSError
sys.path.insert(0, str(ROOT / "examples" / "google"))
from google_search import NeckoSession

URL = "https://www.fangdi.com.cn/"
READ_PAGE = """({url:location.href,title:document.title,ready:document.readyState,
  nodes:document.getElementsByTagName('*').length,links:document.links.length})"""


class Homepage(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.in_title, self.title, self.links = False, "", 0
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self.in_title = True
        if tag == "a" and dict(attrs).get("href"):
            self.links += 1

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title += data


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
        necko = NeckoSession(report["proxy"] or None)
        def call(method, *values, **kwargs):
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise TimeoutError("等待首页超时")
            context.timeout = remaining
            return method(*values, **kwargs)

        def advance():
            try:
                call(context.advance, 250, max_tasks=500)
            except JSError as error:
                entry = {"name": error.name, "message": error.message, "stack": error.stack}
                if entry not in report["scriptErrors"] and len(report["scriptErrors"]) < 10:
                    report["scriptErrors"].append(entry)

        call(context.configure_clock, "system")
        call(context.eval, "location.assign(" + json.dumps(URL) + ");undefined")
        while True:
            advance()
            state = call(context.eval, READ_PAGE)
            if state["ready"] == "complete" and state["title"].strip() == "网上房地产":
                break

        # The page only produces challenge/cookie state. Fetch the final page
        # directly through Necko with the complete Context Cookie header.
        cookie = call(context.cookie_header, URL, source_url=URL)
        headers = [("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")]
        if cookie:
            headers.append(("Cookie", cookie))
        try:
            status, response_headers, payload, version = necko.send("GET", URL, headers)
        except Exception:
            necko.close()
            raise
        html = payload.decode("utf-8", "replace")
        parsed = Homepage(html)
        state = call(context.eval, READ_PAGE)
        report.update(httpStatus=status, title=parsed.title.strip(),
                      htmlBytes=len(html.encode("utf-8")), links=parsed.links,
                      page=state)
        report["passed"] = (status == 200 and report["title"] == "网上房地产"
                            and parsed.links > 0)
        report["homepageStatuses"] = [row.get("status") for row in call(context.net_log)
            if urlsplit(row["url"]).netloc == "www.fangdi.com.cn"
            and urlsplit(row["url"]).path == "/"]
        report["cookieNames"] = call(context.eval, """document.cookie.split(';')
          .map(x=>x.trim().split('=')[0]).filter(Boolean)""")
        if args.html and report["passed"]:
            args.html.resolve().parent.mkdir(parents=True, exist_ok=True)
            args.html.write_text(html, "utf-8")
            report["htmlFile"] = str(args.html.resolve())
        if args.dom:
            args.dom.resolve().parent.mkdir(parents=True, exist_ok=True)
            args.dom.write_text(call(context.eval, "document.documentElement.outerHTML"), "utf-8")
        context.timeout = min(5, max(1, deadline - monotonic()))
        necko.close()


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    proxy = parser.add_mutually_exclusive_group()
    proxy.add_argument("--proxy", help="HTTP(S) 代理，默认环境变量/本机 7890/直连")
    proxy.add_argument("--direct", action="store_true", help="直接连接")
    parser.add_argument("--timeout", type=float, default=45, help="总期限，秒")
    parser.add_argument("--html", type=Path, help="保存最终 HTTP 200 首页 HTML")
    parser.add_argument("--dom", type=Path, help="可选保存页面执行后的 DOM，供排查页面异常")
    args = parser.parse_args()
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout 必须是正有限数")
    report = {"passed": False, "transport": "ruyijs-parameters+necko", "proxy": None if args.direct else (args.proxy or auto_proxy()),
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
