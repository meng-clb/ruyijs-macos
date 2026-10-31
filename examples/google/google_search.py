"""ruyijs Google search example: one file, standard library only.

  python google_search.py                             default: "electric bikes", 3 more pages
  python google_search.py --query python --pages 1
  python google_search.py --query "a" --query "b" --region us --proxy http://127.0.0.1:7890
  python google_search.py --json > out.json          full JSON (every result, timings)
  python google_search.py --dump-profile my.json      write the built-in profile to edit,
  python google_search.py --profile my.json           then run with it
  python google_search.py --query "site:tiktok.com electric bile" --pages 3
                                                      site: poisoning check (see below)

Requires Python 3.10+ on Windows x64 and the ruyijs wheel, which includes its runtime.
A source checkout with dist/js.exe and vendor/necko-derived/python also works.
RUYIJS_SHELL can select an executable in another runtime's dist directory.

How it works: Necko (ruyijs's Firefox network stack) requests the search like a top-level
navigation and gets Google's SG_SS check page. ruyijs, configured with the whole fingerprint
profile, runs that page at its real URL until it sets the SG_SS cookie. Necko then repeats the
search with SG_SS and sei=<eid>, and follows each page's own Next link. A mid-session
"Verifying your request" page is waited out like a user clicking Continue.

Poisoning check: with site:example.com in the query every result must come from that site.
Google can serve a session results that ignore site: (Facebook, Taobao, YouTube, ... for
site:tiktok.com) while still answering HTTP 200 with a full page; such a page is "poisoned".
Each result is matched by the host shown in <cite>, or, for video and social results that show
view counts there, by the source name above it; results showing neither count as unverified.
A spelling correction ("electric bile" -> "electric bike") is accepted: Google's Next links
carry the corrected query.
Exit code 0 means every requested page passed: results, the query, and no off-site result.
"""
import argparse
import ctypes
import json
import os
from pathlib import Path
import random
import re
import socket
import struct
import subprocess
import sys
from html import unescape
from time import monotonic, sleep
from urllib.parse import parse_qsl, unquote_plus, urlencode, urljoin, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parent.parent.parent
sys.dont_write_bytecode = True
if (ROOT / "dist" / "js.exe").is_file() or os.environ.get("RUYIJS_SHELL"):
    sys.path.insert(0, str(ROOT / "python"))

PYTHON = None  # Resolved by main() or the first imported NeckoSession.
DEFAULT_QUERY = "electric bikes"
NAVIGATION_ACCEPT = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
BODY_LIMIT = 8 * 1024 * 1024  # the Necko helper's response body bound

