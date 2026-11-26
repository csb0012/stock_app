# PROGRESS.md

작업 이력과 자주 쓰는 명령어를 관리하는 파일. 작업이 끝날 때마다 갱신한다.

> **규칙: 수정 → 충분한 테스트 → push → PC·서버에서 pull.** 테스트를 통과하지 못한 수정은 push 하지 않는다.
> 테스트 항목은 [CLAUDE.md "테스트 후 반영 규칙"](CLAUDE.md), 각 작업에서 실제로 무엇을 테스트했는지는 아래 작업 이력의 `검증:` 줄.
> "실서버 미검증" 으로 적힌 부분은 pull 후 실제 KIS·외부 API 로 확인이 필요한 부분 ("알려진 이슈" 참고).

## 자주 쓰는 명령어

### 어떤 방법으로 실행하나? (PC마다 하나만 — 섞지 말 것)
| PC | 방법 | 설치·실행 안내 | 실행 |
|---|---|---|---|
| 회사 PC | 직접 설치 (Python 3.13 + Node + venv) | [docs/setup-local.md](docs/setup-local.md) | `start.bat` |
| 집 PC | Docker (Python·Node 설치 안 함, venv·pip 안 씀) | [docs/setup-docker.md](docs/setup-docker.md) | `start-docker.bat` |
| 서버 (24시간) | 클라우드 (Oracle Cloud 무료 VM + DuckDNS) | [docs/setup-cloud.md](docs/setup-cloud.md) | `bash deploy/setup-server.sh` / `bash deploy/update.sh` |

클라우드 서버를 켜 두면 PC 에서는 `start.bat`·`start-docker.bat` 를 켜지 않고 브라우저로 접속만 한다 (같은 KIS 키 동시 사용 → 호출 제한·DB 갈라짐).

세 방법 모두 `.env`·`stock_app.db`·`.secret_key` 위치는 **`C:\claude\stock_app\backend\`** 로 같다.

### 최신 코드 받기 (공통, 작업 전 필수 — 클라우드 서버는 `bash deploy/update.sh` 가 pull 까지 함)
```powershell
cd C:\claude\stock_app
git pull origin claude/dazzling-darwin-et76zj
```
로컬 변경사항 때문에 pull이 막히면:
```powershell
git stash
git pull origin claude/dazzling-darwin-et76zj
```
pull 후 패키지 목록이 바뀌었을 때:
- 직접 설치(회사 PC): `requirements.txt` → 가상환경 켜고 `backend` 에서 `pip install -r requirements.txt` (⚠️ `--upgrade` 금지 — bcrypt 5.x 로 올라가 로그인 깨짐), `package.json` → `frontend` 에서 `npm install`
- Docker(집 PC): `start-docker.bat` 다시 실행 (이미지 재빌드)

### 켜기 / 끄기
| | 직접 설치 (회사 PC) | Docker (집 PC) |
|---|---|---|
| 켜기 | `start.bat` 더블클릭 | Docker Desktop 켜고 `start-docker.bat` 더블클릭 |
| 끄기 | 열린 cmd 창 2개 닫기 | `docker compose down` |
| 백엔드 로그 | 백엔드 cmd 창 | `docker compose logs -f backend` |
| 계정 추가 | 가상환경 켜고 `backend` 에서 `python create_admin.py <아이디> <비밀번호>` | `docker compose exec backend python create_admin.py <아이디> <비밀번호>` |
| 비밀번호 초기화 (메일 못 쓸 때) | `backend` 에서 `python create_admin.py --reset-password <아이디> <새 비밀번호>` | `docker compose exec backend python create_admin.py --reset-password <아이디> <새 비밀번호>` |
| 2단계 인증 해제 (휴대폰 분실) | `backend` 에서 `python create_admin.py --reset-totp <아이디>` | `docker compose exec backend python create_admin.py --reset-totp <아이디>` |
| 초대 코드 (화면에 못 들어갈 때) | `backend` 에서 `python create_admin.py --invite 메모` | `docker compose exec backend python create_admin.py --invite 메모` |
| 누가 관리자인지 보기 | `backend` 에서 `python create_admin.py --list` | `docker compose exec backend python create_admin.py --list` |
| 관리자 바꾸기 | `backend` 에서 `python create_admin.py --admin <아이디>` | `docker compose exec backend python create_admin.py --admin <아이디>` |

수동 실행·처음 설치·문제 해결(winget 없음, WSL, 실행 정책 등)은 각 `docs/setup-*.md` 참고.

### 점검용
- KIS 연결 테스트: `http://localhost:8000/api/stocks/test/kis` (ok/오류만 — 토큰은 안 보여줌)
- 종목 검색 테스트: `http://localhost:8000/api/stocks/search?q=삼성전자`
- 백엔드가 `KIS_APP_KEY 가 backend/.env 에 설정되지 않았습니다` 로 안 뜨면 → `backend\.env` 확인
- 종목마스터 캐시: `backend\app\data\master_cache.json` (하루 1회 KIS에서 자동 갱신, 지우면 다음 실행 때 다시 받음)
- KIS 토큰 저장 파일: `backend\.kis_token.json` (재시작해도 23시간 재사용. 키를 바꾸면 자동으로 새로 받음). 모의투자 주문용은 `backend\.kis_mock_token.json`
- KIS 모의투자 주문 상태: 관리자 로그인 → 사이드바 '관리자 전용 → KIS 모의투자 주문' (API `/api/kis/status` — 연결·정지·잔고·대조·자동 운영 오류, `/api/kis/log` 감사 로그). 백엔드 로그 `[kis] ...`
- 예측 검증 API: `http://localhost:8000/api/predictions/review?days=90&kind=all` (호출 시 장 끝난 예측 채점, kind = all/live/backtest)
- 백테스트 진행 상황: 로그인 후 `http://localhost:5173/api/predictions/backtest/status` (화면: 예측 검증 > 과거 1년 백테스트). 백엔드 로그 `[backtest] ... 실패` 도 확인
- 학습 모델 상태·방식별 적중률: 예측 검증 화면 "예측 방식별 적중률" 카드 (API: `/api/predictions/review` 의 `method_accuracy`, `model`). 학습 결과 파일 `backend\app\data\model_{US,KR,KR_base,KRF,KRF_base}.json` (지우면 다음 백테스트 때 다시 학습)
- 외국인·기관 수급 수집 현황·변동성 이벤트 일정: 로그인 후 `/api/market/scheduler-status` 의 `flows`(쌓인 건수·마지막 수집·오류), `events`(FRED 발표 일정 갱신 시각·오류)
- 자동 예측 기록 현황: 로그인 후 `/api/market/scheduler-status` (국내 장 시작 전·장 마감 후, 미국 장 마감 후 마지막 실행 결과)
- 외부 데이터 수집 결과 파일: `backend\app\data\extras_cache.json` (재시작해도 다시 안 받음, 지워도 됨)
- 백테스트 기록 DB: `backend\stock_app.db` 의 `prediction_backtest` 테이블 (실제 예측은 `prediction_log`). 처음부터 다시 계산하려면 화면의 "전체 다시 계산"
- 백엔드 시작 로그 `[repair] 종목코드 복구 ...` = 잘못 저장된 종목코드를 자동으로 고친 것
- 장 운영 상태: `http://localhost:8000/api/market/status` (사이드바 하단에도 표시)
- 로그인 토큰 서명 키: `backend\.secret_key` (`.env` 의 SECRET_KEY 가 예시값이면 자동 생성. 다른 PC로 옮길 때 같이 복사하면 재로그인 불필요)
- 계정 추가: 다른 사람은 마이페이지 → 관리자 → 초대 코드로 가입. 내 계정은 위 "켜기 / 끄기" 표의 계정 추가 명령 (관리자가 없으면 관리자)
- FRED·Finnhub·DART 수집 현황: 로그인 후 `http://localhost:5173/api/market/extras-status` (키 설정 여부, 수집 성공/실패 수, 거시환경 점수) — 백엔드 로그 `[extras] ... 수집 실패` 도 확인
- DART 고유번호 캐시: `backend\app\data\dart_corp.json` (7일마다 자동 갱신)
- 장기 보유 분석 원본: 로그인 후 `http://localhost:5173/api/stocks/recommendations/longterm/horizon` (종목별 `horizons`·`advice`·`errors`, 비교 지수 `benchmarks`)
- 헬스체크: `http://localhost:8000/api/health`
- API 문서: `http://localhost:8000/docs`
- 매집 탐지 결과·진행: 로그인 후 `/api/accumulation` (`status.running`·`done/total`, `result.base_date`), 결과 파일 `backend\app\data\accumulation.json` (지우면 다시 계산)
- 테마 구성 갱신 상태: 로그인 후 `/api/themes/status` (테마 수·마지막 갱신·오류), 파일 `backend\app\data\themes.json` (지우면 다시 받음)
- 대시보드 구역별 데이터: 로그인 후 `/api/market/overview/kr_indices` (또는 `global_indices`·`bigtech`·`etfs`) — `updated_at`(기준 시각)·`refreshing`(뒤에서 갱신 중)·`refresh_error`
- 화면이 이상한 옛 데이터를 보이면: 로그아웃 후 다시 로그인 (브라우저 저장 데이터 `rq-cache-v1` 삭제됨). 2026-11-23 부터는 화면을 열면 저장본을 항상 한 번 새로 받음
- 미국 주간거래 가격(한국 10:00~18:00, 서머타임 ~17:00): 사이드바 "미국 — 주간거래 중", 관심종목·투자종목·AI 추천·종목탐색·대시보드 빅테크에 `주간거래 $가격 +%` 배지.
  원본: 로그인 후 `/api/watchlist/analysis` 의 미국 종목 `daytime` (조회 실패면 `daytime.error`), `/api/market/status` 의 `US.daytime`

- 퀀트 점수 원본: 로그인 후 `/api/quant?limit=20` (`quant.validation.buckets` = 점수 구간별 시장 대비 이긴 비율, `weights`·`ic` = 요인 비중). 결과 파일 `backend\app\data\accumulation.json` 의 `quant` (지우면 다시 계산)
- 시장 상태 원본: 로그인 후 `/api/market/regime` (지수별 `state`·`dist_days`·`validation`)
- AI 모의투자: 화면 'AI 모의투자'. 원본: 로그인 후 `/api/paper/accounts` (계좌별 `last_error`·`pending`), `/api/paper/accounts/<번호>` (거래·판단 기록 `log`),
  `/api/paper/simulations` (과거 시뮬레이션 목록·진행), `/api/paper/config` 의 `status`(자동 운영 `last_tick`·`last_error`). 백엔드 로그 `[paper] ...`.
  DB 테이블 `paper_account`·`paper_trade`·`paper_equity`·`paper_sim` (지우면 모의투자 기록만 사라짐)

### 테스트 (개발용 — 앱 실행엔 필요 없음)
- 전체 점검(push 전): 저장소 루트에서 `bash scripts/check.sh` (백엔드 import → pytest → 프론트 빌드 → 화면 테스트). 화면 테스트 빼기: `SKIP_E2E=1 bash scripts/check.sh`
- 백엔드 테스트만: `cd backend` → `pip install -r requirements-dev.txt`(처음 한 번, pytest) → `python -m pytest` (외부 API·실제 DB 안 씀)
- 화면 테스트만: `cd frontend` → `npm run build` → `node e2e/smoke.mjs` (Playwright 필요: `npm i -D playwright` + `npx playwright install chromium` — 클라우드 개발 환경엔 이미 있음). 스크린샷: `E2E_SHOTS=폴더 node e2e/smoke.mjs`

### 클라우드 서버 (24시간, `docs/setup-cloud.md`)
- 처음 설치: 서버에서 `cd ~/stock_app && bash deploy/setup-server.sh`
- 업데이트: `bash deploy/update.sh` (git pull + 화면 재빌드 + 백엔드 재시작)
- 로그: `sudo docker compose -f docker-compose.cloud.yml logs -f --tail 100 backend`
- 백업: 매일 04:00(서버 시간, 기본 UTC = 한국 13:00) 자동 → `~/stock_app/backups/` (수동: `bash deploy/backup.sh`)
- 접속: `https://<이름>.duckdns.org` → 접속 비밀번호(Caddy) → 앱 로그인

## 작업 이력

### 2026-11 — 초기 셋업 & 버그 수정
- `create_admin.py` 재실행 시 UNIQUE 에러 → 계정 이미 존재, 재실행 불필요
- `/api/stocks/test/kis` 404 → 로컬 코드가 구버전, `git pull`로 해결
- CLAUDE.md 생성 (한국어)
- **추천 전부 50% 표시 버그**: pandas-ta 버전별 볼린저밴드 컬럼명 차이(`BBU_20_2.0` KeyError) → `analysis.py`에서 `startswith("BBU_")`로 동적 탐색

### 2026-11 — 기능 추가 1차
- 관심종목 추가 모달에 자동완성 검색 (한글/영문/코드) — `backend/app/data/stock_list.json` + `GET /api/stocks/search` *(이후 stock_list.json 삭제, KIS 종목마스터로 교체)*
- 대시보드에 KOSPI/KOSDAQ 지수, 미국 주요 ETF(SPY/QQQ/SOXL/TQQQ/TLT) 추가
- 경제캘린더: 과거 3개월(실제 vs 예상 + 행 클릭 시 해설) + 향후 3개월

### 2026-11 — 기능 추가 2차 (commit `a0df057`)
- **AI 추천 속도 개선**: KIS 순차 호출 → yfinance 배치 다운로드(KR/US 병렬) + 15분 캐시
- **₩0 표시 수정**: 추천 가격을 yfinance 종가에서 추출
- **추천 종목 확대**: 장기 KR25+US25, 단기 KR 거래량상위20 + US 모멘텀13
- **진입 추천가**: `predict_next_day()`가 `entry_price`, `entry_comment` 반환 (확률 ≥55%일 때만)
- **투자종목 탭 신설**: `PortfolioItem` 모델, `/api/portfolio` CRUD + `/analysis`, `Portfolio.tsx`
  - 보유수량·평단가 입력, 수익률/평가손익, 내일 전망
- **종목탐색 개편**: 국내/미국 탭 × 거래량급증/거래대금/급등/급하향
  - KR: KIS API 우선 → 실패 시 yfinance 상위 30종목 fallback
  - US: yfinance 상위 50종목

### 2026-11-20 — 문서
- PROGRESS.md 추가, CLAUDE.md에 pull 방법·절대경로 실행 명령 추가 (`47a03c7`, `ab4bdd6`, `0f1e9d0`)
- PROGRESS.md에 "다른 PC로 옮기기" 절차 추가 (.env, stock_app.db 수동 복사)

### 2026-11-20 — 기능 추가 3차 (commit `ca04925`)
- **KIS 키 필수화**: `KIS_APP_KEY/SECRET/ACCOUNT_NO` 가 없거나 예시값이면 서버 시작 시 오류. `.env`·`stock_app.db` 경로를 `backend/` 기준 절대경로로 고정
- **오류 숨김 제거**: KIS 응답 오류(`rt_cd != 0`)를 메시지 그대로 화면에 표시. 국내 스크리너의 yfinance 대체 동작 삭제. 토큰 만료 시 재발급 후 재시도, 초당 호출 제한 대응
- **종목코드 오류 수정 (SOL AI반도체TOP2플러스 ₩21,675 → 실제 ₩11,395)**: 원인은 손으로 적은 `stock_list.json` 의 잘못된 코드(441800). KIS 공식 종목마스터(`services/stock_master.py`, 국내 주식·ETF·ETN + 미국 NAS/NYS/AMS 전체)로 교체하고 json 삭제. 투자종목·관심종목 추가 시 마스터에 있는 코드만 허용, 기존에 잘못 저장된 종목은 경고 표시
- **국내 시세를 KIS로**: 투자종목·관심종목·추천의 국내 가격/일봉을 KIS로 조회(장중 실시간). KIS 일봉이 최신순이라 지표가 거꾸로 계산되던 버그 수정(날짜 오름차순 정렬)
- **내일 전망 근거**: `predict_next_day()` 가 `factors`(지표별 상승/하락/중립 + 점수)와 `summary`(한 줄 요약) 반환 → `PredictionReasons` 컴포넌트로 투자종목·관심종목·추천·검색에 표시
- **투자종목**: 국내(원)/미국(달러) 손익 분리 + USD/KRW 환율(yfinance `KRW=X`) 적용한 원화 총합
- **관심종목**: 현재가·등락률·5일/20일 수익률·RSI·기간 고저 위치·내일 전망·메모·목표 매수가(도달 표시), 정렬. `watchlist` 테이블에 `memo`, `target_price` 컬럼 추가 (기존 DB는 시작 시 자동 ALTER)
- **종목탐색**: 종목 검색(자동완성) → 시세·전망 카드, 행 클릭 시 상세, 20개씩 더보기. 국내는 KOSPI+KOSDAQ 순위 합산(최대 60), 미국은 Yahoo 전체 시장 스크리너(`yf.screen`, 최대 200)
- **KIS 순위 API 파라미터 수정**: 거래량급증 = `FID_BLNG_CLS_CODE=1`(거래증가율), 거래대금 = `3`(거래금액순). 기존 `FID_DIV_CLS_CODE=1` 은 보통주 필터였음. 등락률은 `fid_prc_cls_code=1`(종가대비)
- **AI 추천**: 국내/미국 탭 분리, 상승확률 높은 순/낮은 순 정렬, 분석 실패 종목 표시

### 2026-11-20 — 로그인 오류 수정
- `pip install -r requirements.txt --upgrade` 안내 때문에 bcrypt가 5.x로 올라가 passlib 비밀번호 검증이 `ValueError(password cannot be longer than 72 bytes)` → 로그인 500. requirements.txt에 `bcrypt==4.0.1`, `sqlalchemy[asyncio]` 고정, 갱신 명령에서 `--upgrade` 제거

### 2026-11-20 — 시작 오류 수정
- `stock_list.json` 삭제로 `backend/app/data/` 폴더가 git에서 사라져 종목마스터 캐시 저장 시 `FileNotFoundError` → 백엔드 시작 실패. 저장 전에 폴더 생성하도록 수정
- 확인됨: 회사 PC에서 KIS 종목마스터 다운로드·파싱은 정상 (저장 단계까지 도달)

### 2026-11-20 — 기능 추가 4차 (commit `80a4aa5`)
- **잘못 저장된 종목코드 자동 복구** (`services/repair.py`): 시작 시 투자종목·관심종목의 코드와 종목마스터 이름을 대조, 저장된 이름과 정확히 같은 종목이 하나뿐이면 코드 교체 (SOL AI반도체TOP2플러스 441800 → 0167A0)
- **다음 거래일 라벨** (`services/market_calendar.py`, `holidays` 패키지 XKRX/NYSE): 예측에 `target_date`, `target_label`("오늘"/"내일"/"월요일(11/23)") 추가 → 금요일엔 "월요일(11/23) 상승 확률"
- **AI 추천 실시간 갱신**: `/stocks/recommendations/{kind}` 가 호출마다 현재가(국내 KIS 현재가, 미국 yfinance 1분봉)로 오늘 봉을 갱신해 확률 재계산(10초 캐시). 일봉·종목 목록은 15분 캐시. 화면은 15초마다 자동 갱신, 확률 변화량(▲▼%p) 표시
- **뉴스 요인** (`services/news.py`): 국내 네이버 금융 종목뉴스, 미국 yfinance 뉴스 → 호재/악재 키워드 수로 15점 요인 추가 (종목별 10분 캐시)
- **예측 검증 메뉴** (`/predictions`, `models/prediction.py`, `services/prediction_log.py`): 추천·투자종목·관심종목·검색에서 낸 예측을 (종목, 대상일)별로 저장(대상일 전까지 최신 값으로 갱신) → 대상일 장 마감 후 채점(30분 주기 + 화면 열 때). 상승 예측(≥55%)/하락 예측(≤45%) 적중률, 확률 구간별 실제 상승 비율, 틀린 이유(시장 동반 등락·시가 갭·거래량 급증·뉴스·근거 지표 실패) 표시
- **단기/스윙 분류**: 국내 주식 / 미국 / 스팩 / ETF·ETN 탭 (`stock_master.category()`), 거래량 급증 후보 20 → 30종목
- **속도 개선**: KIS 연결 재사용(keep-alive), 토큰 파일 저장(재시작 시 재발급 생략), 일봉 60초 캐시, 투자종목·관심종목 국내 일봉 1회 호출(100개), 대시보드 지수 배치 조회 + 60초 캐시, 환율 5분 캐시

### 2026-11-20 — 코드 점검 + 기능 추가 5차 (commit `0150176`)
**찾아서 고친 오류**
- 가격이 전혀 안 움직인 종목(스팩·거래정지 등)은 RSI 가 NaN → JSON 응답 실패로 **AI 추천 화면 전체가 500 오류** 날 수 있었음 → 지표값 NaN/inf 를 None 으로 정리 (`analysis._clean`)
- 지표값이 정확히 0 이면 None 으로 사라지던 문제 (`if x` → `if x is not None`)
- AI 추천(15초 갱신)과 투자종목·관심종목이 동시에 같은 종목 예측을 저장하면 UNIQUE 충돌 → 화면 오류 가능 → 저장 직렬화, 저장 실패해도 화면은 정상 (로그만)
- KIS 점검 시간 등 HTML 응답일 때 JSON 파싱 예외 → KIS 오류 메시지로 정리
- 네이버 금융 뉴스(EUC-KR) 글자 깨짐 → 호재/악재 판단 불가 → 인코딩 지정
- AI 추천 여러 탭/요청 동시 접속 시 현재가 재계산이 중복 실행 → 종류별 잠금
- 종목검색 화면에서 미국 아멕스(AMS) 종목(SOXL 등) 조회 불가 → 자동완성으로 거래소 자동 지정
- `/stocks/kr`, `/stocks/us` 에서 KIS 외 예외는 500 으로 떨어지던 문제 → 502 + 원인 메시지
- 대시보드 지수 조회 실패가 `0` 으로 보이던 문제 → "조회 실패" 표시
- 관심종목·종목탐색에서 추가 실패(종목마스터에 없는 코드 등) 시 아무 표시 없던 문제
- `start.bat` 가 가상환경을 켜지 않아 시스템 Python 으로 실행되던 문제, CRLF 줄바꿈·한글 깨짐(chcp 65001)
- **보안**: `start.bat` 가 `0.0.0.0` 으로 열려 회사 네트워크의 다른 PC에서 접속 가능 + 회원가입 API 공개 → 누구나 가입해서 내 KIS 키로 조회 가능했음 → `127.0.0.1` 바인딩, 계정이 있으면 가입 차단
- **보안**: `SECRET_KEY` 가 예시값이면 로그인 토큰 위조 가능 → 무작위 키 자동 생성(`backend/.secret_key`)

**추가 기능**
- 투자종목: 오늘 손익(종목별·통화별·원화 합계) + 종목 비중(원화 환산 평가금액 기준)
- 사이드바 하단: 국내/미국 장 운영 상태(장중·개장 전·장 마감·휴장) + 다음 개장 시각(한국시간)
- AI 추천 카드에서 바로 관심종목 추가
- 예측 검증: 지표별 적중률 (각 지표가 상승/하락 신호를 냈을 때 실제로 맞은 비율)
- 종목검색: 종목명 자동완성 (코드 몰라도 검색)

### 2026-11-20 — 새 PC 설치 안내 정리
- PROGRESS.md "최초 설치"·"다른 PC로 옮기기" 를 "새 PC 설치 (처음부터)" 하나로 통합: 필요한 프로그램(Git·Python 3.13·Node.js LTS), 실행 정책, clone 위치, `.env`/`stock_app.db`/`.secret_key` 복사 위치, 가상환경 위치(루트 `.venv` 로 통일), npm install, 폴더 구조
- 기존 "최초 설치" 에 프론트엔드 `npm install` 이 빠져 있던 것 보완, 가상환경 위치가 문서마다 달랐던 것(backend\.venv vs 루트 .venv) 통일

### 2026-11-20 — Docker 실행 지원
- `docker-compose.yml`, `backend/Dockerfile`(python:3.13-slim), `frontend/Dockerfile`(node:22-slim), `.dockerignore`, `start-docker.bat` 추가 → PC에 Python·Node 설치/버전 맞추기 불필요
- backend·frontend 폴더를 컨테이너에 그대로 연결: `.env`/`stock_app.db`/`.secret_key` 위치 동일, 코드 수정 자동 반영(Windows 폴더 감지를 위해 폴링)
- 포트는 `127.0.0.1` 에만 공개. `.env` 등 비밀 파일은 이미지에 포함하지 않음(.dockerignore)
- `vite.config.ts`: 프록시 대상을 `VITE_PROXY_TARGET` 환경변수로 (Docker 에선 backend 컨테이너), `VITE_POLL` 이면 파일 감지 폴링
- `requirements.txt` 에 `tzdata` 명시 (Windows·Docker 에서 Asia/Seoul 시간대 DB 보장)
- 검증: 이미지 빌드 → compose 기동 → 프론트(5173) 경유 로그인·장 상태·종목 검색·회원가입 차단·컨테이너 안 create_admin 동작 확인 (실제 KIS 호출은 미검증)

### 2026-11-20 — 설치 문서 정리 (방법별 분리)
- 직접 설치(venv)와 Docker 안내가 한 곳에 섞여 Docker 사용 중 `python -m venv` 를 실행하는 혼란 → `docs/` 폴더로 방법별 분리
  - `docs/setup-local.md` (회사 PC, 직접 설치), `docs/setup-docker.md` (집 PC, Docker)
- PROGRESS.md "자주 쓰는 명령어" 는 어느 PC가 어떤 방법인지 표 + 공통 명령(pull) + 방법별 켜기/끄기 표만 남김
- CLAUDE.md "앱 실행"·"최초 설치" 도 방법별로 나누고 docs 를 가리키도록 수정

### 2026-11-20 — 외부 데이터 요인 + 추천 매입가 + 뉴스 오류 수정 (commit `14ce352`)
- **뉴스 410 오류 수정**: `finance.naver.com/item/news_news.naver` 가 폐지(410 Gone) → 네이버 증권 모바일 API(`m.stock.naver.com/api/news/stock/{코드}`), 실패하면 Google 뉴스 RSS(종목명 검색)로 받고 출처를 요인 설명에 표시. 종목검색 화면 뉴스도 같은 모듈 사용(`market_data.get_news_naver` 삭제)
- **뉴스 판단 개선**: "우려 해소"·"흑자 전환"·"적자 축소" 같은 문구를 먼저 판단 (예전엔 '하락 우려 해소' 를 악재로 셈)
- **외부 데이터 요인** (`services/extras.py`, `.env` 키 있을 때만):
  - 거시환경 10점 (FRED, 전 종목): VIX 수준·추세, 하이일드 스프레드 20일 변화, 미 10년 금리 20일 변화, 장단기 금리차
  - 애널리스트 15점 (Finnhub, 미국 개별주): 최근 월 매수/보유/매도 의견 비율
  - 실적 10점 (Finnhub, 미국 개별주): 최근 4분기 EPS 예상치 상회 횟수 + 7일 내 실적발표 예정이면 ⚠ 경고
  - 공시 10점 (DART, 국내 일반 주식): 최근 14일 공시 제목 → 호재성(자사주 취득·공급계약·무상증자 등) / 악재성(유상증자·CB·최대주주변경·소송 등)
  - 호출 제한(Finnhub 무료 분당 60회) 때문에 화면 요청 안에서 기다리지 않고 백그라운드 큐로 수집. 수집 전엔 "수집 중 — 중립", 실패하면 "조회 실패 — 중립 (원인)". 시작 시 추천 후보 종목을 미리 수집 예약
- **추천 매입가** (`analysis._buy_zone`): 현재가 아래 지지선(20일선·60일선·볼린저 중심/하단·최근 20일 저점)과 ATR 로 계산
  - 65%↑ 지금 가격대 분할 매수 / 55~64% 가까운 지지선까지 눌리면 / 45~54% 1 ATR 이상 아래 지지선까지 관망 / 45% 미만 볼린저 하단·최근 저점에서 하락 멈춤 확인 후
  - 매입가·범위·현재가 대비 %·설명 표시. 손절가는 매입가보다 아래로 조정
  - AI 추천 카드(추천 매입가/목표가/손절가 3칸), 종목탐색 검색 카드, 관심종목(AI 추천 매입가), 투자종목(추가 매수 추천가), 종목검색 화면

