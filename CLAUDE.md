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
| `KIS_MOCK_APP_KEY`·`KIS_MOCK_APP_SECRET`·`KIS_MOCK_ACCOUNT_NO` | 선택 | KIS 모의투자 주문(AI 제안 → 관리자 승인) 전용 키·계좌 — 비우면 주문 기능 꺼짐. `KIS_IS_REAL=false` 면 비워 둬도 시세용 키·계좌를 씀. 실거래 서버로는 주문 안 함 (`docs/kis-mock-trading.md`) |
| `NTFY_TOPIC`·`NTFY_SERVER`·`NTFY_TOKEN`·`NTFY_CLICK_URL` | 선택 | 휴대폰 푸시(ntfy 앱, 날씨 알림과 같은 JSON 방식·다른 주제) — KIS 모의투자 제안·체결·막힘·정지. 주제를 비우면 끔. 주제 이름은 비밀처럼(로그·화면·오류에 안 냄). 알림을 누르면 웹 `/kis?order=번호` — 사이트 주소 = `NTFY_CLICK_URL`(주소 부분만) 또는 클라우드 `DOMAIN`(docker-compose.cloud.yml 이 deploy/.env 를 backend 에도 넘김) |
| `SECRET_KEY` | 권장 | JWT 서명 키 — 예시값이면 무작위 키를 만들어 `backend/.secret_key` 에 저장해 사용 |
| `TOTP_ISSUER` | — | Google Authenticator 에 보이는 이름 (기본 `StockApp`) |
| `FINNHUB_API_KEY` | 선택 | 미국 종목 애널리스트 의견·실적 요인 (경제 캘린더는 Finnhub 유료라 안 씀) |
| `DART_API_KEY` | 선택 | 국내 종목 최근 공시 요인 (opendart.fss.or.kr) |
| `FRED_API_KEY` | 선택 | 거시환경 요인 (VIX·하이일드 스프레드·금리) + 경제 캘린더 일정·발표값 |
| `SMTP_HOST`·`SMTP_PORT`·`SMTP_USER`·`SMTP_PASSWORD`·`SMTP_FROM` | 선택 | 회원가입·비밀번호 찾기·이메일 변경 인증 코드 메일 (네이버 smtp.naver.com 465). 없으면 그 기능만 503 |
| `SMS_API_KEY`·`SMS_API_SECRET`·`SMS_FROM`·`SMS_DAILY_LIMIT` | 선택 | 휴대폰 문자 인증 (솔라피 solapi.com, SMS_FROM = 등록한 발신번호, 하루 기본 50건). 없으면 휴대폰 인증만 503 |
| `SIGNUP_OPEN` | — | 기본 true. false 면 가입 자체를 막음 (초대 코드가 있어도) |
| `INVITE_ONLY` | — | 기본 true — 관리자가 만든 1회용 초대 코드 + 이메일/휴대폰 인증이 있어야 가입. false = 인증만 하면 누구나 (예전 방식) |
| `REQUIRE_TOTP` | — | 기본 true — 2단계 인증(Google Authenticator) 필수. 안 켠 계정은 2단계 등록 API·/me·비밀번호 변경·로그아웃만 되고 나머지는 403 + `X-Totp-Required` |
| `PWNED_CHECK` | — | 기본 true — 가입·비밀번호 변경 때 유출 비밀번호(HIBP, 해시 앞 5글자만 전송) 거부, 로그인 때 경고 |
| `LOGIN_ALERT` | — | 기본 true — 처음 보는 IP 로그인·계정 잠금을 인증된 이메일로 알림 (SMTP 설정 있을 때) |

## 아키텍처

### 백엔드 (`backend/app/`)

