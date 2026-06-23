#!/usr/bin/env python3
# Freddie's space — 웹 글쓰기 백엔드 + 정적 HTML/사이트맵/RSS 생성 (검색·AI 노출용)
# Caddy가 /write 를 basic_auth 로 보호한 뒤 이 서버로 프록시한다 (strip_prefix /write).
import os, re, json, glob, base64, subprocess, datetime
import html as html_mod
from urllib.parse import quote
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import markdown as mdlib
from bs4 import BeautifulSoup

REPO   = "/repo"
PUBLIC = os.path.join(REPO, "public")
LOGDIR = os.path.join(PUBLIC, "log")
MEDIA  = os.path.join(LOGDIR, "media")
SITE   = os.environ.get("SITE_URL", "https://codedeck.duckdns.org")
AUTHOR = "Freddie"
OG_DEFAULT = SITE + "/jwst-carina.jpg"
PORT   = int(os.environ.get("PORT", "8080"))
MAXUP  = 20 * 1024 * 1024

os.makedirs(MEDIA, exist_ok=True)

# ───────────────────────── helpers ─────────────────────────
def slugify(date, title):
    base = re.sub(r"\s+", "-", title.strip())
    base = re.sub(r"[^0-9A-Za-z가-힣_-]", "", base)
    base = re.sub(r"-+", "-", base).strip("-") or "untitled"
    return f"{date}-{base}"

def today():
    return datetime.datetime.now().strftime("%Y-%m-%d")

def rebuild_index():
    posts = []
    for f in sorted(glob.glob(os.path.join(LOGDIR, "*.md"))):
        name = os.path.basename(f)[:-3]
        mo = re.match(r"(\d{4}-\d{2}-\d{2})", name)
        date = mo.group(1) if mo else ""
        lines = open(f, encoding="utf-8").read().splitlines()
        title, summary = name, ""
        for l in lines:
            s = l.strip()
            if s.startswith("# "): title = s[2:].strip(); break
        for l in lines:
            s = l.strip()
            if s and not s.startswith("#"):
                summary = re.sub(r"[*_`>\[\]]", "", s)[:90]; break
        posts.append({"slug": name, "date": date, "title": title, "summary": summary})
    posts.sort(key=lambda p: (p["date"], p["slug"]), reverse=True)
    open(os.path.join(LOGDIR, "index.json"), "w", encoding="utf-8").write(
        json.dumps(posts, ensure_ascii=False, indent=2) + "\n")
    return posts

def render_markdown(md):
    """마크다운 → (본문 html, standfirst, 읽기시간분, 설명용 평문). figure/캡션 가공 포함."""
    md = re.sub(r"^(?:﻿?\s*#\s+.*(?:\r?\n|$))+", "", md).lstrip()
    standfirst = ""
    m = re.match(r"^##\s*[—–-]\s*(.+?)\s*(?:\r?\n|$)", md)
    if m:
        standfirst = m.group(1).strip(); md = md[m.end():]
    raw = mdlib.markdown(md, extensions=["extra", "sane_lists", "nl2br"])
    soup = BeautifulSoup(raw, "html.parser")
    for p in list(soup.find_all("p")):
        kids = [c for c in p.children if not (isinstance(c, str) and not c.strip())]
        if not kids or getattr(kids[0], "name", None) != "img":
            continue
        img = kids[0]
        fig = soup.new_tag("figure")
        src = (img.get("src") or "").lower()
        if re.search(r"\.(svg|png|gif|webp)(\?|#|$)", src):
            fig["class"] = "fig-diagram"
        cap_em = p.find("em")
        img.extract(); fig.append(img)
        if cap_em is not None:
            cap = soup.new_tag("figcaption")
            cap.append(BeautifulSoup(cap_em.decode_contents(), "html.parser"))
            fig.append(cap)
        else:
            nxt = p.find_next_sibling()
            if nxt is not None and nxt.name == "p":
                nk = [c for c in nxt.children if not (isinstance(c, str) and not c.strip())]
                if len(nk) == 1 and getattr(nk[0], "name", None) == "em":
                    cap = soup.new_tag("figcaption")
                    cap.append(BeautifulSoup(nk[0].decode_contents(), "html.parser"))
                    fig.append(cap); nxt.decompose()
        p.replace_with(fig)
    for img in soup.find_all("img"):
        img["loading"] = "lazy"; img["referrerpolicy"] = "no-referrer"
    text = soup.get_text(" ", strip=True)
    chars = len(re.sub(r"\s+", "", text))
    reading = max(1, round(chars / 500))
    return str(soup), standfirst, reading, text

