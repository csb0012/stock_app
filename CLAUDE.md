# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

개인용 주식 투자 웹앱 — 국내(KOSPI/KOSDAQ) + 미국(NYSE/NASDAQ) 시장. 백엔드: FastAPI + SQLite. 프론트엔드: React + TypeScript + Vite. Windows PC 로컬 전용 배포. Electron 데스크탑 래퍼는 추후 목표.

## 앱 실행

**Windows (빠른 방법):** 루트의 `start.bat` 더블클릭 — 백엔드(8000), 프론트엔드(5173) 각각 cmd 창으로 실행.

**최신 코드 받기 (실행 전):**
```powershell
cd C:\claude\stock_app
git pull origin claude/dazzling-darwin-et76zj

# 로컬 변경사항 때문에 pull이 막히면
git stash
git pull origin claude/dazzling-darwin-et76zj
```

**수동 실행:**
```powershell
# 백엔드 (backend/ 에서 .venv 활성화 후)
cd C:\claude\stock_app\backend
.venv\Scripts\Activate
python -m uvicorn app.main:app --reload --port 8000

# 프론트엔드 (별도 터미널)
cd frontend
npm run dev
```

## 최초 설치

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate
pip install -r requirements.txt
pip install "sqlalchemy[asyncio]" "bcrypt==4.0.1"   # Python 3.13 필수
cp .env.example .env   # KIS_APP_KEY, KIS_APP_SECRET, KIS_ACCOUNT_NO 입력

python create_admin.py <아이디> <비밀번호>   # 첫 계정 생성
```

```powershell
cd frontend
npm install
```

## 주요 환경변수 (backend/.env)

| 변수 | 필수 | 용도 |
|---|---|---|
| `KIS_APP_KEY` / `KIS_APP_SECRET` | 필수 | KIS OAuth 토큰 — 없거나 예시값이면 서버가 시작되지 않음 |
| `KIS_ACCOUNT_NO` | 필수 | 증권 계좌번호 (위와 동일하게 필수 검증) |
| `KIS_IS_REAL` | — | `false` = 모의서버, `true` = 실서버 |
| `SECRET_KEY` | 필수 | JWT 서명 키 |
| `FINNHUB_API_KEY` | 선택 | 실제 경제 캘린더 (없으면 목업 사용) |

## 아키텍처

### 백엔드 (`backend/app/`)

```
core/
  config.py      — Pydantic Settings (backend/.env 절대경로로 읽음, KIS 키 필수 검증)
  database.py    — async SQLAlchemy + aiosqlite (backend/stock_app.db); init_db()가 새 컬럼 자동 ALTER
  security.py    — bcrypt 해싱, JWT 생성/검증, pyotp TOTP
models/
  user.py        — User (username, hashed_password, totp_secret, totp_enabled)
  watchlist.py   — WatchlistItem (symbol, market, name, memo, target_price)
  portfolio.py   — PortfolioItem (symbol, market, name, quantity, avg_price)
services/
  kis_api.py     — KISClient: 토큰 캐시, 초당 호출 제한, rt_cd 오류 → KISError
                   국내 현재가·일봉(get_kr_chart, 오름차순)·거래량/등락률 순위(KOSPI+KOSDAQ 합산)
  stock_master.py— KIS 공식 종목마스터(국내 mst + 미국 cod) 다운로드·캐시·검색·코드 검증
  quote.py       — 공통 시세+분석: 국내는 KIS, 미국은 yfinance 배치, USD/KRW 환율
  market_data.py — yfinance: 지수/매크로/빅테크; BeautifulSoup: 네이버 뉴스; Finnhub: 캘린더
  analysis.py    — calc_technical_indicators(), predict_next_day()(factors·summary 포함), classify_investment_style()
