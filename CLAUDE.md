# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

개인용 주식 투자 웹앱 — 국내(KOSPI/KOSDAQ) + 미국(NYSE/NASDAQ) 시장. 백엔드: FastAPI + SQLite. 프론트엔드: React + TypeScript + Vite. Windows PC 로컬 전용 배포. Electron 데스크탑 래퍼는 추후 목표.

## 앱 실행

PC마다 아래 방법 중 **하나만** 쓴다 (섞으면 헷갈림). 모든 방법에서 `.env`·`stock_app.db`·`.secret_key` 위치는 `backend/` 로 같다.
클라우드 서버를 켜 두면 PC 에서는 아무것도 실행하지 않고 브라우저로 접속만 한다 (같은 KIS 키로 동시에 돌리면 초당 호출 제한에 걸리고 DB 가 갈라짐).

| 방법 | 쓰는 PC | 설치·실행 안내 | 실행 |
|---|---|---|---|
| **직접 설치** — Python 3.13 + Node + venv | 회사 PC | `docs/setup-local.md` | 루트 `start.bat` (가상환경 자동 활성화, 백엔드 127.0.0.1:8000, 프론트 5173) |
| **Docker** — Python·Node 설치 안 함, venv·pip·npm install 안 씀 | 집 PC | `docs/setup-docker.md` | 루트 `start-docker.bat` (= `docker compose up -d --build`, backend/frontend 폴더 마운트, 127.0.0.1 만 공개) |
| **클라우드 (24시간)** — Oracle Cloud Always Free VM + DuckDNS | 서버 | `docs/setup-cloud.md` | 서버에서 `bash deploy/setup-server.sh` (처음) / `bash deploy/update.sh` (업데이트). `docker-compose.cloud.yml`: Caddy(HTTPS·접속 비밀번호·빌드된 화면·/api 프록시) + backend(비공개) |

두 방법을 같은 PC에서 동시에 켜면 포트(8000, 5173) 충돌.

**최신 코드 받기 (공통, 실행 전):**
```powershell
cd C:\claude\stock_app
git pull origin claude/dazzling-darwin-et76zj

# 로컬 변경사항 때문에 pull이 막히면
git stash
git pull origin claude/dazzling-darwin-et76zj
```

**직접 설치 방식 수동 실행** (가상환경은 루트 `C:\claude\stock_app\.venv`):
```powershell
cd C:\claude\stock_app
.venv\Scripts\Activate
cd backend
python -m uvicorn app.main:app --reload --port 8000

# 프론트엔드 (별도 터미널)
cd C:\claude\stock_app\frontend
npm run dev
```

## 최초 설치

방법별 전체 절차(필요 프로그램, 파일 복사 위치, 문제 해결)는 `docs/setup-local.md` / `docs/setup-docker.md` / `docs/setup-cloud.md` 에 있다. 설치 절차를 바꾸면 해당 docs 파일을 고친다.

## 주요 환경변수 (backend/.env)

| 변수 | 필수 | 용도 |
|---|---|---|
| `KIS_APP_KEY` / `KIS_APP_SECRET` | 필수 | KIS OAuth 토큰 — 없거나 예시값이면 서버가 시작되지 않음 |
| `KIS_ACCOUNT_NO` | 필수 | 증권 계좌번호 (위와 동일하게 필수 검증) |
| `KIS_IS_REAL` | — | `false` = 모의서버, `true` = 실서버 |
| `SECRET_KEY` | 권장 | JWT 서명 키 — 예시값이면 무작위 키를 만들어 `backend/.secret_key` 에 저장해 사용 |
| `TOTP_ISSUER` | — | Google Authenticator 에 보이는 이름 (기본 `StockApp`) |
| `FINNHUB_API_KEY` | 선택 | 경제 캘린더 + 미국 종목 애널리스트 의견·실적 요인 |
| `DART_API_KEY` | 선택 | 국내 종목 최근 공시 요인 (opendart.fss.or.kr) |
| `FRED_API_KEY` | 선택 | 거시환경 요인 (VIX·하이일드 스프레드·금리) |

## 아키텍처

