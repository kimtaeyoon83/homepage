# Freddie's space

개인 홈페이지 — 제임스 웹 우주망원경 이미지 슬라이드쇼 + 글(Log).
`https://codedeck.duckdns.org` 에서 Caddy(Docker)가 정적 서빙한다.

## 구조

```
homepage/
├── index.html              홈 (JWST 슬라이드쇼 · 30초/장)
├── log.html                글 목록 + 읽기 화면 (Markdown 렌더)
├── jwst-*.jpg              배경 이미지 6종 (NASA/ESA/CSA/STScI, public domain)
├── log/
│   ├── *.md                글 한 편 = 파일 하나 (YYYY-MM-DD-제목.md)
│   └── index.json          글 목록 (자동 생성)
├── log.sh                  글 생성 / 목록 갱신 도구
├── deploy.sh               caddy 컨테이너로 배포
└── infra/                  Caddyfile · docker-compose.yml (참고용)
```

## 글 쓰는 법

```bash
./log.sh new "오늘의 제목"     # log/2026-06-23-오늘의-제목.md 생성 + 목록 갱신
# → 생성된 .md 파일을 열어 내용 작성 (Markdown: # 제목, ## 소제목, **굵게**, > 인용 …)
./deploy.sh                    # 라이브 반영
git add -A && git commit -m "log: 오늘의 제목" && git push   # 백업
```

기존 글 제목을 바꾸는 등 수정 후에는 `./log.sh build` 로 목록을 다시 만든다.

## 메모

- **이미지/HTML 수정**은 `deploy.sh` 후 새로고침이면 끝 (Caddy 재시작 불필요).
- **Caddyfile 수정 시에는** 반드시 `docker restart caddy` (단일 파일 마운트 inode 이슈).
- 인증서는 443(TLS-ALPN-01)로 자동 발급/갱신. 포트 80은 ISP가 막아도 무관.
