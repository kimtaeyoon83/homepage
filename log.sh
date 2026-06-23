#!/usr/bin/env bash
# Freddie's space — 글(로그) 관리 도구
#   ./log.sh new "제목"     오늘 날짜로 새 글(.md) 생성 후 목록 갱신
#   ./log.sh build          log/index.json 재생성 (제목·날짜·요약 자동 추출)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIR="$ROOT/log"
mkdir -p "$DIR"

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
    echo "✓ 생성됨: $file"
    echo "  이제 파일을 열어 내용을 채운 뒤  ./deploy.sh  로 배포하세요."
    ;;
  build) build ;;
  *) echo '사용법:  ./log.sh new "제목"   |   ./log.sh build' ;;
esac