# ---------------------------------------------------------------------------------------------
# Fingerprint profile (Firefox 158 on Windows 10). Edit it with --dump-profile / --profile.
# Keep timezone, language and location consistent with the proxy's exit IP.
# ---------------------------------------------------------------------------------------------
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
  "language": "en-US",
  "languages": [
   "en-US",
   "en"
  ],
  "hardwareConcurrency": 16,
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
  "width": 1920,
  "height": 1080,
  "availWidth": 1920,
  "availHeight": 1032,
  "availLeft": 0,
  "availTop": 0,
  "colorDepth": 24,
  "pixelDepth": 24,
  "top": 0,
  "left": 0
 },
 "viewport": {
  "width": 1920,
  "height": 951,
  "devicePixelRatio": 1
 },
 "locale": {
  "timezone": "Asia/Hong_Kong"
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
   "alpha": true,
   "antialias": true,
   "depth": true,
   "failIfMajorPerformanceCaveat": false,
   "powerPreference": "default",
   "premultipliedAlpha": true,
   "preserveDrawingBuffer": false,
   "stencil": false
  },
  "extensions": [
   "ANGLE_instanced_arrays",
   "EXT_blend_minmax",
   "EXT_color_buffer_half_float",
   "EXT_depth_clamp",
   "EXT_float_blend",
   "EXT_frag_depth",
   "EXT_polygon_offset_clamp",
   "EXT_shader_texture_lod",
   "EXT_sRGB",
   "EXT_texture_compression_bptc",
   "EXT_texture_compression_rgtc",
   "EXT_texture_filter_anisotropic",
   "OES_element_index_uint",
   "OES_fbo_render_mipmap",
   "OES_standard_derivatives",
   "OES_texture_float",
   "OES_texture_float_linear",
   "OES_texture_half_float",
   "OES_texture_half_float_linear",
   "OES_vertex_array_object",
   "WEBGL_color_buffer_float",
   "WEBGL_compressed_texture_s3tc",
   "WEBGL_compressed_texture_s3tc_srgb",
   "WEBGL_debug_renderer_info",
   "WEBGL_debug_shaders",
   "WEBGL_depth_texture",
   "WEBGL_draw_buffers",
   "WEBGL_lose_context",
   "WEBGL_provoking_vertex"
  ],
  "extensions2": [
   "EXT_color_buffer_float",
   "EXT_depth_clamp",
   "EXT_float_blend",
   "EXT_polygon_offset_clamp",
   "EXT_texture_compression_bptc",
   "EXT_texture_compression_rgtc",
   "EXT_texture_filter_anisotropic",
   "OES_draw_buffers_indexed",
   "OES_texture_float_linear",
   "OVR_multiview2",
   "WEBGL_compressed_texture_s3tc",
   "WEBGL_compressed_texture_s3tc_srgb",
   "WEBGL_debug_renderer_info",
   "WEBGL_debug_shaders",
   "WEBGL_lose_context",
   "WEBGL_provoking_vertex"
  ],
  "limits": {}
 },
 "media": {
  "devices": [
   "audioinput|||"
  ],
  "decoding": {
   "video/webm; codecs=\"vp9\"": {
    "supported": true,
    "smooth": true,
    "powerEfficient": false
   }
  }
 },
 "storage": {
  "quota": 10737418240,
  "usage": 0,
  "persisted": false
 },
 "speech": {
  "voices": [
   "Microsoft Huihui - Chinese (Simplified, PRC)",
   "Microsoft Kangkang - Chinese (Simplified, PRC)",
   "Microsoft Yaoyao - Chinese (Simplified, PRC)",
   "Microsoft Huihui Desktop - Chinese (Simplified)",
   "Microsoft Zira Desktop - English (United States)"
  ],
  "langs": [
   "zh-CN",
   "zh-CN",
   "zh-CN",
   "zh-CN",
   "en-US"
  ],
  "default": ""
 },
 "canvas": {
  "mode": "pixel",
  "seed": 1,
  "strength": 1,
  "density": 64,
  "preserveAlpha": true,
  "preserveWhitePoint": true,
  "pngMetadata": true
 },
 "audio": {
  "sampleRate": 48000,
  "baseLatency": 0,
  "maxChannelCount": 2
 },
 "mediaFeatures": {
  "prefersColorScheme": "light",
  "prefersReducedMotion": "no-preference",
  "prefersContrast": "no-preference",
  "forcedColors": "none",
  "colorGamut": "srgb",
  "dynamicRange": "standard",
  "pointer": "fine",
  "anyPointer": "fine",
  "hover": "hover",
  "anyHover": "hover"
 },
 "fonts": {
  "serif": "Times New Roman",
  "sansSerif": "Arial",
  "monospace": "Courier New"
 }
}
""")
REGIONS = {
    "hk": {},
    "us": {
        "locale": {"timezone": "America/Los_Angeles"},
        "speech": {"voices": ["Microsoft David - English (United States)",
                              "Microsoft Mark - English (United States)",
                              "Microsoft Zira - English (United States)",
                              "Microsoft David Desktop - English (United States)",
                              "Microsoft Zira Desktop - English (United States)"],
                   "langs": ["en-US"] * 5},
        "geolocation": {"latitude": 34.0544, "longitude": -118.244, "accuracy": 50},
        "rtc": {"iceCandidates": ["candidate:0 1 UDP 2122252543 "
                                  "376e1e4a-30cb-4a96-a220-eeba8e11c9c3.local 51723 typ host"]},
    },
}


def build_profile(region):
    profile = json.loads(json.dumps(PROFILE))
    for group, fields in REGIONS[region].items():
        profile.setdefault(group, {}).update(fields)
    return profile


# ---------------------------------------------------------------------------------------------
# Result pages: organic results, the Next link and the two interstitials.
# ---------------------------------------------------------------------------------------------
def text(fragment):
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def results(html):
    """Organic results: title, the host Google displays in <cite> (links are /goto tokens) and
    the source name above it. Video and social results show view or follower counts in <cite>
    instead of a URL; for those the source name ("TikTok", "YouTube", ...) is all there is."""
    out, body = [], html[html.find('id="rso"'):] if 'id="rso"' in html else html
    for m in re.finditer(r"<h3[^>]*>(.*?)</h3>", body, re.S):
        after = body[m.end():m.end() + 6000]
        cite = re.search(r"<cite[^>]*>(.*?)</cite>", after, re.S)
        host = re.match(r"https?://([^\s/›]+)", text(cite.group(1)) if cite else "")
        source = re.search(r'<span class="VuuXrf"[^>]*>(.*?)</span>', after, re.S)
        out.append({"title": text(m.group(1)), "host": host.group(1) if host else "",
                    "source": text(source.group(1)).split("·")[0].strip() if source else ""})
    return out


def on_site(result, site):
    """True/False when the result's host or source name shows whether it belongs to site:,
    None when the page shows neither."""
    if result["host"]:
        return result["host"] == site or result["host"].endswith("." + site)
    if result["source"]:  # "TikTok Shop" for tiktok.com, "YouTube" is not
        label = re.sub(r"^www\.", "", site).split(".")[0]
        return label in re.sub(r"[^a-z0-9]", "", result["source"].lower())
    return None


def corrected_query(html):
    """The query Google searched instead ("Showing results for ..."), or None."""
    m = re.search(r'<a[^>]*id="fprsl"[^>]*>(.*?)</a>', html, re.S)
    return text(m.group(1)) if m else None


def next_link(html, url):
    m = (re.search(r'<a[^>]*id="pnnext"[^>]*href="([^"]+)"', html) or
         re.search(r'<a[^>]*href="([^"]+)"[^>]*id="pnnext"', html))
    return urljoin(url, unescape(m.group(1))) if m else None


def with_sei(url, html):
    """The interstitial's retry: the same search with sei=<the page's eid>."""
    eid = (re.findall(r"var\s+eid\s*=\s*'([^']*)'", html) or [""])[-1]
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if k not in ("sg_ss", "sei", "eid")] + [("sei", eid)]
    return urlunsplit(parts._replace(query=urlencode(query)))


def verify_wait(html):
    """Seconds the "Verifying your request" page holds its Continue button, or None."""
    delay = re.search(r"var\s+delayMillis\s*=\s*(\d+)", html)
    return min(int(delay.group(1)), 30000) / 1000 if delay and "var eid" in html else None


def classify(status, url, html, queries, site):
    """passed: HTTP 200, path /search, q is the query (or Google's spelling correction of it,
    which its Next links carry), at least 3 organic results, and with site: no result shown
    from another site. Otherwise blocked (/sorry/), no_results, wrong_response, or poisoned."""
    final = urlsplit(url)
    if final.path.startswith("/sorry/"):
        return "blocked", []
    found = results(html)
    if not found:
        return "no_results", found
    q = [v for k, v in parse_qsl(final.query, keep_blank_values=True) if k == "q"]
    ok = status == 200 and final.path == "/search" and len(q) == 1 and q[0] in queries \
        and len(found) >= 3
    if not ok:
        return "wrong_response", found
    if site and any(on_site(r, site) is False for r in found):
        return "poisoned", found
    return "passed", found


# ---------------------------------------------------------------------------------------------
# Necko: the helper js.exe itself uses (ruyijs_necko.oneshot --session), with cookies/redirects.
# ---------------------------------------------------------------------------------------------
def auto_proxy():
    """An environment proxy first, then a local proxy on 127.0.0.1:7890, else direct."""
    for name in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        if os.environ.get(name):
            return os.environ[name]
    try:
        with socket.create_connection(("127.0.0.1", 7890), timeout=0.3):
            return "http://127.0.0.1:7890"
    except OSError:
        return None


class NeckoSession:
    """One helper process and one cookie jar per session."""

    def __init__(self, proxy=None):
        python = PYTHON
        if python is None:
            from ruyijs import get_runtime_path
            p_base = get_runtime_path() / "vendor" / "necko-derived" / "python"
            cands = [p_base / "bin" / "python3", p_base / "python3", p_base / "python.exe"]
            python = next((c for c in cands if c.is_file()), p_base / "python.exe")
        if not python.is_file():
            raise FileNotFoundError(f"Necko Python not found: {python}")
        environment = dict(os.environ)
        environment.pop("RUYIJS_HTTP_PROXY", None)
        if proxy:
            environment["RUYIJS_HTTP_PROXY"] = proxy
        self.cookies = {}
        self.process = subprocess.Popen(
            [str(python), "-I", "-B", "-m", "ruyijs_necko.oneshot", "--session"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env=environment, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    @staticmethod
    def _text(value):
        data = value.encode("utf-8")
        return struct.pack("<I", len(data)) + data

    def _read(self, size):
        data = self.process.stdout.read(size)
        if len(data) != size:
            raise EOFError("Necko session closed")
        return data

    def _read_text(self):
        return self._read(struct.unpack("<I", self._read(4))[0]).decode("utf-8")

    def send(self, method, url, headers, body=b""):
        """One request frame; returns (status, headers, body, http_version)."""
        frame = [self._text(method), self._text(url), struct.pack("<I", len(headers))]
        frame += [self._text(name) + self._text(value) for name, value in headers]
        frame.append(struct.pack("<I", len(body)) + body)
        self.process.stdin.write(b"".join(frame))
        self.process.stdin.flush()
        status = struct.unpack("<I", self._read(4))[0]
        if status == 0:
            raise ConnectionError("Necko: " + self._read_text())
        count = struct.unpack("<I", self._read(4))[0]
        fields = [(self._read_text(), self._read_text()) for _ in range(count)]
        payload = self._read(struct.unpack("<I", self._read(4))[0])
        self._read(20)  # observation trailer: magic, encoded and decoded byte counts
        return status, fields, payload, self._read_text()

    def navigate(self, url, headers, max_redirects=5):
        """GET like a top-level navigation: cookies in, Set-Cookie kept, redirects followed.
        `headers` is a function (url, site) -> header list, so Sec-Fetch-Site follows redirects."""
        site = None
        for _ in range(max_redirects + 1):
            fields = list(headers(url, site))
            cookie = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
            if cookie:
                fields.append(("Cookie", cookie))
            status, response, body, version = self.send("GET", url, fields)
            for name, value in response:
                if name.lower() == "set-cookie":
                    key, sep, val = value.split(";", 1)[0].partition("=")
                    if sep:
                        self.cookies[key.strip()] = val.strip()
            location = next((v for k, v in response if k.lower() == "location"), None)
            if status in (301, 302, 303, 307, 308) and location:
                previous, url = url, urljoin(url, location)
                site = ("same-origin" if urlsplit(previous).netloc == urlsplit(url).netloc
                        else "cross-site")
                continue
            return {"status": status, "url": url, "body": body.decode("utf-8", "replace"),
                    "headers": response, "http": version}
        raise ConnectionError("Too many redirects")

    def close(self):
        if self.process.poll() is None:
            self.process.stdin.close()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()


def firefox_headers(profile, referer=None, site="none"):
    """js.exe's navigation request defaults (domain/resource_network/request_defaults.h)."""
    nav = profile["navigator"]
    langs = [lang for lang in nav["languages"] if lang][:10]
    language = ",".join(lang if i == 0 else f"{lang};q=0.{10 - i}" for i, lang in enumerate(langs))

    def build(url, redirect_site):
        fields = [("User-Agent", nav["userAgent"]), ("Accept-Language", language),
                  ("Upgrade-Insecure-Requests", "1"), ("Accept", NAVIGATION_ACCEPT),
                  ("Accept-Encoding", "gzip, deflate, br, zstd"), ("Connection", "keep-alive"),
                  ("Priority", "u=0, i")]
        if referer:
            fields.append(("Referer", referer))
        fields += [("Sec-Fetch-Dest", "document"), ("Sec-Fetch-Mode", "navigate"),
                   ("Sec-Fetch-Site", redirect_site or site), ("Sec-Fetch-User", "?1")]
        return fields
    return build