def first_image(md):
    m = re.search(r"!\[[^\]]*\]\(([^)\s]+)", md)
    if not m: return None
    u = m.group(1)
    return SITE + u if u.startswith("/") else u

def og_image(md):
    return first_image(md) or OG_DEFAULT

def desc_of(standfirst, summary, text):
    d = (standfirst or summary or text or "").strip()
    d = re.sub(r"\s+", " ", d)
    return d[:155]

def pad(n): return str(n).zfill(3)

# ───────────────────────── static page template ─────────────────────────
PAGE_CSS = r"""
  :root{--ink:#070a12;--star:#f3efe3;--brass:#c7a24a;--haze:#9aabc8;--line:rgba(199,162,74,.16);--inset:34px}
  *{margin:0;padding:0;box-sizing:border-box}
  html{scroll-behavior:smooth}
  body{min-height:100%;background:var(--ink);color:var(--star);font-family:'IBM Plex Mono',ui-monospace,monospace;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
  .bg1{position:fixed;inset:0;z-index:0;pointer-events:none;background:radial-gradient(1000px 680px at 80% 8%, rgba(40,58,120,.20), transparent 62%),radial-gradient(880px 600px at 8% 92%, rgba(96,58,130,.14), transparent 64%),radial-gradient(circle at 50% 26%, #0b1020 0%, #070a12 70%, #03040a 100%)}
  .bg2{position:fixed;inset:0;z-index:0;pointer-events:none;opacity:.28;background-image:radial-gradient(1.1px 1.1px at 40px 60px,#fff,transparent),radial-gradient(1px 1px at 220px 120px,#cfe0ff,transparent),radial-gradient(1.2px 1.2px at 380px 220px,#fff,transparent),radial-gradient(1px 1px at 540px 80px,#a9c2ff,transparent);background-repeat:repeat;background-size:600px 320px}
  .plate{position:fixed;inset:var(--inset);z-index:1;pointer-events:none;border:1px solid rgba(199,162,74,.14)}
  .tick{position:absolute;width:12px;height:12px;opacity:.8;background:linear-gradient(var(--brass),var(--brass)) center/12px 1px no-repeat,linear-gradient(var(--brass),var(--brass)) center/1px 12px no-repeat}
  .tl{left:-6px;top:-6px}.tr{right:-6px;top:-6px}.bl{left:-6px;bottom:-6px}.br{right:-6px;bottom:-6px}
  #progress{position:fixed;top:0;left:0;height:2px;width:100%;background:var(--brass);transform:scaleX(0);transform-origin:left center;z-index:12;transition:transform .12s linear;box-shadow:0 0 8px rgba(199,162,74,.55);pointer-events:none}
  .wrap{position:relative;z-index:2;max-width:680px;margin:0 auto;padding:clamp(58px,10vh,116px) clamp(26px,6vw,42px) 130px}
  .top{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:clamp(40px,8vh,82px)}
  .back{font-size:11px;letter-spacing:.26em;text-transform:uppercase;color:var(--brass);text-decoration:none;border-bottom:1px solid transparent;padding-bottom:2px;transition:color .3s,border-color .3s}
  .back:hover{color:var(--star);border-color:var(--brass)}
  .crumb{font-size:11px;letter-spacing:.26em;text-transform:uppercase;color:var(--haze)}
  .phead{margin-bottom:clamp(28px,5vh,48px)}
  .phead .meta{display:flex;flex-wrap:wrap;align-items:center;gap:10px;font-size:11px;letter-spacing:.22em;text-transform:uppercase;margin-bottom:20px}
  .phead .meta .n{color:var(--brass)}.phead .meta .sep{color:rgba(199,162,74,.4)}.phead .meta .x{color:var(--haze)}
  .phead h1{font-family:'Cormorant','Noto Serif KR',serif;font-weight:500;font-size:clamp(32px,5.2vw,55px);line-height:1.07;letter-spacing:.008em;color:var(--star);text-wrap:balance}
  .standfirst{font-family:'Cormorant','Noto Serif KR',serif;font-style:italic;font-weight:500;font-size:clamp(18px,2.3vw,23px);color:#b9a368;margin-top:18px;line-height:1.32;letter-spacing:.01em}
  .fs-prose{font-family:'Newsreader','Noto Serif KR',serif;font-size:17px;line-height:1.78;color:#e4e0d2;font-variant-numeric:oldstyle-nums}
  .fs-prose > p:first-of-type{font-size:1.05em;line-height:1.72;color:#efeadd}
  .fs-prose p{margin:0 0 1.3em}
  .fs-prose h2{font-family:'Cormorant','Noto Serif KR',serif;font-weight:600;font-size:1.68em;line-height:1.14;margin:2.2em 0 .6em;color:#f5f1e6;letter-spacing:.005em}
  .fs-prose h2:first-child{margin-top:0}
  .fs-prose h3{font-family:'Cormorant','Noto Serif KR',serif;font-weight:600;font-size:1.3em;line-height:1.24;margin:1.9em 0 .5em;color:#f1ecdf}
  .fs-prose strong{color:#f5f1e6;font-weight:600}
  .fs-prose em{font-style:italic;color:#e9e4d6}
  .fs-prose a{color:#c7a24a;text-decoration:underline;text-decoration-thickness:1px;text-underline-offset:3px;text-decoration-color:rgba(199,162,74,.42);transition:color .25s,text-decoration-color .25s}
  .fs-prose a:hover{color:#f3efe3;text-decoration-color:#c7a24a}
  .fs-prose ul,.fs-prose ol{margin:0 0 1.3em;padding-left:1.3em}
  .fs-prose li{margin:.4em 0;padding-left:.2em}.fs-prose li::marker{color:#c7a24a}
  .fs-prose blockquote{margin:1.9em 0;padding:.5em 0 .5em 1.5em;border-left:2px solid #c7a24a;font-style:italic;color:#cdd4e3}
  .fs-prose blockquote p{margin:.5em 0}.fs-prose blockquote strong{color:#e3c373;font-style:normal}
  .fs-prose code{font-family:'IBM Plex Mono',monospace;font-size:.8em;background:rgba(199,162,74,.1);padding:.13em .42em;border-radius:3px;color:#e3c373}
  .fs-prose pre{background:rgba(9,14,26,.7);border:1px solid rgba(199,162,74,.16);border-radius:6px;padding:18px 20px;overflow:auto;margin:1.7em 0}
  .fs-prose pre code{background:none;padding:0;color:#dfe6f2;font-size:.84em;line-height:1.65}
  .fs-prose hr{border:0;height:1px;background:linear-gradient(90deg,transparent,rgba(199,162,74,.5),transparent);margin:2.8em 0}
  .fs-prose table{width:100%;border-collapse:collapse;margin:2em 0;font-family:'IBM Plex Mono',monospace;font-size:13.5px;line-height:1.5}
  .fs-prose thead th{text-align:left;color:#c7a24a;font-weight:500;letter-spacing:.06em;text-transform:uppercase;font-size:11.5px;padding:11px 16px 11px 0;border-bottom:1px solid rgba(199,162,74,.42)}
  .fs-prose tbody td{padding:12px 16px 12px 0;border-bottom:1px solid rgba(199,162,74,.12);color:#d7d2c3;vertical-align:top}
  .fs-prose tbody td:first-child{color:#efeadd}
  .fs-prose figure{margin:2.2em 0}
  .fs-prose figure img{width:100%;height:auto;display:block;border-radius:4px;border:1px solid rgba(199,162,74,.18);background:rgba(10,16,30,.5)}
  .fs-prose figure.fig-diagram img{background:#f4f1e9;padding:20px;box-sizing:border-box}
  .fs-prose figcaption{font-family:'IBM Plex Mono',monospace;font-size:11.5px;line-height:1.65;color:#9aabc8;margin-top:11px;letter-spacing:.015em;padding-left:14px;border-left:1px solid rgba(199,162,74,.32)}
  .fs-prose img{max-width:100%;height:auto}
  .foot{margin-top:clamp(56px,9vh,92px)}
  .foot .div{display:flex;align-items:center;gap:16px;margin-bottom:30px}
  .foot .div span.l{flex:1;height:1px;background:rgba(199,162,74,.18)}
  .foot .div span.s{color:var(--brass);font-size:13px;letter-spacing:.4em}
  .nav{display:flex;gap:18px;align-items:stretch}
  .nav a{flex:1;text-decoration:none;color:inherit;border:1px solid var(--line);border-radius:4px;padding:16px 18px;transition:background .3s,border-color .3s}
  .nav a:hover{background:rgba(199,162,74,.05);border-color:rgba(199,162,74,.4)}
  .nav a.newer{text-align:right}
  .nav .lbl{font-size:10px;letter-spacing:.2em;text-transform:uppercase;color:var(--haze)}
  .nav .t{font-family:'Cormorant','Noto Serif KR',serif;font-size:20px;color:var(--star);margin-top:7px;line-height:1.15}
  .tolist{margin-top:30px;text-align:center;font-size:11px;letter-spacing:.18em}
  .tolist a{color:var(--brass);text-decoration:none}.tolist a:hover{color:var(--star)}
  @media (max-width:560px){:root{--inset:16px}.nav{flex-direction:column}.nav a.newer{text-align:left}.fs-prose{font-size:17.5px}.fs-prose table{font-size:12.5px}}
  @media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}*{animation:none!important;transition:none!important}}
"""

