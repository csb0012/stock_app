# StockApp — 개인용 주식 분석 웹앱

국내(KOSPI/KOSDAQ) + 미국(NYSE/NASDAQ) 시세·내일 전망·AI 추천·매집 탐지·테마·예측 검증.
백엔드 FastAPI + SQLite, 프론트엔드 React + TypeScript + Vite.

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
| Finnhub | [finnhub.io](https://finnhub.io) | 경제 캘린더, 미국 애널리스트·실적 | 선택 |
| DART | [opendart.fss.or.kr](https://opendart.fss.or.kr) | 국내 공시 요인 | 선택 |
| FRED | [fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api/api_key.html) | 거시환경 요인, 미국 지표 발표 일정 | 선택 |

## Google Authenticator (선택)
화면에는 설정 메뉴가 없어 API 로 켠다 (직접 설치·Docker 방식: `http://localhost:8000/docs` → Authorize 에 로그인 토큰).
1. `POST /api/auth/setup-totp` → QR 코드(`qr_code`, base64) 발급
2. Google Authenticator 앱에서 QR 스캔
3. `POST /api/auth/enable-totp` `{"totp_code": "123456"}` 로 활성화
4. 이후 로그인할 때 6자리 코드 입력

## 문서
- [CLAUDE.md](CLAUDE.md) — 구조·설계 원칙·**테스트 후 반영 규칙**
- [PROGRESS.md](PROGRESS.md) — 작업 이력, 자주 쓰는 명령어·점검 URL, 알려진 이슈

## 나중에
- Electron 데스크탑 래퍼 (추후 목표)