# ---------------------------------------------------------------------------------------------
# ruyijs: run the check page at its real URL until it sets SG_SS.
# ---------------------------------------------------------------------------------------------
def compute_sg_ss(args, profile, url, html, headers):
    from ruyijs import Context, JSError
    errors = 0
    with Context(shell=args.shell, proxy=args.proxy, timeout=args.timeout) as context:
        context.configure_fingerprint(profile)
        context.configure_clock("system")
        kept = [[k, v] for k, v in headers if k.lower() in ("content-type", "set-cookie")]
        context.put_resource(url, html, headers=kept)  # served exactly as Necko received it
        context.eval("location.assign(%s);undefined" % json.dumps(url))
        deadline = monotonic() + args.timeout
        while monotonic() < deadline:
            try:
                # One task at a time: stop once SG_SS is set, before the page's own
                # retry navigation (that request is Necko's job here).
                context.advance(10, max_tasks=1)
            except JSError:
                errors += 1  # an uncaught page-script exception; the page keeps running
            match = re.search(r"(?:^|;\s*)SG_SS=([^;]+)", context.eval("document.cookie"))
            if match:
                return match.group(1), errors
    raise TimeoutError("The check page did not set SG_SS")


def search(args, profile, url):
    """One search plus args.pages Next pages; returns (session, timings, pages)."""
    timings, pages, started = {}, [], monotonic()
    point = started

    def lap(name):
        nonlocal point
        timings[name] = round(monotonic() - point, 2)
        point = monotonic()
        return timings[name]

    site = (re.findall(r"site:([^\s&]+)", unquote_plus(url)) or [None])[0]
    query = ([v for k, v in parse_qsl(urlsplit(url).query) if k == "q"] or [""])[0]
    session, necko, start_url = {"attempts": 0}, None, url
    try:
        # No results on page 1 (another check, or SG_SS rejected): fresh session and jar.
        for attempt in range(1 + args.retries):
            necko and necko.close()
            necko = NeckoSession(args.proxy)
            session["attempts"] = attempt + 1
            suffix = "" if attempt == 0 else f".retry{attempt}"
            reply = necko.navigate(start_url, firefox_headers(profile))
            seconds = lap("necko.search" + suffix)
            url, html = reply["url"], reply["body"]
            session.update(http=reply["http"], interstitial="SG_SS" in html)
            if session["interstitial"]:
                sg_ss, session["scriptErrors"] = compute_sg_ss(args, profile, url, html,
                                                               reply["headers"])
                lap("ruyijs.sgss" + suffix)
                necko.cookies["SG_SS"] = sg_ss
                reply = necko.navigate(with_sei(url, html),
                                       firefox_headers(profile, referer=url, site="same-origin"))
                url, html = reply["url"], reply["body"]
                seconds = lap("necko.page1" + suffix)
            if results(html):
                break
        queries = {query}
        for index in range(args.pages + 1):
            corrected = corrected_query(html)
            if corrected:
                queries.add(corrected)
            outcome, found = classify(reply["status"], url, html, queries, site)
            entry = {"page": index + 1, "status": outcome, "httpStatus": reply["status"],
                     "seconds": seconds, "finalUrl": url, "resultCount": len(found)}
            if corrected:
                entry["correctedQuery"] = corrected
            if site:
                for r in found:
                    r["onSite"] = on_site(r, site)
                entry["offSite"] = sum(r["onSite"] is False for r in found)
                entry["unverified"] = sum(r["onSite"] is None for r in found)
            entry["results"] = found
            if not found:  # what the page was instead (a check page, an empty page, ...)
                entry["excerpt"] = re.sub(r"\s+", " ", re.sub(
                    r"<script.*?</script>|<style.*?</style>|<[^>]+>", " ", html, flags=re.S))[:300]
            pages.append(entry)
            nxt = next_link(html, url)
            if index == args.pages or not nxt or outcome == "blocked":
                break
            sleep(args.read_ms / 1000)  # a reader's pause before clicking Next
            point = monotonic()
            reply = necko.navigate(nxt, firefox_headers(profile, referer=url, site="same-origin"))
            url, html = reply["url"], reply["body"]
            for _ in range(2):  # Google's mid-session "Verifying your request" page
                wait = None if results(html) else verify_wait(html)
                if wait is None:
                    break
                session["verifications"] = session.get("verifications", 0) + 1
                print(f"  Google asked to verify; waiting {wait:g}s like a user ...", file=sys.stderr)
                sleep(wait)
                reply = necko.navigate(with_sei(url, html),
                                       firefox_headers(profile, referer=url, site="same-origin"))
                url, html = reply["url"], reply["body"]
            seconds = lap(f"necko.page{index + 2}")
    finally:
        necko and necko.close()
    timings["total"] = round(monotonic() - started, 2)
    return session, timings, pages