```
core/
  swr.py         — SWRCache: 기존 값을 바로 주고 뒤에서 갱신(stale-while-revalidate), 동시 요청 1회 실행. 응답에 updated_at·refreshing·refresh_error
                   fresh_for(값) 로 값마다 신선 기간 조절 (경제 캘린더: 일정·발표값 일시 실패면 5분)
  config.py      — Pydantic Settings (backend/.env 절대경로로 읽음, KIS 키 필수 검증, .env 의 모르는 값은 무시)
  database.py    — async SQLAlchemy + aiosqlite (backend/stock_app.db); init_db()가 새 컬럼 자동 ALTER
                   DB_TIMEOUT=30초 (다른 연결이 쓰는 중이면 기다리는 한도). 큰 저장은 나눠 commit (백테스트 SAVE_CHUNK=300) — 한 번에 하면 그동안 잠겨 'database is locked'
  security.py    — bcrypt 해싱, JWT 생성/검증, pyotp TOTP, totp_step(코드의 30초 칸 번호 — 재사용 방지용, _now 로 테스트 시각 고정)
models/
  user.py        — User (username, hashed_password, totp_secret, totp_enabled, email·email_verified, phone·phone_verified, nickname,
                   password_changed_at, session_epoch(모든 기기 로그아웃), totp_last_step(쓴 2단계 코드), password_leaked(유출 비밀번호 경고),
                   is_admin(관리자 — 관리자가 없으면 init_db 가 가장 작은 id 를 관리자로), invited_by, locked_until(계정 잠금, DB 에 남아 재시작해도 유지))
                   Invite (invites: 초대 코드 HMAC 해시·끝 4글자·메모·만료·사용자·취소)
                   EmailCode (email_codes: 6자리 코드 — 받는 곳 = 이메일 또는 휴대폰 번호, HMAC 해시만 저장, 10분, 5번 틀리면 무효)
                   AccountEvent (account_events: 로그인·실패·비밀번호/연락처 변경 등 활동 기록, 사용자당 최근 100개)
  watchlist.py   — WatchlistItem (symbol, market, name, memo, target_price)
  portfolio.py   — PortfolioItem (symbol, market, name, quantity, avg_price)
  prediction.py  — PredictionLog (실제 예측, 종목·대상일별 + 채점 결과·틀린 이유) / BacktestLog (prediction_backtest, 같은 컬럼)
  flow.py        — InvestorFlow (investor_flow: 종목·날짜별 외국인·기관·개인 순매수 수량)
  kis.py         — KIS 모의투자 주문: KisTrade (kis_trade 1행: 정지 여부·한도·매매 규칙·state JSON(expected 앱 기록 보유 수량·meta 손절/목표/보유일·log·day_start)) /
                   KisOrder (kis_orders: 제안 1건 → 승인 → 주문 → 체결, source ai/exit(목표가 제안)/stop(자동 손절), limit_price(지정가)·cancel_req(취소 요청 시각), 상태 proposed/approved/submitting/submitted/filled/partial/unfilled/unknown/rejected/expired/cancelled/blocked/failed) /
                   KisLog (kis_log: 감사 로그 — 지우지 않음)
  paper.py       — AI 모의투자: PaperSim (paper_sim: 과거 시뮬레이션 결과 JSON) / PaperAccount (paper_account: 실시간 계좌, 보유·대기 주문·판단 기록은 state JSON) /
                   PaperTrade (체결) / PaperEquity (거래일 종가 기준 자산 + 지수 종가)
services/
  kis_api.py     — KISClient: 토큰 캐시, 초당 호출 제한, rt_cd 오류 → KISError. 네트워크 오류(httpx)는 KISConnectionError(이유 문구 + maybe_sent:
                   연결 자체 실패면 False, 보낸 뒤 응답 시간 초과·끊김이면 True — 주문이면 '결과 모름' 처리)
                   국내 현재가·일봉(get_kr_chart, 오름차순)·월봉(get_kr_monthly, 장기 분석용)·거래량/등락률 순위(KOSPI+KOSDAQ 합산)
                   미국 주간거래 현재가 get_us_daytime_price (해외 현재가 HHDFS00000300, EXCD 를 NAS/NYS/AMS → BAQ/BAY/BAA 로)
  kis_order.py   — KIS 모의투자 서버 주문 API (국내): order(price 있으면 지정가 ORD_DVSN 00, 없으면 시장가)·tick_size/tick_up(호가 단위)·cancel·balance(잔고·D+2 예수금·전날 총자산)·executions(일별 체결, cancel_qty).
                   **모의투자 서버 주소가 아니면 거부**(_guard). 키 = KIS_MOCK_*(없고 KIS_IS_REAL=false 면 시세용 키), 토큰 backend/.kis_mock_token.json.
                   TR 은 새 번호 → '없는 TR' 응답일 때만 예전 번호 (주문은 그 외 오류면 다시 안 보냄). KISClient 를 키·주소를 받아 따로 만듦
  kis_trade.py   — KIS 모의투자 주문 운영 (AI 제안 → 관리자 2단계 승인 → 장중 조건 맞으면 주문, 위험 줄이는 일은 자동 — 사용자 결정 2026-11-26):
                   propose(장 마감 15분 뒤, papertrade.analyze_live 로 KIS 실제 잔고를 놓고 판단, 이전 제안 만료, 다음 거래일 15:30 까지 유효) ·
                   propose_intraday(장중 AI 제안 — 사용자 결정 2026-11-26: 10:00~14:00 하루 intraday_runs(기본 3)번 schedule_intraday 가 뒤에서(감시 안 멈춤),
                     analyze_live(intraday=True) = 오늘 미완성 봉을 지금 가격 종가로·거래량 하루치 환산(project_today) → 새 매수만 source='intraday',
                     보유·직전 장 마감 뒤 제안·주문 종목·오늘 +허용%↑/−허용×2%↓(intraday_chase) 제외, 승인 대기 매수는 산 것으로(현금·자리), 오늘 15:30 까지. 판단은 잠금 밖) ·
                   watch(장중 5초, loop 안): _fetch_prices(kis_ws 실시간 체결가 → 없으면 REST 멀티종목 15초, 못 받은 종목은 판단 안 함)·_hist(10분 가격) →
                     check_exits(prices) 손절가 이하 = 승인 없이 source='stop' 시장가 매도(긴급 정지 중엔 안 함, 손실 한도 정지 중엔 함 — _stops_ok, 2분 뒤 재시도·하루 3번) / 목표가 = 매도 제안 ·
                     shock_reason(제안가 −허용×2% · 10분 안 −fast_drop%) → 승인 대기·조건 대기 _auto_cancel, 접수된 매수 cancel_sent(why) ·
                     buy_wait_reason(개장 5분·제안가 +허용%·지수 _index_change −index_drop%) → 기다림(_set_wait, 메모) 아니면 submit(auto) ·
                   approve(조건부 UPDATE 로 한 번만, 장중이면 바로 submit) ·
                   submit(직전 확인: 정지·기한·장 시간(09:01~15:20, 매수 09:05~)·하루 횟수(손절 제외)·같은 종목 중복·하루 손실(넘으면 _halt)·잔고 대조(다르면 매수 안 함)·
                   매수는 _quote(REST 현재가 + VI·거래 정지) → 급변이면 취소 / VI·비쌈·지수면 기다림(_wait, 30초 뒤 다시) → 지정가 tick_up(현재가×(1+limit_slip%))·1회 한도 →
                   'submitting' 먼저 저장 후 KIS 주문, 보낸 뒤 응답을 못 받으면 unknown(같은 종목 그날 다시 안 보냄)) ·
                   cancel_sent(취소 전 체결 반영 → KIS 취소 → cancel_req, 체결 내역에 반영되면 cancelled/partial) ·
                   refresh_fills(체결 내역 → expected/meta, _sync_fills — 화면 대조·매수 직전 대조 전에 먼저 반영, 기준 맞추기 땐 apply=False 로 '반영됨'만 표시해 두 번 안 더함) · halt(긴급 정지, 코드 없이)·resume·rebaseline·set_config ·
                   _limits(row) = 저장된 한도 + 새 항목 기본값 · loop(5초 watch + 1분 tick, 재시작 때 submitting → unknown). 모든 일은 audit() 로 kis_log. 새 제안·정지는 관리자 이메일로 알림
  us_daytime.py  — 미국 정규장 밖 가격 → 행의 daytime{label,price,base,change_rate,time} (label 주간거래/프리마켓/애프터마켓, 시간대는 겹치지 않음):
                   주간거래(한국 10:00~18:00, 서머타임 ~17:00 · 블루오션) = KIS, 종목별 30초 캐시 /
                   프리마켓(04:00~09:30 ET)·애프터마켓(16:00~20:00 ET, market_calendar.us_ext_session) = Yahoo 5분봉 prepost 의 오늘 그 시간대 마지막 체결,
                   행의 현재가(KIS 정규장 종가) 대비 등락률, 60초 캐시, 빈 응답·봉 없는 종목은 error (KIS 해외 현재가는 정규장 가격만 줘서).
                   attach(rows, extended) 가 **새 목록** 반환 (캐시된 원본 안 바꿈). 표시 전용 — 예측 확률·매입가 계산엔 안 씀.
                   관심종목·투자종목·AI 추천·종목 조회 응답에 붙음. attach_screener = 종목탐색 미국 표(Yahoo 스크리너 시세의 pre/postMarketPrice, 없으면 앞 30종목만 5분봉). 대시보드 빅테크/ETF 는 주간거래만(extended=False — 시간외는 market_data 의 ext)
  invites.py     — 초대 코드: 헷갈리는 글자 뺀 12글자(XXXX-XXXX-XXXX, 약 60비트), HMAC(SECRET_KEY) 해시만 저장, 1회용·기본 3일(1~14)·관리자당 사용 가능 10개,
                   consume = 조건부 UPDATE (같은 코드 동시 가입은 한 명만)
  pwned.py       — 유출 비밀번호 확인 (Have I Been Pwned range API, SHA-1 앞 5글자만 전송 + Add-Padding, 앞자리 캐시). 확인 못 하면 None(막지 않음)
  factor_weights.py — 예측 검증 결과로 지표 비중 조정: 백테스트 기록의 RSI·MACD·볼린저·이평 점수로 지표별 적중률(상승·하락 신호 적중률 평균) → 51%↑ 1배 / 46%↓ 0.3배 (줄이기만, 신호 150건↑),
                   walk-forward(그 날짜 전 결과만으로 비중) 방향 적중률이 원래보다 0.3%p↑ 일 때만 채택 → live(market) 를 quote.analyze_candles 가 predict_next_day(weights=) 로.
                   백테스트·과거 시뮬레이션엔 안 씀(미래 데이터). backtest.run 끝에 recompute → app/data/factor_weights.json. 학습 모델이 쓰이면 모델 우선(모델 입력은 원래 비중)
  kis_ws.py      — KIS 실시간 체결가 웹소켓 (국내 H0STCNT0): 장 시간(08:55~15:35)·보는 종목이 있을 때만 연결, want()=구독 목록(2분 TTL·최대 40), get()=10초 안 값,
                   접속키 /oauth2/Approval, PINGPONG 되돌림, 끊기면 5~60초 뒤 재연결. quote.live_prices 가 5초 안 값이 있으면 REST 안 부름. status() → scheduler-status 의 kis_ws
  notify.py      — 휴대폰 푸시 (ntfy): send(제목·내용·우선순위·태그·click, JSON 으로 POST — 한글 제목), send_bg(뒤에서, 실패해도 계속), status()(주제 이름 없이 켜짐·서버·link·마지막 결과).
                   app_url(path) = 사이트 주소(NTFY_CLICK_URL 의 scheme+host → 없으면 https://DOMAIN) + path — click 이 '/…' 면 이걸로. kis_trade._push(order_id=) → /kis?order=번호.
                   kis_trade 가 씀: 제안·정지 = 푸시+메일(_alert_admins), 체결·막힘·거부·결과 모름 = 푸시만(_push). 테스트는 conftest 가 NTFY_TOPIC 을 비움
  mailer.py      — SMTP 메일 발송 (465 = SSL, 그 외 STARTTLS). 설정 없으면 MailError(보낸 척 안 함), 오류 문구에 비밀번호 안 넣음
  sms.py         — 휴대폰 문자 발송 (솔라피 /messages/v4/send-many/detail, HMAC-SHA256 서명). 설정 없으면 SmsError, 하루 SMS_DAILY_LIMIT 건
  email_codes.py — 인증 코드 발급·확인 (이메일·문자 공통): 같은 받는 곳·용도 60초 재발송 제한, IP 당 1시간 10통, 용도 signup/reset/change/phone,
                   normalize_phone (010-1234-5678·+82 → 01012345678)
  stock_master.py— KIS 공식 종목마스터(국내 mst + 미국 cod) 다운로드·캐시·검색·코드 검증
  quote.py       — 공통 시세+분석: 국내는 KIS, 미국 일봉은 yfinance 배치(60초 캐시), 실시간 현재가 패치(국내는 웹소켓 → 멀티종목 시세 30개씩,
                   미국은 us_live_prices = KIS 해외 현재가(정규장 실서버 10초·모의 60초·장 밖 10분 캐시), KIS 실패 종목만 yfinance 1분봉 + source 'Yahoo (KIS 실패)'),
                   analyze_items(관심·투자종목)는 미국 현재가를 KIS 로 받아 오늘 봉에 반영(price_source),
                   analyze_candles 결과 메모(입력 같으면 재계산 안 함), 미국 PER/PBR(KIS 해외 상세), USD/KRW 환율
  news.py        — 종목 뉴스 + 문구·키워드 기반 호재/악재 분위기. 국내 종목: 해외 영문 기사(Yahoo .KS 뉴스 + Google 뉴스 영문,
                   TRUSTED_FOREIGN 매체만, 30분 캐시)만 확률 반영(weight_source="foreign") / 국내 기사(네이버 → Google 한국어,
                   TRUSTED_KR 언론사만)는 보여주기만(weighted=False). 영문 회사명 app/data/kr_en_names.json. 미국: yfinance (10분 캐시)
  extras.py      — 외부 데이터 요인: FRED 거시환경 / Finnhub 애널리스트·실적(미국) / DART 공시(국내).
                   호출 제한 때문에 백그라운드 큐(worker)로 수집, get_extra() 는 기다리지 않고 캐시값 또는 pending 반환
  market_calendar.py — 거래소 휴장일(holidays XKRX/NYSE) 기반 다음 거래일·"월요일(11/23)" 라벨,
                   us_daytime_session() (미국 주간거래 시간: 한국 날짜가 미국 거래일 + 10:00~미국 04:00 ET), market_status("US").daytime
  prediction_log.py  — 예측 기록(upsert) · 장 마감 후 채점(grade) · 적중률/틀린 이유 집계 (review: 실제+백테스트 합산, 실제 우선)
                   tracks()/attach_tracks(): 종목별 최근 90일 예측 적중 기록(30분 캐시) → 관심종목·AI 추천·종목 조회 행의 track
                   채점 기준: 50% 초과 상승 / 50% 미만 하락 (정확히 50 만 제외), 55/45 는 '확신 예측' 비교용
  backtest.py    — 최근 1년(DAYS=365) 백테스트: 대상일 전날까지의 데이터만으로 규칙 점수·학습 모델(walk-forward) 예측 → 채점 →
                   prediction_backtest 저장 (증분, 하루 1회 — 저장된 날짜는 규칙 점수를 DB 값으로 재사용) + 학습 모델 최종 학습·채택 판정.
                   국내 일봉 800개·미국/지수 yfinance 5y. 미래 데이터를 쓰지 않는 것이 핵심 규칙
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
  quant.py       — 퀀트 점수(국내 전 종목, Seeking Alpha 퀀트 등급·TipRanks 스마트 점수·IBD RS 참고): 요인 = 모멘텀 RS(1·3·6개월 0.2/0.4/0.4)·
                   추세(50/120일선·200일 고저)·거래량 매집(50일 상승일/하락일 거래량)·안정성(60일 변동성 낮음)·고점 근접(200일 고점 대비),
                   같은 날 전 종목 백분위 → 요인 비중 = 날짜별 순위 상관(IC)이 양수인 만큼 (손으로 안 정함) → 종합 백분위·점수 1~10·등급 A+~F.
                   검증: 앞쪽 날짜로 비중을 정하고(20거래일 겹침 제거) 뒤쪽 날짜에서 점수 구간별 '20거래일 뒤 그날 전 종목 중간값을 이긴 비율'.
                   매집 스캔(accumulation.scan)이 같은 일봉으로 계산해 accumulation.json 의 quant 에 저장 (KIS 추가 호출 없음). 거래대금 1억 미만 제외
  market_regime.py — 시장 상태(CAN SLIM 'M'): 코스피·코스닥·S&P500·나스닥 yfinance 5년 일봉 → 50/200일선·200일선 기울기·분산일(25일 중 −0.2%↓+거래량↑)
                   → 상승 추세/상승 압박/하락 추세 + 상태별 20거래일 뒤 지수 성과 검증. 예측 확률엔 안 넣고 경고로만
  themes.py      — 테마별 종목: 네이버 증권 모바일 API(m.stock.naver.com/api/stocks/theme, JSON) → 하루 1회 app/data/themes.json
                   (테마 설명·종목별 편입 사유 포함, 종목코드는 종목마스터로 확인). 예전 PC 화면 finance.naver.com/sise/theme.naver 는 폐지됨.
                   테마 등락은 KIS 멀티종목 시세로 직접 계산 (overview: 평균 등락률·상승/하락 수·주도주, detail: 종목별 + 매집 점수).
                   네이버는 등락률 순·페이지당 최대 100개라 장중엔 페이지 사이 순서가 바뀜 → 번호로 중복 제거 + 전체 개수 찰 때까지 다시 훑음(_paged),
                   예전 중복 파일은 불러올 때 정리하고 바로 다시 받음
  events.py      — 변동성 이벤트 경고(확률 영향 없음): 옵션 만기일(국내 둘째 목·미국 셋째 금, 분기 = 마녀의 날) + FRED 미국 주요 지표 발표일 (econ_calendar 일정 사용)
                   + FOMC 금리 결정일(연준 공식 일정 페이지 — FRED 의 FOMC 항목은 매일 나와서 안 씀)
  repair.py      — 시작 시 잘못 저장된 종목코드를 종목마스터 이름으로 자동 복구
  market_data.py — 대시보드: 코스피·코스닥 = KIS 업종 현재지수(Yahoo ^KS11 은 하루 늦을 수 있어 안 씀), 해외 지수·매크로·빅테크·ETF = yfinance
                   (각 값에 source·as_of, 날짜 늦으면 stale, 미국 종목은 시간외 가격 ext)
  econ_calendar.py — 경제 캘린더: FRED 공식 발표 일정 + 연준 FOMC 일정(federalreserve.gov 파싱, 하루 캐시) → 일정을 하나도 못 받으면 오류.
                   실제·이전 값 = FRED 시리즈를 발표 당일 기준(vintage, realtime_start=그날)으로 조회해 전날 기준과 비교(수정 발표도 구분),
                   FOMC = DFEDTARL·DFEDTARU 결정 전날 vs 다음 날. 발표된 값은 메모리 캐시. 예상치(컨센서스)는 무료 공식 출처가 없어 안 다룸.
                   INDICATORS(지표별 시리즈·계산·해설: about + 오름/내림/같음 시장 영향). 외부 API 오류 문구에 키가 든 URL 을 넣지 않음 (err_text)
                   '오늘'·발표 여부는 미국 중부 날짜(fred_today) 기준 — 한국 날짜로 FRED 에 realtime_start 를 보내면 미래 날짜라 HTTP 400
  paper_engine.py— AI 모의투자 계산만 (DB·외부 호출 없음): AI 점수 = 상승확률 45%(규칙 점수, 실시간은 학습 모델 포함 AI 추천 확률) + 퀀트 종합 백분위 35%
                   (요인 비중은 그날 결과가 확정된 과거로만, 20거래일마다) + 매집 20%(40점 초과분).
                   개선 옵션(기본 켬): adaptive = 세 신호 비중을 최근 120거래일 IC(10거래일 뒤 수익률, 확정일 ≤ 판단일만)로 20거래일마다 + 고정 비중과 반반(축소),
                   trend_filter = 50일선 아래는 안 삼. prepare() = 시작 180일 전부터 점수(학습형용, 비교 실행이 재사용). 시장 상태(market_regime)로 주식 비중 상한 100/60/30%,
                   다음 거래일 이벤트(event_labels: FOMC·주요 발표·옵션 만기)면 새 매수 절반. entry_guard(급변 보호, 기본 켬, 시뮬레이션만) = guarded_entry:
                   시가 +3% 넘게 출발 → 저가가 +3% 까지 오면 그 값에 삼 / −6% 넘게 출발 → 안 삼 (KIS 주문 장중 규칙의 일봉 근사). decide() = 장 마감 후 판단 → 주문, fill_buy/fill_sell(수수료·거래세·슬리피지),
                   intraday_exit(손절 먼저), after_close(보유일·추격 손절), simulate() = 하루씩 그날 종가까지로 판단 → 다음 날 시가 체결 → 장중 손절/목표 → 종가 평가
  papertrade.py  — AI 모의투자 실행 (analyze_live = 실시간 판단 점수 — 실시간 계좌와 KIS 모의투자 제안이 같이 씀): 과거 시뮬레이션(1~24개월, AI 추천 후보 고정 목록, 한 번에 하나, 결과 paper_sim,
                   개선 옵션이 켜져 있으면 같은 점수로 옵션 끈 '기본 방식'도 계산해 result.compare, 중단 = cancel_sim → 진행 표시 때 SimCancelled,
                   결과 저장은 DB 잠금이면 재시도, 서버 시작 때 '계산 중'으로 남은 기록은 실패로 정리) /
                   실시간 계좌(사용자당 5개): 만들면 바로 판단(장중이면 바로 현재가 체결), loop() 1분마다 — 개장 1분 뒤 대기 주문 체결, 장중 5분마다 손절·목표,
                   장 마감 15분 뒤 판단(실패 시 30분 뒤 재시도, 같은 날 자동 판단 중복 안 함). 실시간 대상 = 후보 + 내 관심·투자종목 + (국내) 전 종목 퀀트·매집 상위 + 보유.
                   계좌별 asyncio 잠금으로 state 를 순서대로 고침. 오늘 미완성 봉은 판단에서 뺌(_closed_only)
  longterm.py    — 장기 보유 분석: 월봉(국내 KIS 수정주가·배당 제외 / 미국·지수 yfinance 배당 포함)으로 모든 달을 '산 달'로 놓고
                   1·3·5·10년(계산은 1~20년) 보유 수익률 → 이익 확률·하위10%/중간/상위10%·최악·최고·지수보다 나은 비율,
                   보유 기간 제안(그 기간 '이상' 모두 90%↑ / 손실 0 인 가장 짧은 기간), 최대 낙폭·회복 기간, 장기 점수
                   (5년 이익 확률 40 + 지수 대비 30 + 낙폭 20 + 데이터 길이 10). 비교 지수 = 코스피 / 나스닥 종합(나스닥 상장) / S&P 500. SWR 6시간
  analysis.py    — calc_technical_indicators(), predict_next_day()(factors·summary 포함), classify_investment_style()
api/routes/
  auth.py        — /options (가입 가능·메일/문자 설정 여부), /signup/send-code → /register (email 또는 phone 중 하나의 코드 + 아이디 3~20자 + 닉네임(선택) +
                   비밀번호 8자↑ 영문·숫자·아이디 미포함, 바로 토큰), /login (아이디 또는 인증된 이메일·휴대폰 번호, TOTP, 오류 문구 한국어),
                   /password/forgot (email 또는 phone, 가입 여부 노출 안 하는 같은 답) → /password/reset, /password/change (새 토큰 반환),
                   /email/send-code → /email/verify, /phone/send-code → /phone/verify, PUT /profile (닉네임 2~12자, 남의 닉네임·아이디와 중복 금지),
                   /contact/remove (비밀번호, 본인인증 수단 하나는 남아야), /logout-all (새 토큰), /activity (최근 활동 + 7일 로그인 실패 수),
                   /delete-account (비밀번호 + 2단계 코드, 관심·투자종목·활동 기록 같이 삭제),
                   /setup-totp (이미 켜져 있으면 거부), /enable-totp, /disable-totp (현재 코드 필요), /me (nickname·display_name·email·phone·verified·created_at).
                   토큰의 pwv(비밀번호 버전) ≠ password_changed_at 이거나 sev ≠ session_epoch 이면 401 → 비밀번호 변경·모든 기기 로그아웃 시 다른 기기 끊김
  admin.py       — 관리자 전용 (get_admin): /admin/summary (회원·2단계 미등록·차단·24시간 로그인·7일 실패·사용 가능한 초대),
                   /admin/users/{id} (회원 상세: 연락처 가림·로그인 IP·실패·쓰는 기능 수·최근 활동 50 — 비밀번호·2단계 비밀값 없음), /admin/events (전체 회원 보안 기록), /admin/invites (GET 목록 · POST 만들기 {memo, days, totp_code} — 코드 원문은 이 응답에만 · DELETE /{id} 취소),
                   /admin/users (GET 회원 목록: 2단계 등록·초대한 사람·최근 로그인), PUT /admin/users/{id}/active {active, totp_code} (차단 = 모든 기기 끊김, 나·관리자는 불가).
                   만들기·차단은 2단계 코드를 다시 받음(_step_up)
  kis.py         — KIS 모의투자 주문 (모두 get_admin): GET /kis/status (연결·정지·한도·오늘 주문 수·잔고·대조·판단 기록) · GET /kis/orders?kind=open|all · GET /kis/log ·
                   POST /kis/propose (?intraday=true = 장중 판단) · POST /kis/orders/approve {ids, totp_code} · POST /kis/orders/reject · POST /kis/orders/{id}/cancel · POST /kis/halt (코드 없음) ·
                   POST /kis/resume · POST /kis/baseline · PUT /kis/config {limits, params} · POST /kis/notify-test (휴대폰 알림 시험). 승인·다시 시작·설정은 2단계 필수(_step_up, 2단계 안 켠 관리자는 403). 기준 맞추기(baseline)는 주문 없이 앱 기록만 바꿔서 코드 없음(사용자 결정 2026-11-26)
  stocks.py      — /live?symbols= (국내 실시간 현재가 — kis_ws 메모리 값, KIS 호출 없음, 물은 종목은 구독), /search, /test/kis (인증 불필요 — 그래서 토큰 일부도 안 보여줌, ok/오류만), /quote/{market}/{symbol}, /kr/{symbol}, /us/{symbol}, /volume-surge,
                   /recommendations/{longterm,shortterm} ({items, errors, updated_at} — 호출마다 현재가·뉴스로 재계산),
                   /recommendations/longterm/horizon (장기 보유 분석 — 장기 탭은 내일 확률 대신 이것을 표시),
                   /screener/{kr,us}/{mode}
  market.py      — /overview/{kr_indices|global_indices|bigtech|etfs} (구역별 SWR 캐시, 화면이 따로 받아 먼저 온 것부터 표시), /overview (전체), /status (장 운영 상태), /regime (시장 상태, SWR 1시간), /extras-status (외부 데이터 수집 현황), /scheduler-status, /calendar
  watchlist.py   — 관심종목 CRUD + PUT(메모·목표가) + /analysis. 입력 검증: market KR/US, 중복 = 시장+코드, 없는 항목 삭제 404
  portfolio.py   — 투자종목 CRUD + /analysis (통화별 합계 + 원화 환산 총합). 수량 > 0·평단가 ≥ 0 검증(422), 없는 항목 삭제 404
  chat.py        — POST /chat ({messages:[{role,content}]} → 마지막 질문만 보고 {reply, tools, model:"규칙 기반"}), GET /chat/status
  themes.py      — GET /themes (테마 전체, SWR 60초), GET /themes/{no} (테마 종목), POST /themes/refresh, GET /themes/status
  accumulation.py— GET /accumulation (?min_score, 후보·검증·스캔 상태), POST /accumulation/scan (전 종목 다시 계산),
                   GET /quant (?limit, 퀀트 점수 상위·요인 비중·검증 — 전 종목 점수표는 응답에 안 실음)
  predictions.py — /review (채점 후 적중률·기록·method_accuracy·factor_weights(지표 비중 조정)·model 상태, kind=all|live|backtest, outcome, limit), POST /backtest (?force), /backtest/status
  papertrade.py  — /paper/config (기본값·설정 범위·자동 운영 상태), /paper/simulations (POST 시작 {market, capital, months, params} — 범위 밖 422·계산 중 409 / GET 목록 / GET·DELETE /{id}),
                   POST /paper/simulations/{id}/cancel (계산 중이 아니면 409),
                   /paper/accounts (POST 생성 / GET 목록(현재가 평가) / GET /{id} 거래·자산 곡선·판단 기록 / POST /{id}/run / PUT /{id}/active / DELETE /{id}). 남의 것 404
```