api/routes/
  auth.py        — /register, /login (TOTP 지원), /setup-totp, /enable-totp, /me
  stocks.py      — /search, /quote/{market}/{symbol}, /kr/{symbol}, /us/{symbol},
                   /recommendations/{longterm,shortterm} ({items, errors}), /screener/{kr,us}/{mode}
  market.py      — /overview (지수 + 빅테크), /calendar
  watchlist.py   — 관심종목 CRUD + PUT(메모·목표가) + /analysis
  portfolio.py   — 투자종목 CRUD + /analysis (통화별 합계 + 원화 환산 총합)
```

**오류 처리 원칙:** KIS·yfinance 실패를 빈 목록이나 다른 데이터로 대체하지 않는다. `HTTPException(502, 원인 메시지)`로 올려서 화면에 그대로 표시한다.

**종목코드:** 종목을 손으로 적은 코드표로 관리하지 않는다. 검색·추가·검증은 모두 `stock_master` (KIS 공식 파일, `backend/app/data/master_cache.json` 에 하루 단위 캐시)로 한다.

모든 라우트는 `main.py`에서 `/api` 접두사로 마운트.

### 주식 분석 데이터 흐름

1. `quote.py` 에서 캔들 조회 — 국내는 KIS 일봉(최대 100개씩 기간을 나눠 받아 날짜 오름차순 정렬), 미국은 yfinance.
2. `analysis.calc_technical_indicators()` — RSI, MACD, 볼린저밴드, MA20/60 계산.
3. `analysis.predict_next_day()` — 룰 기반 점수 → 확률(15~85% 클램프), ATR 기반 목표가·손절가, 지표별 근거(`factors`)와 요약(`summary`).
4. `analysis.classify_investment_style()` — `long_term_score`, `short_term_score` 반환.

### 프론트엔드 (`frontend/src/`)

```
api/client.ts      — axios 인스턴스; Bearer 토큰 자동 주입; 401 → /login 리디렉트
store/auth.ts      — Zustand: token + user 상태
pages/             — Dashboard, Recommendations, Screener, Search, Watchlist, Portfolio, Calendar, Login
components/common/ — Layout (사이드바 네비), ChangeTag, LoadingSpinner,
                     PredictionReasons (전망 근거), StockSearchBox (자동완성), StockQuoteCard, format.ts
index.css          — CSS 변수: --bg-primary, --bg-secondary, --bg-card,
                     --accent (#4f8ef7), --green (#34d399), --red (#f87171), --text-muted
```

Vite가 `/api` → `localhost:8000` 프록시 (`vite.config.ts`).

데이터 조회는 전부 React Query. 인증 상태는 Zustand (`store/auth.ts`).

### KIS API 주의사항

- 실서버: `https://openapi.koreainvestment.com:9443` (실거래 계좌 + API 신청 필요)
- 모의서버: `https://openapivts.koreainvestment.com:29443` (`KIS_IS_REAL=false`)
- 토큰은 프로세스 내 23시간 캐시; uvicorn 재시작 시 항상 재발급.
- 연결 테스트 엔드포인트 (인증 불필요): `GET /api/stocks/test/kis`

### 인증

- JWT를 `localStorage`에 저장, `Authorization: Bearer …` 헤더로 전송.
- TOTP(Google Authenticator)는 선택사항; `/api/auth/setup-totp` → `/api/auth/enable-totp` 순서로 활성화.

## Git

개발 브랜치: `claude/dazzling-darwin-et76zj`. 로컬 PC에서 작업 전 반드시 pull 후 편집, 완료 후 이 브랜치로 push.

## 작업 기록 규칙

`PROGRESS.md`가 작업 이력·명령어·알려진 이슈의 단일 기록이다. 작업 시작 전 먼저 읽고, 작업을 마칠 때마다(커밋 전) 다음을 갱신한다:
- "작업 이력"에 이번 작업 요약 추가 (날짜, 커밋 해시)
- 새로 생긴 명령어/점검 URL은 "자주 쓰는 명령어"에 추가
- 해결된 이슈는 체크, 새로 발견한 이슈는 "알려진 이슈"에 추가