### 2026-11-20 — 과거 90일 백테스트 + 하락확률 정렬 (commit `363898e`)
- **AI 추천 정렬 추가**: 하락확률 높은 순 / 낮은 순 (하락 확률 = 100 − 상승 확률). 카드에 하락 확률도 같이 표시
- **과거 90일 백테스트** (`services/backtest.py`): 최근 90일(달력) 거래일마다 **대상일 전날 종가까지의 일봉 130개만** 보고 예측 → 대상일 실제 등락으로 채점 (미래 데이터 미사용)
  - 대상: AI 추천 후보(국내 장기·미국 장기·미국 단기) + 관심종목 + 투자종목
  - 결과는 `stock_app.db` 의 `prediction_backtest` 테이블에 저장. 이미 계산한 날짜는 건너뜀 → 서버 시작 20초 후 + 하루 한 번 새 날짜만 추가
  - 뉴스·FRED·Finnhub·DART 는 과거 시점 기록이 없어 빼고 기술적 지표(RSI·MACD·볼린저·이평)만 사용
  - 틀린 이유 분석(시장 동반 등락·갭·거래량 급증·근거 지표)은 실제 예측과 같은 로직 (`prediction_log.grade()` 로 공통화)
  - 종목 데이터 조회 실패는 건너뛰고 화면에 "실패 N건" 으로 원인 표시
- **예측 검증 화면**: 기본 최근 90일, "실제 + 백테스트 / 실제 예측만 / 백테스트만" 선택 (같은 종목·날짜면 실제 예측 우선), 실제·백테스트 적중률 따로 표시, 종목별 적중률, 백테스트 실행 버튼·진행률, 목록은 서버에서 거르고 200건씩 "더 보기"

### 2026-11-20 — KIS 초당 호출 제한(EGW00201) 대응 (commit `34e8890`)
- 증상: 백테스트 중 `삼성바이오로직스(207940): KIS FHKST03010100 실패 (HTTP 500, EGW00201): 초당 거래건수를 초과하였습니다`
- `kis_api._get`: EGW00201 이면 1·2·3·4·5초씩 늘려가며 최대 5회 재시도(최대 약 15초). 기다리는 동안 **다른 KIS 요청도 같이 멈춤**(앱키 단위 제한이라), 이후 1분간 호출 간격 2배(0.07→0.14초) 후 원래 속도로
- 그래도 안 되면 `KISRateLimitError` (KISError 하위) — 화면에는 기존처럼 원인 표시
- 백테스트: 호출 제한으로 실패한 종목은 바로 실패 처리하지 않고 끝에 모아서 **10초 → 30초 → 60초 기다렸다가 그 종목만 다시 계산**. 세 번 다 실패하면 그때 "실패" 목록에 표시. 대기 중엔 진행 줄에 노란색으로 "초당 호출 제한 — N초 후 M종목 다시 계산" 표시
- 다른 오류(데이터 부족 등)는 재시도하지 않고 바로 표시

### 2026-11-20 — 학습형 예측 모델 + 종목탐색 자동 갱신 (commit `a55bd31`)
- 배경: 실데이터 백테스트에서 규칙 점수 적중률 49.6% (상승 판정 45.9%) — 동전 던지기 수준
- **학습 모델** (`services/ml_model.py`, numpy 로지스틱 회귀): 지표를 점수로 바꾸지 않고 값 그대로(최근 1·5·20일 수익률, RSI, MACD, 볼린저 위치, 5·20·60일선 이격, 거래량 배수, ATR, 당일 종가 위치, 시가 갭, 지수 1·5일 등락, 지수 대비 초과수익) + **국내는 간밤 미국장(S&P500·나스닥) 등락** 을 넣고 과거 약 2년(국내 KIS 일봉 500개, 미국 yfinance 2y)으로 "다음 날 상승 여부" 를 학습
  - 변형 3개: `US`, `KR`(간밤 미국장 반영 — 미국장 마감 후~한국장 시작 전에만 사용), `KR_base`(미국장 결과 반영 전)
  - **walk-forward 검증**: 최근 90일을 10거래일씩 나눠, 각 구간은 그 전에 결과가 나온 데이터로만 학습해 예측 (미래 누설 없음)
  - **채택 조건** (셋 다 만족해야 실제 화면에 사용, 아니면 기존 규칙 점수): ① 방향 적중률이 동전 던지기보다 통계적으로 높음(단측 95%) ② 상승/하락 판정 30건 이상 ③ 판정 적중률이 같은 기간 규칙 점수보다 높음
  - 실시간: 학습 모델 확률 + 뉴스(±3%p)·거시(±2)·애널리스트(±3)·실적(±2)·공시(±3) 소폭 보정. "근거 자세히" 맨 위에 "학습 모델" 요인(주요 근거 3개, 백테스트 적중률), 미채택이면 사유 표시
  - 매일 백테스트 때 재학습. 지수 일봉은 10분마다 갱신
- **장 시작 전 자동 갱신**: 국내 거래일 08:20~08:58 사이 서버가 켜져 있으면 국내 대상 종목(추천 후보·관심·투자)을 간밤 미국장 반영해 다시 예측·기록 (출처 "장전 자동") → 이 예측이 채점됨
- **백테스트 개편**: 같은 날짜를 규칙 점수/학습 모델/(국내) 장 시작 전 모델로 모두 계산해 저장 (`rule_probability`, `model_probability`, `preopen_probability`, `method` 컬럼 추가). 예전 기록(method 없음)은 자동 삭제 후 재계산. 실제 예측 기록에도 같은 컬럼 저장
- **예측 검증 화면**: "예측 방식별 적중률" 카드(판정 적중률·상승/하락 판정·방향 적중률·판정 비율) + 변형별 학습 모델 사용 여부와 사유, 백테스트 진행 단계 표시
- **AI 추천 정렬**: 상승확률 높은 순 / 하락확률 높은 순만 남김 (낮은 순은 반대 정렬과 같아서 삭제)
- **종목탐색 자동 갱신**: 순위 목록 10초마다(백엔드 캐시 국내 8초·미국 30초), 마지막 갱신 시각 표시. 검색 카드도 15초마다 갱신(현재가 실시간 반영 후 확률 재계산)
- 가짜 데이터 검증: 패턴을 심은 데이터 → 국내(장 전) 67%·미국 61% 로 학습·채택, 완전 무작위 데이터 → 방향 적중률 49~50% 로 모두 미채택 (누설 없음 확인)

### 2026-11-20 — 실데이터 백테스트 결과 기록 + 문구 수정 (commit `1035382`)
- 실데이터 첫 결과 (최근 90일, 61종목, 3,791건): 규칙 점수 판정 49.5%·방향 50% / 학습 모델(장중·마감 후 기준) 판정 53.1%·방향 50.3% / **국내 장 시작 전 모델(간밤 미국장 반영) 판정 56.6%·방향 55.4% → 채택(사용 중)**
- 미국 모델(방향 48.8%), 국내 장중/마감 후 모델(방향 52.0% < 기준 52.1%)은 우연 수준을 못 넘어 미사용 → 규칙 점수 유지
- 예측 검증 화면의 백테스트 설명이 "기술적 지표만" 으로 남아 있던 것을 학습 모델 포함 설명으로 수정

### 2026-11-20 — 클라우드 서버 배포 (commit `1ae8c2a`)
- 목적: PC 를 켜두지 않고 24시간 운영 (08:20 장 시작 전 예측·채점·백테스트)
- 조사: Render·Koyeb 등 무료 PaaS 는 유휴 시 잠듦/파일 초기화 → 부적합. 무료로 계속 켜지는 건 Oracle Cloud Always Free VM(2026-08부터 Ampere 2 OCPU/12GB 한도)·Google Cloud e2-micro 정도 → Oracle 한국 리전 선택 (KIS 를 국내 IP 에서 호출) — *이후 무료 가입 목록에 한국 리전이 없어 일본 오사카·도쿄로 변경, 현재 기준은 docs/setup-cloud.md*
- `docker-compose.cloud.yml` + `deploy/` (Dockerfile.web: React 빌드 → Caddy, Caddyfile: 자동 HTTPS·보안 헤더·basic auth·/api 프록시, setup-server.sh: Docker 설치·스왑·iptables 80/443·도메인/비밀번호·매일 백업 cron·실행, update.sh, backup.sh: SQLite 온라인 백업 14개 보관)
- 보안: backend 비공개, 앱 로그인 앞 basic auth, 로그인 5회 실패 시 IP 15분 차단(`auth.py`), FastAPI 문서는 /api 밖이라 비공개
- 문서: `docs/setup-cloud.md` (가입·VM·DuckDNS·SSH·배포 키·파일 복사·설치·백업·문제 해결)
- 이 환경에서 Docker 로 검증: 두 이미지 빌드, 비밀번호 없으면 401, 화면/SPA 경로/`/api` 프록시 정상, http→https 리다이렉트, 보안 헤더, 로그인 차단(5회 실패 → 429, 다른 IP 는 정상)

### 2026-11-20 — Oracle 유휴 회수 대응 (commit `32ead00`)
- 공식 기준 확인: 7일간 CPU 95퍼센타일·네트워크·메모리(A1 전용) 사용률이 **모두** 20% 미만이면 회수 → 하나만 넘으면 됨
- 측정: 백엔드 메모리 약 200MB(대기)~310MB(백테스트 중) → VM 을 1 OCPU/2GB 로 만들면 OS·Docker·Caddy 포함 35~45% → 회수 대상 아님. 문서의 권장 사양을 6GB → 2GB 로 변경
- CPU 를 일부러 돌리는 방식은 하루 한 번으로는 95퍼센타일 기준을 못 넘고(하루 약 72분 이상 필요) 자원 낭비라 채택 안 함
- `setup-server.sh` 마지막에 현재 메모리 사용률 출력

### 2026-11-20 — Oracle Ampere 자리 부족 대응 (commit `68d9f0f`)
- 증상: VM 생성 시 `Out of capacity for shape VM.Standard.A1.Flex in availability domain AD-1` (오사카)
- `deploy/oci-launch-retry.sh` (Oracle Cloud Shell 에서 실행): 공개 서브넷 없으면 VCN·인터넷 게이트웨이·서브넷 생성 → 80/443(+UDP 443) 허용 보안 목록 `stock-web` 생성·연결 → SSH 키 생성 → A1.Flex 1 OCPU/2GB Ubuntu 24.04 생성을 90초마다 재시도(429 면 5분 대기, 한도 초과·기타 오류는 중단) → 공인 IP 출력. 이미 VM 이 있으면 건너뜀
- 가짜 oci 명령으로 흐름 검증 (자리 없음 2회 → 3번째 성공, 보안 목록·서브넷 연결 호출 확인). 실제 Oracle 에서는 미검증
- 실제 Cloud Shell 실행: 네트워크·80/443 규칙 생성까지 성공, SSH 키 생성에서 `ED25519 keys are not allowed in FIPS mode` → RSA 4096 키(`~/.ssh/oci_rsa`)로 변경 (commit `eaee55c`)
- 첫 시도가 "요청이 너무 잦음(429)" 으로 분류됨 → 오류 응답의 opc-request-id 안에 '429' 글자가 있어도 잘못 걸릴 수 있어 `TooManyRequests` 또는 `"status": 429` 일 때만 429 로 판단하도록 수정, 시도마다 Oracle 오류 메시지 표시
- 저장소가 공개(public)임을 확인 → setup-cloud.md: 서버는 https 로 clone(배포 키 불필요), Cloud Shell 은 curl 로 스크립트 받기

### 2026-11-21 — 화이트/다크 모드 + 알려진 이슈 정리 (commit `2a89af6`)
- **화이트/다크 모드**: 사이드바 아래 "화이트 모드 / 다크 모드" 버튼 (로그인 화면은 오른쪽 위). 선택은 브라우저에 저장, 처음엔 OS 설정을 따름
  - 화이트 모드 색: 바탕 `#F5F5F5`·카드 `#FFFFFF`, 버튼·강조 파랑 `#006CE1`, 사이드바 진회색 `#4F4F4F`
  - `index.css` 의 `:root[data-theme="light"]` 변수만 바꾸는 방식. 화면 곳곳의 고정색 옅은 배경(rgba)을 테마 색 기반 `color-mix` 로 바꿔 두 테마 모두 맞게 함
- **자동 예측 기록** (`services/scheduler.py`): 국내 장 마감 후(15:40~16:20 KST)·미국 장 마감 후(16:10~16:50 ET)·국내 장 시작 전(08:20~08:58, 기존) 에 대상 종목 예측을 자동 기록 → 화면을 안 열어도 매일 채점 대상이 쌓임
- **AI 추천 첫 로딩 대기 제거**: 기본 데이터(일봉·뉴스)를 14분마다 백그라운드에서 미리 계산 (갱신 중에도 기존 캐시로 응답)
- **외부 데이터 수집 결과 파일 저장** (`extras_cache.json`): 재시작 후 "수집 중" 없이 바로 사용 (유효기간 지난 값·오류는 저장/복원 안 함)
- **미국 PER/PBR**: KIS 해외주식 현재가상세(HHDFS76200200)로 조회, 12시간 캐시, ETF 제외. 실패하면 그 종목만 PER 표시 안 함(로그). 장기 적합도 계산에도 반영
- **새해 첫 거래일 국내 10:00 개장** 반영 (장 운영 상태·채점 시각)
- 해결된/낡은 이슈 정리 (뉴스 문구 판단, SECRET_KEY 첫 실행, 백테스트 설명·호출 수 중복 항목)

### 2026-11-21 — 대시보드 시세 출처·정확도 + 상단 바 (commit `847a3b6`)
- 사용자 이중검증에서 대시보드 값이 실제와 다름: 코스피 앱 5,137.89(+1.39%) vs 실제 4,869 / 엔비디아 앱 125.53 vs 130.09 / 애플 342.56 vs 344.92
- 원인
  - 대시보드는 전부 Yahoo Finance(yfinance) 일봉.
  - **Yahoo 의 ^KS11·^KQ11 은 최신 거래일이 하루 늦게 들어오는 경우가 있어** 전날 값이 보였음.
  - 미국 종목은 정규장 종가였는데, 비교한 값은 장 마감 후 **애프터마켓 가격**이었던 것으로 보임 (토 09:52 KST = 미국 금 애프터마켓 중).
- 수정
  - 코스피·코스닥 = **KIS 업종 현재지수(FHPUP02100000)** 로 변경. 실패하면 Yahoo 로 대체하지 않고 "조회 실패 — 원인" 표시.
  - 모든 카드에 **출처·기준일** 표시 ("KIS 실시간 · 11/20", "Yahoo · 11/20 종가"). Yahoo 날짜가 최신 거래일보다 늦으면 "⚠ 최신 아님".
  - 빅테크·ETF: "11/20 종가 $125.53" 옆에 **애프터마켓/프리마켓 가격과 종가 대비 %** 따로 표시. yfinance 5분봉 prepost 의 마지막 값이고, 정규장 시간이면 표시 안 함.
  - 학습 모델의 지수 특징값도 코스피·코스닥 최신 거래일 값을 KIS 실시간 지수로 채움(`ml_model._patch_kr_index`) → Yahoo 지연 때문에 국내 학습 모델이 "특징값 부족"으로 빠지던 문제 방지.
- **상단 바**: 화이트/다크 모드·로그아웃 버튼을 사이드바 맨 아래에서 페이지 오른쪽 위(새로고침 위)로 이동, 사용자 이름 표시

### 2026-11-21 — 하드코딩 자체검증·가짜 캘린더 삭제, 모델 결합, 속도 개선 (commit `cb9b9e9`)
- **하드코딩 자체검증**
  - 저장소 전체에서 화면 숫자(5137·4869·6910·125.53 등)와 가격 직접 대입을 검색 → 코드에는 없음 (PROGRESS.md 기록만).
  - 대시보드 값은 `market_data.py` 에서 매번 KIS·yfinance 로 받음.
  - **발견·삭제: 경제 캘린더 가짜 데이터**
    - Finnhub 키가 없거나 호출이 실패하면, 손으로 적은 과거 일정·가짜 발표치·"AI 해설"(`_get_mock_calendar`)을 조용히 보여주고 있었음.
    - Finnhub 경제 캘린더는 유료 기능일 가능성이 높아, 실제로는 계속 가짜가 보였을 수 있음.
  - 수정: Finnhub → 안 되면 **FRED 공식 발표 일정**(무료, CPI·고용·GDP·PCE·FOMC·PPI·소매판매·JOLTS·실업수당·미시간대).
    - 출처와 Finnhub 실패 사유를 화면에 표시. 둘 다 안 되면 502 오류.
    - 발표치·예상치가 둘 다 숫자일 때만 "예상 상회/하회/부합" 계산.
- **상단 바 위치**: 페이지 내용 폭 안이 아니라 창 오른쪽 끝으로 이동
- **모델 + 규칙 결합(앙상블)·보정** (`ml_model.stack_fit`)
  - walk-forward 모델 확률(logit)과 규칙 점수 확률을 로지스틱 회귀로 결합. 백테스트 기간을 시간순 5구간으로 나눠, 앞 구간으로 결합 → 다음 구간 예측 (미래 누설 없음).
  - 실력만큼만 반영되고, 실력이 없으면 50% 근처로 모임.
  - 사용 조건: 모델 가중치 > 0, 방향 적중률 > 50%, 판정 30건 이상, 판정 적중률이 50%와 규칙보다 높음.
  - 실시간 우선순위: 결합 → 모델 단독(엄격한 채택) → 규칙 점수.
  - 가짜 데이터 검증: 무작위 데이터에서는 셋 다 사용 안 함. 패턴 데이터에서는 국내(장 전)·미국 결합 사용, 패턴 없는 KR_base 는 사용 안 함.
  - 백테스트·실제 기록에 `combo_probability`, `preopen_combo_probability` 컬럼 추가. 예측 검증 "방식별 적중률" 에 결합 2줄 추가.
  - 예전 백테스트 기록은 결합 값이 없어 자동 재계산.
- **속도**
  - AI 추천 15초 갱신의 국내 현재가: 종목마다 KIS 1회 → **멀티종목 시세(FHKST11300006) 30종목당 1회** (55종목 55회 → 2~3회). 멀티 호출이 실패하거나 빠진 종목만 종목별 현재가로 다시 조회.
  - 분석 결과 메모: 입력(일봉 마지막 2개·뉴스·외부데이터·모델)이 같으면 재계산 안 함 (90종목 2.0초 → 0.01초, 장 마감 후·가격 그대로인 종목)

### 2026-11-21 — 50% 기준 채점, 하락확률 정렬 표시, 극단값 과신 수정, 스팩 제외 (commit `9f98d99`)
- **채점 기준 변경**
  - 상승 = 확률 50% 초과, 하락 = 50% 미만. 모든 예측을 둘 중 하나로 채점하고, 정확히 50% 만 제외. 예전에는 55% 이상·45% 이하만 채점하고 사이는 "중립".
  - 저장된 예전 기록도 화면에서는 새 기준으로 다시 채점 (`prediction_log.outcome_of`).
  - 55/45 는 "확신 예측" 으로 방식별 비교표에만 남김.
- 상승/하락 예측 적중률은 서로 다른 묶음의 적중률이라 합이 100이 아님 → 카드에 "틀림 %"(= 100 − 적중률)를 같이 표시해 각 묶음 안에서 합 100 이 되게 함
- **하락확률 높은 순 정렬**
  - 카드의 큰 막대·숫자를 하락 확률로 바꿔 표시 (하락 확률이 높을수록 빨강).
  - 정렬은 15~85% 로 자르기 전 값(`probability_exact`) 기준이라, 같은 85% 끼리도 순서가 정해짐.
- **극단값 과신 수정**
  - 증상: 금요일 미국장 급락(나스닥 −5.3%) 다음 국내 종목이 전부 상승 15%·하락 85% 로 똑같이 나옴.
  - 원인: 직선(로지스틱) 모델이 학습 범위 밖 극단값을 그대로 키움.
  - 수정: `ml_model.fit` 이 특징값별 학습 데이터 1~99% 범위를 기억하고, 예측 때 범위 밖 값은 끝값으로 자름 (예: −5.3% → 학습 범위 끝 −2.3% 로 계산 → 25%).
  - 다음 백테스트(서버 시작 시)에 재학습되어 적용.
- **AI 추천에서 스팩 제외**: 탭 삭제 + 단기 추천(거래량 급증) 후보에서 스팩 제외

### 2026-11-21 — 뉴스 클릭 시 원문 기사로 이동 (commit `872170e`)
- AI 추천 카드의 뉴스 제목을 누르면 새 탭에서 원문 기사가 열림 (`components/common/NewsLink.tsx`)
  - 링크: 네이버 뉴스 / Google 뉴스 / Yahoo.
  - http·https 링크만 허용, `noopener noreferrer`.
  - 링크가 없으면 일반 글자로 표시하고, 마우스를 올리면 언론사·날짜 표시.
- 종목검색 화면의 뉴스 목록도 같은 링크 검사 적용
- 참고 (예측에 들어가는 것):
  - 가격·거래량·지수(국내는 간밤 미국장) 기반 학습 모델/규칙 점수.
  - 뉴스 분위기·FRED 거시(VIX·하이일드·금리)·애널리스트·실적·공시는 소폭 반영.
  - 7일 내 실적발표는 경고만 표시.
  - FOMC·CPI 발표일·옵션 만기일(마녀의 날)은 아직 예측에 안 들어감.

### 2026-11-21 — 변동성 이벤트 경고 + 외국인·기관 수급 (commit `b688bb3`)
- **변동성 이벤트 경고** (`services/events.py`, 확률은 안 바꾸고 경고만)
  - 옵션 만기일 (날짜 규칙으로 계산, 휴장이면 앞 거래일):
    - 국내: 매월 둘째 목요일, 3·6·9·12월은 "네 마녀의 날".
    - 미국: 매월 셋째 금요일, 3·6·9·12월은 "쿼드러플 위칭".
  - 미국 주요 지표 발표 (FRED 공식 발표 일정, 6시간마다 갱신, 중요도 high: CPI·고용·GDP·PCE·FOMC):
    - 미국: "발표일 — 변동성 주의".
    - 국내: "간밤 미국 ○○ 발표 결과가 반영되는 날" / "오늘 밤 미국 ○○ 발표 예정".
  - AI 추천 카드에 노란 배지, 요약·경고 목록에도 표시.
- **외국인·기관·개인 수급** (`services/flows.py`, `models/flow.py` → `investor_flow` 테이블)
  - KIS 주식현재가 투자자(FHKST01010900)로 일별 순매수 수량 수집. KIS 가 최근 약 30거래일만 줘서 DB 에 쌓음:
    - 백테스트 때 국내 대상 종목 전부 수집.
    - 매일 18:10~18:50 KST 수집 (스케줄러 `flow_kr`).
    - 서버 시작 때 DB 에서 불러옴.
  - AI 추천 카드: "수급 5일 · 외국인 +13.6만주 · 기관 −12.5만주 · 개인 −30.0만주".
  - 학습 모델 특징값 추가: 외국인·기관 순매수 ÷ 20일 평균 거래량 (전일·5일 합). 새 변형 `KRF`(장 시작 전 + 수급), `KRF_base`(장중·마감 후 + 수급).
    - 기존 변형과 같은 walk-forward 검증·채택 조건을 통과해야 사용.
    - 실시간은 수급 변형 → 수급 없는 변형 순서로, 검증 통과 + 오늘 특징값이 다 있는 첫 변형을 사용.
  - 가짜 데이터 검증: 수급에 패턴을 심으면 KRF 방향 67.7% 로 학습·사용. 패턴이 없으면 사용 안 함.
  - **실데이터로는 약 2~3개월 쌓여야 학습·검증 가능** (학습 800건 + 검증 구간 필요). 그 전에는 예측 검증 화면에 쌓인 건수 표시.

### 2026-11-23 — AI 챗봇 (commit `e80f88a`)
- *(이후 규칙 기반으로 교체, 챗봇 페이지도 오른쪽 아래 위젯으로 변경 — 아래 2026-11-23 항목들 참고)*
- 사이드바 "AI 챗봇" (`pages/Chat.tsx`, `api/routes/chat.py`, `services/chatbot.py`)
  - Claude API (anthropic SDK 2.x, `claude-opus-5-5`, effort medium) + tool runner.
  - Claude 가 질문에 맞춰 앱 데이터를 직접 조회 (도구는 전부 읽기 전용):
    - 오늘의 매수·매도 후보: AI 추천 장기 + 단기 후보
    - 종목 상세: 확률·추천 매입가·목표가·손절가·근거·수급·뉴스
    - 내 투자종목 손익·전망 / 관심종목
    - 시장 지수·빅테크 시간외
    - 예측 적중률·모델 사용 상태
    - 옵션 만기·미국 지표 발표 일정
  - 지시(system):
    - 숫자는 도구 결과만 쓰고, 오류는 그대로 말함.
    - 추천에는 "언제·얼마에 사고(추천 매입가) 언제 팔지(목표가·손절가)" + 근거 + 주의(이벤트) + 실제 적중률을 붙임.
    - "확실한 종목" 요청에는 근거가 가장 겹치는 후보를 고르되, 확실하지 않은 이유를 함께 말함.
  - 현재 시각(한국시간)·장 상태는 마지막 질문 앞에 붙임 (system 은 고정해 프롬프트 캐시).
  - 안전 정책 거절 시 서버가 다른 모델로 이어서 처리 (`fallbacks="default"`).
  - 대화 기록은 브라우저(localStorage)에 최근 40개, 요청에는 최근 20개.
  - 예시 질문 버튼, 조회한 도구 표시, 진행 시간 표시, 간단한 마크다운(표·목록·굵게) 표시.
- `ANTHROPIC_API_KEY` 없으면 화면에 발급·설정 방법 안내. 키 오류·한도 초과·연결 실패는 원인 메시지로 표시 (다른 답으로 대체 안 함)
- **새 패키지 `anthropic`** → 직접 설치 PC 는 `pip install -r requirements.txt` 필요 (Docker·클라우드는 재빌드 때 자동)
- 가짜 Claude API 서버로 흐름 검증: 도구 3개 호출 → 결과 전달 → 답변, 요청에 모델·effort·fallbacks·캐시 설정 포함 확인. 실제 API 로는 미검증

### 2026-11-23 — 화면 속도 개선: 받은 데이터부터 바로 표시 (commit `d7bce43`)
- 증상: 대시보드를 비롯한 모든 화면이 데이터를 다 받을 때까지 "로딩 중"으로 오래 비어 있음
- **브라우저에 마지막 데이터 저장** (`frontend/src/api/persist.ts`, `api/queryClient.ts`)
  - 성공한 조회 결과를 localStorage(`rq-cache-v1`)에 저장 → 새로고침·재접속하면 마지막 데이터가 즉시(0.1초) 보이고 뒤에서 최신 값으로 바뀜
  - 24시간 지난 값은 버림. 검색 자동완성·챗봇 상태는 저장 안 함. 로그아웃·로그인·로그인 만료 때 지움
  - 화면 이동 후 돌아와도 받은 데이터를 버리지 않음 (React Query gcTime 24시간)
  - 각 화면에 "HH:MM:SS 기준 · 최신 데이터 받는 중…" 표시 (`components/common/FetchStatus.tsx`). 갱신 실패 시 이전 값을 보여주면서 "⚠ 갱신 실패 (이전 데이터)"
- **대시보드 구역별 조회**: `/api/market/overview/{kr_indices|global_indices|bigtech|etfs}` 를 따로 받아 먼저 온 구역부터 표시 (느린 Yahoo 가 KIS 국내 지수를 막지 않음). 아직 안 온 구역은 자리 표시
  - 빅테크·ETF 의 일봉과 시간외 5분봉을 동시에 받음 (전에는 순서대로)
  - 서버 시작 2초 뒤 대시보드 데이터를 미리 받아 둠
- **서버 캐시: 기존 값 먼저 주고 뒤에서 갱신** (`backend/app/core/swr.py` SWRCache)
  - 대시보드 구역(60초 / 6시간까지 이전 값), 경제 캘린더(1시간 / 하루), AI 추천 현재가 재계산(10초 / 30분), 스크리너(국내 8초 / 1분, 미국 30초 / 3분)
  - 응답에 `updated_at`·`refreshing`·`refresh_error`. 화면은 `refreshing` 이면 3초 뒤 다시 받아 새 값으로 교체
  - 값이 없거나 너무 오래됐으면 기다림, 그때 실패하면 오류 그대로(빈 값으로 숨기지 않음). 같은 조회가 동시에 와도 한 번만 실행
  - 관심종목·투자종목 분석: 같은 목록이면 15초 안 재요청·동시 요청은 한 번만 분석
  - AI 추천 기본 데이터(14분마다 갱신)가 바뀌어도 이전 결과를 지우지 않음 → 갱신 직후에도 대기 없음
- **KIS 호출 우선순위**: 자동 예측 기록·추천 미리 계산·백테스트·채점·수급 수집(백그라운드)은 화면 요청이 KIS 차례를 기다리는 동안 양보 (`kis_api.mark_background`)
  - 전에는 백그라운드가 종목 수십 개를 받는 동안 대시보드·관심종목 조회가 그 뒤에 줄 섰음. 테스트: 백그라운드 20건 대기 중 화면 요청 0.08초 (전에는 약 0.9초+)
