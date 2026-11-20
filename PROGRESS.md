# PROGRESS.md

작업 이력과 자주 쓰는 명령어를 관리하는 파일. 작업이 끝날 때마다 갱신한다.

## 자주 쓰는 명령어

### 최신 코드 받기 (로컬 PC, 작업 전 필수)
```powershell
cd C:\claude\stock_app
git pull origin claude/dazzling-darwin-et76zj
```
로컬 변경사항 때문에 pull이 막히면:
```powershell
git stash
git pull origin claude/dazzling-darwin-et76zj
```
pull 후 `requirements.txt`가 바뀌었으면 패키지 갱신 (백엔드 .venv 활성화 상태에서):
```powershell
cd C:\claude\stock_app\backend
pip install -r requirements.txt --upgrade
```

### 서버 실행
```powershell
# 백엔드
cd C:\claude\stock_app\backend
.venv\Scripts\Activate
python -m uvicorn app.main:app --reload --port 8000

# 프론트엔드 (frontend/ 에서, 별도 터미널)
npm run dev
```
또는 루트의 `start.bat` 더블클릭.

### 최초 설치
```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate
pip install -r requirements.txt
pip install "sqlalchemy[asyncio]" "bcrypt==4.0.1"
cp .env.example .env
python create_admin.py <아이디> <비밀번호>   # 이미 계정이 있으면 UNIQUE 에러 → 재실행 불필요
```

### 다른 PC로 옮기기
git으로 안 넘어가는 파일(.gitignore 대상)은 직접 복사해야 한다:
- `backend\.env` — KIS 키·계좌번호·SECRET_KEY. **절대 커밋 금지**
- `backend\stock_app.db` — 로그인 계정, 관심종목, 투자종목 데이터 (안 옮기면 `create_admin.py`로 계정 새로 생성)
- `.venv`, `node_modules` — 복사하지 말고 새 PC에서 "최초 설치" 절차로 재설치
```powershell
cd C:\claude
git clone -b claude/dazzling-darwin-et76zj https://github.com/csb0012/stock_app.git
# 이후 .env, stock_app.db 를 backend\ 에 복사 → 최초 설치 절차 진행
```

### 점검용
- KIS 연결 테스트: `http://localhost:8000/api/stocks/test/kis`
- 종목 검색 테스트: `http://localhost:8000/api/stocks/search?q=삼성전자`
- 백엔드가 `KIS_APP_KEY 가 backend/.env 에 설정되지 않았습니다` 로 안 뜨면 → `backend\.env` 확인
- 종목마스터 캐시: `backend\app\data\master_cache.json` (하루 1회 KIS에서 자동 갱신, 지우면 다음 실행 때 다시 받음)
- 헬스체크: `http://localhost:8000/api/health`
- API 문서: `http://localhost:8000/docs`

## 작업 이력

### 2026-11 — 초기 셋업 & 버그 수정
- `create_admin.py` 재실행 시 UNIQUE 에러 → 계정 이미 존재, 재실행 불필요
- `/api/stocks/test/kis` 404 → 로컬 코드가 구버전, `git pull`로 해결
- CLAUDE.md 생성 (한국어)
- **추천 전부 50% 표시 버그**: pandas-ta 버전별 볼린저밴드 컬럼명 차이(`BBU_20_2.0` KeyError) → `analysis.py`에서 `startswith("BBU_")`로 동적 탐색

### 2026-11 — 기능 추가 1차
- 관심종목 추가 모달에 자동완성 검색 (한글/영문/코드) — `backend/app/data/stock_list.json` + `GET /api/stocks/search`
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

## 알려진 이슈 / 확인 필요
- [ ] KIS 순위 API(거래량순위 `FHPST01710000`, 등락률순위 `FHPST01700000`) 파라미터 실서버 검증 필요 — 이제 실패하면 KIS 오류 메시지가 종목탐색 화면에 그대로 뜸
- [ ] KIS 종목마스터 파일 형식(국내 고정폭 227/221자, 미국 탭 구분) 실서버 파일로 검증 필요 — 형식이 다르면 시작 시 "종목마스터 형식이 예상과 다릅니다" 오류
- [ ] 미국 스크리너는 `yf.screen` 필요 → yfinance 0.2.54 이상 (`pip install -r requirements.txt --upgrade`)
- [ ] 국내 AI 추천은 KIS를 종목마다 호출해서 첫 로딩 10초 내외 (15분 캐시)
- [ ] 미국 종목 가격은 yfinance 기준 (장중 15분 지연 가능), PER/PBR 0 표시
- [x] ~~투자종목 합계 KR(₩)+US($) 환율 없이 합산~~ → 통화별 분리 + 원화 환산 총합
- [x] ~~단기 추천 KOSDAQ fallback 동기 호출~~ → 국내는 KIS로 조회해서 해당 없음
- [x] ~~국내 추천 가격이 yfinance 종가~~ → KIS 실시간
- [x] ~~국내 PER/PBR 0 고정~~ → KIS 값 사용

## 다음 할 일 후보
- KIS 토큰을 파일에 저장 (uvicorn --reload 재시작마다 재발급 → 1분 1회 발급 제한에 걸릴 수 있음)
- 미국 시세도 KIS 해외시세로 전환 검토
- Electron 데스크탑 래퍼