### 백엔드 (`backend/app/`)

```
core/
  swr.py         — SWRCache: 기존 값을 바로 주고 뒤에서 갱신(stale-while-revalidate), 동시 요청 1회 실행. 응답에 updated_at·refreshing·refresh_error
  config.py      — Pydantic Settings (backend/.env 절대경로로 읽음, KIS 키 필수 검증, .env 의 모르는 값은 무시)
  database.py    — async SQLAlchemy + aiosqlite (backend/stock_app.db); init_db()가 새 컬럼 자동 ALTER
  security.py    — bcrypt 해싱, JWT 생성/검증, pyotp TOTP
models/
  user.py        — User (username, hashed_password, totp_secret, totp_enabled)
  watchlist.py   — WatchlistItem (symbol, market, name, memo, target_price)
  portfolio.py   — PortfolioItem (symbol, market, name, quantity, avg_price)
  prediction.py  — PredictionLog (실제 예측, 종목·대상일별 + 채점 결과·틀린 이유) / BacktestLog (prediction_backtest, 같은 컬럼)
  flow.py        — InvestorFlow (investor_flow: 종목·날짜별 외국인·기관·개인 순매수 수량)
services/
  kis_api.py     — KISClient: 토큰 캐시, 초당 호출 제한, rt_cd 오류 → KISError
                   국내 현재가·일봉(get_kr_chart, 오름차순)·거래량/등락률 순위(KOSPI+KOSDAQ 합산)
  stock_master.py— KIS 공식 종목마스터(국내 mst + 미국 cod) 다운로드·캐시·검색·코드 검증
  quote.py       — 공통 시세+분석: 국내는 KIS, 미국은 yfinance 배치(60초 캐시), 실시간 현재가 패치(국내는 멀티종목 시세 30개씩),
                   analyze_candles 결과 메모(입력 같으면 재계산 안 함), 미국 PER/PBR(KIS 해외 상세), USD/KRW 환율
  news.py        — 종목 뉴스 + 문구·키워드 기반 호재/악재 분위기. 국내 종목: 해외 영문 기사(Yahoo .KS 뉴스 + Google 뉴스 영문,
                   TRUSTED_FOREIGN 매체만, 30분 캐시)만 확률 반영(weight_source="foreign") / 국내 기사(네이버 → Google 한국어,
                   TRUSTED_KR 언론사만)는 보여주기만(weighted=False). 영문 회사명 app/data/kr_en_names.json. 미국: yfinance (10분 캐시)
  extras.py      — 외부 데이터 요인: FRED 거시환경 / Finnhub 애널리스트·실적(미국) / DART 공시(국내).
                   호출 제한 때문에 백그라운드 큐(worker)로 수집, get_extra() 는 기다리지 않고 캐시값 또는 pending 반환
  market_calendar.py — 거래소 휴장일(holidays XKRX/NYSE) 기반 다음 거래일·"월요일(11/23)" 라벨
  prediction_log.py  — 예측 기록(upsert) · 장 마감 후 채점(grade) · 적중률/틀린 이유 집계 (review: 실제+백테스트 합산, 실제 우선)
                   채점 기준: 50% 초과 상승 / 50% 미만 하락 (정확히 50 만 제외), 55/45 는 '확신 예측' 비교용
  backtest.py    — 최근 90일 백테스트: 대상일 전날까지의 데이터만으로 규칙 점수·학습 모델(walk-forward) 예측 → 채점 →
                   prediction_backtest 저장 (증분, 하루 1회) + 학습 모델 최종 학습·채택 판정. 미래 데이터를 쓰지 않는 것이 핵심 규칙
  ml_model.py    — 학습 모델(numpy 로지스틱 회귀): feature_frame(특징값), walk_forward, adoption(채택 조건), live_predict(실시간),
                   stack_fit/stack_usable(모델+규칙 결합·보정, 시간순 구간 검증). 실시간 우선순위: 결합 → 모델 단독 → 규칙
                   변형 US / KR(간밤 미국장 반영, 미국장 마감 후에만) / KR_base / KRF·KRF_base(+외국인·기관 수급).
                   실시간은 검증 통과 + 오늘 특징값이 다 있는 첫 변형(수급 포함 우선). 결과 app/data/model_*.json (gitignore)
  scheduler.py   — 자동 예측 기록: 국내 장 시작 전(08:20~)·장 마감 후(15:40~), 미국 장 마감 후(16:10~ ET), 국내 수급 수집(18:10~)
                   + AI 추천 기본 데이터 14분마다 미리 계산 + 이벤트 일정 6시간마다 갱신
  flows.py       — 국내 외국인·기관·개인 일별 순매수 (KIS FHKST01010900, 최근 30일만 줘서 investor_flow 테이블에 매일 쌓음)
  chatbot.py     — 규칙 기반 챗봇 (외부 AI 없음): route() 가 질문 키워드로 의도(종목 분석·매수/매도 후보·투자종목·관심종목·
                   테마·매집·시장·적중률·이벤트·도움말)를 고르고, 기존 데이터(AI 추천 _live·analyze_kr/us·portfolio/watchlist 분석·
                   prediction_log.review·events)를 조회해 정해진 마크다운 형식으로 답함. 종목은 종목마스터 정확 일치 우선
  accumulation.py— 매집·바닥 다지기 탐지: 국내 전 종목(일반 주식, 스팩 제외) 일봉 200개로 점수(횡보25·변동성 축소15·OBV 매집20·
                   거래량 꿈틀15·저점 상승10·바닥권15). 그날까지 데이터만 사용(score_frame). 제외: 20일 +25% 이상·거래대금 1억 미만·상장 120일 미만.
                   검증 = 과거 날짜별 점수 → 이후 20거래일 안 +20% 도달률을 점수 구간별로 전체 평균과 비교(lift).
                   하루 1회(scheduler accum_kr 16:30~, 결과 없으면 시작 2분 뒤), mark_background, 결과 app/data/accumulation.json
  themes.py      — 테마별 종목: 네이버 증권 모바일 API(m.stock.naver.com/api/stocks/theme, JSON) → 하루 1회 app/data/themes.json
                   (테마 설명·종목별 편입 사유 포함, 종목코드는 종목마스터로 확인). 예전 PC 화면 finance.naver.com/sise/theme.naver 는 폐지됨.
                   테마 등락은 KIS 멀티종목 시세로 직접 계산 (overview: 평균 등락률·상승/하락 수·주도주, detail: 종목별 + 매집 점수)
  events.py      — 변동성 이벤트 경고(확률 영향 없음): 옵션 만기일(국내 둘째 목·미국 셋째 금, 분기 = 마녀의 날) + FRED 미국 주요 지표 발표일
  repair.py      — 시작 시 잘못 저장된 종목코드를 종목마스터 이름으로 자동 복구
  market_data.py — 대시보드: 코스피·코스닥 = KIS 업종 현재지수(Yahoo ^KS11 은 하루 늦을 수 있어 안 씀), 해외 지수·매크로·빅테크·ETF = yfinance
                   (각 값에 source·as_of, 날짜 늦으면 stale, 미국 종목은 시간외 가격 ext);
                   경제 캘린더 = Finnhub → 안 되면 FRED 공식 발표 일정 → 둘 다 안 되면 오류 (가짜 일정 없음)
  analysis.py    — calc_technical_indicators(), predict_next_day()(factors·summary 포함), classify_investment_style()
api/routes/
  auth.py        — /register, /login (TOTP 지원), /setup-totp, /enable-totp, /me
  stocks.py      — /search, /test/kis (인증 불필요), /quote/{market}/{symbol}, /kr/{symbol}, /us/{symbol}, /volume-surge,
                   /recommendations/{longterm,shortterm} ({items, errors, updated_at} — 호출마다 현재가·뉴스로 재계산),
                   /screener/{kr,us}/{mode}
  market.py      — /overview/{kr_indices|global_indices|bigtech|etfs} (구역별 SWR 캐시, 화면이 따로 받아 먼저 온 것부터 표시), /overview (전체), /status (장 운영 상태), /extras-status (외부 데이터 수집 현황), /scheduler-status, /calendar
  watchlist.py   — 관심종목 CRUD + PUT(메모·목표가) + /analysis
  portfolio.py   — 투자종목 CRUD + /analysis (통화별 합계 + 원화 환산 총합)
  chat.py        — POST /chat ({messages:[{role,content}]} → 마지막 질문만 보고 {reply, tools, model:"규칙 기반"}), GET /chat/status
  themes.py      — GET /themes (테마 전체, SWR 60초), GET /themes/{no} (테마 종목), POST /themes/refresh, GET /themes/status
  accumulation.py— GET /accumulation (?min_score, 후보·검증·스캔 상태), POST /accumulation/scan (전 종목 다시 계산)
  predictions.py — /review (채점 후 적중률·기록·method_accuracy·model 상태, kind=all|live|backtest, outcome, limit), POST /backtest (?force), /backtest/status
```