- **예측 검증**: 장 끝난 예측 채점을 최대 2초만 기다리고 기존 기록을 먼저 보여줌 → 채점이 끝나면 화면이 5초마다 다시 받아 자동 반영
- 검증: 느린 가짜 서버(구역별 0.3/1.5/4/6초)로 브라우저 확인 — 국내 지수 0.3초, 해외 지수 1.5초에 먼저 표시, 새로고침 시 저장 데이터 0.12초 표시, 콘솔 오류 없음. 실제 KIS·Yahoo 로는 미검증 (이 환경에서 Yahoo 차단)

### 2026-11-23 — 챗봇을 규칙 기반으로 변경 (Claude API 제거) (commit `022bff2`)
- 요청: 챗봇 추가 후 느려진 것 같음 → AI 대신 규칙 기반으로, `.env` 의 챗봇 설정 제거
  - 참고: 코드상 예전 챗봇도 메시지를 보낼 때만 동작해 다른 화면을 느리게 하진 않았음 (AI 답변 자체가 10~60초 걸렸던 것)
- `services/chatbot.py` 전면 교체: 질문 키워드로 의도를 고르고 앱 데이터를 조회해 정해진 형식(표·목록)으로 답변. 외부 API·과금 없음
  - 의도 순서: 종목명·코드 정확 일치 → 투자종목 → 관심종목 → 매도·하락 → 매수·추천 → 적중률 → 이벤트 → 시장 → 종목명 일부(3글자 이상) → 사용법 안내
  - "국내/미국" 시장 필터, "3개" 개수. "매수 추천 … 언제 팔지" 는 매수 (매도·하락·위험 같은 강한 단어가 있을 때만 매도 쪽)
  - 매수 후보는 상승 확률 50% 초과만 (추천 매입가·목표가·손절가 표), 매도·주의 후보는 50% 미만만 (보유 중이면 "비중 축소 검토")
  - 종목 분석: 확률·신호·추천 매입가·목표가·손절가·RSI/PER/PBR·수급·근거·뉴스·경고. 투자종목: 총손익 + 종목별 의견(손절가 이하 표시)
  - 추천·종목 답변에 최근 90일 실제 적중률 한 줄 (55% 미만이면 "참고 수준")
  - 마지막 질문만 보고 답함 (앞 대화는 기억 안 함). "AI"·"ETF"·"CPI" 같은 단어는 종목코드로 보지 않음
  - 응답 속도: 데이터가 캐시돼 있으면 수 ms (가짜 데이터로 9가지 질문 확인)
- 제거: `anthropic` 패키지(requirements.txt), `ANTHROPIC_API_KEY`·`CHAT_MODEL`·`CHAT_EFFORT` 설정, 화면의 API 키 안내
- **`.env` 에 모르는 값이 있어도 서버가 시작되도록** (`config.py` `extra = "ignore"`) — 전에는 `.env` 에 안 쓰는 줄이 있으면 시작 실패(extra_forbidden)
- 메뉴 이름 "AI 챗봇" → "챗봇"

### 2026-11-23 — AI 추천·종목탐색 탭 순서 (commit `de570f5`)
- AI 추천: "단기/스윙 추천" 탭을 앞으로, 처음 열면 단기/스윙이 보임. 서버도 단기 후보를 먼저 미리 계산
- 종목탐색: 탭 순서 거래대금 → 급등 → 급하향 → 거래량 급증, 처음 열면 거래대금

### 2026-11-23 — 국내 종목 뉴스 근거: 해외 주요 매체만 반영, 네이버는 참고, 공시 비중 2배 (commit `09fd29e`)
- 요청: 네이버 뉴스는 믿음이 안 감 → 해외 매체 기사 사용, 네이버 뉴스는 확률 비중에서 빼고 보여주기만
- **해외 영문 기사 = 확률 반영** (`news.py`): Yahoo Finance 종목 뉴스(`005930.KS`) + Google 뉴스 영문 검색(영문 회사명, 최근 14일)
  - 신뢰 매체만 남김 (`TRUSTED_FOREIGN`): Reuters, Bloomberg, CNBC, FT, WSJ, Nikkei Asia, AP, Barron's, MarketWatch, The Economist, Investing.com, Yahoo Finance, Korea Herald, Korea JoongAng Daily, Korea Times, Yonhap(영문)
  - Simply Wall St.·MarketBeat 같은 자동 생성·홍보성 사이트 제외, 같은 기사 중복 제거, 30분 캐시
  - 영문 회사명은 Yahoo 에서 한 번 받아 `backend/app/data/kr_en_names.json` 에 저장 (KIS 종목마스터에 영문명 없음). 짧은 이름(KT 등)은 "Korea" 를 같이 검색
  - 대형주 위주라 **중소형주는 해외 기사가 거의 없음 → 뉴스 요인 미반영** (중립 7점으로 메우지 않고 점수 계산에서 빠짐, 근거에 "반영 안 함" 표시)
  - 영문 호재/악재 단어 추가 (falls short, misses, climb, record high 등)
- **국내 기사 = 보여주기만** (확률 0): 네이버 → 실패 시 Google 뉴스(한국어). 신뢰 언론사만 남김 (`TRUSTED_KR`: 연합뉴스, 연합인포맥스, 한국경제, 매일경제, 서울경제, 머니투데이, 이데일리, 뉴스1, 뉴시스, 조선비즈)
- **DART 공시 비중 2배**: 규칙 점수 10 → 20점, 학습 모델 사용 시 보정 ±3 → ±6%p. 악재 공시 키워드 추가 (감사의견 거절·부적정·한정, 투자경고·투자위험, 실질심사, 채무불이행, 파산, 계약해지, 손상차손 등), 호재 추가 (기술이전, 품목허가, 임상시험계획승인)
- 화면: 기사 앞에 `[Reuters]` 같은 매체 이름, 국내 기사는 "참고" 표시. 종목검색 뉴스 카드에 반영 기준 안내. 챗봇 종목 답변도 같은 표시
- 검증: 가짜 출처 데이터로 확인 — 대형주(해외 2건 반영, 찌라시·Simply Wall St.·MarketBeat 제외, 중복 제거), 중소형주(뉴스 미반영), 해외 조회 실패(미반영 + 사유 표시). 실제 Yahoo·Google·네이버로는 미검증 (이 환경에서 차단)

### 2026-11-23 — 매집·바닥 다지기 탐지, 테마별 주식, 챗봇 오른쪽 아래로 (commit `ad4bbf6`)
- **매집 탐지** (사이드바 "매집 탐지", `services/accumulation.py`)
  - 급등 전 흔한 "몇 주~몇 달 좁은 횡보 + 조용한 거래량 증가" 패턴을 국내 전 종목(일반 주식, 스팩 제외)에서 100점 점수로
  - 요소: 횡보 25(60일 가격 범위) · 변동성 축소 15(최근 20일 변동폭 / 그 전 40일) · OBV 매집 20(가격 제자리 + OBV 증가) · 거래량 꿈틀 15(5일 거래량 1.5배, 가격 ±8% 안) · 저점 상승 10 · 바닥권 15(200일 범위 아래 35%)
  - 제외: 최근 20일 이미 +25% 이상(출발함), 20일 평균 거래대금 1억 미만, 상장 120거래일 미만
  - **검증**: 과거 각 날짜에 그날까지 데이터로만 점수 → 이후 20거래일 안 +20% 도달률을 점수 구간별(50/60/70/80+)로 전체 평균과 비교("기준 대비 n배"). 1.3배 이상이면 의미 있는 신호, 1.1 미만이면 "믿지 마세요" 표시
  - 미래 데이터 미사용 테스트: 이후 가격을 바꿔도 그 날까지 점수 동일 확인. 가짜 데이터에서 바닥 다지기 패턴 65점 / 무작위 15점
  - KIS 일봉 200개 × 약 2,500종목 → 실서버 7~10분 (모의서버는 1시간+). 백그라운드 우선순위라 화면 조회는 안 느려짐
  - 실행: 국내 거래일 16:30 이후 하루 1회 (오늘 결과 있으면 건너뜀), 결과가 아예 없으면 서버 시작 2분 뒤, 화면의 "지금 다시 계산"
- **테마별 주식** (사이드바 "테마별 주식", `services/themes.py`)
  - 테마 분류는 네이버 증권 테마 화면(KIS 에 테마 없음)을 하루 1번 읽어 저장. 종목코드는 KIS 종목마스터로 확인한 것만 (영문 섞인 새 코드 0035S0 형식 지원)
  - 테마별 오늘 평균 등락률·상승/하락 수·+5% 이상 수·주도주는 KIS 멀티종목 시세로 직접 계산 (60초 캐시, 이전 값 먼저 표시)
  - 평균 등락률순(기본)/강세 종목 수순/이름순, 테마 이름 검색. 테마 클릭 → 종목별 현재가·등락률·거래량·매집 점수·다른 테마·관심 추가, 종목 클릭 → 시세·전망 카드
- **챗봇**: 사이드바 메뉴·페이지 삭제 → 모든 화면 오른쪽 아래 떠 있는 버튼 (`components/common/ChatWidget.tsx`, Esc 로 닫기). "매집 종목", "로봇 테마", "삼성전자 테마", "휴림로봇 매집 점수" 질문 추가
- 검증: 네이버 화면 형식의 예시 HTML·가짜 KIS 로 테마 파싱(&amp; 처리, 중복·없는 코드 제거)·스캔·API·챗봇 확인, 가짜 서버로 세 화면 브라우저 확인(콘솔 오류 없음). **실제 네이버·KIS 로는 미검증** (이 환경에서 차단)

### 2026-11-23 — 테마가 안 나오던 문제 수정: 네이버 모바일 API 로 변경 (commit `15eb1d7`)
- 증상: 테마별 주식 화면 "테마 목록을 읽지 못함 (0개)"
- 원인: 네이버가 예전 테마 화면(`finance.naver.com/sise/theme.naver`, `sise_group_detail.naver`)을 새 사이트 `stock.naver.com` 으로 옮김 → 302 이동 후 JavaScript 로 그리는 화면이라 HTML 에 테마 링크가 없음
- 수정: 같은 데이터를 JSON 으로 주는 네이버 증권 모바일 API 사용 (뉴스에 이미 쓰는 `m.stock.naver.com`)
  - 테마 목록 `/api/stocks/theme?page=N&pageSize=100` (전체 개수 totalCount 만큼 페이지), 테마 종목 `/api/stocks/theme/{번호}?page=N&pageSize=100`
  - 덤으로 **테마 설명**과 **종목별 편입 사유**(예: "로봇청소기 핵심부품 공급")를 받아 화면에 표시
- 테마를 받는 동안(서버 시작 1분 뒤부터 1~2분) 화면에 진행 상황 표시, 5초마다 자동 재확인
- **실제 네이버 API 로 확인**: 테마 265개 전부 성공(실패 0), 약 2분, 가장 큰 테마 146종목(페이지 넘김 정상), 로봇 테마 77종목(휴림로봇·코스모로보틱스·빅웨이브로보틱스 0035S0 등)

### 2026-11-23 — md 문서 정리 + "테스트 후 반영" 규칙 (commit `126d328`)
- **규칙 추가**: 수정 → 충분한 테스트 → push → PC·서버에서 pull. CLAUDE.md 에 "테스트 후 반영 규칙"(백엔드 compileall·import, 프론트 `npm run build`, 바꾼 기능 직접 실행, 실행 방법별 영향, 문서 경로 대조, PROGRESS `검증:` 줄·실서버 미검증 표시), PROGRESS.md 맨 위·docs 의 pull 안내에 요약
- **코드와 달랐던 부분 수정**
  - README.md: 가상환경 없이 `pip install` 하던 옛 절차 → 3가지 실행 방법(docs)으로 안내, TOTP 발급 `GET` → `POST /api/auth/setup-totp`, API 키 용도 갱신
  - CLAUDE.md: 없는 `LoadingSpinner` 삭제, `Layout.tsx` 위치(components/common), 빠진 컴포넌트(ChatWidget·Markdown·ThemeToggle·FetchStatus·NewsLink)·`/volume-surge`·`/test/kis`·`/api/health`·`TOTP_ISSUER`, lifespan 의 `flows.load_all`·`market.warm_overview`, setup-cloud.md 안내 추가
  - PROGRESS.md: 실행 방법 표에 클라우드 추가, 학습 모델 파일에 `KRF`·`KRF_base` 추가, 규칙 기반으로 바뀐 챗봇의 옛 이슈(Claude API 과금·10~60초 대기) 해결 처리, 옛 이력에 이후 변경(한국 → 일본 리전, stock_list.json 삭제, 챗봇 교체) 메모
  - setup-cloud.md: 백업 cron 은 서버 시간(기본 UTC) 04:00 = 한국 13:00 임을 명시
  - `start.bat`: 가상환경 없을 때 안내가 없는 "PROGRESS.md 최초 설치" → `docs\setup-local.md`
- 검증: md 에 적힌 파일 경로·md 링크·API 경로·컴포넌트·페이지를 스크립트로 실제 파일·라우트와 대조(없는 것 0), `python -m compileall -q app` · 가짜 KIS 값으로 `import app.main` 성공, `npm run build` 성공. 코드 동작 변경 없음 (start.bat 은 안내 문구만, CRLF 유지)

### 2026-11-23 — 경제 캘린더: FOMC 가 매일 나오던 문제 + 오류 문구의 API 키 노출 (commit `ce27a5f`)
- **증상**: 경제캘린더에 "FOMC 금리결정"이 주말 포함 매일 표시, 실제·예상·이전 값이 전부 "-"
- **원인 1 (FOMC 매일)**: FRED 의 "FOMC Press Release" 발표 일정에는 매일 갱신되는 기준금리 데이터(목표 범위)가 들어 있어 날마다 발표일로 나옴.
  실제로 2026-11 에는 FOMC 회의가 없음(10/27-28 다음 12/8-9). 같은 데이터를 쓰는 **예측 이벤트 경고에도 매일 "FOMC 발표" 경고가 붙고 있었음**
- **원인 2 ("-" 표시)**: 11-21 에 가짜 캘린더(손으로 적은 발표치)를 삭제한 뒤로, Finnhub 경제 캘린더(유료 기능일 가능성)가 실패하면
  FRED 발표 일정으로 대체 — FRED 는 날짜만 있고 발표치·예상치가 없음. 예전에 "잘 나오던" 발표치는 가짜 값이었음 (이번에 바꾸지 않음)
- 수정
  - FRED 목록에서 FOMC 제외 → **연준 공식 일정 페이지**(`federalreserve.gov/monetarypolicy/fomccalendars.htm`)에서 정례 회의 결정일(회의 마지막 날) 파싱, 하루 캐시.
    `*`(경제전망·점도표 동반)는 이름에 표시, 표결만 한 회의(notation vote)·임시 회의 제외, `Apr/May 30-1` 처럼 달이 걸치면 뒤쪽 달
  - 경제 캘린더(Finnhub 실패 시)·이벤트 경고 모두 FRED + FOMC 를 합침. 한쪽만 실패하면 나머지는 표시하고 실패 사유를 errors / `scheduler-status` 의 events.error 에 표시
  - **보안**: FRED·Finnhub(`market_data.py`)·외부 데이터 수집(`extras.py` 의 FRED·Finnhub·DART) 오류 문구가 `raise_for_status()` 그대로라 **API 키가 든 URL** 이 화면·로그·`extras_cache.json` 에 남던 문제 → 상태 코드만 표시
- 검증: **실제 연준 페이지**(이 환경에서 접속 허용 후)로 2021~2027 년 56개 회의 결정일 파싱 확인 (2023 `Jan/Feb 31-1` → 02-01, 2025-08-22 notation vote 제외, 2026 = 01-28·03-18·04-29·06-17·07-29·09-16·10-28·12-09).
  경계값(빈 HTML, 이상한 달 이름, 31일 없는 달, 해 넘김, unscheduled) 확인. 가짜 FRED 서버(FOMC Press Release 를 매일 반환 + CPI·고용·실업수당)로 캘린더·이벤트 경고 확인 — FOMC 는 12-09 하루만,
  미국 12-09 "FOMC 발표일", 국내 12-10 "간밤 FOMC 반영", 11-24 경고 없음. FRED 실패·둘 다 실패(→ 오류, 이벤트는 이전 일정 유지), 오류 문구에 키 없음 확인.
  서버를 띄워 `/api/market/calendar` 응답과 `/calendar` 화면(Playwright, 콘솔 오류 없음), `scheduler-status` events 확인. compileall·import·`npm run build` 성공.
  **실제 FRED·Finnhub 키로는 실서버 미검증** (이 환경에 키 없음)

### 2026-11-23 — 경제 캘린더 "FRED:" 뒤가 빈 오류 + Finnhub 403 안내 (commit `45845a3`)
- **증상** (사용자 PC): `⚠ Finnhub: HTTP 403 … / FRED:` — FRED 오류 이유가 비어 있고 FRED 일정(CPI 등)이 빠짐, 출처가 연준 FOMC 일정만
- **원인**: httpx 의 시간 초과·연결 오류(ReadTimeout·ConnectError 등)는 `str(e)` 가 빈 문자열 → 이유 없이 "FRED:" 만 보임. FRED 전체 발표 일정 조회가 15초를 넘긴 것으로 보임(키 문제면 HTTP 400 문구가 나옴).
  게다가 캘린더는 1시간 캐시라 한 번 실패하면 1시간 동안 그대로 보였음
- 수정
  - `market_data.err_text()`: 시간 초과 → "응답 시간 초과 (ReadTimeout)", 연결 오류 → "연결 실패 (…)" (캘린더·이벤트 경고). `SWRCache` 의 실패 사유도 빈 문자열이면 오류 종류 표시
  - FRED 발표 일정: 대기 15 → 30초, 시간 초과·연결 끊김이면 2초 뒤 한 번 재시도
  - 일부 출처가 일시적으로 실패한 캘린더 결과(`retry: true`)는 **5분** 뒤 다시 받음 (`SWRCache(fresh_for=…)`, 정상은 1시간 그대로)
  - 이벤트 경고 일정: 일시적 실패가 있으면 6시간이 아니라 **10분** 뒤 재시도 (`events.due()`)
  - Finnhub 403 문구: "유료 기능일 수 있음" → "경제 캘린더는 유료 기능이라 무료 키로는 못 받음 (키는 정상, 애널리스트·실적 요인은 무료로 동작)", 401 은 "키가 맞지 않음"으로 구분
- 검증: 가짜 서버로 FRED 시간 초과 1번 → 재시도로 성공(호출 2회, CPI 표시), 2번 → "FRED: 응답 시간 초과 (ReadTimeout)" + retry, 오류 문구에 키 없음, Finnhub 403/401 문구,
  캘린더 캐시(retry 결과는 300초 뒤 백그라운드 갱신, 정상 3600초), 이벤트 재시도 시점(실패 직후 X, 10분 뒤 O, 성공 후 X, 첫 실행 O) 확인.
  서버를 띄워 `/calendar` 화면 확인(콘솔 오류 없음), compileall·import·`npm run build` 성공. **실제 FRED 응답 시간은 실서버 미검증** — pull 후에도 계속 시간 초과면 PC 에서 FRED 접속 확인 필요

### 2026-11-23 — 경제 캘린더: 예상치 삭제, FRED 실제 발표값·이전 대비 변화·해설 추가 (commit `60c682e`)
- 요청: 예상치(컨센서스)는 무료 공식 출처가 없으니 빼고, 올랐나 내렸나와 그로 인해 생길 현상 설명을 볼 수 있게
  - Investing.com 등 수집은 하지 않음 (Cloudflare 봇 차단·이용약관상 자동 수집 금지·형식 변경 위험)
- 백엔드: 캘린더 코드를 `market_data.py` → 새 `services/econ_calendar.py` 로 분리. **Finnhub 경제 캘린더 호출 삭제**(유료라 403, Finnhub 키는 애널리스트·실적만)
  - 실제·이전 값: FRED 시리즈를 **발표 당일 기준(vintage)** 으로 조회 → 그날 시장이 본 숫자(나중 수정치 아님). 전날 기준보다 새 값이 생겼을 때만 '발표됨',
    같은 기간 값이 바뀌었으면 '수정 발표'(GDP 잠정·확정치) — 이전 = 직전 발표치. FRED 에 아직 없으면 "아직 반영 전" 사유 표시
  - 지표: CPI 전년비(CPIAUCSL) · 근원 PCE 전년비(PCEPILFE) · PPI 전년비(PPIFIS) · 비농업 고용 증감(PAYEMS) · GDP 성장률(A191RL1Q225SBEA) ·
    소매판매 전월비(RSAFS) · JOLTS 구인(JTSJOL) · 실업수당 청구(ICSA) · 미시간대 심리(UMCSENT) · FOMC 목표 범위(DFEDTARL·DFEDTARU 결정 전날 vs 다음 날)
  - 변화: 화면 숫자 기준 오름/내림/같음 + 지표별 문구(상승률 확대·증가폭 축소·인하/동결 등). 해설: 지표 설명 + 이번 방향의 일반적인 시장 영향,
    앞으로 일정은 오르면/내리면(FOMC 는 인상/인하/동결) 시나리오. 응답 `disclaimer`: 일반적 경향이며 실제 반응은 예상 대비 결과 등에 따라 다름
  - 발표값 조회 실패는 그 행에 사유 + 상단 ⚠, 결과는 5분 뒤 다시 받음. 발표된 값은 캐시해서 다시 조회 안 함
- 화면(`Calendar.tsx`): 예상·결과 칸 삭제 → 최근 발표(최신순): 날짜·이벤트(기준 기간·지표)·실제·이전·변화 / 향후 일정: 날짜·이벤트·발표 내용.
  행을 누르면 해설. 오늘 날짜는 브라우저 현지 날짜(이전엔 UTC 라 한국 오전엔 어제), 오늘 발표돼 값이 있으면 '최근 발표'로
- 검증: 발표일 기준 조회를 흉내 낸 가짜 FRED 서버(공개일이 있는 시리즈)로 CPI 전년비 313/301→4.0% vs 312/300→4.0% '같음', 소매판매 +0.0%(−0.0 안 나옴) vs +0.5%,
  실업수당 22.8→22.1→23.5만 건, GDP 같은 분기 2.8→3.1 '수정 발표', PPI 미공개 → "아직 반영 전"(캐시 안 하고 다음에 재조회), FOMC 10-28 3.75~4.00→3.50~3.75 '▼0.25%p 인하'·
  변화 없음 '동결'·다음 날 값 없음 → 반영 전, 발표된 값 재조회 안 함, 소매판매 시간 초과 → 그 행 사유 + errors + retry, 키 없음 → FOMC 일정만 확인.
  서버를 띄워(가짜 FRED) `/calendar` 화이트·다크 화면 확인(해설 펼침, 콘솔 오류 없음, 폭 390px 가로 스크롤 없음), compileall·import·`npm run build` 성공.
  **실제 FRED 발표일 기준(vintage) 조회는 실서버 미검증** (이 환경에 키 없음)

### 2026-11-23 — 테마 목록 중복 수정 + 장기투자 추천을 보유 기간 분석으로 (commit `8c88961`)
- **테마 중복** (사용자 화면: 시스템반도체가 여러 번, 같은 숫자): 네이버 테마 목록 API 가 '오늘 등락률 순'·페이지당 최대 100개(300 요청은 빈 응답, 정렬 옵션 없음).
  장중에 1·2·3페이지를 받는 사이 순서가 바뀌어 같은 테마가 두 페이지에 나오고 다른 테마는 빠졌음 (테마 안 종목 목록도 같은 문제)
  - 수정: 테마 번호·종목코드로 중복 제거 + 고유 개수가 전체 개수가 될 때까지 최대 8번 다시 훑음 (`themes._paged`).
    예전 버전이 저장한 중복 파일은 불러올 때 정리하고(`_dedupe`) 빠진 테마가 있을 수 있어 서버 시작 1분 뒤 바로 다시 받음
- **장기투자 추천**: 내일 상승 확률·추천 매입가·단기 근거 대신 **과거 월봉 보유 기간 분석** (`services/longterm.py`, `/api/stocks/recommendations/longterm/horizon`)
  - 데이터: 국내 KIS 월봉(`get_kr_monthly`, 수정주가, 100개씩 나눠 최대 30년) / 미국·지수 yfinance 월봉 전체 기간(배당 포함 수정주가)
  - 모든 달을 '산 달'로 놓고 1·3·5·10년 보유 시: 이익 확률, 나쁜 경우(하위 10%)·보통(중간)·좋은 경우(상위 10%) 수익률 + 지금 가격 기준 예상 가격
  - 보유 기간 제안: 그 기간 '이상' 모든 보유 기간에서 90% 이상 이익 / 손실 구간 0 이 된 가장 짧은 기간 (긴 기간에 다시 손실이 있으면 인정 안 함)
  - 최대 낙폭(언제→언제, 회복까지 걸린 기간 또는 미회복)·지금 고점 대비·연평균·연 변동성, 비교 지수(코스피 / 나스닥 종합 / S&P 500)보다 나았던 비율
  - 장기 점수 = 5년 이익 확률 40 + 지수 대비 30 + 낙폭 20 + 데이터 길이 10 (3년 미만이면 점수 없음). 정렬: 장기 점수·5년 이익 확률·5년 보통 수익률·낙폭 작은 순
  - 화면 위 비교 지수 카드(국내 = 코스피, 미국·ETF = 나스닥·S&P 500), 생존 편향·배당 기준 안내
- 검증: **실제 네이버 API** 로 테마 갱신 → 265개 전부 고유(중복 0), 시스템반도체 1개(59종목), 가장 큰 테마 146종목. 매 요청마다 순서를 섞는 가짜 네이버(최악)로 20번 → 빠짐 0.
  예전 중복 파일 정리·다시 받기 표시 확인. 장기 통계: 매달 1% 상승 20년 → 연평균 12.7%·1년 구간 229개·손실 0, 10년 상승 후 −80% 폭락 → 낙폭·고점·저점·4.6년 회복 정확,
  1년 미만·3년 미만(점수 없음)·0/음수/NaN/inf·빈 목록, 지수 대비 100%, 긴 기간에 다시 손실 나는 경우의 제안 기간 확인, JSON 에 NaN 없음.
  KIS 월봉 페이지 나누기(가짜 `_get`, 2001년 상장 → 309개월 전부, 5회 호출)·yfinance 월봉 모양(MultiIndex, 일부 종목 없음, 1종목) 파싱 확인.
  가짜 KIS·Yahoo 로 서버를 띄워 장기 탭(미국·국내, 정렬, 모바일 390px 가로 스크롤 없음)·테마 화면(실제 네이버 테마 파일) 브라우저 확인, 콘솔 오류 없음.
  compileall·import·`npm run build` 성공. **실제 KIS 월봉·Yahoo 월봉 응답은 실서버 미검증** (이 환경에서 차단)

### 2026-11-23 — 미국 주간거래 가격 · 관심종목 화면 개편 · 경제 캘린더 옛 데이터 · 종목검색 통합 · 테스트 체계 (commit `322a7fb`)
- **브로드컴 304.41 vs 토스 320.53**: 304.41 은 11/20(금) 정규장 종가(그날 −12.19%)로 맞는 값, 320.53 은 토스가 보여주는 **미국 주간거래**(한국 낮, 블루오션) 가격.
  Yahoo 에는 주간거래가 없어서 앱은 금요일 종가만 보였음
  - KIS 해외 현재가(HHDFS00000300)에 EXCD 를 주간거래 코드(나스닥 BAQ · 뉴욕 BAY · 아멕스 BAA)로 조회 (`kis_api.get_us_daytime_price`, `services/us_daytime.py`)
  - 주간거래 시간(`market_calendar.us_daytime_session`): 한국 날짜가 미국 거래일 + 한국 10:00 ~ 미국 04:00 ET(겨울 18:00 · 서머타임 17:00). 그 밖엔 조회 안 함
  - 등락률은 KIS 기준가(직전 정규장 종가) 대비로 직접 계산, 체결 없으면 표시 안 함, 종목별 30초 캐시, 실패는 그 종목에 "주간거래 ⚠ 조회 실패"(사유는 마우스)
  - 관심종목·투자종목·AI 추천·종목탐색 상세·대시보드 빅테크/ETF 에 `주간거래 $320.53 +5.30% 17:31` 배지, 사이드바 "주간거래 중 (~18:00)". **예측 확률 계산엔 안 씀**(거래량 적은 시장)