`main.py` lifespan: init_db → stock_master.load → repair_symbols → flows.load_all (쌓아둔 수급) → 백그라운드: themes.loop (테마 구성 하루 1회), accumulation.startup (결과나 퀀트 점수가 없으면 전 종목 스캔 — 매집·퀀트 같이), papertrade.loop (AI 모의투자 자동 운영), 30분마다 prediction_log.evaluate_pending, 하루 1회 backtest.run (시작 20초 후 첫 실행, 학습 모델 재학습 포함), 10분마다 ml_model.refresh_ctx (지수 일봉), scheduler.loop (장 시작 전·장 마감 후 자동 예측 기록), scheduler.warm_recommendations, extras.worker (수집 결과는 app/data/extras_cache.json 에 저장·복원, 시작 1초 뒤 추천 후보 종목 미리 수집 예약), 시작 2초 뒤 market.warm_overview (대시보드 미리 받기).

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
api/client.ts      — loginUrl(next)/safeNext(): 로그인 풀리면 /login?next=원래 주소 → 로그인 후 그 화면 (사이트 안 경로만, //·/\\ 거부). axios 인스턴스; 로그인 토큰을 **X-Access-Token** 헤더로 자동 주입 (Authorization 은 클라우드 Caddy 접속 비밀번호(Basic)
                     자리라 쓰면 안 됨 — 덮으면 모든 요청이 Caddy 401); 401 → /login 리디렉트, 403 + X-Totp-Required → /setup-2fa
