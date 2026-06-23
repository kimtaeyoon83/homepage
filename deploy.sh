#!/usr/bin/env bash
# 사이트는 ~/homepage/public 을 Caddy 가 직접 서빙한다 → 파일 저장 즉시 라이브.
# 따라서 '배포' = GitHub 백업이다. (웹 작성기로 쓴 글은 자동 백업되므로 이건 터미널 편집용.)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
git add -A
if git diff --cached --quiet; then echo "변경 없음 — 백업할 것이 없습니다."; exit 0; fi
git commit -m "${1:-update $(date +%F)}"
git push origin main
echo "✓ GitHub 백업 완료"