- **관심종목 화면**: 국내/미국 탭(개수 표시) · 3열 카드(넓은 화면 3 → 2 → 휴대폰 1열) · 카드마다 추천 매입가/목표가(익절)/손절가 3칸 · 상승 확률 막대 ·
  근거는 2줄 요약(펼치면 전체) · 메모·목표 매수가는 카드 안에서 수정. **표 보기**(한 화면에 많이: 현재가·등락·5일·20일·전망·매입가·목표가·손절가·목표 매수가·메모),
  요약 줄(상승/하락 수·평균 등락·상승 확률 55% 이상·목표 매수가 도달), 정렬에 '매입가 근접순' 추가, 탭·보기·정렬 기억, 1분마다 자동 갱신, 삭제는 확인 후
- **경제 캘린더 값이 '-' 로만 보이던 문제**: 업데이트 전 백엔드가 준 예전 형식(발표값·해설 없음) 데이터가 브라우저 저장본으로 남아 있었고,
  캘린더는 staleTime 1시간이라 새로 받지 않았음 (사용자 화면: 실제·이전 '-', 행을 펼치면 빈칸 = 정확히 예전 형식)
  - 수정: 저장본을 불러오면 모두 '오래됨' 표시 → 화면을 열면 항상 한 번 새로 받음 (`api/persist.ts`). 백엔드가 아직 예전 버전이면 캘린더에 "백엔드를 다시 시작하세요" 안내
  - 캘린더 화면 순서: 발표 결과·일정을 맨 위로, 지표 가이드는 접기
- **종목검색 메뉴 삭제** → 종목탐색 상세 카드로 통합 (주간거래·매입가/목표가/손절가·RSI/MACD/이평/볼린저·최근 뉴스). 예전 주소 `/search` 는 종목탐색으로 이동
- **휴대폰(폭 860px 이하)**: 사이드바가 화면을 차지해 본문이 찌그러지던 문제 → ☰ 버튼으로 여닫는 메뉴, 본문 여백 16px
- 공통 부품: `PriceLevels`(매입가·목표가·손절가 — AI 추천도 이걸로), `DaytimePrice`
- **테스트 체계** (CLAUDE.md "테스트 후 반영 규칙" 개정): `bash scripts/check.sh` 한 번으로 백엔드 import → pytest → 프론트 빌드 → 화면 테스트.
  `backend/tests/`(pytest, 외부 API 가짜·메모리 DB): 주간거래(시간 경계·서머타임·추수감사절·변환·캐시·실패 미캐시·원본 미변경) · API 응답 형식(관심종목·투자종목·
  종목 조회·대시보드·AI 추천·장 상태) · 경제 캘린더(발표일 기준 값·반영 전·수정 발표·오류 시 retry·FOMC 파싱) · 기존 핵심(지표 NaN 없음·확률 범위·가격대 순서·미래 데이터 미사용·SWR).
  `frontend/e2e/smoke.mjs`(Playwright, 가짜 API): 화면 19개 시나리오
- 검증: pytest **48개 통과**, 화면 테스트 **19/19 통과**(관심종목 3열·탭·표·설정 기억·메모 저장 PUT·정렬·삭제 확인·390px 1열/가로 스크롤 없음(밝은·어두운)·빈 목록·502 오류 문구,
  사이드바/☰ 메뉴, `/search` → 종목탐색, 상세 카드, 대시보드·AI 추천·투자종목 주간거래, 캘린더 값·해설·예전 형식 안내, 모든 화면 밝은/어두운 모드 오류 없음).
  캘린더 수정은 **고치기 전 코드로 돌리면 화면 테스트가 실패**(1시간 이내 저장된 예전 형식이 그대로 보임)하는 것까지 확인.
  실제 서버(`app.main`, KIS 주소만 가짜 KIS 서버) + 빌드된 화면으로 로그인 → 관심종목 추가(AVGO·NVDA·KO·005930) → 분석: KIS 로 BAQ(AVGO·NVDA)·BAY(KO) 요청 확인,
  AVGO `주간거래 $320.53 +5.30%`, NVDA 는 KIS 오류 문구 그대로 "주간거래 ⚠ 조회 실패", 정규장 시세 실패(이 환경은 Yahoo 차단)여도 주간거래 가격은 표시, 콘솔 오류 없음.
  compileall·import·`npm run build` 성공. **실제 KIS 주간거래 응답(필드 last·base, 모의서버 지원 여부)은 실서버 미검증**

### 2026-11-23 — 다른 추천 사이트 방식 반영: 퀀트 점수 · 시장 상태 · 종목별 예측 적중 기록 (commit `f12a0ea`)
- 조사: Zacks Rank(실적 추정 변경) · Seeking Alpha Quant Rating(가치·성장·수익성·모멘텀·추정 변경 요인 등급, 같은 업종 안 상대 비교) ·
  TipRanks Smart Score(1~10, 애널리스트·내부자 등 + 애널리스트별 적중률 공개) · Danelfin(머신러닝, 약 3개월 시장 대비 확률) · IBD(RS Rating 백분위, 시장 방향 'M', 분산일).
  공통점: ① 내일 방향이 아니라 1~3개월 **시장 대비** 성과를 봄 ② 절대값이 아니라 **전 종목 안 순위** ③ 여러 요인을 합치되 **과거에 맞은 만큼** 비중 ④ 시장 전체 추세가 나쁘면 신호를 덜 믿음 ⑤ 적중 기록 공개.
  이 앱의 '내일 상승 확률'(학습 모델·백테스트·결합)은 이미 있어서, 빠져 있던 ①~⑤를 추가 (유료 데이터·크롤링 없이 KIS·Yahoo 무료 데이터만)
- **퀀트 점수** (`services/quant.py`, 화면 '퀀트 점수', `/api/quant`): 국내 전 종목, 요인 5개(모멘텀 RS · 추세 · 거래량 매집 · 안정성 · 고점 근접)를 같은 날 전 종목 백분위로 →
  요인 비중은 순위 상관(IC)으로 자동 결정 → 종합 점수 1~10·등급 A+~F. **검증**: 앞쪽 날짜로 비중을 정하고(20거래일 겹침 제거) 뒤쪽 날짜에서 점수 구간별
  '20거래일 뒤 그날 전 종목 중간값을 이긴 비율'(기준 50%) · 상하위 차이 · IC 표시. 종목별로 '과거 같은 구간 종목이 시장을 이긴 비율' 표시.
  매집 탐지 스캔이 받는 일봉으로 같이 계산 (KIS 추가 호출 없음), 퀀트 계산이 실패해도 매집 결과는 저장. 관심종목(국내)·AI 추천·종목탐색 상세에 '퀀트 A · 9/10' 배지
- **시장 상태** (`services/market_regime.py`, 대시보드 맨 위, `/api/market/regime`): 코스피·코스닥·S&P500·나스닥 — 50/200일선, 200일선 기울기, 분산일(최근 25일 −0.2%↓ + 거래량↑) →
  상승 추세/상승 압박/하락 추세 + 5년간 상태별 20거래일 뒤 지수 오른 비율. 관심종목·AI 추천·퀀트 화면 위에 그 시장이 상승 추세가 아니면 경고 줄
- **종목별 예측 적중 기록** (`prediction_log.tracks`): 최근 90일 백테스트+실제 예측(같은 날은 실제 우선)의 방향 적중·확신 예측(55%↑/45%↓) 적중 → '예측 적중 61% (23건)',
  10건 미만은 흐리게, 10건 이상인데 45% 미만이면 빨간색 (이 종목은 예측을 덜 믿기)
- 검증: pytest **62개 통과**(+14: 퀀트 8 — 요인 미래 데이터 미사용·추세 지속 가짜 시장에서 모멘텀 IC 양수·상위 구간 > 55% > 하위·**무작위 시장에선 모든 구간 35~65%(꾸미지 않음)**·
  거래대금 부족 제외·빈 입력·2,500종목 4.5초·스캔→파일→API·퀀트 실패해도 매집 저장 / 시장 상태 4 — 상승·하락·압박·분산일로 압박 전환·거래량 없으면 분산일 없음·
  미래 데이터 미사용·검증 표 개수·지수 일부 실패·전부 실패 오류 / 적중 기록 2), 화면 테스트 **23/23 통과**(+4: 퀀트 화면 검증 표·필터·상세 카드, 퀀트 없음 문구,
  대시보드 시장 상태·과거 성과 펼침, 관심종목 퀀트·적중 배지와 시장 경고(국내만)). 실제 서버(`app.main`, KIS 일봉만 가짜 80종목)로 전 종목 스캔 → `/api/quant`
  (요인 비중·뒤쪽 기간 검증·상위 종목) → 관심종목 분석·종목 조회에 퀀트 등급 확인, `/api/market/regime` 은 Yahoo 차단 환경에서 502 + 원인 문구 확인.
  **실데이터(KIS 전 종목 일봉·Yahoo 지수 5년) 결과는 실서버 미검증**

### 2026-11-25 — 전체 점검: 모든 API·버튼 실행해 보고 발견한 문제 수정 (commit `88ad129`)
- 방법: 실제 서버(`app.main`)에 **가짜 KIS 서버(국내·해외 시세·일봉·월봉·순위·수급·지수 전부)** + **가짜 yfinance**(Yahoo 가 이 환경에서 차단)를 붙여
  ① API 89개 호출(정상·잘못된 입력·없는 항목) ② 백그라운드 작업(백테스트 3,840건·테마 124개·전 종목 스캔) 완주 ③ 빌드된 화면으로 로그인 후 10개 화면의 보이는 버튼을 전부 눌러 보는 크롤러 + 챗봇·테마 토글·로그아웃.
  500 오류·화면 깨짐은 없었고, 아래 문제를 찾아 고침
- **로그인 비밀번호가 틀리면 화면이 새로고침돼서 아무 문구도 안 보였음** (전역 401 처리가 로그인 요청에도 /login 새로고침) → 로그인 요청은 제외, 오류 문구 한국어
- **버튼이 실패해도 아무 표시가 없던 곳**: 매집 '지금 다시 계산'·백테스트 실행·테마 다시 받기·투자종목 수정/삭제·관심종목 삭제 등 → 전역 알림(Toast)으로 사유 표시
- **입력 검증 오류가 '[object Object]'로 보임**(422 목록) → 문장으로 (`errMsg`)
- **투자종목**: 수량 0·음수, 평단가 음수가 저장됐음 → 서버에서 거부(422) + 화면 버튼 비활성. 삭제는 확인 후에만, 추가 창 Esc 로 닫기(창이 남아 다른 버튼을 막았음)
- **관심종목·투자종목**: market 값 검증(KR/US), 중복 판단을 '코드'만이 아니라 '시장+코드'로, 없는 항목 삭제 → 404 (예전엔 '삭제됨')
- **종목 조회**: 종목마스터에 없는 코드(주소 직접 입력)도 시세를 받고 예측 기록까지 남겼음 → 404
- **2단계 인증**: 문서는 켜라고 하는데 **켜는 화면이 없었음** → 오른쪽 위 '보안' 버튼(QR → 6자리 확인, 끄기). 이미 켜진 상태에서 다시 등록하면 비밀값이 바뀌어
  **휴대폰 앱 코드가 안 맞아 로그인 불가**가 되던 문제 → 켜져 있으면 거부. `/api/auth/disable-totp`(현재 코드 필요), 휴대폰 분실 시 `create_admin.py --reset-totp <아이디>`
  (계정·관심종목 그대로). `create_admin.py` 같은 아이디 재실행 시 오류 대신 안내
- **시장 상태**: 국내 장중엔 오늘 종가가 아직 없는데 '최신 아님' 경고가 떴음 → 종가가 나온 마지막 거래일 기준 (`last_closed_session`)
- **예측 검증 기록**: 한 번에 200건 → 50건 (화면 길이 1만 px 넘던 것)
- 검증: pytest **77개 통과**(+15: 입력 검증 6·수정/삭제·관심종목 검증·없는 종목 404·로그인 문구·**2단계 인증 전체 흐름**(등록→틀린 코드→켜기→재등록 거부→로그인 코드 요구→끄기)·장중/마감 후/주말/추수감사절 기준일 4),
  화면 테스트 **29/29 통과**(+6: 로그인 실패 문구·새로고침 없음(**고치기 전 코드로 돌리면 실패** 확인), 로그인 성공, 실패 알림, 투자종목 삭제 확인·Esc·수량 0,
  422 문장, 2단계 인증 켜기/끄기·6자리 아니면 확인 불가). 실제 서버(가짜 KIS)로 비밀번호 틀림·수량 0·market XX·없는 항목 삭제·없는 종목 조회·
  2단계 인증 등록→켜기→재등록 거부→코드 요구→끄기, 장중 시장 상태 경고 없음 확인. `create_admin.py` 생성·중복·`--reset-totp`·없는 아이디 확인.
  **실제 KIS·Yahoo 응답은 실서버 미검증** (이번 수정은 외부 API 형식과 무관)

### 2026-11-25 — 회원가입(이메일 인증) · 비밀번호 찾기/변경 · 마이페이지 (commit `99ee384`)
- 계기: Chrome '비밀번호 유출' 경고(Chrome 비밀번호 진단 — 그 비밀번호가 다른 곳 유출 목록에 있다는 뜻, 이 앱 유출 아님)인데 앱에 비밀번호 변경 기능이 없었음
- **회원가입** (사용자 결정: 이메일 인증만 하면 누구나 — `SIGNUP_OPEN=false` 로 막을 수 있음): 로그인 화면 '회원가입' → 이메일 6자리 코드 → 아이디(영문·숫자·밑줄 3~20자)·
  비밀번호(8자↑, 영문+숫자, 아이디 미포함, 입력하는 동안 바로 안내) → 가입하면 바로 로그인. 아이디 대신 인증된 이메일로도 로그인 가능
- **비밀번호 찾기**: 인증된 이메일로 코드 → 새 비밀번호. 가입 여부가 드러나지 않게 항상 같은 답. 이메일 없는 예전 계정은 `create_admin.py --reset-password`
- **마이페이지** (오른쪽 위 내 아이디, 이메일 미인증이면 노란 점): 내 정보 · 이메일 인증/변경 · 비밀번호 변경 · 2단계 인증('보안' 창에서 옮김) · 회원 탈퇴(아이디 입력+비밀번호+2단계 코드, 관심·투자종목 같이 삭제)
- 보안: 코드는 HMAC 해시만 저장, 10분 유효, 5번 틀리면 무효, 같은 메일 60초 재발송 제한, IP 당 1시간 10통. 메일 발송이 실패하면 코드를 지워 바로 재시도 가능.
  **비밀번호를 바꾸면(변경·찾기·서버 명령) 다른 기기의 로그인 토큰은 무효** — 토큰에 비밀번호 버전(pwv). (처음엔 발급 시각 비교였는데 같은 1초 안에 발급된 토큰이 살아남는 문제를
  테스트가 잡아서 버전 방식으로 바꿈). 지금 화면은 새 토큰으로 계속
- 메일: `services/mailer.py`(SMTP, 465=SSL / 그 외 STARTTLS), 네이버 설정 방법 `docs/setup-cloud.md` 7-1. 설정이 없으면 회원가입·비밀번호 찾기만 503 + 안내 (보낸 척 안 함)
- 기타: 상단 바 사용자 이름이 원래 한 번도 안 보이던 문제(`setUser` 를 아무도 안 부름) → `/auth/me` 로 표시. 탈퇴 직후 로그인 화면 안내 문구가 사라지던 문제(로그아웃이 먼저 리디렉트) 수정
- 검증: pytest **97개 통과**(+20 `test_account.py`: 가입 흐름·아이디/비밀번호 규칙 7가지·코드 5번 틀림·다른 메일 코드·만료·메일 설정 없음/가입 닫힘·
  60초 재발송·IP 한도·메일 실패 후 바로 재시도·비밀번호 찾기(없는 메일 같은 답·재사용 불가·예전 토큰 무효)·이메일 없는 계정은 메일 안 감·비밀번호 변경(다른 기기 끊김)·
  예전 계정 이메일 등록·다른 계정 이메일 가로채기 불가·탈퇴(2단계 코드·관심종목 삭제·같은 메일 재가입)·**가짜 SMTP 서버로 실제 발송**(로그인·받는 사람·보내는 주소)·
  틀린 SMTP 비밀번호 문구에 비밀번호 없음·닫힌 포트), 화면 테스트 **36/36 통과**(+7: 로그인 화면 링크, 가입(형식·60초·규칙 안내·확인 불일치·요청 내용·토큰 저장),
  메일 설정 없음 안내, 서버 오류 문구, 비밀번호 찾기→로그인 안내, 마이페이지(이메일 인증·같은 비밀번호 거부·새 토큰), 탈퇴(아이디 불일치·확인 취소·로그인 화면 안내)).
  실제 서버(`app.main`, **업데이트 전 DB 그대로 → 새 컬럼 자동 추가 확인**) + 가짜 SMTP 서버(smtplib 실제 발송, 한글 제목 인코딩)로 가입→이메일 로그인→비밀번호 찾기→
  예전 토큰 401→변경(새 토큰 200·이전 토큰 401)→예전 계정 이메일 인증→탈퇴→로그인 불가, `create_admin.py --reset-password`(짧은 비밀번호 거부·예전 토큰 무효),
  빌드된 화면으로 가입(메일 코드)→마이페이지→로그아웃→이메일로 로그인, 콘솔 오류 없음. **네이버 SMTP 실제 발송은 실서버 미검증**

### 2026-11-25 — 마이페이지 확장 · 휴대폰(문자) 본인인증 · 닉네임 · 로그인 기록 (commit `3be9a6d`)
- **본인인증 = 이메일 또는 휴대폰 중 하나** (사용자 요청): 회원가입·비밀번호 찾기 화면에 [이메일로 인증] [휴대폰으로 인증] 탭. 휴대폰은 문자 6자리 코드
  (번호 입력하면 010-1234-5678 로 자동 하이픈). 서버에 발송 설정이 없는 쪽 탭은 '준비 안 됨'으로 못 누름. 인증한 휴대폰 번호로도 로그인 가능
- 문자 발송: `services/sms.py` — 솔라피(SOLAPI) API (`POST api.solapi.com/messages/v4/send-many/detail`, HMAC-SHA256 서명 — 공식 Python SDK solapi 5.0.3 소스로 형식 확인).
  설정 `SMS_API_KEY`·`SMS_API_SECRET`·`SMS_FROM`(솔라피에 등록한 발신번호), 요금 폭탄 방지 `SMS_DAILY_LIMIT`(기본 하루 50건) + 기존 IP 당 1시간 10건·번호당 60초.
  설정이 없으면 503 + 안내 (보낸 척 안 함), 오류 문구에 키 안 넣음. 코드 저장·검사는 이메일과 같은 `email_codes`(받는 곳 = 이메일 또는 휴대폰 번호)
- **마이페이지 다시 구성** (네이버·토스 등 계정 관리 화면 참고): 맨 위 프로필 카드(닉네임·아이디·이메일/휴대폰/2단계 인증 표시·가입일, 본인인증 안 했으면 경고) + 바로가기 버튼 +
  닉네임 · 본인인증(이메일·휴대폰 각각 등록/변경/삭제 — 삭제는 비밀번호 확인, **하나는 남아야** 함) · 비밀번호 변경 · 2단계 인증 ·
  **로그인 기기·최근 활동**(로그인·실패·비밀번호 변경·연락처 변경 등 최근 30건, 시각·IP·기기(Chrome · Windows 처럼), 최근 7일 로그인 실패 경고, **모든 기기에서 로그아웃**) ·
  **내 데이터 내려받기**(관심종목·투자종목 CSV, 엑셀 한글용 BOM) · 회원 탈퇴. 필요 없던 '비밀번호 변경: 바꾼 적 없음' 줄은 뺌
- **닉네임**: 한글·영문·숫자·밑줄 2~12자, 다른 사람의 닉네임·아이디와 같으면 안 됨(대소문자 무시, 사칭 방지 — 가입할 때 남의 닉네임과 같은 아이디도 막음), admin·관리자 등 금지.
  가입할 때 선택 입력, 오른쪽 위 이름이 닉네임(없으면 아이디). 상단 노란 점 = 이메일·휴대폰 둘 다 미인증
- 모든 기기 로그아웃: 사용자 `session_epoch` + 토큰 `sev` (비밀번호 버전 `pwv` 와 같은 방식). 지금 화면은 새 토큰으로 계속
- 새 API: `/auth/phone/send-code`·`/phone/verify`, `PUT /auth/profile`, `/auth/contact/remove`, `/auth/logout-all`, `GET /auth/activity`. `/signup/send-code`·`/register`·
  `/password/forgot`·`/password/reset` 은 `email` 또는 `phone` 중 하나. `/options` 에 `sms_configured`, `/me` 에 nickname·display_name·phone·phone_verified·verified
- DB: users 에 nickname·phone·phone_verified·session_epoch, 새 테이블 account_events (사용자당 최근 100개) — 기존 DB 는 시작할 때 자동 추가
- 검증: pytest **121개 통과**(+24 `test_account.py`: 휴대폰 번호 정규화 6·잘못된 번호 6, 휴대폰 가입→번호로 로그인(하이픈 유무)→같은 번호 재가입 불가→비밀번호 찾기(없는 번호 같은 답),
  이메일·휴대폰 둘 다/둘 다 없음 거부, 문자 설정 없음 503(메일은 정상), 문자 실패 후 바로 재시도, 마이페이지 휴대폰 등록·남의 번호 거부·마지막 수단 삭제 거부·비밀번호 확인,
  닉네임 규칙·중복·남의 아이디·가입 시 아이디 충돌·지우기, 모든 기기 로그아웃(이전 토큰 401·새 로그인 정상), 활동 기록(순서·IP·기기·실패 수·없는 아이디 기록 안 함·100개 유지·탈퇴 시 삭제),
  **가짜 솔라피 서버로 실제 HTTP 발송**(경로·본문·서명 검증·단문 90바이트 이내)·인증 실패 문구에 키 없음·접수 실패·400·하루 한도·연결 실패),
  화면 테스트 **43/43 통과**(+7: 휴대폰 가입(탭·하이픈·닉네임·요청 내용), 문자 설정 없으면 탭 비활성, 휴대폰으로 비밀번호 찾기, 닉네임(규칙·서버 오류·상단 이름 변경),
  휴대폰 등록→이메일 삭제 가능, 활동 표·실패 경고·모든 기기 로그아웃(취소/새 토큰), CSV 내려받기 내용 — 기존 마이페이지 테스트는 '바꾼 적 없음' 없음 확인 추가).
  실제 서버(`app.main`, **업데이트 전 형식의 DB → 새 컬럼·테이블 자동 추가 확인**) + 가짜 솔라피·가짜 SMTP 로 휴대폰 가입→번호 로그인→이메일 추가(실제 SMTP 경로)→휴대폰 삭제/재등록→
  닉네임→휴대폰으로 비밀번호 찾기→예전 토큰 401→모든 기기 로그아웃→다른 토큰 401→활동 기록 10건, 예전 계정 로그인. 빌드된 화면으로 휴대폰 번호 로그인→마이페이지→닉네임 변경(상단 반영)→
  모든 기기 로그아웃 후 새로고침해도 로그인 유지→휴대폰 가입 문자 발송, 콘솔 오류 없음. **솔라피 실제 발송은 실서버 미검증** (이 환경에서 solapi.com 접속 불가)

### 2026-11-25 — AI 모의투자 · 백테스트 1년 · 경제 캘린더 HTTP 400 수정 (commit `c35db5c`)
- **경제 캘린더 HTTP 400** ("Variable realtime_start can not be after today's date"): 한국 오전 = 미국 전날 밤인데 한국 날짜(11/25)로 FRED 에
  '11/25 기준 값'을 물어서 FRED 가 미래 날짜라며 거부. → 발표 여부·조회 날짜를 **미국 중부 시간(FRED 기준) 날짜**로 판단(`econ_calendar.fred_today`),
  한국 날짜로는 오늘이지만 미국은 아직 전날이면 "미국 현지 날짜로 아직 발표일 전" 으로 표시하고 조회 안 함. 시계 차이로 그래도 같은 400 이 오면 오류가 아니라 '발표 전'
- **백테스트 90일 → 1년(365일)**: 국내 일봉 500 → 800개(학습용 2년 + 1년), 미국·지수 yfinance 2y → 5y. 이미 저장된 날짜는 규칙 점수를 다시 계산하지 않고
  DB 값을 씀(1년치를 매일 다시 계산하지 않게 — 그날 전날까지 데이터로만 정해지는 값이라 같음). 예측 검증 화면 기간 버튼에 180일·365일 추가
- **AI 모의투자 (새 사이드바 메뉴)** — 매집 탐지·퀀트 점수·AI 추천·경제 캘린더(시장 상태·발표 일정)를 합친 'AI 점수'로 가상 자금 운용. 실제 주문 없음
  - AI 점수(0~100) = AI 추천 상승확률 45% + 퀀트 종합 백분위 35% + 매집 점수 20%(40점 넘는 만큼 가산, 제외 조건이면 0). 지수 시장 상태로 주식 비중 상한
    (상승 추세 100%·상승 압박 60%·하락 추세 30%), 다음 거래일에 FOMC·CPI·고용·GDP·PCE 발표(국내는 간밤 결과 반영일)·옵션 만기일이면 새 매수 금액 절반
  - 매수: 점수 ≥ 매수 기준 + 상승확률 ≥ 55%, 점수 순, 총자산 ÷ 최대 보유 종목 수. 매도: 손절(추격 손절)·목표가는 장중 도달 즉시, 점수 < 매도 기준·상승확률 ≤ 40%·최대 보유일은 다음 날 시가.
    수수료·거래세(국내 0.20%)·슬리피지 반영. 시작 자금·최대 종목 수·매수/매도 기준·손절%·익절%·최대 보유일·추격 손절은 사용자가 설정 (범위 밖이면 422)
  - **과거 시뮬레이션**(1개월~2년): 하루씩 **그날 종가까지의 데이터로만** 판단 → **다음 거래일 시가**에 체결. 퀀트 요인 비중도 그날 이미 결과가 나온(20거래일 뒤 날짜 ≤ 그날) 과거로만 정함.
    결과: 최종 자산·수익률·코스피/S&P500 대비·최대 낙폭·승률·손익비·평균 주식 비중·수수료, 자산 곡선(AI vs 지수), 거래 내역(이유), 날짜별 판단 기록.
    대상은 AI 추천 후보(고정 목록) — 지금 점수가 높은 종목을 넣으면 미래를 보고 고른 셈이라 안 넣음. 뉴스·공시는 과거 기록이 없어 빠짐. 한 번에 하나씩 계산(1년 약 1~3분)
  - **실시간 모의투자**(계좌 최대 5개): 만들면 바로 최근 종가로 판단(장중이면 그 자리에서 현재가 체결) → 매 거래일 장 마감 15분 뒤 판단 → 다음 개장 1분 뒤 현재가 체결,
    장중 5분마다 손절·목표가 확인. 학습 모델 포함 AI 추천 확률 + (국내) 전 종목 퀀트·매집 상위 + 내 관심·투자종목까지 검토. '지금 AI 판단 실행'·자동 매매 멈춤·삭제.
    서버가 켜져 있어야 자동 매매됨. 자동 판단 실패는 30분 뒤 다시 (매분 KIS 호출 반복 방지), 같은 날 이미 판단했으면 자동 실행은 건너뜀
  - 새 파일: `services/paper_engine.py`(계산만), `services/papertrade.py`(데이터·실행·자동 운영 `loop`), `models/paper.py`(테이블 4개, 시작 시 자동 생성),
    `api/routes/papertrade.py`(`/api/paper/...`), `frontend/src/pages/PaperTrading.tsx`. 회원 탈퇴 시 모의투자 기록도 삭제