`main.py` lifespan: init_db → stock_master.load → repair_symbols → flows.load_all (쌓아둔 수급) → 백그라운드: themes.loop (테마 구성 하루 1회), accumulation.startup (결과 없으면 전 종목 스캔), 30분마다 prediction_log.evaluate_pending, 하루 1회 backtest.run (시작 20초 후 첫 실행, 학습 모델 재학습 포함), 10분마다 ml_model.refresh_ctx (지수 일봉), scheduler.loop (장 시작 전·장 마감 후 자동 예측 기록), scheduler.warm_recommendations, extras.worker (수집 결과는 app/data/extras_cache.json 에 저장·복원, 시작 1초 뒤 추천 후보 종목 미리 수집 예약), 시작 2초 뒤 market.warm_overview (대시보드 미리 받기).

**오류 처리 원칙:** KIS·yfinance 실패를 빈 목록이나 다른 데이터로 대체하지 않는다. `HTTPException(502, 원인 메시지)`로 올려서 화면에 그대로 표시한다. 단, 예측 기록(prediction_log)처럼 부가 기능의 실패는 주 응답을 막지 않고 로그로 남긴다.

**지표값:** `calc_technical_indicators()` 결과는 NaN/inf 가 없어야 한다 (FastAPI JSON 응답이 NaN 에서 실패함) → `_clean()` 으로 None 처리.

