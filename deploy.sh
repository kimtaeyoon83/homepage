#!/usr/bin/env bash
# ~/homepage 의 웹 파일을 실행 중인 caddy 컨테이너(/srv)로 배포한다.
# (Caddy 가 정적 서빙하므로 재시작 불필요. 저장 → 이 스크립트 → 끝)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
C=caddy

docker cp "$ROOT/index.html" "$C:/srv/index.html"
docker cp "$ROOT/log.html"   "$C:/srv/log.html"
for img in "$ROOT"/*.jpg; do [ -e "$img" ] && docker cp "$img" "$C:/srv/"; done

docker exec "$C" mkdir -p /srv/log /srv/log/media
docker exec "$C" sh -c 'rm -f /srv/log/*.md /srv/log/index.json' 2>/dev/null || true
for f in "$ROOT"/log/*.md "$ROOT"/log/index.json; do [ -e "$f" ] && docker cp "$f" "$C:/srv/log/"; done

# 글에 들어가는 사진들 (log/media/*)
if compgen -G "$ROOT/log/media/*" > /dev/null; then
  for m in "$ROOT"/log/media/*; do [ -f "$m" ] && docker cp "$m" "$C:/srv/log/media/"; done
fi

echo "✓ 배포 완료 → https://codedeck.duckdns.org"