- 검증: pytest **144개 통과**(+23: `test_papertrade.py` 17 — 설정값 범위·AI 점수 가중치·체결 비용/손익 계산·장중 손절/목표 순서(둘 다 닿으면 손절)·추격 손절·
  시장 상태별 비중 상한·이벤트 절반·매도 규칙 3가지·이벤트 날짜(국내 간밤·미국 당일·옵션 만기)·시뮬레이션 회계(현금+보유=자산, 체결가=다음 날 시가)·
  **미래 데이터 미사용(이후 일봉·지수를 바꿔도 그날까지 판단·거래·자산 동일)**·기간 부족 오류·API(시뮬레이션 시작→진행→결과·삭제, 실패 사유, 계좌 생성→판단→체결→손절,
  계좌 5개 제한, 남의 계좌 404, 같은 날 자동 판단 건너뜀)·미완성 오늘 봉 제외 / `test_backtest.py` 3 — 1년 설정, 저장된 날짜 재계산 안 함(값 동일), 미래 데이터 미사용 /
  `test_econ_calendar.py` +3 — 한국 오늘=미국 어제면 FRED 조회 안 함(**고치기 전 코드로 돌리면 실패** 확인), 400 realtime_start 는 오류 아님, FRED 날짜 = 미국 중부),
  `test_account.py` 탈퇴 시 모의투자 4개 테이블 삭제 추가. 화면 테스트 **47/47 통과**(+4: 실시간 계좌(보유·거래 이유·판단 기록·설명), 계좌 생성 요청·422 문구,
  시뮬레이션 결과(요약·그래프 2선·거래·판단 기록·경고)·시작 요청(기간·설정), 계산 중 진행·실패 사유 / 모든 화면·390px 목록에 /paper 추가). 화면 가짜 응답은 백엔드 코드로 실제로 만든 응답.
  실제 서버(`app.main`, KIS·Yahoo 만 무작위 일봉 가짜 함수 — 이 환경은 KIS·Yahoo·FRED 차단)로 로그인 → 국내 1년 시뮬레이션 완주(거래 190건, FRED 키 없음 경고) →
  미국 계좌 생성(하락 추세 → 30% 한도로 2종목 대기 주문, 다음 개장 체결 대기) → 1년 백테스트 완주(60종목 14,885건, 2025-11-25~2026-11-24), 다음 실행은 새 날짜만(계산 약 15초).
  빌드된 화면으로 로그인 → AI 모의투자 두 탭, 밝은·어두운 모드·폭 390px 가로 스크롤 없음·콘솔 오류 없음.
  **실서버 미검증**: 실제 KIS·Yahoo·FRED 데이터로 시뮬레이션·실시간 계좌 (아래 알려진 이슈)

### 2026-11-25 — Oracle VM 자동 재시도를 집 PC Docker 에서 (Cloud Shell 이 몇 시간이면 끊김) (commit `f18cc51`)
- 문제: `deploy/oci-launch-retry.sh` 를 Oracle Cloud Shell 에서 돌리면 몇 시간 뒤 세션이 끊기고 브라우저에 '사이트에서 나가시겠습니까?' → 재시도가 멈춤
- 스크립트를 PC 의 Docker(`python:3.12-slim` + `pip install oci-cli`)에서도 돌게 고침: 테넌시를 `~/.oci/config` 에서 읽음, `jq`·`ssh-keygen` 이 없으면
  python(oci-cli 와 같이 설치되는 cryptography)으로 대신, `oci` 가 없거나 API 키 로그인이 안 되면 실제 오류를 보여 주고 멈춤,
  `MICRO=1` 이면 AMD 1GB(VM.Standard.E2.1.Micro — 자리 거의 항상 있음, 느림)로 생성. Cloud Shell 에서는 예전처럼 그대로 동작
- `docs/setup-cloud.md` 에 "PC 에서 자동 재시도" 절차 (API 키 만들기 → `C:\Users\내이름\.oci\config`·`oci_api_key.pem` → `docker run -d --name oci-retry ...` →
  `docker logs -f oci-retry` → 절전 끄기 → 성공 시 SSH 키 `.oci\stock_ssh_key` 를 `.ssh\oracle.key` 로 복사)
- 검증: 이 환경의 Docker 에서 문서의 명령과 같은 `python:3.12-slim` + oci-cli 3.96.3 설치 → 가짜 API 키 config 로 실행해 테넌시를 config 에서 읽고
  "Oracle 로그인(API 키) 실패" + 실제 오류 문구 표시 확인 (이 환경은 Oracle 접속이 막혀 시간 초과). 가짜 `oci` 명령으로 jq·ssh-keygen 없는 컨테이너에서
  전체 흐름: 서브넷 → 80/443 규칙 생성·연결(보안 목록 JSON 합치기) → SSH 키 생성(OpenSSH RSA 4096, 공개키 일치 확인) → '자리 없음' 2번 재시도 → 성공 → 공인 IP,
  A1 은 1 OCPU/2GB shape-config 전달·Micro 는 생략 확인, `oci` 없을 때 안내. `bash -n` 문법 확인. 앱 코드 변경 없음.
  **실제 Oracle 계정으로는 실서버 미검증** (알려진 이슈)

### 2026-11-25 — PC Docker 재시도 명령이 Windows 에서 바로 실패하던 문제 (commit `fb2fbb1`)
- 증상(사용자 PC): `set: pipefail: invalid option name` + `syntax error near unexpected token 'else'`. 원인: Windows git 이 받을 때 `.sh` 줄 끝을 `\r\n` 으로 바꿔 저장 → 리눅스 bash 가 못 읽음
- 수정: 문서의 `docker run` 명령이 `tr -d '\r'` 로 정리한 복사본을 실행 (저장소 파일·git 설정은 안 바꿈 — `.gitattributes` 를 추가하면 이미 받은 PC 에서 파일이 '수정됨'으로 보여 pull 이 막힐 수 있음).
  메모장으로 저장한 `.oci\config`(줄 끝 `\r\n`)에서 테넌시를 못 읽던 것도 수정(awk 에서 `\r` 제거). pip 경고 문구도 끔
- 검증: 이 환경 Docker 에서 스크립트를 `\r\n` 으로 바꿔 **예전 명령으로 사용자와 같은 오류 재현** → 새 명령으로 가짜 `oci` 전체 흐름(재시도 2번 → 성공 → IP) 통과,
  `\r\n` config 에서 테넌시 값이 `\r` 없이 넘어가는지(가짜 oci 호출 기록) 확인, 실제 oci-cli 3.96.3 이 `\r\n` config 를 정상으로 읽는지(`validate_config`) 확인.
  `scripts/check.sh`: pytest 144개 통과, 화면 테스트는 1회 '탈퇴' 항목이 일시 실패(같은 시각 Docker 데몬 실행 중 — 이번 변경은 화면 코드와 무관) → 다시 3번 47/47 연속 통과.
  실제 Oracle 계정으로는 실서버 미검증

### 2026-11-25 — AI 모의투자 과거 시뮬레이션 "database is locked" 실패 수정 (commit `d9f0f2e`)
- 증상(사용자 PC): 시뮬레이션 실패 `(sqlite3.OperationalError) database is locked [SQL: SELECT paper_sim ...]` — 몇 분 계산한 결과를 저장하는 순간 실패
- 원인: 백테스트를 1년으로 늘리면서 첫 실행이 기록 약 1만 5천 건을 **한 번에 commit** → commit 동안 DB 가 잠기고, 다른 연결은 기본 5초만 기다리고 실패.
  PC(특히 Docker 의 Windows 폴더)는 디스크가 느려 commit 이 5초를 넘김. 재현: 6만 건 한 번에 commit(11초) 중 다른 저장이 5초 대기 후 같은 오류
- 수정: ① 백테스트 기록을 300건씩 나눠 commit (`backtest.SAVE_CHUNK`, 저장 부분을 `_save()` 로 분리) — 같은 재현에서 최대 대기 0.04초
  ② DB 대기 한도 5초 → 30초 (`database.DB_TIMEOUT`) ③ 시뮬레이션 결과·실패 저장이 잠금이면 5·15·30초 뒤 다시 시도 (`papertrade._save_sim`)
- 검증: pytest **147개 통과**(+3: 백테스트 저장이 나눠 commit 되는지(**고치기 전처럼 한 번에 저장하면 실패** 확인), 다른 연결이 쓰기 잠금을 2.5초 잡은 동안
  시뮬레이션 저장이 다시 시도해 성공(**재시도를 빼면 사용자와 같은 'database is locked' 로 실패** 확인)·잠금이 아닌 오류는 바로 올림, 대기 한도 30초),
  화면 테스트 47/47. 실제 서버(`app.main`, 가짜 KIS·Yahoo, 새 DB)로 **첫 1년 백테스트(14,885건 저장, 저장 단계 약 2분)와 국내 3개월 시뮬레이션 62번을 겹쳐 실행** →
  시뮬레이션 62개 모두 성공(저장 단계와 겹친 9개 포함), API 오류 0, 최대 응답 3.9초. 실제 PC 디스크 속도로는 미검증

### 2026-11-25 — 시뮬레이션 중단 버튼 · AI 모의투자 개선 옵션(학습형 가중치·추세 필터)+기본 방식 비교 · 서버 공개 전 보안 강화 (commit `1537b67`)
- **[중요 버그] 클라우드에서 로그인 직후 다시 로그인 화면으로 튕기던 문제** (서버에 올리기 전에 찾음): Caddy 접속 비밀번호(basic auth)는 브라우저의
  `Authorization` 헤더를 쓰는데 화면이 같은 헤더에 로그인 토큰을 넣어 덮어씀 → 로그인 뒤 모든 API 가 Caddy 401. 실제 Caddy(Docker, 이 저장소 Caddyfile)로 재현.
  → 화면은 토큰을 `X-Access-Token` 으로 보냄 (백엔드는 둘 다 받음 — PC 직접 실행·API 문서도 그대로)
- **과거 시뮬레이션 중단 버튼**: 계산 중 카드의 '중단' (확인 후) → 몇 초 안에 멈추고 '중단' 표시. 서버가 계산 도중 꺼져 '계산 중'으로 남은 기록은 시작할 때 실패로 정리
  (예전엔 지우지도 못했음). `POST /api/paper/simulations/{id}/cancel`
- **AI 모의투자 개선 옵션 (기본 켬, 설정에서 끌 수 있음)** — 근거 없이 "좋아졌다"고 하지 않도록 **같은 데이터로 옵션을 끈 '기본 방식'을 매번 같이 계산해 비교 표·그래프(노란 점선)로 보여줌**
  - 학습형 가중치: 상승확률·퀀트·매집 비중을 고정 45/35/20 대신, 결과(10거래일 뒤 수익률)가 **판단일까지 확정된** 최근 120거래일의 날짜별 순위 상관(IC)만큼 20거래일마다.
    고정 비중과 반반 섞음(짧은 기간에 과하게 맞추지 않게 — 실제 서버 첫 실행에서 '퀀트 100%' 로 몰리는 것을 보고 추가). 셋 다 안 맞으면 고정 비중. 판단 기록에 그때 비중 표시
  - 추세 필터: 50일선 아래 종목은 새로 사지 않음 (판단 기록에 '50일선 아래라 안 삼 — 종목')
  - 실시간 계좌도 같은 옵션 (학습형이면 최근 200일 점수를 같이 계산). 예전에 만든 계좌는 옵션 없음 = 예전 방식 그대로
- **보안 (인터넷 공개 대비)**:
  - 유출된 비밀번호 차단 — 가입·비밀번호 찾기·변경 때 Have I Been Pwned 유출 목록에 있으면 거부, 로그인 때 지금 비밀번호가 목록에 있으면 모든 화면 위에 빨간 경고
    (Chrome '비밀번호 유출' 경고와 같은 종류). SHA-1 앞 5글자만 전송·비교는 서버 안·Add-Padding, 조회가 안 되면 막지 않음. `PWNED_CHECK`
  - 계정별 잠금 — 같은 계정 15분 안 10번 틀리면(IP 를 바꿔도) 그 계정 15분 잠금 (맞는 비밀번호도), 활동 기록 '계정 잠금' + 알림 메일
  - 처음 보는 IP 로그인 알림 메일 (인증된 이메일 + SMTP 설정 시, `LOGIN_ALERT`)
  - 2단계 인증 코드 재사용 불가 (같은 코드·이전 코드 거부 — 켤 때·로그인·끌 때·탈퇴 모두)
  - IP 판단을 X-Forwarded-For **맨 뒤** 값으로 (맨 앞은 접속자가 위조해 IP 차단을 피할 수 있었음)
  - **`/api/stocks/test/kis`(로그인 불필요)가 KIS 접근 토큰 앞 20자를 보여주던 것 제거**
  - Caddy: CSP(`script-src 'self'` 등 — 화면에 스크립트가 끼어들어도 로그인 토큰을 못 훔쳐 감), Permissions-Policy, COOP. 그래서 index.html 의 테마 초기화 스크립트를 `public/theme-init.js` 로 분리
  - `setup-server.sh`: 자동 보안 업데이트(unattended-upgrades), `.env`·`.secret_key`·DB·KIS 토큰 파일 600, SSH 비밀번호 로그인 켜져 있으면 경고,
    접속 비밀번호 12자 미만·확인 불일치 거부, 가입이 열려 있으면 `SIGNUP_OPEN=false` 안내. `docs/setup-cloud.md` 7-0 보안 체크리스트
- 검증: pytest **166개 통과**(+19: `test_security.py` 11 — HIBP 앞 5글자만·패딩 무시·캐시, 조회 실패 시 통과, 유출 비번 로그인 경고·변경 거부·변경 후 경고 해제,
  조회 안 될 때 로그인 정상, IP 바꿔 10번 → 계정 잠금(맞는 비번도 429)·알림 메일·다른 계정 무관, **XFF 위조로 IP 차단 회피 불가(고치기 전 코드로 실패 확인)**,
  새 IP 알림(첫 로그인·같은 IP·끔은 안 보냄), 2단계 코드 재사용 거부, totp_step 범위, KIS 테스트 주소에 토큰 없음, **Basic 인증 + X-Access-Token 로 /me 정상**;
  `test_papertrade.py` +8 — 학습형 비중이 맞히는 신호로 감·0 인 신호 없음, **판단일 뒤에 확정되는 결과를 바꿔도 비중 동일**(이미 확정된 결과를 바꾸면 달라짐 확인),
  안 맞으면 고정 비중, 추세 필터, 시뮬레이션 비중 기록·같은 점수 재사용해도 결과 같음, 중단 API(계산 중 → 중단·끝난 것 409), 기본 방식 비교 결과·옵션 끄면 비교 안 함,
  재시작 뒤 '계산 중' 정리; 기존 '미래 데이터 미사용' 시뮬레이션 테스트가 이제 개선 옵션 켠 상태로 통과). 2단계 인증 테스트는 시각을 고정해 30초 경계에서 흔들리지 않게.
  화면 테스트 **53/53**(+5: 중단 버튼(취소면 요청 안 함)·중단 표시, 비교 표·3선 그래프·옵션 체크·요청 본문, **Caddyfile 의 CSP 를 그대로 걸고 화면 5개·테마·2단계 QR**
  (**예전 인라인 스크립트로 돌리면 실패** 확인), 유출 경고 띠·링크, 토큰을 X-Access-Token 으로만 보냄).
  실제 서버: `app.main`(가짜 KIS·Yahoo) 앞에 **실제 Caddy 2.8 + 이 저장소 Caddyfile**(Docker) — 설정 읽기 정상, 접속 비밀번호 없으면 401, 보안 헤더 전부, Server 헤더 없음,
  XFF 를 매번 바꿔 5번 틀려도 실제 IP 차단, 브라우저로 로그인 → AI 모의투자 1년 시작 → 중단 → 3개월 완주(비교 표) → 2단계 QR, API 401 0건·콘솔 오류 0.
  실시간 계좌 생성 → 학습형 비중으로 판단·주문. **실서버 미검증**: 실제 HIBP(이 환경에서 api.pwnedpasswords.com 차단)·실제 도메인 HTTPS 인증서·알림 메일 실제 발송·
  우분투 VM 에서 setup-server.sh 보안 단계(문법·비밀번호 입력 부분·set -e 동작만 확인)

### 2026-11-25 — 2단계 인증 필수 · 초대 코드로만 가입 · 관리자(초대·회원 차단) · 한 일/할 일 정리 (commit `3a756a5`)
- **정리 문서**: [docs/status.md](docs/status.md) — 지금까지 한 일 / 앞으로 할 일(사용자 할 일 · 2단계 KIS 모의투자 · 3단계 전 보안 · 실서버 확인 목록)
- **2단계 인증(Google Authenticator) 필수** (`REQUIRE_TOTP`, 기본 켬): `get_current_user` = 로그인 확인(`get_user_before_totp`) + 2단계 확인.
  안 켠 계정은 /me·setup/enable-totp·비밀번호 변경·모든 기기 로그아웃만 되고 나머지 API 는 403 + `X-Totp-Required: 1`.
  화면: 로그인·가입 응답의 `totp_setup_required` → `/setup-2fa`(등록 화면), ProtectedRoute·axios 403 처리도 같은 곳으로. 등록하면 첫 화면.
  필수일 땐 마이페이지 '끄기' 대신 '휴대폰 바꾸기'(지우면 바로 재등록 화면). 2단계 등록 시 인증된 이메일로 알림
- **초대받은 사람만 가입** (`INVITE_ONLY`, 기본 켬): `services/invites.py` — 12글자 1회용 코드(헷갈리는 글자 제외, 약 60비트), DB 엔 HMAC 해시·끝 4글자만, 기본 3일(1~14),
  관리자당 사용 가능 10개. 인증 코드 받기·가입 둘 다 초대 코드 확인 (틀린 초대면 메일·문자 안 보냄 + IP 실패 횟수 → 5번이면 15분 차단). 같은 코드 동시 가입은 조건부 UPDATE 로 한 명만
- **관리자** (`users.is_admin`, 관리자가 없으면 init_db 가 가장 먼저 만든 계정을 관리자로): `api/routes/admin.py` — 초대 코드 만들기(코드는 응답에 한 번만)·목록·취소,
  회원 목록(2단계 등록·초대한 사람·최근 로그인), 회원 차단/해제(차단 = session_epoch 갱신으로 모든 기기 즉시 끊김, 나·관리자는 불가). 만들기·차단은 2단계 코드 다시 확인(재사용 불가).
  화면: 마이페이지 맨 위 '관리자 — 초대 · 회원'(`AdminSection`). 서버 명령 `create_admin.py --invite [메모]`, `--admin <아이디>`, 새 계정은 관리자가 없으면 관리자
- 계정 잠금을 DB(`users.locked_until`)에도 저장 → 서버를 다시 켜도 잠금 유지. 로그인 유지 24시간 → 12시간. `--reset-totp` 가 쓴 코드 기록도 지움
- 문서: setup-cloud(7. 접속·7-0 체크리스트·7-1), setup-local·setup-docker(첫 로그인 = 2단계 등록), `.env.example`(INVITE_ONLY·REQUIRE_TOTP), setup-server.sh(두 값을 false 로 두면 경고), CLAUDE.md
- 검증: pytest 175개 (+9 `tests/test_invite_totp.py`: 2단계 등록 전 403+헤더·/me 허용·켜면 같은 토큰으로 통과·휴대폰 바꾸기 후 다시 403·설정 끄면 선택,
  초대 없이/틀린 초대 → 메일 안 감·2단계 재확인·원문 미저장·소문자/하이픈 없이 입력·1회용·만료·취소·register 직접 호출 거부·틀린 초대 5번 IP 차단·10개 한도·INVITE_ONLY=false,
  차단 → 토큰 401·로그인 401·해제, 업그레이드 시 첫 계정 관리자 / `test_security` 계정 잠금이 메모리를 지워도 DB 로 유지),
  화면 테스트 58개 (+5: 비밀번호만 로그인 → 등록 화면 강제 → 켜면 대시보드, 403 X-Totp-Required → 등록 화면(저장된 내 정보가 오래돼도 머묾),
  초대 코드 가입(코드 없으면 버튼 막힘·대문자 변환·요청에 포함·가입 후 등록 화면), 관리자 구역(초대 만들기 2단계 코드·새 코드 표시·목록·차단 버튼), 일반 회원은 관리자 구역 없음),
  `bash scripts/check.sh` 통과. **실서버 확인**: 실제 `app.main`(KIS·Yahoo·메일만 가짜) + 실제 Caddy(접속 비밀번호·CSP) + 빌드된 화면, Playwright 로
  `create_admin.py` 새 계정(관리자) → 비밀번호 로그인 → 등록 화면 강제(관심종목 API 403·`X-Totp-Required: 1`, /paper 로 가도 등록 화면) → QR 비밀값으로 만든 코드로 등록 → 대시보드 →
  마이페이지 관리자 구역에서 새 30초 코드로 초대 코드 만들기 → 다른 브라우저에서 틀린 초대 거부·소문자 초대 + 가짜 메일 코드로 가입 → 등록 화면 →
  관리자가 회원 차단 → 가입자 바로 로그인 화면 → 관리자 코드로 재로그인. DB 기록(is_admin·invited_by·초대 used_by·해시 64자·활동 기록) 확인, API 401 0건·콘솔 오류 0.
  실서버 미검증: 실제 메일 발송(2단계 등록 알림·초대 가입 인증 코드), 실제 Google Authenticator 앱 스캔(같은 RFC 6238 계산으로만 확인)

### 2026-11-25 — 관리자 페이지 분리 · KIS 모의투자 주문 (AI 제안 → 내가 승인할 때만 주문) (commit `b7b4edd`)
- **관리자 페이지 분리** (사용자 요청: 관리자 화면과 일반 화면 따로): 사이드바 아래 '관리자 전용'(관리자에게만 보임) → `/admin` · `/kis` (`AdminRoute` — 관리자가 아니면 첫 화면으로, 서버도 `get_admin`).
  `/admin`: 요약(회원·2단계 미등록·차단·24시간 로그인·7일 로그인 실패·사용 가능한 초대) · 회원 목록 + **회원 상세**(연락처 가림·로그인 IP·최근 7일 실패·쓰는 기능 수·최근 활동 50 — 비밀번호·2단계 비밀값은 안 보냄) ·
  초대 코드 · **전체 회원 보안 기록**(로그인 실패·잠금·비밀번호·2단계·연락처 변경·차단·초대). 새 API `/admin/summary`·`/admin/users/{id}`·`/admin/events`.
  마이페이지의 관리자 구역은 없애고 링크만 (`AdminSection` → `AdminPanels`: InvitePanel·MemberPanel, 활동 이름은 `accountEvents.ts` 로 공통)
- **KIS 모의투자 주문** (사용자 결정: 'AI 가 주문을 제안하고 내가 승인할 때만 주문'): [docs/kis-mock-trading.md](docs/kis-mock-trading.md)
  - `services/kis_order.py`: 모의투자 서버 주문 API (시장가 주문·취소·잔고·일별 체결). **모의투자 주소가 아니면 주문 거부**. 키 `KIS_MOCK_APP_KEY`·`KIS_MOCK_APP_SECRET`·`KIS_MOCK_ACCOUNT_NO`
    (비어 있고 `KIS_IS_REAL=false` 면 시세용 키). `KISClient` 가 키·주소·토큰 파일을 받아 따로 만들 수 있게 바꿈 + POST 지원, 토큰 파일 권한 600
  - `services/kis_trade.py` + `models/kis.py`(kis_trade·kis_orders·kis_log) + `api/routes/kis.py`: 장 마감 15분 뒤 **KIS 실제 잔고를 놓고** AI 모의투자와 같은 판단(`papertrade.analyze_live` 로 분리해 같이 씀) → 제안,
    장중 5분마다 손절·목표 → 매도 제안, 관리자가 2단계 코드로 승인(여러 건 한 번에) → 장중이면 바로·아니면 다음 개장 1분 뒤 주문 → 1분마다 체결 확인
  - 안전장치: 승인마다 2단계(재사용 불가, 2단계 안 켠 관리자는 불가) · 1회 매수 한도 · 하루 주문 횟수 · 하루 손실 한도(넘으면 자동 정지) · 가격 +3%/−6% 넘게 움직이면 매수 안 함 ·
    같은 종목 중복 주문 방지 · 한 제안 한 번만 승인 · 'submitting' 먼저 저장(재시작하면 결과 모름 — 다시 안 보냄) · 앱 기록과 KIS 잔고가 다르면 매수 안 함('기준 다시 맞추기') ·
    긴급 정지(코드 없이, 대기·접수 주문 취소) / 다시 시작(코드) · 15:20 이후 새 주문 안 보냄 · 제안은 다음 거래일 15:30 까지 · 모든 일 감사 로그 · 새 제안·정지 관리자 메일 알림
  - 화면 `/kis`(`KisTrade.tsx`): 상태(운영/정지·오늘 주문·오늘 손익·한도)·긴급 정지·잔고(손절·목표·보유일)·대조 경고·제안 선택 → 승인/거절·주문 전 취소·접수 주문 취소·지금 제안 만들기·최근 판단 기록·설정·주문 기록·감사 로그. 키가 없으면 연결 안내만
- 문서: 새 `docs/kis-mock-trading.md`, setup-cloud(7. 접속 관리자 페이지 · 7-3), setup-local·setup-docker, `.env.example`, CLAUDE.md, docs/status.md
- 검증: pytest 203개 (+27 `tests/test_kis_trade.py` — 가짜 KIS 계좌(FakeBroker)로 승인 2단계 필수·틀린 코드/재사용 거부·주문 수량(1회 한도로 깎임)·1주도 못 사면 막음·하루 횟수·가격 상승/급락·
  같은 종목 두 번 방지·하루 손실 → 자동 정지 + 대기 제안 취소 → 정지 중 승인 불가 → 코드로 다시 시작·잔고 대조 다르면 매수 막음 → 기준 맞추기·매도는 팔 수 있는 수량까지·KIS 거부 문구·
  긴급 정지 시 접수 주문 KIS 취소·보내던 중 재시작 → 결과 모름(다시 안 보냄)·장 마감 뒤 안 체결·장 밖 승인 → 09:01 전엔 안 보내고 09:01 에 보냄·기한 지남·설정 검증(틀린 값은 코드 쓰기 전 422)·감사 로그,
  장 마감 15분 뒤 자동 제안(KIS 잔고 보유 종목으로 판단·예전 제안 만료·제안만 하고 주문 없음·하루 한 번), 손절 매도 제안(중복 없음),
  주문 API: 실거래 주소 거부·요청 본문(CANO·ACNT_PRDT_CD·ORD_DVSN=01)·새 TR → 없는 TR 응답이면 예전 TR·그 외 오류면 주문 다시 안 보냄·잔고 필드 해석·키 설정 / +1 `test_invite_totp`: 관리자 요약·회원 상세(가린 연락처·비밀값 없음)·보안 기록·일반 회원 403),
  화면 테스트 63개 (+7·−2: 관리자 페이지(사이드바 관리자 메뉴·마이페이지 링크·요약·초대 만들기·회원 상세·차단·보안 기록), 일반 회원은 관리자 메뉴·링크 없고 /admin·/kis → 첫 화면·관리자 API 안 부름,
  KIS 승인 흐름(선택·코드 없으면 버튼 막힘·요청 ids/코드·거절·주문 취소·주문 기록·감사 로그), 정지 상태(승인 막힘·다시 시작 코드·대조 경고·기준 맞추기), 긴급 정지·설정 저장, 키 없음 안내(390px 다크), 390px 가로 스크롤),
  `bash scripts/check.sh` 통과. **실서버 확인**: 실제 `app.main`(시세·Yahoo·메일만 가짜) + **가짜 KIS 모의투자 HTTP 서버**(실제 KIS 응답 필드 이름) + 실제 Caddy(접속 비밀번호·CSP) + 빌드된 화면, Playwright 로
  새 관리자 2단계 등록 → 사이드바 관리자 전용 → 관리자 페이지(요약·회원 상세·보안 기록) → KIS 화면. 장 마감 뒤(16:48) 서버가 켜지자 자동으로 토큰 발급·잔고 조회(VTTC8434R) → 제안 2건 →
  틀린 코드 승인 거부 → 새 코드로 1건 승인(개장 대기)·1건 거절 → 시계를 다음 날 09:01 로 옮겨 다시 켜니 자동으로 시장가 매수(VTTC0012U, 본문 CANO 50123456·PDNO·ORD_QTY 39) → 체결 조회(VTTC0081R) → 체결·잔고 일치 →
  긴급 정지 → 코드로 다시 시작, 감사 로그 순서 확인, API 401·5xx 0건·콘솔 오류 0. 이 과정에서 찾아 고친 것: 주문 직후 화면이 20초 캐시된 잔고로 '대조 다름'을 띄움 → 주문·체결 때 캐시 비움,
  제안 뒤 급락한 종목도 매수됨 → −6% 넘게 떨어지면 막음. 전체 테스트를 돌리다 `test_api_live_account_flow` 가 한 번 실패(계좌 상태를 체결 저장 직전에 읽어 보유 종목 없음) → 테스트가 보유 종목까지 기다리게.
  **실서버 미검증**: 실제 KIS 모의투자 서버(TR 번호·잔고/체결 필드·주문 응답), 제안 알림 메일 실제 발송

### 2026-11-25 — 관리자가 누군지 확인하기 (사용자: "관리자 페이지가 안 보인다") (commit `c14f08a`)
- 관리자 = `users.is_admin` 이 켜진 계정 (처음 만든 계정, 관리자가 없으면 서버 시작 때 가장 먼저 만든 계정). 관리자 메뉴는 그 계정으로 로그인해야 보임
- 서버 명령 `create_admin.py --list` (계정·관리자·2단계·차단·가입일 목록 + 누가 관리자인지), `--admin` 성공 문구에 '새로고침' 안내
- 마이페이지 프로필 카드에 '관리자' / '일반 회원' 표시, 일반 회원이면 관리자 확인·변경 명령 안내. setup-local·docker·cloud 에 '관리자 메뉴가 안 보이면' (다시 켜기·새로고침·--list·--admin)
- 검증: pytest 204개 (+1 `test_create_admin_list_and_switch`: 계정 없음 → 1, 첫 계정 관리자 표시, --admin 으로 바꾸면 목록·DB 가 바뀜), 화면 테스트 63개 (관리자/일반 회원 표시·안내 문구 확인 추가),
  `bash scripts/check.sh` 통과, 실제 `create_admin.py` 를 파일 DB 로 실행해 --list → 계정 2개·관리자 first → --admin me → --list 에서 me 로 바뀜 확인