**종목코드:** 종목을 손으로 적은 코드표로 관리하지 않는다. 검색·추가·검증은 모두 `stock_master` (KIS 공식 파일, `backend/app/data/master_cache.json` 에 하루 단위 캐시)로 한다.

모든 라우트는 `main.py`에서 `/api` 접두사로 마운트. 헬스체크 `GET /api/health`.

### 주식 분석 데이터 흐름

1. `quote.py` 에서 캔들 조회 — 국내는 KIS 일봉(최대 100개씩 기간을 나눠 받아 날짜 오름차순 정렬), 미국은 yfinance.
2. `analysis.calc_technical_indicators()` — RSI, MACD, 볼린저밴드, MA20/60 계산.
3. `analysis.predict_next_day(candles, indicators, news, extra, model)` — 룰 기반 점수(RSI 30·MACD 25·볼린저 20·이평 25·뉴스 15(국내는 해외 기사가 있을 때만) + 키가 있을 때 거시환경 10·애널리스트 15·실적 10·공시 20) → 확률(15~85% 클램프), 지표별 근거(`factors`)·요약(`summary`)·경고(`warnings`). 가격: `_buy_zone()` 이 지지선·ATR 로 추천 매입가(`buy_price`, `buy_low/high`, `buy_gap_pct`, `buy_comment`), 목표가 = 현재가+2ATR, 손절가 = 매입가 아래. `quote.analyze_candles(..., symbol)` 가 대상일(`target_date`, `target_label`)과 `extras.get_extra()`, `ml_model.live_predict()` 를 붙인다. 학습 모델이 채택돼 있으면 최종 확률 = 모델 확률 + 뉴스·외부데이터 소폭 보정(`_apply_model`), 아니면 규칙 점수 확률 (`rule_probability`, `model_probability`, `method`, `model_status` 같이 반환).
4. 분석한 예측은 `prediction_log.record()` 로 저장 → 대상일 장 마감 후 채점.
5. `analysis.classify_investment_style()` — `long_term_score`, `short_term_score` 반환.