GA = ('<script async src="https://www.googletagmanager.com/gtag/js?id=G-JJQRYQ0NG6"></script>'
  "<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments)}"
  "gtag('js',new Date());gtag('config','G-JJQRYQ0NG6');</script>")

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com"/>'
  '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>'
  '<link href="https://fonts.googleapis.com/css2?family=Cormorant:ital,wght@0,400;0,500;0,600;1,400;1,500;1,600&family=IBM+Plex+Mono:wght@400;500&family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;0,6..72,600;1,6..72,400;1,6..72,500&display=swap" rel="stylesheet"/>'
  '<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@400;500;600;700&display=swap" rel="stylesheet"/>')

def post_page(meta, num, body_html, standfirst, reading, older, newer, desc, ogimg):
    slug, title, date = meta["slug"], meta["title"], meta["date"]
    url = f"{SITE}/log/{quote(slug)}.html"
    e = html_mod.escape
    jsonld = json.dumps({
        "@context": "https://schema.org", "@type": "BlogPosting",
        "headline": title, "datePublished": date, "dateModified": date,
        "inLanguage": "ko", "author": {"@type": "Person", "name": AUTHOR},
        "publisher": {"@type": "Person", "name": AUTHOR},
        "mainEntityOfPage": url, "url": url, "image": ogimg, "description": desc,
    }, ensure_ascii=False)
    sf = f'<p class="standfirst">{e(standfirst)}</p>' if standfirst else ""
    nav = ""
    if older:
        nav += (f'<a class="older" href="/log/{quote(older["slug"])}.html">'
                f'<div class="lbl">&larr; 이전 기록</div><div class="t">{e(older["title"])}</div></a>')
    if newer:
        nav += (f'<a class="newer" href="/log/{quote(newer["slug"])}.html">'
                f'<div class="lbl">다음 기록 &rarr;</div><div class="t">{e(newer["title"])}</div></a>')
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>{e(title)} · Freddie's space</title>
<meta name="description" content="{e(desc)}"/>
<meta name="author" content="{AUTHOR}"/>
<link rel="canonical" href="{url}"/>
<meta property="og:type" content="article"/>
<meta property="og:site_name" content="Freddie's space"/>
<meta property="og:title" content="{e(title)}"/>
<meta property="og:description" content="{e(desc)}"/>
<meta property="og:url" content="{url}"/>
<meta property="og:image" content="{e(ogimg)}"/>
<meta property="article:published_time" content="{date}"/>
<meta name="twitter:card" content="summary_large_image"/>
<meta name="twitter:title" content="{e(title)}"/>
<meta name="twitter:description" content="{e(desc)}"/>
<meta name="twitter:image" content="{e(ogimg)}"/>
<script type="application/ld+json">{jsonld}</script>
{GA}
{FONTS}
<style>{PAGE_CSS}</style>
</head>
<body>
<div class="bg1"></div><div class="bg2"></div>
<div class="plate"><i class="tick tl"></i><i class="tick tr"></i><i class="tick bl"></i><i class="tick br"></i></div>
<div id="progress"></div>
<div class="wrap">
  <div class="top"><a class="back" href="/log.html">&larr; Field Log</a><span class="crumb">Entry</span></div>
  <article>
    <div class="phead">
      <div class="meta"><span class="n">LOG · {pad(num)}</span><span class="sep">/</span><time class="x" datetime="{date}">{date}</time><span class="sep">/</span><span class="x">{reading}분 읽기</span></div>
      <h1>{e(title)}</h1>
      {sf}
    </div>
    <div class="fs-prose">{body_html}</div>
  </article>
  <div class="foot">
    <div class="div"><span class="l"></span><span class="s">✦</span><span class="l"></span></div>
    <div class="nav">{nav}</div>
    <div class="tolist"><a href="/log.html">전체 목록으로</a> · <a href="/">Freddie&rsquo;s space</a></div>
  </div>