### 2026-11-25 — KIS 모의투자 '잔고를 못 받음: INVALID_CHECK_ACNO' 원인 안내 (commit `e9d5609`)
- 사용자 화면 오류: `KIS VTTC8434R 실패 (HTTP 200, OPSQ2000): ERROR : INPUT INVALID_CHECK_ACNO` = 모의투자 서버가 계좌번호를 거부 (앱키와 짝이 아닌 계좌 / 실전 계좌번호 / 상품코드 / 모의투자 기간 만료)
- `kis_order`: 이 응답이면 `AccountRejected` 로 무엇을 고칠지 설명 — `KIS_MOCK_*` 가 비어 시세용 `KIS_ACCOUNT_NO` 를 빌려 쓰는 중이면 그 사실과 세 줄을 넣으라고,
  모의 계좌를 넣었으면 ①모의투자 계좌번호인지 ②앱키를 그 계좌로 발급받았는지 ③모의투자 기간. `OPSQ2000`(입력값 오류)은 '없는 TR' 목록에서 빼서 주문을 예전 TR 로 다시 보내지 않게
- `/kis/status` 에 `account_source`(어느 .env 값을 쓰는지), 화면 상태 줄에 `계좌 ****1234-01 (.env KIS_MOCK_ACCOUNT_NO)` + 시세용 계좌를 빌려 쓰면 노란 경고, 잔고 오류 문구를 자르지 않음
- 문서: kis-mock-trading.md 문제 해결에 INVALID_CHECK_ACNO 항목
- 검증: pytest 206개 (+2: 실제 오류 문구 그대로 두 경우(시세용 계좌 빌림 / 모의 계좌 거부) 설명·가린 계좌번호·주문은 TR 한 번만, 상태 API 에 오류 문구),
  화면 테스트 64개 (+1: 계좌 출처 표시·경고·오류 안내), `bash scripts/check.sh` 통과.
  **실서버 확인**: 실제 `app.main` + 가짜 KIS 모의 서버(앱키와 다른 계좌면 실제와 같은 `OPSQ2000 / ERROR : INPUT INVALID_CHECK_ACNO` 응답)로
  ①모의 키 비움+KIS_IS_REAL=false → 'KIS_ACCOUNT_NO 를 쓰는 중' 안내 ②다른 모의 계좌번호 → ①②③ 확인 안내 ③맞는 계좌 → 오류 없음. 실서버 미검증: 실제 KIS 가 다른 원인에도 같은 코드를 주는지

### 2026-11-25 — 계좌를 고쳤는데 '제안 실패: INVALID_CHECK_ACNO' 가 계속 보임 (commit `4c7bc72`)
- 원인: 17:24 자동 제안이 계좌번호 오류로 실패 → 그 오류(last_error)가 다음 제안이 성공할 때까지 남고, 실패한 날은 자동 제안을 다시 안 함(손으로만) → .env 를 고쳐 잔고는 받아져도 빨간 줄이 그대로
- 고침: 잔고가 받아지면 지난 계좌번호 오류를 지우고 오늘 자동 제안을 다시 하게(장 마감 15분 뒤면 1분 안에, 감사 로그 '계좌 확인됨'),
  자동 제안이 실패하면 30분마다 다시 시도(매분은 아님). 화면은 '마지막 자동 제안 실패 — 시각' + '30분마다 다시 · 지금 제안 만들기' 안내
- 검증: pytest 208개 (+2: 실패 → 1분 뒤 안 함 → 30분 뒤 다시 해서 제안, 사용자 화면 상태(오늘 실패 기록 + 잔고 정상) → 상태 API 가 오류 지움 → 다음 1분에 제안 + 감사 로그),
  화면 테스트 64개 (제안 실패 표시 문구 확인 추가), `bash scripts/check.sh` 통과.
  **실서버 확인**: 실제 `app.main` + 가짜 KIS 모의 서버로 17:49 에 틀린 계좌로 켜기 → 자동 제안 실패(propose_fail) → 맞는 계좌로 다시 켜고 상태 API 호출 → 오류 지움(account_ok) → 1분 안에 자동 제안 2건

### 2026-11-25 — KIS 모의투자 알림을 휴대폰으로 (ntfy) (commit `3831485`)
- 사용자 요청: 제안을 날씨 알림처럼 ntfy 로. 판단: **같은 ntfy 앱 · 같은 방식(JSON POST, weather-app 의 send_ntfy 와 같음) · 주제는 stock_app 전용으로 따로**
  (날씨와 섞이지 않고 주식 알림만 끄거나 소리를 바꿀 수 있음, 주제 이름 하나가 새도 다른 쪽은 안전). 설정 이름도 날씨 앱과 같게 `NTFY_TOPIC`·`NTFY_SERVER` (+ 선택 `NTFY_TOKEN`·`NTFY_CLICK_URL`)
- `services/notify.py`: send(한글 제목 그대로 — JSON), send_bg(실패해도 주문 흐름 계속), status()(주제 이름은 화면·오류·로그에 안 냄), 주제 형식 확인, 401/403 이면 토큰 안내
- 보내는 것: AI 주문 제안(높음, 종목·금액)·손절 매도 제안(긴급)/목표 매도 제안(높음)·정지(긴급) = 푸시 + 메일 / 체결(보통)·안전장치로 안 보냄·KIS 거부·결과 확인 필요(높음) = 푸시만.
  승인은 알림으로 안 되고 앱에서 2단계 코드로만. 화면: 상태 칸에 알림 켜짐/꺼짐·마지막 실패·'알림 시험 보내기'(POST /kis/notify-test)
- 테스트가 PC 의 .env 에 NTFY_TOPIC 이 있어도 진짜 알림을 안 보내게 conftest 가 비움
- 문서: kis-mock-trading.md '1-1. 휴대폰 알림' (주제 만들기·무작위 이름 명령·알림 종류), `.env.example`, CLAUDE.md
- 검증: pytest 213개 (+5 `tests/test_notify.py`·`test_kis_trade`: JSON 본문(날씨 앱과 같은 필드)·토큰 헤더·click·우선순위 1~5·서버 주소 끝 / 정리·403 안내에 주제 이름 없음·잘못된 주제 거부·설정 없으면 안 보냄,
  체결 → '체결' 푸시·가격 급등으로 막힘 → '주문 안 보냄' 푸시, 시험 API 503/200/502·상태 API 에 주제 이름 없음), 화면 테스트 64개 (알림 켜짐 표시·시험 버튼·꺼짐 안내), `bash scripts/check.sh` 통과.
  **실서버 확인**: 실제 `app.main` + 가짜 KIS 모의 서버 + **가짜 ntfy 서버**로 알림 시험 → 받은 JSON(topic·title·message·priority·tags·click) 확인, 18:43(장 마감 뒤) 자동 제안 2건 → 'AI 주문 제안 2건 — 승인 대기' 푸시 도착, 서버 로그·상태 API 에 주제 이름 0건.
  실서버 미검증: 실제 ntfy.sh 발송·아이폰 ntfy 앱 수신 (이 환경에선 외부로 못 보냄)

### 2026-11-25 — 예측 검증 결과로 지표 비중 조정 · KIS 실시간 웹소켓 현재가 ('다음 할 일 후보' 두 개) (commit `547f6dc`)
- **지표 비중 조정** (`services/factor_weights.py`): 과거 1년 백테스트 기록의 RSI·MACD·볼린저·이평 점수와 다음 날 실제 등락으로 지표별 적중률
  (상승 신호 적중률과 하락 신호 적중률의 평균 — 상승장에서 상승 신호가 저절로 맞는 착시 방지) → 51% 이상 1배 / 46% 이하 0.3배 / 사이는 비례, **줄이기만** (신호 150건 미만은 그대로).
  채택 검증: 날짜마다 그 전날까지 결과가 나온 기록으로만 비중을 정해 그날 확률을 다시 계산(walk-forward) → 원래 비중보다 방향 적중률이 0.3%p 이상 나을 때만(검증 300건↑) 실시간에 씀.
  백테스트가 끝날 때(하루 1번) 다시 계산 → `app/data/factor_weights.json`(git 제외). 실시간 예측(quote.analyze_candles)에만 적용 — 백테스트·과거 시뮬레이션은 원래 비중(미래 데이터 미사용).
  학습 모델을 쓰는 종목은 모델이 먼저이고 모델 입력은 원래 비중 확률. `predict_next_day(weights=)` → `weighted_probability`, method `rules:weighted`, 지표 근거에 '비중 ×0.6' 표시.
  화면: 예측 검증 '지표 비중 자동 조정' 카드(시장별 지표 적중률·비중·날짜별 검증 원래→조정·사용 여부)
- **KIS 실시간 현재가** (`services/kis_ws.py`): 국내 장 시간(08:55~15:35)에 화면·서버가 보는 국내 종목만 KIS 웹소켓(H0STCNT0 실시간 체결가)으로 구독(최대 40, 2분 안 물으면 해제, 아무도 안 보면 1분 뒤 연결 끊음).
  접속키 `/oauth2/Approval`(시세용 키), PINGPONG 응답, 한 메시지 여러 건 해석, 끊기면 5·10·30·60초 뒤 재연결. 받은 값은 서버 메모리(10초 지나면 안 씀).
  `GET /api/stocks/live?symbols=` (KIS 호출 없이 메모리 값 — 화면이 장중 2초마다), `quote.live_prices` 도 5초 안 실시간 값이 있으면 REST 를 안 부름(AI 추천·모의투자 등 KIS 호출 감소).
  화면: 관심종목(카드·표)·종목 상세 카드의 국내 현재가·등락률을 2초마다 바꾸고 '● 실시간 10:15:30' 표시 (전망·확률은 기존 1분·15초 갱신). 장 마감이면 요청 안 함.
  상태 `/api/market/scheduler-status` 의 `kis_ws`. 미국은 아직 REST·yfinance (KIS 해외 실시간은 별도 신청 필요)
- 검증: pytest 226개 (+7 `test_factor_weights.py`: 비중 규칙 경계·확률 식이 analysis 와 같음·거꾸로 맞는 지표만 줄고 채택·잡음/기록 부족은 미채택·
  **미래 데이터 미사용**(뒤쪽 결과를 뒤집어도 앞쪽 날짜 비중 같음 — 전체 기록으로 비중을 정하게 바꾼 코드로는 실패 확인)·모델이 있으면 모델 우선·DB 로 재계산→파일→다시 읽기,
  +6 `test_kis_ws.py`: KIS 예시 형식 46필드 해석·여러 건·다른 TR 무시·구독 TTL/40개·10초 지난 값 안 씀·구독/해제 메시지 형식·PINGPONG 되돌림·장 시간·/stocks/live·live_prices 가 실시간 값이 있으면 REST 안 부름),
  화면 테스트 67개 (+3: 장중 관심종목 실시간 가격·배지·2초마다·없는 종목 그대로, 장 마감이면 실시간 요청 없음, 예측 검증 비중 카드 — 실제 백엔드 응답으로 만든 가짜 데이터), `bash scripts/check.sh` 통과.
  **실서버 확인**: 실제 `app.main` + **가짜 KIS 웹소켓 서버**(0.5초마다 체결가 밀어 줌) + 가짜 KIS(접속키): 접속키 발급 → 연결 → 2종목 구독(H0STCNT0, 접속키 포함) → PINGPONG 응답 → /stocks/live 가 2초마다 새 가격(70,440 → 70,520 → 70,600) → 2분 뒤 구독 해제 2건.
  가짜 일봉으로 1년 백테스트 14,910건 → 비중 계산(무작위 데이터라 적중률 약 50% → '조정해도 비슷함 — 원래 비중', 과적합 안 함 확인), 국내 RSI 0.3배 채택 상태로 /stocks/kr/005930 → method rules:weighted · 원래 56% → 조정 57% · RSI 근거에 '비중 ×0.3'.
  **실서버 미검증**: 실제 KIS 웹소켓 주소(ops.koreainvestment.com:21000/31000)·접속키·체결가 필드 순서, 실제 백테스트 기록에서 어떤 지표가 줄어드는지

### 2026-11-25 — 전체 점검 (문서·모든 API·주요 버튼 흐름) 후 고친 것 (commit `3388e28`)
- 사용자 요청: PROGRESS.md 와 md 문서를 보고 전체 테스트 후 고칠 부분 자동 수정
- 점검 방법: ① `bash scripts/check.sh` ② 문서에 적힌 파일 경로·링크·API 경로·환경변수·`create_admin.py` 옵션을 실제 코드와 자동 대조(스크립트)
  ③ 실제 `app.main` + 가짜 KIS·KIS 모의 서버·KIS 웹소켓으로 **GET 라우트 전부** 호출(500 오류 0건, 502 는 가짜 서버에 없는 KIS 시세라 이유 문구가 정상 표시)
  ④ 주요 버튼 흐름(관심·투자종목 추가·수정·분석, 챗봇 5가지 질문, 과거 시뮬레이션 1개월, 실시간 모의계좌, KIS 제안, 알림 시험, 초대 코드, 모든 기기 로그아웃)
- **고친 버그**
  - **관심종목·투자종목 분석에서 국내 종목이 빠짐** — 직전 작업(실시간 웹소켓)에서 '실시간 값이 있으면 REST 생략' 코드가 `live_prices` 뿐 아니라 `analyze_items` 에도 들어감
    → 장중에 실시간 가격이 들어온 종목은 '분석 결과 없음'. `analyze_items` 원래대로 + 테스트(고치기 전 코드로 실패 확인)
  - **KIS 연결 오류 문구가 비어 있음** — '지금 제안 만들기'가 "처리 실패: " 만 표시 (httpx 연결 오류는 문구가 빈 문자열).
    `kis_api` 가 네트워크 오류를 `KISConnectionError`("KIS 토큰 발급 연결 실패 (ConnectError) — 인터넷·방화벽·KIS 점검 시간 확인")로 바꿈
  - **주문을 보낸 뒤 응답을 못 받으면 'KIS 거부'로 기록되던 것** — 실제로는 들어갔을 수 있음 → '결과 모름' + 긴급 휴대폰 알림, 그날 같은 종목 주문 막음.
    연결 자체가 안 된 경우만 '주문은 안 들어감'
- **문서**: README(2단계 인증이 '선택·API 로 켬'으로 남아 있던 것 → 필수·화면 등록, 초대 가입·관리자 확인 명령, KIS 모의투자·ntfy, 문서 목록),
  `.env.example`(빠져 있던 `PWNED_CHECK`·`LOGIN_ALERT` 설명, 초대 코드 만드는 곳 '관리자 페이지'로), docs/status.md(할 일에 휴대폰 알림, 미검증 목록에 KIS 모의 서버·웹소켓·ntfy),
  kis-mock-trading.md(결과 모름 경우), CLAUDE.md
- 검증: pytest 229개 (+3: 실시간 값이 있어도 분석 목록에서 안 빠짐, 네트워크 오류 종류별 문구·maybe_sent, 보낸 뒤 응답 없음 → 결과 모름·같은 종목 막음·연결 실패 → 안 들어감),
  화면 테스트 67개, `bash scripts/check.sh` 통과, 문서 대조 스크립트 남은 항목 0 (외부 사이트 주소 오탐 제외).
  **실서버 확인**: 고친 뒤 가짜 웹소켓이 삼성전자 실시간 가격을 보내는 중에 관심종목·투자종목 분석 정상(오류 없음, 상승 확률 표시), KIS 에 못 닿을 때 '지금 제안 만들기' 문구 정상

### 2026-11-25 — 미국 현재가를 KIS 해외 현재가로 (Yahoo 는 KIS 가 실패한 종목만) (commit `44c0ff1`)
- 사용자 질문 '해외 주식은 왜 Yahoo?' → 일봉(수년 치·여러 종목 한 번에)·지수·환율·배당 포함 월봉은 Yahoo 가 편해서 그대로 두고, **현재가만 KIS** 로 (사용자 선택)
- `quote.us_live_prices`: KIS 해외 현재가(HHDFS00000300, 거래소 코드는 종목마스터 NAS/NYS/AMS) → 가격·등락률·거래량, `source: "KIS"`.
  같은 종목은 정규장 중 실서버 10초·모의서버 60초(초당 2건 제한 — 국내 시세가 밀리지 않게)·장 밖 10분 동안 다시 안 물음.
  KIS 가 실패한 종목만 yfinance 1분봉(최대 15분 지연)으로 받고 `source: "Yahoo (KIS 실패)"`·`kis_error` 를 남김 (숨기지 않음), 둘 다 실패하면 오류
- 쓰는 곳: `live_prices`(AI 추천 15초 갱신·종목 조회 카드·AI 모의투자 체결·손절 확인), `analyze_items`(관심종목·투자종목 — 현재가를 오늘 봉에 반영해 확률도 그 가격으로, `price_source`)
- `get_us_stock_price`: 등락 부호(sign 4·5 = 하락) 처리, output 이 목록으로 와도 읽음
- 화면: 관심종목(카드·표)·투자종목에서 KIS 를 못 받아 Yahoo 가격일 때만 'Yahoo·지연 가능' 표시
- 검증: pytest 235개 (+6 `tests/test_us_live.py`: KIS 우선·거래소 코드·Yahoo 는 실패 종목만·출처 표시·0원/둘 다 실패 이유·캐시 시간·live_prices·관심종목 분석이 KIS 가격으로 오늘 봉 반영·둘 다 실패면 'Yahoo (KIS 실패)'·하락 부호),
  화면 테스트 68개 (+1: Yahoo 대체 가격만 표시), `bash scripts/check.sh` 통과, 테스트가 실제 KIS 를 부르지 않는지 출력으로 확인.
  **실서버 확인**: 실제 `app.main` + 가짜 KIS(해외 현재가 실제 응답 필드 last·diff·rate·sign)로 관심종목 AAPL → 321.45·출처 KIS (요청 EXCD=NAS·SYMB=AAPL·TR HHDFS00000300),
  TSLA(가짜 KIS 가 일부러 실패) → 일봉 값·출처 'Yahoo (KIS 실패)'·로그 '미국 현재가 KIS 실패 1종목 → Yahoo', 종목 조회 AAPL 321.45.
  **실서버 미검증**: 실제 KIS 해외 현재가가 무료 계정에서 실시간인지(지연 시세일 수 있음)·거래소 코드가 다른 종목(ETF 등)

### 2026-11-26 — 미국 프리마켓·애프터마켓 가격 표시 (관심종목·투자종목·AI 추천·종목 조회) (commit `a9c8fcf`)
- 사용자 제보: 미국 애프터마켓인데 화면엔 종가가 보임 → 원인: KIS 해외 현재가(HHDFS00000300)는 정규장 마지막 가격만 줌. 시간외 가격은 대시보드 빅테크·ETF(`ext`)에만 있었음
- `market_calendar.us_ext_session()`: 프리마켓 04:00~09:30 ET · 애프터마켓 16:00~20:00 ET (미국 거래일만) + 한국시간 표기. `market_status("US").extended`
- `us_daytime`: 주간거래가 아닐 때 프리·애프터마켓이면 Yahoo 5분봉(prepost)에서 **오늘 그 시간대의 마지막 체결**을 `daytime` 자리에 `label: 프리마켓/애프터마켓` 으로 붙임
  (등락률 = 행의 현재가(KIS 정규장 종가) 대비, 종목별 60초 캐시). 그 시간대 체결이 없으면 안 붙임(전날 애프터마켓 값을 프리마켓처럼 쓰지 않음).
  yfinance 는 실패해도 빈 표를 주므로 빈 응답·봉 없는 종목은 '조회 실패'로 표시 (실패는 캐시 안 함). 표시 전용 — 예측 확률·매입가 계산엔 안 씀.
  대시보드 빅테크·ETF 는 원래 `ext` 가 있어서 `extended=False` (두 번 안 보이게)
- 화면: 배지 이름이 label 대로(주간거래/프리마켓/애프터마켓), 표 보기는 '프리/애프터/주간', 사이드바 미국 상태 아래 '애프터마켓 중 (~10:00)'
- 검증: pytest 252개 (+15: 시간대 경계(16:00·20:00·04:00·09:29·추수감사절·토요일·서머타임), Yahoo 5분봉에서 오늘 시간외 마지막 값·정규장 기준가·체결 없는 종목 빠짐·
  전날 애프터마켓 무시, 빈 응답/봉 없는 종목 = 오류, 행 종가 대비 등락률, 캐시·실패 미캐시, 대시보드는 extended=False, market/status 의 extended),
  고치기 전 코드로 새 테스트가 실패하는 것 확인, 화면 테스트 69개 (+1: 관심종목 카드·표·사이드바 애프터마켓), `bash scripts/check.sh` 통과.
  **실서버 확인**: 실제 `app.main` + 가짜 KIS(해외 현재가 = 정규장 종가 304.41) + 가짜 Yahoo 5분봉(오늘 19:15 ET 307.5)으로 지금(미국 애프터마켓 시간)
  관심종목 AVGO → 현재가 304.41 + 애프터마켓 307.50 (+1.02%, 한국 09:15), 시간외 체결 없는 AAPL 은 표시 없음, 종목 조회 같음, 빅테크 구역엔 안 붙음,
  `/market/status` US extended = 애프터마켓 06:00~10:00. 빌드 화면에서 로그인 → 관심종목 미국 탭 배지·사이드바 '애프터마켓 중' 확인.
  **실서버 미검증**: 이 환경은 Yahoo 가 막혀 실제 5분봉 prepost 응답으로는 확인 못 함 (대시보드 시간외와 같은 호출 방식)

### 2026-11-26 — 프리·애프터마켓엔 현재가 자리에 그 가격 (종가 대신) (commit `36ebddc`)
- 사용자 의견: 애프터마켓이면 종가 $149.30 -3.91% + 배지 대신 '애프터마켓 $151.68 +1.59%' 만 보이는 게 맞음 (토스처럼) — 동의
- 화면만 바꿈 (서버 응답은 그대로 `daytime{label: 프리마켓/애프터마켓}`): `DaytimePrice.extPrice()`·`SessionTag`.
  관심종목 카드·표(등락률 칸도 시간외 기준), 종목탐색 상세 카드, AI 추천 카드의 현재가·등락률 자리에 '애프터마켓/프리마켓' 표시 + 그 가격·종가 대비 등락률.
  정규장 종가·그날 등락률은 표시(배지)에 마우스를 올리면 보임. 주간거래는 예전처럼 따로 배지 (요청 범위 밖)
- 그대로 둔 것: 투자종목(평가 손익이 정규장 종가 기준이라 섞이지 않게 배지로 따로), 상승 확률·추천 매입가·'현재가 대비 %'는 정규장 종가 기준
- 검증: 화면 테스트 69개 (애프터마켓 테스트를 '현재가 자리 = $307.50, 종가 $304.41·-12.19% 안 보임, 표·종목탐색·AI 추천도 같음, 마우스 올림 안내에 종가'로 강화 —
  고치기 전 화면으로 돌려 실패 확인), `bash scripts/check.sh` 통과 (pytest 252개).
  **실서버 확인**: 실제 `app.main` + 가짜 KIS 종가 + 가짜 Yahoo 시간외 5분봉 + 빌드 화면에서 로그인 → 관심종목 AVGO 현재가 자리 '애프터마켓 $307.50',
  종목탐색 NVDA 상세 API 응답 = 현재가 180.2 + daytime 애프터마켓 181.5 (+0.72%) → 화면은 현재가 자리에 '애프터마켓 $181.50' (같은 응답 모양을 화면 테스트로 확인;
  이 환경은 실제 KIS 가 막혀 PER/PBR 조회가 시간 초과까지 기다려 상세 응답이 4분 걸림 — 실제 PC 에선 해당 없음)

### 2026-11-26 — KIS 잔고 대조: 체결 중 '기준 맞추기'가 수량을 두 번 더하던 버그 + 기준 맞추기 2단계 코드 없앰 (commit `12c1d87`)
- 사용자 화면: 삼립 앱 36 / KIS 24, 인크로스 앱 185 / KIS 183 (보유일 0) + '다를 때마다 2단계 코드가 불편'
- 원인: KIS 잔고에는 체결이 바로 들어오는데 앱 기록은 1분마다 체결 내역으로 반영 → 그 사이 화면에 '다릅니다' → 기준 맞추기를 누르면
  잔고(이미 일부 체결 포함)를 기록으로 삼고, 다음 체결 확인 때 그 체결을 **또 더함** (36 = 먼저 들어온 12 + 주문 24, 185 = 2 + 183)
- 고침 (`kis_trade._sync_fills`): 화면 상태(overview)·매수 직전 대조 전에 체결 내역을 먼저 기록에 반영 / 기준 맞추기 때는 오늘 주문의 체결을 '반영됨'으로만 표시(apply=False)하고 잔고를 기록으로 →
  두 번 안 더함 / 아직 체결 중인 주문이 있는 종목의 차이는 `pending`('(체결 중)', 1분 안에 저절로 맞춰짐 안내, 매수는 그래도 막음)
- 기준 다시 맞추기는 주문을 보내지 않고 앱 기록만 바꿔서 **2단계 코드 없음**(확인 창만, 관리자만) — 사용자 결정. 승인·다시 시작·설정은 그대로 2단계
- 이미 틀어진 기록(삼립 36 등)은 pull 후 '기준 다시 맞추기'를 한 번 누르면 KIS 잔고로 맞춰짐
- 검증: pytest 256개 (+4 `test_kis_trade.py`: 체결 중 기준 맞추기 → 나머지 체결 후 앱=KIS, 체결 확인 전에 화면을 열어도 경고 없음, 잔고만 먼저 바뀐 종목 = pending·직접 산 종목은 아님,
  앞 주문 체결 직후 다음 매수가 '기록 다름'으로 안 막힘 — 고치기 전 코드로 4개 모두 실패 확인), 화면 테스트 70개 (+1 체결 중 안내, 기준 맞추기 코드 칸 없음·코드 안 보냄), `bash scripts/check.sh` 통과.
  **실서버 확인**: 실제 `app.main` + 가짜 KIS 모의투자 서버(주문을 절반만 먼저 체결하게 바꿈)로 코드 없이 기준 맞추기 200 → 삼성전자 18주 승인 → 9주 체결 상태에서 화면 경고 없음 →
  체결 중 기준 맞추기 → 나머지 체결 후 화면 앱 = KIS = 18주·경고 없음·주문 filled 18/18.
  **실서버 미검증**: 실제 KIS 모의 서버에서 잔고와 체결 내역 중 어느 쪽이 먼저 바뀌는지 (어느 쪽이든 1분 안에 맞춰지고, 체결 중이면 '(체결 중)'으로 표시)

### 2026-11-26 — 종목탐색 미국 표(거래대금·급등·급하향·거래량 급증)에도 프리·애프터마켓 가격 (commit `1aac622`)
- 사용자 제보: 종목탐색 상세 카드는 '애프터마켓 $151.58' 인데 아래 표는 엔비디아 $149.30 (종가) 그대로
- `stocks._us_screener_sync`: Yahoo 스크리너 시세의 preMarketPrice·postMarketPrice·Time 을 행의 `_ext` 로 보관 (추가 호출 없음)
- `us_daytime.attach_screener`: 응답 때 지금이 프리/애프터마켓이고 그 시각이 오늘 그 시간대면 `daytime` 으로 (정규장 종가 대비), 시세에 없으면 앞쪽 30종목만 5분봉으로.
  캐시된 행은 안 바꾸고 `_ext` 는 응답에서 뺌. 화면(Screener.tsx): 관심종목과 같이 현재가·등락률 자리에 '애프터마켓' + 그 가격
- 검증: pytest 260개 (+4: 시세 값 사용·어제 값 무시·없으면 5분봉·원본 안 바뀜·장 밖이면 없음·5분봉은 30종목까지·yf.screen 필드 보관·라우트 응답에 _ext 없음 — 고치기 전 코드로 실패 확인),
  화면 테스트 70개 (애프터마켓 테스트에 종목탐색 표: 엔비디아 $151.68 +1.59%, 시간외 없는 마이크론은 종가), `bash scripts/check.sh` 통과.
  **실서버 확인**: 실제 `app.main` + 가짜 yf.screen(엔비디아 postMarketPrice 151.68)·가짜 5분봉, 시간대는 19:40 ET 로 고정(점검 시각에 애프터마켓이 끝나서) →
  /stocks/screener/us/trading_value 엔비디아 149.3 + 애프터마켓 151.68(+1.59%, 5분봉 안 부름), 브로드컴은 5분봉 307.5, 마이크론은 5분봉 없음 → 오류 표시(화면은 종가)
  **실서버 미검증**: 실제 Yahoo 스크리너 응답에 postMarketPrice·preMarketPrice 가 오는지 (안 오면 앞쪽 30종목만 5분봉으로 표시)