api/queryClient.ts, api/persist.ts — React Query 설정 + localStorage 저장 (아래 설명)
store/auth.ts      — Zustand: token + user 상태
pages/             — Dashboard, Recommendations, Screener(종목탐색 = 검색 + 스크리너, 예전 /search 는 여기로), Themes(테마별 주식), Quant(퀀트 점수), Accumulation(매집 탐지),
                     Watchlist(국내/미국 탭 · 3열 카드 또는 표 · 매입가/목표가/손절가 · 탭·보기·정렬은 localStorage 기억), Portfolio,
                     Admin(/admin, 관리자만 — AdminRoute: 요약·회원 목록·회원 상세(활동 기록)·초대 코드·전체 보안 기록),
                     KisTrade(/kis, 관리자만 — KIS 모의투자: 상태·긴급 정지/다시 시작·잔고·대조 경고·기준 맞추기·제안 선택 → 2단계 코드로 승인·거절·취소·설정·주문 기록·감사 로그.
                       ?order=번호 = 휴대폰 알림 링크 → 그 주문 스크롤·강조. 640px 이하(useNarrow)는 표 대신 카드·규칙/설정 접음·승인 줄 화면 아래 고정),
                     Setup2FA(/setup-2fa: 2단계 필수인데 안 켰을 때 — 등록하면 첫 화면, ProtectedRoute 와 403 X-Totp-Required 가 여기로 보냄),
                     PaperTrading(/paper, AI 모의투자: 실시간 계좌 / 과거 시뮬레이션 탭(localStorage paper-tab) · 자산 곡선 SVG(AI vs 지수) · 거래 이유 · 판단 기록),
                     Predictions(예측 검증), Calendar,
                     Login(회원가입·비밀번호 찾기 링크, 아이디·이메일·휴대폰 번호), Signup·ForgotPassword(이메일/휴대폰 탭 → 코드),
                     MyPage(관리자면 관리자 페이지 링크·프로필 카드·닉네임·본인인증(이메일/휴대폰)·비밀번호·2단계 인증·로그인 기기/최근 활동·모든 기기 로그아웃·CSV 내려받기·탈퇴)
                     (챗봇은 페이지가 아니라 모든 화면 오른쪽 아래 ChatWidget)