### 프론트엔드 (`frontend/src/`)

```
api/client.ts      — axios 인스턴스; Bearer 토큰 자동 주입; 401 → /login 리디렉트
api/queryClient.ts, api/persist.ts — React Query 설정 + localStorage 저장 (아래 설명)
store/auth.ts      — Zustand: token + user 상태
pages/             — Dashboard, Recommendations, Screener, Themes(테마별 주식), Accumulation(매집 탐지), Search, Watchlist, Portfolio, Predictions(예측 검증), Calendar, Login
                     (챗봇은 페이지가 아니라 모든 화면 오른쪽 아래 ChatWidget)
components/common/ — Layout (사이드바 메뉴·장 운영 상태 + 페이지 오른쪽 위 상단 바(사용자·화이트/다크 모드·로그아웃) + ChatWidget),
                     ChatWidget (챗봇, Esc 로 닫기), Markdown (챗봇 답변 표·목록), ThemeToggle, FetchStatus (기준 시각·갱신 중),
                     ChangeTag, WatchButton (관심 추가), AccumBadge (매집 점수), PredictionReasons (전망 근거), BuyPrice (추천 매입가),
                     NewsLink (원문 기사 링크, http/https 만), StockSearchBox (자동완성), StockQuoteCard, format.ts
index.css          — CSS 변수 테마: 다크(:root 기본) / 화이트(:root[data-theme="light"]: #F5F5F5·#FFFFFF 바탕, 파랑 #006CE1, 사이드바 #4F4F4F)
                     색은 직접 쓰지 말고 var(--accent) 등 변수, 옅은 배경은 color-mix(in srgb, var(--green) 7%, transparent)
                     ThemeToggle.tsx 가 <html data-theme> + localStorage("theme") 변경, index.html 인라인 스크립트가 첫 화면 깜빡임 방지
```

Vite가 `/api` → `localhost:8000` 프록시 (`vite.config.ts`, Docker 에선 `VITE_PROXY_TARGET=http://backend:8000`).

데이터 조회는 전부 React Query (`api/queryClient.ts`). 성공한 조회는 `api/persist.ts` 가 localStorage(`rq-cache-v1`, 24시간)에 저장 → 다시 열면 이전 데이터를 바로 보여주고 뒤에서 갱신 (로그아웃·로그인 시 삭제). 이전 값을 보여줄 땐 `FetchStatus` 로 기준 시각·갱신 중 표시. 인증 상태는 Zustand (`store/auth.ts`).

**속도 원칙:** 화면은 받은 데이터부터 바로 그린다 (한 번에 다 받을 때까지 비워 두지 않음). 느린 조회는 구역별로 나누고, 서버는 `SWRCache` 로 기존 값을 먼저 준다. 백그라운드 작업은 `kis_api.mark_background()` 로 KIS 호출 순서를 화면 요청 뒤로.

### KIS API 주의사항

- 실서버: `https://openapi.koreainvestment.com:9443` (실거래 계좌 + API 신청 필요)
- 모의서버: `https://openapivts.koreainvestment.com:29443` (`KIS_IS_REAL=false`)
- 토큰은 23시간 캐시 + `backend/.kis_token.json` 에 저장해 재시작 시 재사용 (발급은 1분 1회 제한). 만료 응답(EGW00123/EGW00121)이면 재발급 후 재시도.
- 모든 호출은 공유 httpx 클라이언트(keep-alive) + 초당 호출 간격 제한(실서버 0.07초)을 거친다.
- 연결 테스트 엔드포인트 (인증 불필요): `GET /api/stocks/test/kis`

### 인증