### 2026-11-26 — KIS 모의투자: 장중 실시간 감시 · 승인한 매수는 조건 맞으면 지정가 · 자동 손절 · 급변 매수 자동 취소 (commit `09b9735`)
- 사용자 지적: '시장 마지막 가격으로 하루 한 번만 판단하는 건 틀린 방식 — 주식은 장중에 계속 바뀌고 대형 악재·호재로 급등락이 나올 수 있다'.
  사용자 결정(2026-11-26): **손절 매도와 매수 취소는 승인 없이 자동 + 휴대폰 알림**. '무엇을 살지'(AI 판단)는 하루 한 번 그대로 (AI 가 일봉으로 만들어지고 검증됨 — 단타는 비추천으로 설명)
- `kis_trade.watch()` (loop 안 5초마다, 장중 09:01~15:20): KIS 실시간 체결가(kis_ws 구독) → 없으면 REST 멀티종목 시세(15초), 못 받은 종목은 판단 안 함
  - **자동 손절**: 보유 종목이 손절가 이하 → `source="stop"` 시장가 매도 (승인 없음, 하루 주문 횟수에 안 막힘, 긴급 정지 중엔 안 함·하루 손실 한도 정지 중엔 함, 2분 뒤 재시도·하루 3번, 파는 중·결과 모름이면 안 함)
  - 목표가 도달 = 매도 **제안** (예전대로 승인 필요, 거절하면 그날 다시 안 물음)
  - **급변 → 매수 자동 취소**: 제안가 −6%(허용×2) 넘게 하락 · 10분 안 최고가 대비 −3% 넘게 급락 → 승인 대기·조건 대기 매수 취소, 접수된(안 체결) 매수는 KIS 취소. 정지 중이면 접수된 매수도 취소
  - **승인한 매수 = 조건부**: 개장 5분 뒤부터, 제안가 +3% 이하(넘으면 막지 않고 **기다림**), 코스피·코스닥 −2% 이내(못 받아도 기다림), VI·거래 정지 아님(주문 직전 REST 현재가 `vi_cls_code`·`temp_stop_yn`)
    → **지정가** = 현재가 × 1.003 을 호가 단위로 올림 (`kis_order.order(price=)` ORD_DVSN 00, `tick_size`/`tick_up`). 기다리는 이유는 주문 메모에, 감사 로그는 이유가 바뀔 때만
  - 지정가를 KIS 에 미리 걸어 두지 않고 앱이 보다가 보냄 → 서버가 꺼지면 '안 사는 쪽'
- 새 한도 3개 (화면 설정에 자동 표시): 10분 급락 → 매수 취소(3%), 지수 하락 → 매수 보류(2%), 매수 지정가 여유(0.3%). 업데이트 전 DB 는 `_limits()` 가 기본값으로 채움
- `cancel_sent` 고침: 취소 전에 들어온 체결을 먼저 기록하고 취소 요청 시각(`cancel_req`)을 남겨 체결 내역에 반영되면 cancelled/partial — 예전엔 바로 'cancelled' 로 바꿔 **일부 체결분이 앱 기록에서 빠질 수 있었음**
- 새 컬럼 `kis_orders.limit_price`·`cancel_req` (init_db 자동 ALTER), 체결 내역 `cncl_cfrm_qty`
- 알림(ntfy): 자동 손절 매도(긴급) · 매수 자동 취소(높음) · 조건 충족 매수 주문(보통) · 자동 취소 실패(긴급) — 기존 제안·체결·막힘·정지에 더해
- 검증용 시뮬레이션: AI 모의투자 과거 시뮬레이션에 **급변 보호**(`entry_guard`, 기본 켬, 시뮬레이션만) — 시가 +3% 넘게 출발하면 저가가 +3% 까지 올 때 그 값에 삼, −6% 넘게 출발하면 안 삼.
  결과에 '안 산·기다렸다 산 매수' 건수, '기본 방식' 비교에서 같이 꺼짐. 10분 급락·VI·지수 보류는 일봉으로 알 수 없어 시뮬레이션에 없음
- 화면(KisTrade): 설명 문구, 상태 줄 '실시간 감시 5초마다 · N종목 (실시간 체결가 N · REST N · 가격 못 받음 N) · 지수', 자동 규칙 3칸(현재 한도 값으로), '자동 손절'·'장중 목표가' 표시,
  지정가·시장가 표시, 정지 중 '손절 자동 매도는 계속' 여부
- 문서: kis-mock-trading.md (왜 나눴나 · 2-1 장중 감시 규칙 표 · 알림 · 안전장치 · 미검증 항목), CLAUDE.md
- 검증: pytest 277개 (+21 `test_kis_trade.py` 19: 비싸면 기다렸다 내려오면 지정가 71,800 · 급락 자동 취소 · 개장 5분 전 매수 대기/매도는 09:01 · VI·지수 −2.4%·지수 못 받음 대기 ·
  10분 급락 → 조건 대기·접수된 매수 취소(KIS 취소, 알림 1번) · 15분에 걸친 하락은 아님 · 자동 손절(시장가·알림·두 번 안 팖·접수 중 재전송 안 함) · 긴급 정지 중엔 손절 안 함/손실 한도 정지 중엔 함 ·
  손절은 하루 횟수에 안 막힘·2분 뒤 재시도 · 목표가는 제안·거절하면 다시 안 물음 · 가격 못 받으면 판단 안 함 · 손실 한도 정지 → 걸린 매수 취소 · 일부 체결 후 취소 = partial·5주 보유 ·
  예전 DB 한도 기본값 · 실시간→REST 순서·15초·오래된 값 버림 · 지수 둘 중 나쁜 값·60초 캐시·실패 None · 경계값(+3.0% 허용·−2.0% 보류·09:05·−6.0%) · 호가 단위·지정가 요청 형식 /
  `test_papertrade.py` +2: guarded_entry 경계 · 급변 보호 시뮬레이션이 규칙 밖에서 안 삼), 화면 테스트 70개 (감시 줄·자동 규칙·조건 대기 이유·지정가·자동 손절/급변 취소 기록·
  긴급 정지 중 문구 · 시뮬레이션 급변 보호 옵션·결과 건수·실시간 계좌엔 옵션 안 보임), `bash scripts/check.sh` 통과.
  **실서버 확인**: 실제 `app.main` + 가짜 KIS 서버(실제 TR·필드 이름: 현재가 vi_cls_code·멀티종목·업종지수·잔고·주문·취소·체결 cncl_cfrm_qty) + 가짜 ntfy, 실제 장중 시각(11/26 10:55 KST):
  73,000원(+4.3%)에 승인 → 기다림 → 71,000원 → 지정가 71,300원 14주(ORD_DVSN 00) · 000660 180,000원(손절 186,000) → **6초 안에** 승인 없이 시장가 10주 ·
  NAVER 접수 후 200,000 → 193,000 → 자동 취소(KIS 취소 확인) · 코스닥 −2.5% → 매수 보류 · 푸시 5건(매수 주문·자동 손절·체결 2·자동 취소) · 웹소켓 없이 REST 로 동작 ·
  빌드된 화면을 그 서버에 붙여 /kis 열기(콘솔 오류 0) · 서버 로그 Traceback 0
  **실서버 미검증**: 실제 KIS 모의 서버의 지정가 주문·취소 후 체결 내역 값(`rmn_qty`·`cncl_cfrm_qty`), 현재가 `vi_cls_code` 실제 값(VI 때), 장중 실제 웹소켓 체결가로 감시되는지

### 2026-11-26 — KIS 화면: 안전장치·매매 규칙 칸 정렬 · 잔고 조회 EGW00215 재시도 · 실시간 연결 상태 표시 (commit `ddf866c`)
- 사용자 화면 제보: ① 설정 칸이 라벨 길이(범위가 붙어 두 줄이 되는 것) 때문에 입력칸 높이가 들쭉날쭉 → '주문 한도 / 장중 감시 규칙 / AI 매매 규칙' 3묶음,
  이름·범위를 각각 한 줄로 나눠 같은 줄 입력칸 위치가 같게 (매매 규칙 범위는 서버 `param_meta` 로 — 화면에 숫자를 따로 적지 않음)
  ② '잔고를 못 받음: KIS VTTC8434R 실패 (HTTP 500, EGW00215) 원장에서 허용 가능한 초당 거래건수를 초과' → `kis_api._request` 가 EGW00215 를 **조회(GET)만** EGW00201 처럼 기다렸다 재시도 (주문 POST 는 다시 안 보냄)
  ③ 감시 줄이 '실시간 체결가 0 · REST 3' → 왜 실시간이 안 되는지 보이게 `watch.ws`(kis_ws 연결·마지막 오류) 를 상태에 넣고 '실시간 체결가 연결 안 됨 (이유) — REST 시세(15초)로 감시 중' 표시
- 검증: pytest 279개 (+2: EGW00215 조회는 재시도·주문은 1번만(고치기 전 코드면 조회도 실패), 상태에 ws·param_meta), 화면 테스트 70개 (설정 묶음 3개·묶음마다 첫 줄 입력칸 높이 같음·범위 '1 ~ 15'·실시간 연결 안 됨 이유),
  `bash scripts/check.sh` 통과, 스크린샷으로 설정 칸 정렬 확인. **실서버 미검증**: 사용자 서버에서 웹소켓이 왜 0 인지 (이번 표시로 이유 확인 필요)