components/common/ — Layout (사이드바 메뉴(관리자면 아래에 '관리자 전용': 관리자 · KIS 모의투자 주문)·장 운영 상태(미국 주간거래·프리마켓·애프터마켓 중 표시) + 페이지 오른쪽 위 상단 바(닉네임(없으면 아이디) = 마이페이지 링크, 이메일·휴대폰 둘 다 미인증이면 노란 점·화이트/다크 모드·로그아웃) + ChatWidget.
                     폭 860px 이하(휴대폰)는 사이드바가 ☰ 버튼으로 여닫는 메뉴 — index.css .app-shell/.sidebar/.page-body),
                     ChatWidget (챗봇, Esc 로 닫기), Markdown (챗봇 답변 표·목록), ThemeToggle, FetchStatus (기준 시각·갱신 중),
                     Toast (버튼 요청 실패 알림), TotpSection (마이페이지 2단계 인증 켜기/끄기), AuthForm (로그인류 화면 틀·비밀번호 규칙 안내·
                     이메일/휴대폰 탭 MethodTabs·자동 하이픈 formatPhone·재발송 대기 useCooldown),
                     AdminPanels (관리자 페이지: InvitePanel 초대 코드 만들기(코드는 한 번만 보임)·목록·취소 / MemberPanel 회원 목록·상세·차단 — 2단계 코드 입력),
                     accountEvents.ts (활동 기록 종류 이름·기기 이름 — 마이페이지·관리자 공통),
                     ChangeTag, WatchButton (관심 추가), AccumBadge (매집 점수), PredictionReasons (전망 근거, compact = 좁은 카드용), BuyPrice (추천 매입가),
                     PriceLevels (추천 매입가·목표가·손절가 3칸 — AI 추천·관심종목·종목탐색 공통), DaytimePrice (미국 주간거래·프리마켓·애프터마켓 가격 배지 — label 대로. extPrice()·SessionTag: 프리·애프터마켓이면 관심종목·종목탐색·AI 추천은 현재가 자리에 그 가격(종가는 마우스 올림), 투자종목은 손익 때문에 배지),
                     QuantBadge·TrackBadge (퀀트 등급·종목별 예측 적중), MarketRegime (대시보드 시장 상태 패널 + RegimeWarning 경고 줄),
                     NewsLink (원문 기사 링크, http/https 만), StockSearchBox (자동완성), StockQuoteCard (종목 상세: 시세·주간거래·전망·가격대·지표·뉴스),
                     LongTermPanel (장기 보유 분석 표·지수 카드), format.ts,
                     useNarrow (640px 이하 = 휴대폰 — KIS·캘린더·AI 모의투자·예측 검증은 표 대신 카드), 챗봇 버튼·창 위치는 index.css .chat-fab/.chat-panel (휴대폰 작게),
                     종목탐색 표 .scr-table 휴대폰 여백·한 줄,
                     useLivePrices (국내 장중에만 2초마다 /stocks/live — 관심종목·종목 상세 카드 현재가 덮어쓰기, withLive) · LiveBadge ('● 실시간 HH:MM:SS')
