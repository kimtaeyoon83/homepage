#!/usr/bin/env python3
# Freddie's space — 웹 글쓰기 백엔드 (표준 라이브러리만 사용)
# Caddy가 /write 를 basic_auth 로 보호한 뒤 이 서버로 프록시한다 (strip_prefix /write).
import os, re, json, glob, base64, subprocess, html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REPO   = "/repo"
PUBLIC = os.path.join(REPO, "public")
LOGDIR = os.path.join(PUBLIC, "log")
MEDIA  = os.path.join(LOGDIR, "media")
SITE   = os.environ.get("SITE_URL", "https://codedeck.duckdns.org")
PORT   = int(os.environ.get("PORT", "8080"))
MAXUP  = 20 * 1024 * 1024  # 업로드 최대 20MB

os.makedirs(MEDIA, exist_ok=True)

def slugify(date, title):
    base = re.sub(r"\s+", "-", title.strip())
    base = re.sub(r"[^0-9A-Za-z가-힣_-]", "", base)
    base = re.sub(r"-+", "-", base).strip("-") or "untitled"
    return f"{date}-{base}"

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

def today():
    # 컨테이너 TZ=Asia/Seoul 가정 (compose 에서 설정)
    import datetime
    return datetime.datetime.now().strftime("%Y-%m-%d")

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
            q = dict(p.split("=", 1) for p in self.path.split("?", 1)[1].split("&")) if "?" in self.path else {}
            slug = re.sub(r"[^0-9A-Za-z가-힣_%-]", "", q.get("slug", ""))
            from urllib.parse import unquote; slug = unquote(slug)
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
            content = f"# {title}\n\n{body}\n"
            open(os.path.join(LOGDIR, slug + ".md"), "w", encoding="utf-8").write(content)
            rebuild_index()
            g = git_push(f"log: {title}")
            return self._send(200, {"ok": True, "slug": slug, "url": f"{SITE}/log.html?p={slug}", "git": g})

        if path == "/api/delete":
            slug = re.sub(r"[^0-9A-Za-z가-힣_-]", "", (data.get("slug") or "").strip())
            f = os.path.join(LOGDIR, slug + ".md")
            if os.path.isfile(f): os.remove(f)
            rebuild_index()
            g = git_push(f"log: delete {slug}")
            return self._send(200, {"ok": True, "git": g})

        return self._send(404, {"error": "no route"})

    def log_message(self, *a): pass  # 조용히

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
/* preview */
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
let cur=null; // 편집중 slug (신규면 null)
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
// 이미지 업로드
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
// 미리보기
function render(){if($('#prevPane').classList.contains('hide'))return;
  $('#prevBody').innerHTML=marked.parse('# '+$('#title').value+'\n\n'+$('#body').value)}
function togglePrev(){$('#prevPane').classList.toggle('hide');render()}
body.addEventListener('input',render);$('#title').addEventListener('input',render);
loadList();
</script></body></html>"""

if __name__ == "__main__":
    print(f"writer on :{PORT}  repo={REPO}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