### 2026-11-26 — 휴대폰 알림을 누르면 웹 화면(그 주문 위치)으로 · KIS 화면 휴대폰용 카드 보기 (commit `5cc9ca1`)
- 사용자 요청: ntfy 알림을 누르면 (앱은 아니어도) 웹 홈페이지로 가서 보게 + 모바일용 화면
- 알림 링크: `notify.app_url(path)` = 사이트 주소(`NTFY_CLICK_URL` 의 주소 부분 → 없으면 클라우드 `DOMAIN` → https://DOMAIN) + 경로.
  KIS 알림은 모두 `/kis?order=번호`(제안·정지는 `/kis`), 알림 시험도 `/kis`. `docker-compose.cloud.yml` 이 `deploy/.env`(DOMAIN) 를 backend 에도 넘김 → 클라우드는 설정 없이 동작 (update.sh 의 `up -d --build` 로 적용).
  예전처럼 NTFY_CLICK_URL 에 경로까지 넣었으면 경로 없는 알림은 그 주소 그대로. 상태 `notify.link` → 화면 '알림을 누르면 주소…' / 없으면 노란 안내
- 로그인이 풀린 채 링크를 열면 `/login?next=원래 주소` → 로그인 후 그 화면으로 (`safeNext`: 사이트 안 경로만 — `//evil.com`·`/\\`·https:// 거부 = 다른 사이트로 보내는 주소 조작 방지)
- KIS 화면 `?order=번호`: 그 주문(진행 중 목록, 끝난 주문이면 주문 기록)으로 스크롤 + 파란 테두리 강조
- 휴대폰 폭(640px 이하, `useNarrow`): 잔고·제안·주문 기록·감사 로그를 표 대신 카드, 자동 규칙은 접기, 설정은 요약 + '설정 보기·바꾸기'(펼치면 2열, 이름 두 줄 높이 고정), 승인 줄은 화면 아래에 붙음
- 검증: pytest 281개 (+2 `test_notify.py`: 주소 모르면 링크 없음·DOMAIN·NTFY_CLICK_URL 우선(경로 무시)·예전 경로 설정 유지·이상한 DOMAIN 거부·KIS 알림이 /kis?order=번호),
  화면 테스트 74개 (+4: 390px 알림 링크 → 그 주문 카드 강조·화면 안·표 없음·규칙/설정 접힘·설정 2열 높이·휴대폰 승인 / 끝난 주문은 기록 카드 강조 / 로그인 풀림 → 로그인 → 그 화면 / next=//evil.com → 첫 화면),
  `bash scripts/check.sh` 통과. **실서버 확인**: 실제 `app.main` + 가짜 KIS·가짜 ntfy, `DOMAIN=mystock.duckdns.org` 로 켜서 알림 시험 click = https://mystock.duckdns.org/kis,
  주문 알림 click = …/kis?order=5 → 빌드된 화면을 390px 로 그 주소 열기: 주문 기록의 #5 카드 강조·화면 안 (처음엔 기록 쪽 강조 표시가 빠져 있던 것을 여기서 찾아 고침), 콘솔 오류 0 · Traceback 0
  **실서버 미검증**: 실제 휴대폰 ntfy 앱에서 알림을 눌렀을 때 브라우저가 열리는지 (Caddy 접속 비밀번호 → 앱 로그인 → 그 화면)

### 2026-11-26 — 휴대폰 화면 다듬기 (전 화면 390px 점검) (commit `3fdfc44`)
- 사용자 요청: 모바일에서 UI 적으로 고치는 게 나은 곳을 찾아서 고치기. 12개 화면을 390px 로 캡처해 보고 고친 것:
  - **경제 캘린더**: 표에서 이벤트 이름이 한 글자씩 세로로 쪼개짐 → 휴대폰은 일정 1개 = 한 칸 (이름·날짜 / 실제·이전·변화, 누르면 해설)
  - **AI 모의투자**: 거래 내역 '매/수' 세로 쪼개짐·보유 종목 표 오른쪽 잘림 → 카드 (거래 = 구분·종목·수익률 / 시각·수량×가격·손익 / 사유)
  - **투자종목**: 수량·평단가·수익률·평가손익·오늘 손익 5칸 고정이라 오른쪽이 잘림 → 폭에 따라 줄바꿈 (휴대폰 3+2칸)
  - **대시보드**: '새로고침' 버튼이 새/로/고/침 세로 → 한 줄 고정 · 빅테크 이름 '브/로드컴' → 종목코드 아래 한 줄
  - **예측 검증**: '예측 방식별 적중률' 6칸 표 제목이 세로로 쪼개짐 → 방식별 카드 (2열 수치)
  - **종목탐색 표**: 이름 '삼성전/자'·'거래대/금' 두 줄, 카드 밖으로 잘림 → 칸 여백 줄이고 한 줄, 빈 칸·추세 아이콘·'관심' 글자 숨김(별 아이콘만), 넘치면 표 안에서만 가로 스크롤
  - **챗봇 버튼**: 54px 가 내용 오른쪽(손절가·버튼)을 가림 → 휴대폰은 44px·가장자리(아이폰 아래 안전 영역 고려), 페이지 아래 여백 72px, 챗봇 창은 화면 폭에 맞춤
- 공통 `components/common/useNarrow.ts` (640px 이하) 를 캘린더·AI 모의투자·예측 검증이 같이 씀
- 검증: 화면 테스트 75개 (+1 '휴대폰 390px': 캘린더 표 없음·이벤트 이름 폭 120px↑·눌러서 해설 / 새로고침 버튼 높이 / 투자종목 '오늘 손익' 칸이 화면 안 / AI 모의투자 표 없음·챗봇 버튼 ≤46px /
  예측 방식 카드 / 종목탐색 이름 한 줄·표가 카드 안 / 빅테크 이름 안 잘림 · 각 화면 가로 스크롤 없음, 기존 '모든 화면 — 모바일' 을 12개 화면으로 늘리고 스크린샷), pytest 281개, `bash scripts/check.sh` 통과.
  고친 뒤 12개 화면 390px 스크린샷을 다시 보고 확인 (API·백엔드 변경 없음 — 화면 배치만)

### 2026-11-26 — Oracle VM 자동 재시도: '응답 시간 초과'에서 멈추던 것 (commit `27e68f2`)
- 사용자 제보: `deploy/oci-launch-retry.sh` 340번째 시도 뒤 `다른 오류 — 중단: "The request timed out. The request may have reached the service and the operation may have completed."`
  → 예전엔 '자리 없음'·429·한도 초과 말고는 전부 중단. 이 오류는 VM 이 실제로 만들어졌을 수도 있는 경우
- 고침: 매 시도 전에 이름(`stock-app`)으로 지워지지 않은 VM 이 있는지 먼저 확인(`find_existing`, TERMINATING 제외) → 있으면 그 VM 으로 공인 IP 단계 (두 번 만들지 않음 — A1 은 무료 한도 안에서 여러 개 만들어질 수 있어서).
  시간 초과·연결 끊김·5xx·InternalError(자리 없음 문구가 아닌 것)는 60초 쉬고 다시, 연속 10번이면 중단. 자리 없음이 오면 연속 횟수 초기화. 그 밖의 모르는 오류는 예전처럼 바로 중단
- 문서: setup-cloud.md (PC 자동 재시도 — 이 오류가 나와도 그대로 두면 됨, 예전 스크립트로 멈췄으면 pull → docker rm → 다시 실행)
- 검증: `bash -n` + 가짜 `oci`·`sleep` 명령(PATH 앞에 둠, 실제 OCI 응답 문구)으로 4가지: ① 자리 없음 → 시간 초과(실제로는 생성됨) → 다시 안 만들고 그 VM·IP (launch 2번) ② 시간 초과 2번(안 만들어짐) → 3번째 성공
  ③ 시간 초과 10번 연속 → 중단(exit 1) ④ 권한 오류 → 바로 중단. `bash scripts/check.sh` 통과 (앱 코드 변경 없음). **실서버 미검증**: 실제 OCI 에서 시간 초과 뒤 instance list 에 바로 보이는지 (안 보이면 다음 시도가 'LimitExceeded' 또는 두 번째 생성 — 1 OCPU/2GB 라 무료 한도 안)

### 2026-11-26 — KIS 모의투자: 장중에도 AI 가 다시 판단해서 좋은 종목이면 매수 제안 (commit `e04abd3`)
- 사용자 요청: "여기도 AI 판단으로 장중 좋은 종목 있으면 제안하게" (KIS 모의투자 'AI 주문 제안' — 예전엔 장 마감 15분 뒤 하루 한 번만)
- `kis_trade.propose_intraday`: 10:00~14:00 를 고르게 나눈 시각(설정 '장중 AI 제안 횟수' `intraday_runs`, 기본 3 = 10:00·12:00·14:00, 0 = 끔, 최대 5)에
  장 마감 후와 **같은 판단 함수**(`papertrade.analyze_live(intraday=True)` → `pe.decide`)로 다시 판단 → **새 매수만** 제안 (`source='intraday'`, 이유 '장중 판단 HH:MM — …', 오늘 15:30 까지 유효, 휴대폰·메일 알림).
  오늘 미완성 봉 = 지금 가격을 종가로, 거래량은 지난 장 시간 비율로 하루치 환산(`project_today`, 최소 10%), 시장 상태(지수)는 확정 종가.
  제외: 보유 · 직전 장 마감 뒤 제안·주문 있었던 종목(어제 저녁 거절 포함) · 오늘 +허용%(3) 넘게 오름 / −허용×2%(6) 넘게 빠짐(`intraday_chase`). 승인 대기·진행 중 매수 = 산 것으로 보고 현금·보유 자리에서 뺌.
  장 마감 후 제안은 만료 안 함. 판단(몇 분)은 잠금 밖 + `schedule_intraday` 가 뒤에서 실행 → 그동안 손절·급변 감시 안 멈춤. 놓친 시각은 한 번으로 합침, 실패해도 그 시각은 다시 안 함
- API: `POST /kis/propose?intraday=true`, 상태에 `intraday {slots, done, running, last, result, error}`. 화면: 장중이면 버튼 '지금 장중 판단', 제안 구역에 오늘 시각(지난 건 줄 긋기)·마지막 결과·실패 사유, 구분 '장중 AI', 설정 묶음 '장중 AI 제안'
- 한계(문서에 적음): AI 는 확정 종가로 만들어지고 검증됨 — 장중 판단은 근사라 덜 검증 (그래서 제안만, 승인 필요). 일봉 시뮬레이션으로는 재현 불가
- 문서: kis-mock-trading.md (2-2 장중 AI 제안 · 하루 흐름 · 미검증), CLAUDE.md
- 검증: pytest 289개 (+8 `test_kis_trade.py`: 제안 시각 나누기·놓친 시각 합침·어제 기록 무시·장 밖/토요일/0=끔 · 추격/급락 경계(+3.0% 허용·−6.0% 허용) ·
  오늘 거래량 환산(절반 시간 → 2배·최소 10%·장 끝/오늘 봉 없음 그대로·원본 안 바꿈) · 새 매수만(보유·제안 중·어제 거절·+5%·점수 낮음 제외, 장 마감 후 제안 그대로, 오늘 15:30 기한, 알림, 다음 판단에서 다시 안 물음, 승인 → 지정가 주문) ·
  승인 대기 매수 몫 현금 예약 · 장 밖·정지 중 거부(진행 중 표시 안 남음) · API `?intraday=true` · 뒤에서 한 번만 실행·설정 0 이면 안 함), 화면 테스트 75개 (장중 제안 줄·버튼 '지금 장중 판단' → `?intraday=true`·설정 묶음 4개·기록 '장중 AI'),
  `bash scripts/check.sh` 통과. **실서버 확인**: 실제 `app.main` + 가짜 KIS 서버(일봉 FHKST03010100 — 오늘 봉 = 지금 가격) + 가짜 지수(Yahoo 막힘), **실제 장중 시각(11/26 14:43 KST)**:
  서버 켜고 20초 뒤 자동으로 놓친 10:00·12:00·14:00 을 한 번으로 실행(약 2분, 25종목) → 'NAVER +5.5% 쫓아가서 안 삼'·'POSCO홀딩스 −7.3% 급락 중' 제외 메모 → '지금 장중 판단' API 72초 → 새 매수 제안 4건(15:30 기한) + 푸시 1건 →
  다시 실행하면 '승인 대기 매수 4건(9,600,000원)은 이미 산 것' · 0건 → 삼성전자 승인(2단계) → 지정가 70,300원 28주(ORD_DVSN 00) → 빌드 화면에 붙여 /kis 열기(장중 제안 줄·버튼·'장중 AI' 표시, 콘솔 오류 0), 서버 Traceback 0
  **실서버 미검증**: 실제 KIS 일봉이 장중에 오늘 봉을 지금 가격으로 주는지(그렇다는 전제 — `_closed_only` 가 그래서 있음), 실제 KIS 로 장중 판단 한 번에 걸리는 시간(일봉 호출 종목당 4번)

### 2026-11-26 — KIS 장중 AI 제안: 하루 3번 → 5분마다 (일봉 하루 한 번 캐시 · 두 번 연속 통과한 종목만) (commit `6a79f45`)
- 사용자 요청: "하루 3번은 너무 적다, 3~5분마다 계속하면 안 돼?"
- 그냥 자주 돌리면 생기는 문제 두 가지를 같이 고침:
  ① 부하 — 예전엔 판단마다 대상 종목 1년치 일봉을 다시 받음(KIS 100~200번, 1~2분). → `papertrade._intraday_stocks`: 지난 일봉은 **하루 첫 판단 때 한 번만** 받아 `_intra` 에 두고,
    판단마다 `quote.live_prices`(웹소켓 → 멀티종목 시세)로 오늘 봉만 고침(종가 = 현재가·고가/저가 넓힘·누적 거래량). 현재가 없는 종목은 뺌, 일봉 실패 종목은 30분 뒤 다시.
    점수는 오늘 행만 계산, 학습형 비중(`_intraday_aw`, 확정 일봉으로)·지수(`_intraday_index`)는 하루 한 번. 날짜가 바뀌면 처음부터
  ② 잡음 — 자주 볼수록 잠깐 튄 가격으로 기준을 넘는 일이 늘어남 → **자동 판단은 두 번 연속 매수 조건을 통과한 종목만 제안** (state `intraday.seen`, 앞 통과가 간격×2.5 안, 한 번 끊기면 처음부터).
    처음 통과한 종목은 '확인 대기'. '지금 장중 판단' 버튼은 바로 제안
- 설정 `intraday_runs`(하루 횟수) → `intraday_every_min` '장중 AI 판단 간격 (분, 0 = 끔)' 기본 5, 0 또는 3~60. 시간 09:30~15:00 (예전 10:00~14:00).
  판단 시작 시각 기준 간격, 앞 판단이 안 끝났으면 안 겹침. 제안이 없으면 판단 기록·감사 로그를 안 남김 (5분마다 쌓이지 않게)
- 상태 `intraday {every, from, to, runs, next, running, last, result, error, notes, waiting, took}`. 화면 '장중 AI 판단' 줄: 간격·오늘 횟수·마지막 결과(걸린 초)·다음 시각·확인 대기 종목
- 검증: pytest 291개 (`test_kis_trade.py` 간격 판단(09:30/15:00 경계·5분·어제 기록·토요일·0=끔·1·2·61 거부·예전 설정 이름 무시) · 첫 통과는 확인 대기·감사 로그 안 남김 → 5분 뒤 제안 ·
  연속 끊김(통과 못 함·20분 빔)이면 처음부터·손으로 누르면 바로 · 예약: 09:30 전 안 함·5분 안 두 번 안 함·몇 초 일찍 허용·진행 중이면 안 겹침·0 이면 안 함·next 시각 /
  `test_papertrade.py` +1: 일봉·지수·비중은 두 번째 판단에서 다시 안 받음·오늘 봉 = 지금 가격·현재가 없는 종목 뺌·일봉 실패 종목만 30분 뒤 다시·날짜 바뀌면 전부 다시),
  화면 테스트 75개 (장중 판단 줄 문구·확인 대기·설정 이름), `bash scripts/check.sh` 통과.
  **실서버 확인**: 실제 `app.main` + 가짜 KIS 서버(일봉·멀티종목 시세) + 가짜 지수, 시계만 오늘 10:00 부터 흐르게(실제 장이 끝나서), 간격 3분: 서버 켜자 자동 판단 1번(일봉 받기 150번 호출, 115초) →
  '확인 대기 4' → 3분 뒤 2번째 판단 **1.1초**·제안 4건 → 3·4번째 1.0~1.1초·0건(이미 제안한 종목 뺌), 일봉 호출은 첫 판단 뒤 0번(멀티종목 시세만), 감사 로그는 제안 때 1줄만,
  빌드 화면을 붙여 /kis '장중 AI 판단 … 3분마다 · 오늘 4번 · 마지막 10:09 … (1초) · 다음 10:12' (콘솔 오류 0), 서버 Traceback 0.
  이 과정에서 고친 것: 예약 시작 시각을 시스템 시계로, 비교는 앱 시계(`_kst`)로 해서 어긋날 수 있던 것 → 둘 다 `_kst()` (실제 운영에선 같은 값이라 영향 없었음)
  **실서버 미검증**: 실제 KIS 로 첫 판단 시간·그 뒤 판단이 몇 초인지, 웹소켓/멀티종목 시세 누적 거래량(`acml_vol`)이 오늘 봉 거래량으로 맞는지
### 2026-11-26 — 투자 대가 포트폴리오 · 가치주 찾기 · 쌍끌이/개미 수급 → AI 추천·퀀트 점수에 반영 (commit `448c063`)
- 사용자 요청: 토스의 '투자 대가의 포트폴리오'·'저평가 성장주/가치주' 같은 기능을 넣고, 대가가 산 종목·가치주를 AI 추천·주식 점수에 반영.
  국내는 외국인·기관 쌍끌이, 개미 투자 동향도
- **투자 대가** (`gurus.py`, 화면 `/gurus`): 버핏·리 루·파브라이·캐시 우드·달리오 등 33명의 SEC 13F 공시 (대가당 최근 8분기).
  CUSIP→티커는 OpenFIGI → 못 찾으면 SEC 공식 회사 목록에서 이름 맞추기. 대가별 비중·신규/추가/축소/전량 매도·최근 1년 추정 수익률(토스 방식),
  '대가들이 산 종목'(보유·이번 분기 산·판 대가 수), **따라 사기 검증**(공시 다음 거래일 종가에 사서 63거래일, S&P500 대비)
- **가치주 찾기** (`fundamentals.py`, 화면 `/value`): 국내 = 네이버 증권 분기 실적으로 TTM PER·PBR·ROE·영업이익률·전년 동분기 성장률·배당을 직접 계산,
  토스식 조건 9개(저평가 성장주·성장 기대주·안정 성장주·아직 저렴한 가치주·고수익 저평가·저평가 탈출·돈 잘 버는 회사·고배당주·흑자 전환).
  미국 = Yahoo 스크리너 조건 8개(Yahoo '저평가 성장주', 미래의 배당왕 = 배당 3년↑ 연속 증가 등)
- **수급 동향** (`flows.py` 확장, 화면 `/flows`): 수급 수집 대상을 추천·관심 종목 → 거래대금 1억↑ 국내 전 종목으로. 쌍끌이(외국인·기관 동반 순매수) 연속 일수,
  외국인/기관/개미 순매수·순매도 상위, 동반 순매도, 날짜별 개인·외국인·기관 합계(개미 동향 막대). 처음 업데이트 뒤엔 `signals.loop` 가 한 번 전 종목 30일치를 받음
- **AI 반영 원칙 — 검증된 것만 점수에, 나머지는 근거로만**:
  ① 퀀트 점수에 일봉 밖 요인 3개 추가 — 가치(E/P·B/P)·수익성(ROE·영업이익률)·수급(전날까지 5일 외국인+기관 순매수 ÷ 거래대금).
  다른 요인처럼 과거 20거래일 뒤 성과와의 순위 상관(IC)이 양수인 만큼만 비중, 검증 날짜 15일 미만이면 0 ('쌓는 중' 표시).
  실적은 **공시 기한 뒤부터** 알려진 것으로 봄(1~3분기 +45일, 4분기 +90일) → 과거 날짜에도 미래 실적 안 씀.
  ② AI 추천 장기 점수 = 기존 점수 + 신호 보정 (`signals.apply_longterm`): 국내 가치·수익성·수급은 퀀트 비중 > 0 일 때만 ±최대 5점,
  미국 대가 신호는 따라 사기 검증 통과(표본 30↑·평균 초과 > 0·이긴 비율 50%↑) 일 때만 0~10점. AI 추천 카드·종목 상세에 대가·PER/PBR/ROE·쌍끌이 배지 + 보정 내역
- 새 파일: `services/gurus.py·fundamentals.py·signals.py`, `routes/signals.py`, 화면 `Gurus·ValueScreens·Flows.tsx`, `SignalBadges.tsx`. 설정 `SEC_USER_AGENT`(선택)
- **실데이터 결과** (이 환경에서 실제 SEC·OpenFIGI·Yahoo·네이버 호출):
  - 13F: 대가 33명 공시 264건, 종목 807개, 처음 수집 약 8분(티커 변환), 그 뒤 34초. 티커 못 찾은 종목 55개(작은 비중)
  - **따라 사기 검증: 855건 — S&P500 대비 평균 −2.15%p, 이긴 비율 42%** (대가 2명↑ 같이 산 종목은 −6.2%p) → 검증 미달이라 **AI 점수엔 안 넣고 근거로만** 표시
  - 국내 재무: 시총 상위 360종목 네이버 분기 실적 31초. Yahoo 일봉으로 만든 퀀트 요인과 합쳐 보니 **가치 요인 IC +0.118 → 비중 약 50%**,
    뒤쪽 기간 검증 상위−하위 +4.3%p (일봉 요인 중엔 안정성만 양수). 실제 KIS 전 종목·수급 요인은 실서버 미검증
- 검증: pytest `test_signals.py` 22개 (13F XML 파싱(옵션·채권 제외·합침)·신규/추가/축소/전량 매도·추정 수익률·오래된 공시 제외 · 따라 사기: 공시 **다음** 거래일 매수·
  보유 끝난 뒤 가격을 바꿔도 결과 같음·기간 안 끝나면 pending·검증 기준·가산점 · 이름 매칭(약어·잘린 이름·클래스 모호·동명 회사) · 네이버 파싱(예상치 제외)·공시 기한·
  **기한 전 날짜는 새 실적을 바꿔도 값 같음** · 조건 검색 · 쌍끌이 연속·문구·순위·개미 합계 · 수급 요인은 **그날 수급을 바꿔도 그날 값 같음** · 전 종목 수집 묶음 저장·덮어쓰기·실패 건너뜀 ·
  퀀트 추가 요인: 날짜 부족이면 비중 0 / 충분하면 비중 · 장기 점수 보정은 비중 > 0 일 때만 · API 9개 경로·404·400·502),
  화면 테스트 +6 (투자 대가 목록·상세·대가들이 산 종목·검증 / 가치주 국내·미국·기억·오류 문구 / 수급 동향 / 추천 카드·종목 상세 배지 / 퀀트 '쌓는 중'),
  퀀트 +1 (저장한 요인 원값으로 다시 계산 — KIS 안 부름·추가 요인 들어감·원값 없으면 안 함), `bash scripts/check.sh` 통과 (pytest 313개, 화면 81개).
  이 과정에서 고친 것: 기존 퀀트 스캔 테스트가 요인 원값 파일을 실제 `app/data` 에 쓰던 것 → 임시 폴더로
  **실서버 확인**: 실제 `app.main`(종목마스터만 작은 목록 — KIS 다운로드가 막혀서) + 위에서 받은 실데이터 → 로그인 → `/api/gurus`·`/gurus/stocks`·`/gurus/buffett`·`/value/KR/…`·
  `/value/US/dividend`(실제 Yahoo)·`/flows/overview`(KIS 막혀 빈 목록 + 안내) 응답 확인, 빌드 화면을 붙여 /gurus·/value·/flows·버핏 상세·검증 탭 열기 (콘솔 오류 0)
  **실서버 미검증**: KIS 로 전 종목 수급 수집(약 1,800번 호출 — 실서버 3~5분, 모의서버는 더 오래)·쌍끌이 목록, 실제 스캔 종가로 계산한 국내 가치주 표, 퀀트 가치·수급 요인 비중

## 알려진 이슈 / 확인 필요
- [ ] **투자 대가·가치주·수급 실서버 미검증** (2026-11-26) — pull 후 서버를 켜고 3~10분 뒤: '투자 대가' 화면에 33명이 뜨는지(처음은 티커 변환 5~10분),
  '가치주 찾기' 국내 표의 PER 이 증권사 앱과 비슷한지(최근 4분기 합 기준이라 앱의 '추정 PER' 과는 다름), '수급 동향' 에 쌍끌이 목록이 뜨는지(18:10 이후 확정치),
  '퀀트 점수' 요인 비중 줄에 가치·수익성·수급이 보이는지 ('쌓는 중' 이면 아직 비중 0). 상태: `/api/signals/status`, `/api/gurus` 의 `status`.
  13F 는 분기 말 기준·최대 45일 늦음, 따라 사기 검증은 최근 2년뿐이라 표본이 작음(지금은 시장보다 못해 점수 미반영). 네이버 분기 실적 API 는 비공식 — 형식이 바뀌면 '재무 표 형식이 예상과 다름'.
  SEC 는 연락처 없는 User-Agent 를 일부 막음 → `.env` 에 `SEC_USER_AGENT=StockApp 본인이메일` 권장. 업종 차이(은행 PBR 등)는 보정 안 함
- [ ] **KIS 실시간 웹소켓 실서버 미검증** — 장중에 관심종목 카드에 '● 실시간' 이 뜨는지 확인. 안 뜨면 로그인 후 `/api/market/scheduler-status` 의 `kis_ws.last_error` (접속키·주소·방화벽 21000/31000 포트). 안 돼도 화면은 예전처럼 REST 가격
- [ ] **KIS 모의투자 주문 실서버 미검증** — 가짜 KIS 서버로만 확인. 처음 연결 후 화면 잔고가 KIS 앱과 같은지, 1주 주문 하나로 승인 → 접수 → 체결 확인 (TR: 주문 VTTC0012U/0011U(예전 0802U/0801U)·잔고 VTTC8434R·체결 VTTC0081R(8001R)·취소 VTTC0013U). 보유 20종목 이상이면 잔고 대조를 멈춤 · 국내만 (미국 모의 주문은 아직)
- [ ] **KIS 장중 감시·지정가·자동 손절 실서버 미검증** (2026-11-26) — 가짜 KIS 서버로만 확인. 장중에 화면 상태 줄이 '실시간 체결가 N' 인지(0 이고 REST 만이면 웹소켓 확인),
  승인한 매수가 '지정가 OOO원' 으로 나가 체결되는지, 접수된 매수를 취소하면 '취소'로 바뀌는지(안 바뀌면 체결 내역 `rmn_qty`·`cncl_cfrm_qty` 형식 확인), VI 때 '변동성 완화장치' 대기가 뜨는지.
  자동 손절은 서버가 켜져 있어야 동작 (서버가 꺼져 있으면 KIS 앱에서 직접 손절)
- [ ] **KIS 장중 AI 제안 실서버 미검증** (2026-11-26) — 장중 화면 '장중 AI 판단' 줄이 5분마다 '오늘 N번 · 마지막 HH:MM … (N초)' 로 바뀌는지 (첫 판단만 1~2분, 그 뒤 몇 초), 실패면 빨간 사유.
  장중 판단은 종가로 검증된 AI 의 근사라 덜 검증됨 — 몇 주 써 보고 장중 제안의 결과가 나쁘면 설정 '장중 AI 판단 간격'을 늘리거나 0 (끔)
- [ ] KIS 순위 API(거래량순위 `FHPST01710000`, 등락률순위 `FHPST01700000`) 파라미터 실서버 검증 필요 — 이제 실패하면 KIS 오류 메시지가 종목탐색 화면에 그대로 뜸
- [ ] KIS 종목마스터 파일 형식(국내 고정폭 227/221자, 미국 탭 구분) 실서버 파일로 검증 필요 — 형식이 다르면 시작 시 "종목마스터 형식이 예상과 다릅니다" 오류
- [ ] 미국 스크리너는 `yf.screen` 필요 → yfinance 0.2.54 이상 (`pip install -r requirements.txt` 가 버전 맞춰 설치)
- [x] ~~테마: 네이버 HTML 화면 방식이 폐지돼 0개~~ → 네이버 증권 모바일 API(JSON)로 변경, 실제 API 로 265개 확인
- [x] ~~테마 목록에 같은 테마가 여러 번 나옴 (네이버 페이지가 등락률 순이라 장중에 어긋남)~~ → 번호로 중복 제거 + 다시 훑기 (2026-11-23)
- [ ] 장기 보유 분석: KIS 월봉(FHKST03010100, 기간 M)·yfinance 월봉(period=max) 실서버 미검증 — pull 후 AI 추천 > 장기투자 추천에서 종목별 표·지수 카드 확인,
  "장기 분석 못한 종목" 이 많으면 원인 문구 확인. 국내는 배당 제외 주가 기준이라 배당주(은행·통신)는 실제보다 낮게 나옴. 후보가 지금 살아남은 유명 종목이라 생존 편향 있음
- [ ] 테마: 네이버 모바일 API 는 공식 공개 API 가 아니라 형식이 바뀔 수 있음 → "테마 목록을 읽지 못함" 오류로 표시. 상태: `/api/themes/status`
- [ ] 매집 탐지: 전 종목 스캔은 KIS 호출이 많음(약 5,000~7,500회/일) — 모의서버는 1시간 이상. 검증 적중률은 현재 상장 종목만이라(상장폐지 빠짐) 조금 좋게 나올 수 있음. 뉴스·공시 같은 급등 재료는 반영 안 함
- [ ] 챗봇은 키워드 규칙이라 표현이 많이 다르면 못 알아듣고 사용법을 보여줌 — 종목명은 정확히(삼성전자, NVDA) 쓰는 게 확실
- [ ] 화면에 먼저 보이는 값은 이전에 받은 값일 수 있음 — 각 화면의 "HH:MM 기준" 시각 확인 (화면을 열면 바로 새로 받아 바꿔 끼움). 서버를 막 켰거나 24시간 넘게 안 열었으면 처음 한 번은 기다림
- [x] ~~국내 AI 추천 첫 로딩 10~20초~~ → 14분마다 백그라운드 미리 계산 (서버 켠 직후 1분 정도만 대기 가능)
- [x] ~~예측은 화면을 열었을 때만 기록됨~~ → 장 마감 후·장 시작 전 자동 기록 (서버가 그 시간에 켜져 있어야 함)
- [x] ~~"하락 우려 해소" 를 악재로 셈~~ → 문구 먼저 판단 (2026-11-20). 키워드 기반이라 정확도 한계는 남음
- [x] ~~네이버 금융 종목뉴스 페이지 410 폐지로 뉴스 조회 실패~~ → 네이버 증권 모바일 API + Google 뉴스 RSS
- [ ] 국내 종목 해외 기사: Yahoo 영문명·종목 뉴스, Google 뉴스 영문 검색은 실서버 미검증. Yahoo 가 막히면 영문명을 못 받아 Google 검색도 안 됨 → 뉴스 요인 미반영 (근거에 사유 표시). 신뢰 매체·언론사 목록은 `news.py` 의 `TRUSTED_FOREIGN`·`TRUSTED_KR` 만 고치면 됨
- [ ] 네이버 증권 모바일 API·Google 뉴스 RSS 는 비공식 — 형식이 바뀌면 "뉴스 조회 실패 — 중립" 표시 (실서버 미검증)
- [ ] FRED·Finnhub·DART 응답은 공식 문서 형식 기준으로 작성, 실제 키로 미검증 — `/api/market/extras-status` 로 확인
- [x] ~~Finnhub 수집 중 표시가 재시작마다 반복~~ → 수집 결과 파일 저장. 처음 설치 후 한 번만 몇 분 "수집 중" 
- [ ] 추천 매입가는 기술적 지지선 기반 참고값 — 실제 체결 보장 아님
- [ ] 백테스트는 가격·거래량·지수 데이터만 사용(뉴스·외부 데이터는 과거 기록 없음) → 실제 예측과 적중률이 다를 수 있음. 일봉은 수정주가라 과거 액면분할 등은 현재 기준으로 보정된 값
- [ ] KIS 초당 호출 제한은 **앱키 단위** — 회사 PC와 집 PC에서 같은 키로 동시에 켜 두면 호출 수가 합쳐져 EGW00201 이 더 자주 남 (한쪽만 켜기)
- [x] ~~SECRET_KEY 예시값이면 첫 실행 시 한 번 로그아웃~~ (지난 업데이트 한정, 해당 없음)
- [ ] **미국 프리·애프터마켓 가격(Yahoo 5분봉) 실서버 미검증** — pull 후 한국시간 06:00~10:00(서머타임 05:00~09:00) 애프터마켓 / 18:00~23:30 프리마켓에 관심종목 미국 탭에 '애프터마켓'·'프리마켓' 배지가 뜨고 증권사 앱 시간외 가격과 비슷한지 확인. 실패하면 배지 자리에 '⚠ 조회 실패'
- [ ] 장 운영 시간(장중 판단)은 정규장 기준 (국내 09:00~15:30, 미국 09:30~16:00 현지) — 미국 시간외는 가격 표시·사이드바 표시만 (예측·모의투자는 정규장 기준). 새해 첫 거래일 10시 개장은 반영, **수능일 개장 지연은 미반영**(날짜가 매년 달라 자동 계산 불가)
- [ ] Docker: Windows 폴더 연결은 파일 감지를 폴링으로 해서 코드 수정 반영이 1초 정도 늦고 CPU 를 조금 더 씀
- [ ] Docker: 패키지 버전은 requirements.txt 범위 안에서 빌드 시점 최신 — 회사 PC(일반 실행)와 pandas 등 버전이 다를 수 있음
- [x] ~~예측 확률 모델은 규칙 기반~~ → 학습 모델 추가 (백테스트에서 이길 때만 사용)
- [ ] 학습 모델은 실데이터로 아직 미검증 — 실제로 규칙보다 나을지는 PC에서 백테스트를 돌려 "예측 방식별 적중률" 로 확인. 하루 단위 주가 방향은 원래 맞히기 어려워 실데이터에선 우연 수준을 못 넘어 미채택될 수 있음 (그 경우 기존 규칙 그대로)
- [ ] 국내 '간밤 미국장 반영' 예측은 08:20~08:58 에 서버가 켜져 있어야 자동 기록됨 (꺼져 있으면 전날 저녁 예측이 채점됨)
- [ ] 뉴스·외부 데이터 보정폭(±2~3%p)은 과거 데이터가 없어 검증 안 된 값
- [ ] 클라우드: Oracle 은 7일간 CPU(p95)·네트워크·메모리(A1만) **모두** 20% 미만이면 VM 회수 → VM 을 1 OCPU/2GB 로 작게 만들어 평소 메모리 사용률(약 35~45%)로 유휴 조건을 피함 (CPU 꼼수 불필요). 일주일 뒤 콘솔 Metrics 의 Memory Utilization 확인 필요. 실제 Oracle VM 에서 미검증(ARM 이미지 빌드 포함)
- [ ] Oracle VM 자동 재시도(PC Docker): 실제 Oracle API 키로 미검증 — "Oracle 로그인(API 키) 실패" 가 뜨면 오류 문구와 `.oci\\config` 의 `key_file=~/.oci/oci_api_key.pem`·`region` 확인. Windows 에서 마운트한 키 파일 권한 경고는 `OCI_CLI_SUPPRESS_FILE_PERMISSIONS_WARNING` 으로 끔
- [ ] 클라우드: 2026-11 무료 가입 목록에 한국 리전이 없음 → 일본 오사카(우선)·도쿄 리전 사용. **해외 IP 에서 KIS API 호출은 미검증** — 설치 직후 setup-cloud.md 의 KIS 확인 명령으로 확인
- [ ] 백테스트가 국내 종목마다 KIS 일봉 800개(호출 8~10회)를 받음 → 1년으로 늘린 뒤 첫 실행은 예전보다 오래 걸림(실서버 5~10분 예상, 이후는 새 날짜만 계산). 실서버 미검증
- [ ] 미국 종목: 현재가는 KIS 해외 현재가(2026-11-25~, 실서버 미검증 — 무료 계정이면 지연 시세일 수 있음), 일봉·지수·대시보드 빅테크/ETF 는 yfinance (장중 15분 지연 가능). KIS 실패 종목은 'Yahoo·지연 가능' 표시
- [ ] 퀀트 점수: 실데이터 미검증 — pull 후 서버 시작 2분 뒤 전 종목 스캔(실서버 약 10분)이 끝나면 '퀀트 점수' 화면의 검증 표에서
  **80~100 구간이 50%보다 꾸준히 높은지** 며칠 확인 (50% 근처면 이 요인들이 지금 시장에서 안 맞는다는 뜻 — 점수를 참고만).
  일봉 200개라 RS 는 12개월이 아니라 1·3·6개월, 검증 기간 약 1~2개월로 짧음. 미국 종목은 전 종목 스캔이 없어 퀀트 점수 없음. 업종 안 비교·재무(가치·성장·수익성) 요인은 아직 없음
- [ ] 시장 상태: Yahoo 지수 일봉(5년) 실서버 미검증 — 코스피·코스닥 Yahoo 거래량이 0 이면 분산일 표시 안 됨. Yahoo 가 하루 늦으면 '최신 아님' 표시
- [ ] 메일 발송(네이버 SMTP) 실서버 미검증 — `.env` 에 SMTP_* 를 넣고 회원가입 '인증 코드 받기'로 확인. "메일 계정 로그인 실패"면 네이버 'SMTP 사용' 설정·애플리케이션 비밀번호 확인,
  Oracle 에서 465 가 막히면 `SMTP_PORT=587`. 메일이 스팸함으로 갈 수 있음
- [x] ~~회원가입이 열려 있음(이메일 인증만)~~ → 관리자가 만든 초대 코드가 있어야 가입 (2026-11-25). 초대한 사람도 내 KIS 키·호출 한도를 같이 씀
- [ ] 2단계 인증 필수로 바뀌기 전 만든 계정은 첫 로그인 때 등록 — **업데이트 직후 바로 등록**할 것 (등록 전에는 비밀번호를 아는 사람이 먼저 등록해 버릴 수 있는 틈).
  예전 '누구나 가입' 때 만든 모르는 계정이 있으면 마이페이지 → 관리자 → 회원 목록에서 차단. 관리자가 없던 DB 는 가장 먼저 만든 계정이 관리자가 됨 — 다르면 `create_admin.py --admin <아이디>`
- [ ] 기존 계정은 이메일·휴대폰이 없음 → 마이페이지에서 둘 중 하나를 인증해 둬야 '비밀번호 찾기'를 쓸 수 있음 (상단 바 이름 옆 노란 점)
- [ ] 휴대폰 문자(솔라피) 실서버 미검증 — 솔라피 가입·충전·**발신번호 등록** 후 `.env` 에 SMS_* 를 넣고 회원가입 '휴대폰으로 인증'으로 확인.
  "문자 접수 실패"면 SMS_FROM 이 솔라피에 등록한 번호인지·잔액, "계정 인증 실패"면 키 확인. 휴대폰 가입은 '문자 받을 수 있는 번호'만 확인하며 실명 본인확인(PASS·NICE)은 아님
- [ ] 로그인 기록은 이번 업데이트 이후부터 쌓임. IP 는 클라우드에선 Caddy 가 넘긴 실제 IP, PC 직접 실행은 127.0.0.1
- [ ] 미국 주간거래 가격(KIS HHDFS00000300, EXCD=BAQ/BAY/BAA): **실서버 미검증** — pull 후 한국 10:00~18:00 에 관심종목 미국 탭에서
  `주간거래 $가격` 이 토스와 비슷한지 확인. "주간거래 ⚠ 조회 실패" 가 뜨면 마우스를 올려 KIS 오류 문구 확인 (모의서버 `KIS_IS_REAL=false` 는 주간거래 시세를 안 줄 수 있음).
  주간거래 휴장(블루오션 사정)은 KIS 가 체결 없음으로 주면 표시 안 됨. 시간은 '조회 시각'(KIS 응답에 체결 시각 없음)
- [x] ~~경제 캘린더 실제·이전 값이 '-' 로만 보임 (업데이트 전 저장본이 1시간 동안 그대로)~~ → 저장본은 화면을 열면 항상 새로 받음 (2026-11-23)
- [x] ~~AI 챗봇은 Claude API 유료·미검증~~ → 규칙 기반 챗봇으로 교체 (2026-11-23, 외부 API·과금 없음)
- [x] ~~챗봇 답변 10~60초 대기~~ → 규칙 기반이라 캐시된 데이터면 수 ms
- [ ] KIS 투자자(FHKST01010900) 응답 필드(stck_bsop_date·frgn_ntby_qty·orgn_ntby_qty·prsn_ntby_qty) 실서버 미검증 — `/api/market/scheduler-status` 의 flows.errors 확인
- [ ] 수급 모델은 데이터가 2~3개월 쌓일 때까지 학습 안 됨. 서버가 18:10~18:50 에 꺼져 있던 날은 다음 백테스트(또는 다음 날 수집) 때 최근 30일 범위 안이면 채워짐
- [ ] 한국은행 금통위 일정은 무료 공식 데이터 출처가 없어 이벤트 경고에 없음
- [ ] KIS 멀티종목 시세(FHKST11300006) 응답 필드(inter_shrn_iscd·inter2_prpr·prdy_ctrt) 실서버 미검증 — 안 맞으면 로그 `[quote] 멀티종목 시세 실패` 후 종목별 조회로 동작(느리지만 정상)
- [ ] FRED 발표 일정의 release_name 비교 실서버 미검증 — 이름이 다르면 그 지표만 안 보임
- [x] ~~경제 캘린더·이벤트 경고에 FOMC 가 매일 나옴 (FRED 의 FOMC 항목은 매일 갱신 데이터)~~ → 연준 공식 일정 페이지로 변경 (2026-11-23)
- [ ] FOMC 일정은 연준 웹페이지 HTML 을 읽음 — 형식이 바뀌면 캘린더에 "FOMC 일정(연준): 회의 날짜를 찾지 못함" 표시. FRED 키로 경제 캘린더 전체를 실서버에서 확인 필요 (pull 후 `/calendar` 에서 FOMC 가 12-09 하루만 나오는지)
- [x] ~~경제 캘린더 발표치가 비어 있음~~ → FRED 실제 발표값·이전·변화·해설 (2026-11-23). 예상치(컨센서스)는 무료 공식 출처가 없어 빼기로 함 (Finnhub 는 유료 403 확인)
- [ ] 경제 캘린더 발표값: FRED 발표일 기준(vintage) 조회 실서버 미검증 — pull 후 `/calendar` 최근 발표에 실제·이전 값이 나오는지, "아직 반영 전"만 계속 나오면 알려 주세요.
  미시간대 소비자심리(UMCSENT)는 FRED 에 늦게 올라올 수 있어 값 없음이 나올 수 있음
- [ ] KIS 업종 현재지수(FHPUP02100000) 응답 필드(bstp_nmix_prpr 등) 실서버 미검증 — 대시보드 코스피 카드가 "조회 실패"면 원인 메시지 확인
- [ ] 대시보드 해외 지수(다우·S&P·나스닥·SOX·VIX 등)는 여전히 Yahoo — 날짜가 늦으면 카드에 "⚠ 최신 아님" 표시
- [x] ~~미국 PER/PBR 0 표시~~ → KIS 해외주식 현재가상세. **응답 필드(perx·pbrx) 실서버 미검증** — 안 나오면 로그 `[quote] ... PER/PBR 조회 실패` 확인
- [x] ~~투자종목 합계 KR(₩)+US($) 환율 없이 합산~~ → 통화별 분리 + 원화 환산 총합
- [x] ~~단기 추천 KOSDAQ fallback 동기 호출~~ → 국내는 KIS로 조회해서 해당 없음
- [x] ~~국내 추천 가격이 yfinance 종가~~ → KIS 실시간
- [x] ~~국내 PER/PBR 0 고정~~ → KIS 값 사용
- [x] ~~AI 모의투자 과거 시뮬레이션 "database is locked" (첫 1년 백테스트 저장과 겹칠 때)~~ → 나눠 저장 + 대기 30초 + 재시도 (2026-11-25)
- [ ] 보안 기능 실서버 미검증: 유출 비밀번호 확인(api.pwnedpasswords.com — 서버에서 막히면 로그 `[pwned] ... 확인 실패 (건너뜀)` 이고 기능만 꺼진 채 동작),
  새 IP·계정 잠금 알림 메일(SMTP 설정·이메일 인증 필요), 우분투 VM 의 unattended-upgrades·SSH 점검 단계. IP 차단 기록은 메모리라 서버를 다시 켜면 풀림 (계정 잠금은 2026-11-25 부터 DB 에 남음)
- [ ] AI 모의투자 개선 옵션(학습형 가중치·추세 필터)은 무작위 가짜 데이터로만 돌려 봄 — 실제 데이터에서 나은지는 과거 시뮬레이션의 '개선 옵션 효과' 표로
  국내·미국, 3개월·1년·2년을 몇 번 비교해 확인. 기본 방식이 계속 낫다면 설정에서 끄기. 추세 필터는 하락장에서 거래가 크게 줄어듦
- [ ] AI 모의투자 실서버 미검증 — pull 후 'AI 모의투자 > 과거 시뮬레이션'에서 국내·미국 1년을 돌려 보고 "일봉 못 받은 종목" 경고·지수 비교가 정상인지,
  '실시간 모의투자' 계좌를 만들어 다음 개장 1분 뒤 대기 주문이 체결되는지(판단 기록에 '체결') 확인. 서버가 꺼져 있던 시간의 체결·손절은 하지 않음(켜진 뒤 다음 시점에)
- [ ] AI 모의투자 한계: 과거 시뮬레이션은 현재 상장된 AI 추천 후보(유명 대형주)만이라 생존 편향이 있음 — 실제보다 좋게 나올 수 있음. 뉴스·공시·학습 모델은 과거 시뮬레이션에 없음
  (학습 모델은 최근 2년으로 학습돼 과거에 쓰면 미래를 본 셈). 체결은 시가·현재가 + 슬리피지 0.05% 가정이라 실제 호가·거래 정지·상하한가는 반영 안 됨. 국내 거래세 0.20% 가정
- [ ] AI 모의투자 실시간 체결가: 국내 KIS 현재가(실시간 웹소켓 값 우선), 미국 KIS 해외 현재가 (KIS 실패 종목만 yfinance 1분봉 — 최대 15분 지연)
- [x] ~~경제 캘린더 "발표값 조회 실패 — HTTP 400 (realtime_start can not be after today)"~~ → 미국(FRED) 날짜 기준으로 판단 (2026-11-25)

## 다음 할 일 후보

- [x] ~~예측 검증 결과로 지표 가중치 조정 (적중률 낮은 요인 비중 축소)~~ → `factor_weights.py` (2026-11-25)
- [x] ~~KIS 실시간 웹소켓으로 현재가 수신 (지금은 15초 폴링)~~ → `kis_ws.py` 국내 실시간 체결가 (2026-11-25, 미국은 아직 REST·yfinance)
- [x] ~~미국 시세도 KIS 해외시세로 전환 검토~~ → 현재가만 KIS (2026-11-25). 일봉·지수는 Yahoo 유지 (여러 종목·수년 치를 한 번에, KIS 호출 한도 아낌)
- Electron 데스크탑 래퍼