</div>
<script>
(function(){{
  var bar=document.getElementById('progress');
  function up(){{var h=document.documentElement,m=h.scrollHeight-h.clientHeight,p=m>0?Math.min(1,Math.max(0,(scrollY||h.scrollTop)/m)):0;bar.style.transform='scaleX('+p+')';}}
  addEventListener('scroll',up,{{passive:true}});addEventListener('resize',up);up();
}})();
</script>
</body>
</html>
"""

def build_static(posts):
    for f in glob.glob(os.path.join(LOGDIR, "*.html")):
        os.remove(f)
    n = len(posts)
    for i, p in enumerate(posts):
        md = open(os.path.join(LOGDIR, p["slug"] + ".md"), encoding="utf-8").read()
        body, standfirst, reading, text = render_markdown(md)
        desc = desc_of(standfirst, p.get("summary"), text)
        ogimg = og_image(md)
        page = post_page(p, n - i, body, standfirst, reading,
                         posts[i+1] if i+1 < n else None,
                         posts[i-1] if i > 0 else None, desc, ogimg)
        open(os.path.join(LOGDIR, p["slug"] + ".html"), "w", encoding="utf-8").write(page)

def build_sitemap(posts):
    today_s = today()
    urls = [(SITE + "/", today_s, "weekly", "1.0"),
            (SITE + "/log.html", today_s, "weekly", "0.8")]
    for p in posts:
        urls.append((f"{SITE}/log/{quote(p['slug'])}.html", p["date"] or today_s, "monthly", "0.6"))
    body = ['<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, lastmod, cf, pr in urls:
        body.append(f"  <url><loc>{html_mod.escape(loc)}</loc><lastmod>{lastmod}</lastmod>"
                    f"<changefreq>{cf}</changefreq><priority>{pr}</priority></url>")
    body.append("</urlset>\n")
    open(os.path.join(PUBLIC, "sitemap.xml"), "w", encoding="utf-8").write("\n".join(body))

def build_rss(posts):
    def rfc822(d):
        try: dt = datetime.datetime.strptime(d, "%Y-%m-%d")
        except Exception: dt = datetime.datetime.now()
        return dt.strftime("%a, %d %b %Y 00:00:00 +0900")
    items = []
    for p in posts[:20]:
        link = f"{SITE}/log/{quote(p['slug'])}.html"
        items.append("<item>"
            f"<title>{html_mod.escape(p['title'])}</title>"
            f"<link>{html_mod.escape(link)}</link>"
            f"<guid isPermaLink=\"true\">{html_mod.escape(link)}</guid>"
            f"<pubDate>{rfc822(p['date'])}</pubDate>"
            f"<description><![CDATA[{p.get('summary','')}]]></description>"
            "</item>")
    rss = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<rss version="2.0"><channel>'
           "<title>Freddie's space — Field Log</title>"
           f"<link>{SITE}/log.html</link>"
           "<description>떠오르는 생각을 하나씩, 궤도에 남긴다.</description>"
           "<language>ko</language>"
           f"<atom:link xmlns:atom=\"http://www.w3.org/2005/Atom\" href=\"{SITE}/rss.xml\" rel=\"self\" type=\"application/rss+xml\"/>"
           + "".join(items) + "</channel></rss>\n")
    open(os.path.join(PUBLIC, "rss.xml"), "w", encoding="utf-8").write(rss)

def build_all():
    posts = rebuild_index()
    build_static(posts)
    build_sitemap(posts)
    build_rss(posts)
    return posts

def git_push(msg):
    try:
        subprocess.run(["git", "-C", REPO, "add", "-A"], check=True, timeout=30)
        c = subprocess.run(["git", "-C", REPO, "-c", "user.name=Freddie",
                            "-c", "user.email=kimtayoon@gmail.com", "commit", "-m", msg], timeout=30)
        if c.returncode == 0:
            subprocess.run(["git", "-C", REPO, "push", "origin", "main"], check=True, timeout=60)
            return "pushed"
        return "nochange"
    except Exception as e:
        return f"git-skip: {e}"

# ───────────────────────── HTTP ─────────────────────────
class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)): body = json.dumps(body, ensure_ascii=False)
        if isinstance(body, str): body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json_body(self):
        n = int(self.headers.get("Content-Length", "0"))
        if n > MAXUP: raise ValueError("too large")
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", ""):  return self._send(200, EDITOR, "text/html; charset=utf-8")
        if path == "/api/posts": return self._send(200, rebuild_index())
        if path == "/api/post":
            from urllib.parse import unquote
            q = dict(p.split("=", 1) for p in self.path.split("?", 1)[1].split("&")) if "?" in self.path else {}
            slug = unquote(re.sub(r"[^0-9A-Za-z가-힣_%-]", "", q.get("slug", "")))
            f = os.path.join(LOGDIR, slug + ".md")
            if not os.path.isfile(f): return self._send(404, {"error": "not found"})
            md = open(f, encoding="utf-8").read()
            m = re.search(r"^\s*#\s+(.+)\s*$", md, re.M)
            title = m.group(1).strip() if m else slug
            if m: md = md.replace(m.group(0), "", 1).lstrip("\n")
            return self._send(200, {"slug": slug, "title": title, "markdown": md})
        return self._send(404, {"error": "no route"})

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        try:
            data = self._json_body()
        except Exception as e:
            return self._send(400, {"error": str(e)})

        if path == "/api/upload":
            name = re.sub(r"[^0-9A-Za-z._-]", "_", data.get("name", "img"))
            raw = data.get("data", "")
            if "," in raw: raw = raw.split(",", 1)[1]
            try: blob = base64.b64decode(raw)
            except Exception: return self._send(400, {"error": "bad image"})
            if len(blob) > MAXUP: return self._send(400, {"error": "too large"})
            stem, ext = os.path.splitext(name)
            fn = name; i = 1
            while os.path.exists(os.path.join(MEDIA, fn)):
                fn = f"{stem}-{i}{ext}"; i += 1
            open(os.path.join(MEDIA, fn), "wb").write(blob)
            return self._send(200, {"path": f"/log/media/{fn}"})

        if path == "/api/save":
            title = (data.get("title") or "").strip()
            body  = (data.get("markdown") or "").strip()
            slug  = (data.get("slug") or "").strip()
            if not title: return self._send(400, {"error": "제목을 입력하세요"})
            if not slug:  slug = slugify(today(), title)
            slug = re.sub(r"[^0-9A-Za-z가-힣_-]", "", slug)
            open(os.path.join(LOGDIR, slug + ".md"), "w", encoding="utf-8").write(f"# {title}\n\n{body}\n")
            build_all()
            g = git_push(f"log: {title}")
            return self._send(200, {"ok": True, "slug": slug, "url": f"{SITE}/log/{quote(slug)}.html", "git": g})

        if path == "/api/delete":
            slug = re.sub(r"[^0-9A-Za-z가-힣_-]", "", (data.get("slug") or "").strip())
            for ext in (".md", ".html"):
                fp = os.path.join(LOGDIR, slug + ext)
                if os.path.isfile(fp): os.remove(fp)
            build_all()
            g = git_push(f"log: delete {slug}")
            return self._send(200, {"ok": True, "git": g})

        return self._send(404, {"error": "no route"})

    def log_message(self, *a): pass

EDITOR = r"""<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8">
<base href="/write/">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Write · Freddie's space</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Cormorant:wght@500;600&family=IBM+Plex+Mono:wght@400;500&family=Newsreader:opsz,wght@6..72,400&display=swap" rel="stylesheet">
<style>
:root{--ink:#070a12;--panel:#0d1424;--star:#f3efe3;--brass:#c7a24a;--haze:#9aabc8;--line:rgba(199,162,74,.18)}
*{margin:0;padding:0;box-sizing:border-box}
body{height:100vh;background:var(--ink);color:var(--star);font-family:'IBM Plex Mono',monospace;display:flex;overflow:hidden}
aside{width:260px;flex:none;border-right:1px solid var(--line);padding:22px 16px;overflow:auto;background:#0a0f1c}
aside h2{font-family:'Cormorant',serif;font-weight:600;font-size:24px;color:var(--star);margin-bottom:4px}
aside .sub{font-size:10px;letter-spacing:.2em;color:var(--brass);text-transform:uppercase;margin-bottom:20px}
.newbtn{width:100%;padding:10px;margin-bottom:18px;background:transparent;border:1px solid var(--brass);color:var(--brass);
 border-radius:6px;cursor:pointer;font-family:inherit;font-size:12px;letter-spacing:.1em;transition:.2s}
.newbtn:hover{background:var(--brass);color:var(--ink)}
.plist{list-style:none}.plist li{padding:10px 8px;border-bottom:1px solid var(--line);cursor:pointer;font-size:12px;transition:.2s}
.plist li:hover{background:rgba(199,162,74,.07);padding-left:12px}.plist li.on{color:var(--brass)}
.plist .d{color:var(--haze);font-size:10px;letter-spacing:.08em}
.plist .t{font-family:'Cormorant',serif;font-size:17px;font-weight:500;line-height:1.2;margin-top:2px;color:var(--star)}
main{flex:1;display:flex;flex-direction:column;min-width:0}
.bar{display:flex;align-items:center;gap:10px;padding:14px 22px;border-bottom:1px solid var(--line)}
.bar .grow{flex:1}
.bar a,.bar button{font-family:inherit;font-size:12px;letter-spacing:.08em;cursor:pointer}
.bar a{color:var(--haze);text-decoration:none}.bar a:hover{color:var(--star)}
.btn{padding:9px 18px;border-radius:6px;border:1px solid var(--line);background:transparent;color:var(--haze);transition:.2s}
.btn:hover{color:var(--star);border-color:var(--brass)}
.btn.go{background:linear-gradient(180deg,#d9be72,#c7a24a);border:0;color:var(--ink);font-weight:500}
.btn.go:hover{filter:brightness(1.08)}
.btn.del{margin-left:auto;color:#c98b8b;border-color:rgba(201,139,139,.4)}
.edit{flex:1;display:flex;min-height:0}
.col{flex:1;display:flex;flex-direction:column;min-width:0}
.col.prev{border-left:1px solid var(--line);overflow:auto;padding:32px 40px;background:#05070e}
#title{width:100%;padding:24px 32px 8px;background:transparent;border:0;color:var(--star);
 font-family:'Cormorant',serif;font-size:40px;font-weight:500;outline:none}
#title::placeholder{color:rgba(154,171,200,.4)}
#body{flex:1;width:100%;padding:8px 32px 24px;background:transparent;border:0;resize:none;outline:none;
 color:#e7e3d6;font-family:'IBM Plex Mono',monospace;font-size:14.5px;line-height:1.7}
.drop{outline:2px dashed var(--brass);outline-offset:-10px}
.status{padding:8px 22px;font-size:11px;letter-spacing:.1em;color:var(--haze);border-top:1px solid var(--line);min-height:30px}
.status.ok{color:#9bd6a0}.status.err{color:#e0a3a3}
.prev{font-family:'Newsreader',serif;font-size:17px;line-height:1.75;color:#e7e3d6}
.prev h1{font-family:'Cormorant',serif;font-size:2em;margin:.2em 0 .5em;color:var(--star)}
.prev h2{font-family:'Cormorant',serif;font-size:1.5em;margin:1.2em 0 .4em;color:var(--star)}
.prev p{margin:0 0 1em}.prev a{color:var(--brass)}
.prev blockquote{border-left:2px solid var(--brass);padding-left:1em;color:var(--haze);font-style:italic;margin:1em 0}
.prev img{max-width:100%;border-radius:6px;margin:1em 0}.prev code{background:rgba(199,162,74,.12);padding:.1em .4em;border-radius:3px;font-size:.85em}
.hide{display:none}
@media(max-width:820px){aside{display:none}.col.prev{display:none}}
</style></head><body>
<aside>
  <h2>기록</h2><div class="sub">Field Log · Write</div>
  <button class="newbtn" onclick="newPost()">+ 새 글</button>
  <ul class="plist" id="plist"></ul>
</aside>
<main>
  <div class="bar">
    <input type="file" id="file" accept="image/*" class="hide" multiple>
    <button class="btn" onclick="file.click()">🖼 사진</button>
    <button class="btn" onclick="togglePrev()">👁 미리보기</button>
    <span class="grow"></span>
    <a href="/log.html" target="_blank">사이트 보기 ↗</a>
    <button class="btn del hide" id="delBtn" onclick="del()">삭제</button>
    <button class="btn go" onclick="publish()">발행</button>
  </div>
  <div class="edit">
    <div class="col">
      <input id="title" placeholder="제목">
      <textarea id="body" placeholder="여기에 글을 쓰세요. 마크다운 지원 — ## 소제목, **굵게**, > 인용, 사진은 드래그&드롭"></textarea>
    </div>
    <div class="col prev hide" id="prevPane"><div class="prev" id="prevBody"></div></div>
  </div>
  <div class="status" id="status">새 글을 쓰거나 왼쪽에서 기존 글을 선택하세요.</div>
</main>
<script src="https://cdn.jsdelivr.net/npm/marked@12/marked.min.js"></script>
<script>
const $=s=>document.querySelector(s);
let cur=null;
function st(msg,cls){const e=$('#status');e.textContent=msg;e.className='status'+(cls?' '+cls:'')}
async function loadList(){
  const r=await fetch('api/posts'); const ps=await r.json();
  $('#plist').innerHTML=ps.map(p=>`<li data-slug="${p.slug}" onclick="open_('${p.slug}')">
    <div class="d">${p.date||''}</div><div class="t">${esc(p.title)}</div></li>`).join('');
}
function esc(s){return (s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function newPost(){cur=null;$('#title').value='';$('#body').value='';$('#delBtn').classList.add('hide');
  mark();st('새 글');$('#title').focus();render()}
async function open_(slug){
  const r=await fetch('api/post?slug='+encodeURIComponent(slug)); if(!r.ok)return st('불러오기 실패','err');
  const p=await r.json(); cur=p.slug; $('#title').value=p.title; $('#body').value=p.markdown;
  $('#delBtn').classList.remove('hide'); mark(); st('편집 중: '+p.title); render();
}
function mark(){document.querySelectorAll('.plist li').forEach(li=>li.classList.toggle('on',li.dataset.slug===cur))}
async function publish(){
  const title=$('#title').value.trim(); if(!title)return st('제목을 입력하세요','err');
  st('발행 중…');
  const r=await fetch('api/save',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({slug:cur,title,markdown:$('#body').value})});
  const j=await r.json(); if(!r.ok)return st(j.error||'실패','err');
  cur=j.slug; await loadList(); mark();
  st('✓ 발행됨'+(j.git==='pushed'?' · GitHub 백업 완료':(j.git==='nochange'?'':' · (git: '+j.git+')')),'ok');
}
async function del(){
  if(!cur||!confirm('이 글을 삭제할까요?'))return;
  const r=await fetch('api/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({slug:cur})});
  const j=await r.json(); if(!r.ok)return st(j.error||'실패','err');
  newPost(); await loadList(); st('삭제됨'+(j.git==='pushed'?' · GitHub 반영':''),'ok');
}
async function upload(f){
  st('사진 올리는 중: '+f.name);
  const data=await new Promise(res=>{const fr=new FileReader();fr.onload=()=>res(fr.result);fr.readAsDataURL(f)});
  const r=await fetch('api/upload',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name:f.name,data})});
  const j=await r.json(); if(!r.ok)return st(j.error||'업로드 실패','err');
  insert(`\n![${f.name}](${j.path})\n`); st('✓ 사진 삽입됨: '+j.path,'ok');
}
function insert(t){const b=$('#body');const s=b.selectionStart;b.value=b.value.slice(0,s)+t+b.value.slice(b.selectionEnd);
  b.selectionStart=b.selectionEnd=s+t.length;render()}
$('#file').onchange=e=>{[...e.target.files].forEach(upload);e.target.value=''}
const body=$('#body');
body.addEventListener('dragover',e=>{e.preventDefault();body.classList.add('drop')});
body.addEventListener('dragleave',()=>body.classList.remove('drop'));
body.addEventListener('drop',e=>{e.preventDefault();body.classList.remove('drop');
  [...e.dataTransfer.files].filter(f=>f.type.startsWith('image/')).forEach(upload)});
function render(){if($('#prevPane').classList.contains('hide'))return;
  $('#prevBody').innerHTML=marked.parse('# '+$('#title').value+'\n\n'+$('#body').value)}
function togglePrev(){$('#prevPane').classList.toggle('hide');render()}
body.addEventListener('input',render);$('#title').addEventListener('input',render);
loadList();
</script></body></html>"""

if __name__ == "__main__":
    try:
        build_all()  # 시작 시 정적 페이지/사이트맵/RSS 최신화 (push 안 함)
        print("writer: static build ok", flush=True)
    except Exception as e:
        print("writer: build error", e, flush=True)
    print(f"writer on :{PORT}  repo={REPO}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