index.css          — CSS 변수 테마: 다크(:root 기본) / 화이트(:root[data-theme="light"]: #F5F5F5·#FFFFFF 바탕, 파랑 #006CE1, 사이드바 #4F4F4F)
                     색은 직접 쓰지 말고 var(--accent) 등 변수, 옅은 배경은 color-mix(in srgb, var(--green) 7%, transparent)
                     ThemeToggle.tsx 가 <html data-theme> + localStorage("theme") 변경, index.html 인라인 스크립트가 첫 화면 깜빡임 방지
```

Vite가 `/api` → `localhost:8000` 프록시 (`vite.config.ts`, Docker 에선 `VITE_PROXY_TARGET=http://backend:8000`).

데이터 조회는 전부 React Query (`api/queryClient.ts`). **버튼 요청(useMutation)이 실패하면 전역 MutationCache 가 화면 아래 알림(Toast)으로 사유를 띄운다** —
화면 안에 이미 오류 칸이 있는 요청만 `meta: { inlineError: true }` 로 뺀다. `errMsg()` 는 입력 검증 오류(422 목록)도 문장으로 바꾼다.
401 은 로그인 만료로 보고 /login 으로 보내되, 로그인·회원가입·비밀번호 찾기 요청의 401(비밀번호 틀림 등)은 새로고침하지 않고 화면에 문구를 보여준다.
 성공한 조회는 `api/persist.ts` 가 localStorage(`rq-cache-v1`, 24시간)에 저장 → 다시 열면 이전 데이터를 바로 보여주고 뒤에서 갱신 (로그아웃·로그인 시 삭제).
불러온 저장본은 모두 '오래됨'으로 표시해서 staleTime 과 상관없이 화면을 열면 한 번은 새로 받는다 (업데이트 전 형식의 저장본이 남아 보이던 문제 방지). 이전 값을 보여줄 땐 `FetchStatus` 로 기준 시각·갱신 중 표시. 인증 상태는 Zustand (`store/auth.ts`).

**속도 원칙:** 화면은 받은 데이터부터 바로 그린다 (한 번에 다 받을 때까지 비워 두지 않음). 느린 조회는 구역별로 나누고, 서버는 `SWRCache` 로 기존 값을 먼저 준다. 백그라운드 작업은 `kis_api.mark_background()` 로 KIS 호출 순서를 화면 요청 뒤로.

### KIS API 주의사항

- 실서버: `https://openapi.koreainvestment.com:9443` (실거래 계좌 + API 신청 필요)
- 모의서버: `https://openapivts.koreainvestment.com:29443` (`KIS_IS_REAL=false`)
- 토큰은 23시간 캐시 + `backend/.kis_token.json` 에 저장해 재시작 시 재사용 (발급은 1분 1회 제한). 만료 응답(EGW00123/EGW00121)이면 재발급 후 재시도.
- 모든 호출은 공유 httpx 클라이언트(keep-alive) + 초당 호출 간격 제한(실서버 0.07초)을 거친다.
- 연결 테스트 엔드포인트 (인증 불필요): `GET /api/stocks/test/kis`

### 인증

- JWT를 `localStorage`에 저장, **`X-Access-Token` 헤더**로 전송 (백엔드는 `Authorization: Bearer` 도 받음 — API 문서·스크립트용).
  클라우드에선 `Authorization` 헤더를 Caddy 접속 비밀번호(basic auth)가 쓰므로 화면이 거기에 토큰을 넣으면 안 됨.
- 유출 비밀번호(HIBP) 가입·변경 거부 + 로그인 경고(`password_leaked`, 상단 빨간 띠), 계정별 잠금(15분 안 10번 → 15분, 어느 IP 든),
  처음 보는 IP 로그인·잠금 알림 메일, 2단계 코드 재사용 불가(`totp_last_step`). IP 는 X-Forwarded-For **맨 뒤** 값 (맨 앞은 위조 가능).
- Caddy 응답 헤더: CSP(`script-src 'self'` — 페이지 안 스크립트 금지라 테마 초기화는 `frontend/public/theme-init.js`), Permissions-Policy, COOP, HSTS, X-Frame-Options.
  CSP 를 바꾸면 화면 테스트(`smoke.mjs` 가 Caddyfile 의 CSP 를 그대로 걸고 화면을 엶)로 확인.
- **관리자 페이지와 일반 화면 분리** (사용자 결정 2026-11-25): 관리 기능은 /admin · /kis (사이드바 '관리자 전용', AdminRoute + 서버 get_admin). 마이페이지엔 링크만.
- **KIS 모의투자 주문은 'AI 제안 → 내가 승인할 때만 주문'** (사용자 결정 2026-11-25, 자동 매수 아님). 모의투자 서버 전용, 승인마다 2단계 코드 — `docs/kis-mock-trading.md`.
  승인한 매수는 장중에 조건이 맞을 때 지정가로, **손절가 도달 매도·급변 때 매수 취소는 승인 없이 자동 + 휴대폰 알림** (사용자 결정 2026-11-26). 목표가 매도는 제안(승인 필요).
  **장중에도 AI 가 정해진 시각에 다시 판단해 새 매수를 제안** (사용자 결정 2026-11-26 — 제안만, 승인해야 삼. 종가로 검증된 AI 의 장중 근사라 덜 검증됨)
- 회원가입은 **관리자가 준 초대 코드 + 이메일 또는 휴대폰 6자리 인증** (사용자 결정, 2026-11-25 — 믿는 사람만. 예전 '누구나'는 `INVITE_ONLY=false`).
  초대 코드가 틀리면 메일·문자를 안 보내고 IP 실패 횟수에 넣음(5번 → 15분 차단). 관리자 = 처음 만든 계정. `SIGNUP_OPEN=false` 로 초대 가입까지 막을 수 있음.
- **2단계 인증 필수** (`REQUIRE_TOTP`, 사용자 결정 2026-11-25): `get_current_user` = `get_user_before_totp` + 2단계 확인. 등록 전 토큰으로는 /me·setup/enable-totp·비밀번호 변경·logout-all 만.
  2단계 필수면 '끄기'는 '휴대폰 바꾸기'(지우면 바로 다시 등록해야 함). 로그인 유지 12시간 (`access_token_expire_minutes=720`).
  서버에서 직접: `create_admin.py <아이디> <비밀번호>` (관리자가 없으면 관리자), `--invite [메모]`, `--admin <아이디>`,
  `--reset-password <아이디> <새 비밀번호>` (이메일 없는 예전 계정), `--reset-totp <아이디>` (휴대폰 분실).
- 비밀번호를 바꾸면(변경·찾기·서버 명령) 그 전에 발급된 토큰은 무효 (토큰 pwv ≠ password_changed_at). 마이페이지 '모든 기기에서 로그아웃'도 같음 (sev ≠ session_epoch).
- 백엔드는 `127.0.0.1` 에만 바인딩 (같은 네트워크의 다른 PC 접속 차단). 클라우드에선 backend 는 공개하지 않고 Caddy(80/443)만 공개 — Caddy basic auth(`deploy/auth.caddy`, git 제외) 한 겹 + 앱 로그인.
- 로그인 5회 실패(10분 안) → 그 IP 15분 차단 (`auth.py`, X-Forwarded-For 맨 뒤 값 기준) + 계정별 10회(15분 안) → 그 계정 15분 잠금.
- TOTP(Google Authenticator): 필수(기본). 등록 `/api/auth/setup-totp` → `/api/auth/enable-totp`, 휴대폰 바꾸기 `/disable-totp`(현재 코드). 등록하면 인증된 이메일로 알림.

## Git

개발 브랜치: `claude/dazzling-darwin-et76zj`. 로컬 PC에서 작업 전 반드시 pull 후 편집, 완료 후 이 브랜치로 push.
**push 는 아래 "테스트 후 반영 규칙"을 통과한 뒤에만** 한다 — 사용자가 PC·서버에서 pull 하는 브랜치는 항상 테스트를 마친 상태여야 한다.

## 테스트 후 반영 규칙 (수정 → 충분한 테스트 → push → 사용자가 pull)

수정한 내용은 아래를 **모두** 확인한 뒤에 커밋·push 한다. 하나라도 실패하면 push 하지 않고 고친다.
수정이 여러 군데면 **기능 하나 고칠 때마다 그 기능의 단위 테스트를 돌리고**, 마지막에 전체 점검을 한 번 더 돌린다.

1. **전체 점검 한 번에** (저장소 루트): `bash scripts/check.sh` — 아래 4단계를 순서대로 실행, 하나라도 실패하면 멈춤
   1. 백엔드 문법·import (`compileall` + 가짜 KIS 값으로 `import app.main`)
   2. 백엔드 단위·API 테스트: `cd backend && python -m pytest` (`backend/tests/`, 외부 API 를 부르지 않음, 메모리 DB)
   3. 프론트 타입 검사·빌드: `cd frontend && npm run build` (`tsc -b` 포함 — 클라우드 서버는 이 빌드 결과를 그대로 씀)
   4. 화면 테스트: `cd frontend && node e2e/smoke.mjs` (빌드된 화면 + 가짜 API(`e2e/fixtures.mjs`), Playwright —
      화면별 표시·콘솔 오류·밝은/어두운 모드·폭 390px 가로 스크롤·주요 클릭 흐름). 스크린샷: `E2E_SHOTS=폴더`
2. **테스트를 같이 추가한다** (고친 기능마다)
   - 백엔드 계산·서비스 → `backend/tests/test_<모듈>.py` 에 단위 테스트. 경계값(빈 목록·NaN·0·데이터 부족·시간 경계)과 오류 경로 포함.
     외부 호출(`kis_client._get`·`_fred`·yfinance 등)은 `monkeypatch` 로 가짜 함수로 바꾼다 (`tests/conftest.py` 의 `run`, `api_client`).
   - API 응답 형식이 바뀌면 → `backend/tests/test_routes.py` 에 화면이 쓰는 필드를 검사 (`api_client`: 라우터 + 메모리 DB + 로그인 사용자).
   - 화면이 바뀌면 → `frontend/e2e/smoke.mjs` 에 확인 항목 + `fixtures.mjs` 에 같은 필드 이름의 가짜 응답. 버그를 고쳤으면 **고치기 전 코드로 돌려 실패하는지** 확인.
3. **실제 서버로 확인** — 위 테스트는 가짜 응답 기준이므로, 바꾼 API 는 서버(`app.main`)를 띄워 실제로 호출해 본다.
   외부 API(KIS·Yahoo·네이버 등)가 이 환경에서 막혀 있으면 **가짜 서버**(예: KIS 주소만 가짜 서버로 바꾼 실행 스크립트)로 흐름을 검증하고,
   빌드된 화면을 그 서버에 붙여 로그인부터 바꾼 화면까지 열어 본다. 가짜 데이터로 화면을 채우는 코드는 앱에 넣지 않는다 (오류 처리 원칙).
   - 예측·학습 로직은 "미래 데이터 미사용"을 함께 확인 (이후 데이터를 바꿔도 그날 결과가 같아야 함 — `tests/test_core.py` 참고).
4. **실행 방법별 영향 확인**: `requirements.txt`·`package.json`·Dockerfile·`docker-compose*.yml`·`deploy/` 를 바꿨으면 해당 방법(직접 설치 / Docker / 클라우드)의 설치·실행 절차와 docs 가 맞는지 확인.
   (테스트 도구는 `backend/requirements-dev.txt`(pytest) — 앱 실행용 requirements.txt 에는 넣지 않는다)
5. **문서만 바꾼 경우**: 문서에 적은 파일 경로·명령어·API 경로·설정값이 실제 코드와 같은지 확인.
6. **기록**: PROGRESS.md 작업 이력에 `검증:` 줄로 무엇을 어떻게 테스트했는지 적는다 (테스트 개수 포함). 실제 KIS·외부 API 로 확인하지 못한 부분은 **"실서버 미검증"** 으로 분명히 적고 "알려진 이슈"에 남긴다 (사용자가 pull 후 그 부분을 확인할 수 있게).

## 작업 기록 규칙

`PROGRESS.md`가 작업 이력·명령어·알려진 이슈의 단일 기록이다 (설치 절차만 `docs/setup-local.md`, `docs/setup-docker.md`, `docs/setup-cloud.md` 로 분리). 작업 시작 전 먼저 읽고, 작업을 마칠 때마다(커밋 전) 다음을 갱신한다:
- "작업 이력"에 이번 작업 요약 + `검증:` 줄 추가 (날짜, 커밋 해시) — "테스트 후 반영 규칙" 6번
- 새로 생긴 명령어/점검 URL은 "자주 쓰는 명령어"에 추가
- 해결된 이슈는 체크, 새로 발견한 이슈는 "알려진 이슈"에 추가