def run_one(args, profile, url):
    out = {"url": url}
    try:
        out["session"], out["timings"], out["pages"] = search(args, profile, url)
        statuses = [p["status"] for p in out["pages"]]
        ok = len(out["pages"]) == args.pages + 1 and all(s == "passed" for s in statuses)
        out["status"] = "passed" if ok else "poisoned" if "poisoned" in statuses else "partial"
    except Exception as error:
        out.update(status="error", error=type(error).__name__ + ": " + str(error)[:500])
    return out


def print_summary(report):
    for run in report["searches"]:
        print(f"\n== {run['url']}  [{run['status']}]")
        if "error" in run:
            print("   error:", run["error"])
        for page in run.get("pages", []):
            extra = (f", {page['offSite']} off-site, {page['unverified']} unverified"
                     if "offSite" in page else "")
            if "correctedQuery" in page:
                extra += f", Google searched: {page['correctedQuery']}"
            print(f"-- page {page['page']}: {page['status']}, {page['resultCount']} results, "
                  f"{page['seconds']}s{extra}")
            for i, item in enumerate(page["results"], 1):
                where = item["host"] or item["source"]
                mark = {False: "  << OFF-SITE", None: "  (?)"}.get(item.get("onSite"), "")
                print(f"   {i:2}. {item['title'][:90]}" + (f"  ({where})" if where else "") + mark)
            if "excerpt" in page:
                print("   page text:", page["excerpt"][:200])
        if "timings" in run:
            print("   timings:", ", ".join(f"{k} {v}s" for k, v in run["timings"].items()))
    print(f"\nproxy: {report['proxy']}   status: {report['status']}")


