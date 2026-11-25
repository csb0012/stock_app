# StockApp — 개인용 주식 분석 웹앱

국내(KOSPI/KOSDAQ) + 미국(NYSE/NASDAQ) 시세·내일 전망·AI 추천·퀀트 점수·매집 탐지·테마·예측 검증·AI 모의투자,
관리자용 KIS 모의투자 주문(AI 제안 → 2단계 코드로 승인할 때만 주문). 백엔드 FastAPI + SQLite, 프론트엔드 React + TypeScript + Vite.
지금까지 한 일·앞으로 할 일 요약은 [docs/status.md](docs/status.md).

## 설치·실행

PC마다 아래 방법 중 **하나만** 쓴다 (섞으면 포트 충돌·DB 갈라짐).

| 방법 | 설치·실행 안내 | 실행 |
|---|---|---|
| 직접 설치 (Python 3.13 + Node + venv) | [docs/setup-local.md](docs/setup-local.md) | `start.bat` |
| Docker (Python·Node 설치 안 함) | [docs/setup-docker.md](docs/setup-docker.md) | `start-docker.bat` |
| 클라우드 24시간 (Oracle Cloud 무료 VM) | [docs/setup-cloud.md](docs/setup-cloud.md) | 서버에서 `bash deploy/setup-server.sh` |

접속: http://localhost:5173 (클라우드는 `https://<이름>.duckdns.org`)

`.env`·`stock_app.db`·`.secret_key` 는 모두 `backend/` 에 둔다. KIS 키(`KIS_APP_KEY`·`KIS_APP_SECRET`·`KIS_ACCOUNT_NO`)가 없으면 서버가 시작되지 않는다.

## API 키 (전부 무료)
| 서비스 | 발급 | 용도 | 필수 |
|---|---|---|---|
| KIS API | [apiportal.koreainvestment.com](https://apiportal.koreainvestment.com) | 국내 시세·일봉·순위, 종목마스터, 미국 PER/PBR | 필수 |
| Finnhub | [finnhub.io](https://finnhub.io) | 미국 애널리스트·실적 | 선택 |
| DART | [opendart.fss.or.kr](https://opendart.fss.or.kr) | 국내 공시 요인 | 선택 |
| FRED | [fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api/api_key.html) | 거시환경 요인, 경제 캘린더(미국 지표 발표 일정·발표값) | 선택 |
| KIS 모의투자 | 한국투자증권 모의투자 신청 + 모의투자용 앱키 | 관리자용 KIS 모의투자 주문 ([docs/kis-mock-trading.md](docs/kis-mock-trading.md)) | 선택 |
| ntfy | [ntfy.sh](https://ntfy.sh) (앱 설치, 가입 없음) | 모의투자 주문 제안·체결 휴대폰 알림 | 선택 |

## 로그인 보안
- **2단계 인증(Google Authenticator) 필수** — 처음 로그인하면 QR 등록 화면이 먼저 나온다 (등록해야 다른 화면을 씀)
- **초대받은 사람만 가입** — 관리자(처음 만든 계정)가 왼쪽 메뉴 '관리자 전용 → 관리자'에서 1회용 초대 코드를 만든다
- 누가 관리자인지: `backend` 에서 `python create_admin.py --list` (바꾸기 `--admin <아이디>`)
- 휴대폰 분실: `python create_admin.py --reset-totp <아이디>` → 다시 로그인하면 등록 화면

## 문서
- [CLAUDE.md](CLAUDE.md) — 구조·설계 원칙·**테스트 후 반영 규칙**
- [PROGRESS.md](PROGRESS.md) — 작업 이력, 자주 쓰는 명령어·점검 URL, 알려진 이슈
- [docs/status.md](docs/status.md) — 한 일 · 할 일 요약
- [docs/kis-mock-trading.md](docs/kis-mock-trading.md) — KIS 모의투자 주문 · 휴대폰 알림

## 나중에
- Electron 데스크탑 래퍼 (추후 목표)