- JWT를 `localStorage`에 저장, `Authorization: Bearer …` 헤더로 전송.
- `/api/auth/register` 는 계정이 하나도 없을 때만 동작 (개인용 — 이후 계정은 `create_admin.py`).
- 백엔드는 `127.0.0.1` 에만 바인딩 (같은 네트워크의 다른 PC 접속 차단). 클라우드에선 backend 는 공개하지 않고 Caddy(80/443)만 공개 — Caddy basic auth(`deploy/auth.caddy`, git 제외) 한 겹 + 앱 로그인.
- 로그인 5회 실패(10분 안) → 그 IP 15분 차단 (`auth.py`, X-Forwarded-For 기준).
- TOTP(Google Authenticator)는 선택사항; `/api/auth/setup-totp` → `/api/auth/enable-totp` 순서로 활성화.

## Git

개발 브랜치: `claude/dazzling-darwin-et76zj`. 로컬 PC에서 작업 전 반드시 pull 후 편집, 완료 후 이 브랜치로 push.
**push 는 아래 "테스트 후 반영 규칙"을 통과한 뒤에만** 한다 — 사용자가 PC·서버에서 pull 하는 브랜치는 항상 테스트를 마친 상태여야 한다.

## 테스트 후 반영 규칙 (수정 → 충분한 테스트 → push → 사용자가 pull)

수정한 내용은 아래를 **모두** 확인한 뒤에 커밋·push 한다. 하나라도 실패하면 push 하지 않고 고친다.

1. **백엔드 문법·import** (backend 폴더에서, `.env` 가 없으면 가짜 KIS 값으로):
   ```bash
   python -m compileall -q app
   KIS_APP_KEY=test KIS_APP_SECRET=test KIS_ACCOUNT_NO=00000000-01 python -c "import app.main"
   ```
2. **프론트엔드 타입 검사·빌드** (frontend 폴더에서): `npm run build` (`tsc -b` 포함 — 클라우드 서버는 이 빌드 결과를 그대로 씀)
3. **바꾼 기능을 직접 실행해서 확인**
   - 백엔드: 서버를 띄워 바꾼 API 를 실제로 호출하고 응답(형식·오류 메시지)을 확인. 계산 로직은 경계값(빈 목록·NaN·0·데이터 부족)까지 넣어 본다.
   - 화면: 바꾼 페이지를 브라우저(Playwright)로 열어 표시·콘솔 오류 확인.
   - 외부 API(KIS·Yahoo·네이버 등)가 이 환경에서 막혀 있으면 가짜 응답·가짜 서버로 흐름을 검증한다. 가짜 데이터로 화면을 채우는 코드는 넣지 않는다 (오류 처리 원칙).
   - 예측·학습 로직은 "미래 데이터 미사용"을 함께 확인 (이후 데이터를 바꿔도 그날 결과가 같아야 함).
4. **실행 방법별 영향 확인**: `requirements.txt`·`package.json`·Dockerfile·`docker-compose*.yml`·`deploy/` 를 바꿨으면 해당 방법(직접 설치 / Docker / 클라우드)의 설치·실행 절차와 docs 가 맞는지 확인.
5. **문서만 바꾼 경우**: 문서에 적은 파일 경로·명령어·API 경로·설정값이 실제 코드와 같은지 확인.
6. **기록**: PROGRESS.md 작업 이력에 `검증:` 줄로 무엇을 어떻게 테스트했는지 적는다. 실제 KIS·외부 API 로 확인하지 못한 부분은 **"실서버 미검증"** 으로 분명히 적고 "알려진 이슈"에 남긴다 (사용자가 pull 후 그 부분을 확인할 수 있게).

## 작업 기록 규칙

`PROGRESS.md`가 작업 이력·명령어·알려진 이슈의 단일 기록이다 (설치 절차만 `docs/setup-local.md`, `docs/setup-docker.md`, `docs/setup-cloud.md` 로 분리). 작업 시작 전 먼저 읽고, 작업을 마칠 때마다(커밋 전) 다음을 갱신한다:
- "작업 이력"에 이번 작업 요약 + `검증:` 줄 추가 (날짜, 커밋 해시) — "테스트 후 반영 규칙" 6번
- 새로 생긴 명령어/점검 URL은 "자주 쓰는 명령어"에 추가
- 해결된 이슈는 체크, 새로 발견한 이슈는 "알려진 이슈"에 추가
