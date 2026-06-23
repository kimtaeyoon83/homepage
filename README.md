# Freddie's space

개인 홈페이지 — 제임스 웹 우주망원경 이미지 슬라이드쇼 + 글(Log).
`https://codedeck.duckdns.org` 에서 Caddy(Docker)가 `public/` 을 직접 정적 서빙한다.

## 구조

```
homepage/                      ← git 저장소 (이게 곧 소스)
├── public/                    ← 웹 루트 (Caddy 가 /srv 로 마운트해 서빙)
│   ├── index.html             홈 (JWST 슬라이드쇼 · 30초/장)
│   ├── log.html               글 목록 + 읽기 (Markdown 렌더)
│   ├── jwst-*.jpg             배경 이미지 6종 (NASA/ESA/CSA/STScI)
│   └── log/
│       ├── *.md               글 한 편 = 파일 하나 (YYYY-MM-DD-제목.md)
│       ├── index.json         글 목록 (자동 생성)
│       └── media/             글에 들어가는 사진
├── writer/                    ← 웹 작성기 백엔드 (Docker, Python 표준 라이브러리)
│   ├── writer.py
│   └── Dockerfile
├── log.sh  deploy.sh          터미널용 글 생성 / GitHub 백업
└── infra/                     Caddyfile · docker-compose.yml (참고본, 비밀번호 해시는 가림)
```

`public/` 을 Caddy 가 직접 서빙하므로 **파일을 저장하는 순간 라이브**다. 별도 배포 단계가 없다.

## ✍️ 글 쓰기 — 방법 1: 웹 작성기 (추천)

브라우저에서 **`https://codedeck.duckdns.org/write`** 접속 → 비밀번호 입력 → 제목·내용 작성 → **발행**.
- 폰·외부 어디서나 가능 (basic auth 비밀번호 보호).
- 사진은 본문에 **드래그&드롭** 하거나 🖼 버튼.
- 발행하면 글 저장 + 목록 갱신 + **GitHub 자동 커밋·푸시**까지 한 번에.
- 왼쪽 목록에서 기존 글을 눌러 수정/삭제.

## ✍️ 글 쓰기 — 방법 2: 터미널 (대체 수단)

```bash
cd ~/homepage
./log.sh new "오늘의 제목"      # public/log/2026-06-23-오늘의-제목.md 생성 (즉시 라이브)
nano public/log/2026-06-23-오늘의-제목.md   # 내용 작성
./deploy.sh                     # GitHub 백업 (git add+commit+push)
```

사진은 `public/log/media/` 에 두고 글에서 `![설명](/log/media/이름.jpg)` 로 참조.

## 운영 메모

- **웹 루트 변경**(public/ 안의 파일): 저장 즉시 라이브. 재시작 불필요.
- **Caddyfile / docker-compose.yml 변경**(`~/caddy/`): `cd ~/caddy && docker compose up -d`
  - 단순 Caddyfile 수정만이면 `docker restart caddy` (단일 파일 마운트 inode 이슈).
- **작성기 비밀번호 변경**: `docker exec caddy caddy hash-password --plaintext '새비번'` →
  나온 해시를 `~/caddy/Caddyfile` 의 `basic_auth` 에 넣고 `docker restart caddy`.
- 인증서는 443(TLS-ALPN-01)로 자동 발급/갱신. 포트 80은 ISP가 막아도 무관.
- 작성기 컨테이너는 `~/.ssh/id_ed25519_personal` 키로 GitHub 에 푸시한다.
