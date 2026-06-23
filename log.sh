#!/usr/bin/env bash
# Freddie's space — 터미널에서 글 관리 (웹 작성기 /write 의 대체 수단)
#   ./log.sh new "제목"     오늘 날짜로 새 글(.md) 생성 후 목록 갱신
#   ./log.sh build          public/log/index.json 재생성
# 사이트는 public/ 을 Caddy 가 직접 서빙하므로 저장 즉시 라이브. 백업은 ./deploy.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIR="$ROOT/public/log"
mkdir -p "$DIR/media"

build(){
  python3 - "$DIR" <<'PY'
import os,sys,json,re,glob
d=sys.argv[1]; posts=[]
for f in sorted(glob.glob(os.path.join(d,'*.md'))):
    name=os.path.basename(f)[:-3]
    mo=re.match(r'(\d{4}-\d{2}-\d{2})',name); date=mo.group(1) if mo else ''
    title=name; summary=''; lines=open(f,encoding='utf-8').read().splitlines()
    for l in lines:
        s=l.strip()
        if s.startswith('# '): title=s[2:].strip(); break
    for l in lines:
        s=l.strip()
        if s and not s.startswith('#'):
            summary=re.sub(r'[*_`>\[\]]','',s)[:90]; break
    posts.append({'slug':name,'date':date,'title':title,'summary':summary})
posts.sort(key=lambda p:(p['date'],p['slug']),reverse=True)
open(os.path.join(d,'index.json'),'w',encoding='utf-8').write(json.dumps(posts,ensure_ascii=False,indent=2)+'\n')
print(f'✓ index.json 갱신 — 글 {len(posts)}개')
PY
}

case "${1:-}" in
  new)
    [ -n "${2:-}" ] || { echo '제목을 입력하세요:  ./log.sh new "제목"'; exit 1; }
    title="$2"; date="$(date +%F)"
    slug="${date}-$(echo "$title" | tr '[:space:]' '-' | tr -cd '[:alnum:]가-힣_-' | sed 's/-\+/-/g;s/-$//')"
    file="$DIR/$slug.md"
    [ -e "$file" ] && { echo "이미 있음: $file"; exit 1; }
    printf '# %s\n\n여기에 글을 쓰세요.\n' "$title" > "$file"
    build
    echo "✓ 생성됨: $file  (저장 즉시 라이브 · 백업은 ./deploy.sh)"
    ;;
  build) build ;;
  *) echo '사용법:  ./log.sh new "제목"   |   ./log.sh build' ;;
esac