def launched_by_double_click():
    """The console holds only cmd.exe and this Python: it closes when we exit."""
    if os.name != "nt" or not (sys.stdin.isatty() and sys.stdout.isatty()):
        return False
    try:
        return ctypes.windll.kernel32.GetConsoleProcessList((ctypes.c_uint32 * 8)(), 8) <= 2
    except (AttributeError, OSError):
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--query", action="append",
                        help=f'search terms; repeat for several searches (default: "{DEFAULT_QUERY}")')
    parser.add_argument("--url", action="append", help="a full google.com/search URL instead")
    parser.add_argument("--pages", type=int, default=3, help="Next pages after page 1 (default 3)")
    parser.add_argument("--region", choices=sorted(REGIONS), default="hk",
                        help="built-in profile variant: hk (Asia/Hong_Kong) or us (Los Angeles)")
    parser.add_argument("--profile", type=Path, help="a profile JSON file instead of the built-in one")
    parser.add_argument("--dump-profile", type=Path, metavar="FILE",
                        help="write the selected built-in profile to FILE and exit")
    parser.add_argument("--seed", type=int, help="canvas noise seed (default: random)")
    parser.add_argument("--proxy", help="HTTP(S) proxy URL (default: env proxy, 127.0.0.1:7890, direct)")
    parser.add_argument("--direct", action="store_true", help="never use a proxy")
    parser.add_argument("--timeout", type=float, default=60, help="seconds for the SG_SS check")
    parser.add_argument("--retries", type=int, default=2, help="fresh sessions when page 1 has no results")
    parser.add_argument("--read-ms", type=int, default=0, help="pause before each Next (ms)")
    parser.add_argument("--json", action="store_true", help="print the full JSON report")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    pause = launched_by_double_click()
    from ruyijs import get_runtime_path
    global PYTHON
    try:
        runtime = get_runtime_path()
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    PYTHON = runtime / "vendor" / "necko-derived" / "python" / "python.exe"
    if not PYTHON.is_file():
        print(f"Necko Python not found: {PYTHON} (run tools/build.py or use a release)", file=sys.stderr)
        return 1

    profile = build_profile(args.region)
    if args.dump_profile:
        args.dump_profile.write_text(json.dumps(profile, ensure_ascii=False, indent=1) + "\n", "utf-8")
        print(f"wrote {args.dump_profile}")
        return 0
    if args.profile:
        profile = json.loads(args.profile.read_text("utf-8"))
    if "canvas" in profile:
        profile["canvas"]["seed"] = args.seed or random.randint(1, 2**53 - 1)

    args.shell = Path(os.environ.get("RUYIJS_SHELL") or runtime / "dist" / "js.exe").resolve()
    args.proxy = None if args.direct else (args.proxy or auto_proxy())
    urls = list(args.url or []) + ["https://www.google.com/search?" + urlencode({"q": q})
                                   for q in (args.query or []) if q.strip()]
    urls = urls or ["https://www.google.com/search?" + urlencode({"q": DEFAULT_QUERY})]

    report = {"transport": "ruyijs-parameters+necko", "proxy": args.proxy or "direct", "searches": []}
    if not args.shell.is_file():
        report["searches"].append({"url": urls[0], "status": "error",
                                   "error": f"ruyijs runtime not found: {args.shell} "
                                            "(run tools/build.py or set RUYIJS_SHELL)"})
    else:
        for url in urls:
            if not args.json:
                print(f"searching {url} via {report['proxy']} ...", file=sys.stderr)
            report["searches"].append(run_one(args, profile, url))
    passed = sum(run["status"] == "passed" for run in report["searches"])
    report["status"] = ("passed" if passed == len(urls) and len(report["searches"]) == len(urls)
                        else "poisoned" if any(r["status"] == "poisoned" for r in report["searches"])
                        else "partial" if passed else "error")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_summary(report)
    if pause:
        input("\nPress Enter to close ...")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
