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
pip install -r requirements.txt
```
⚠️ `--upgrade` 붙이지 말 것 — bcrypt가 5.x로 올라가 로그인이 500 오류로 깨짐 (requirements에 `bcrypt==4.0.1` 고정해 둠)
로그인이 갑자기 안 되면: `pip install "bcrypt==4.0.1"` 후 백엔드 재시작

### 서버 실행
```powershell
# 백엔드 (가상환경은 루트 C:\claude\stock_app\.venv)
cd C:\claude\stock_app
.venv\Scripts\Activate
cd backend
python -m uvicorn app.main:app --reload --port 8000

# 프론트엔드 (별도 터미널)
cd C:\claude\stock_app\frontend
npm run dev
```
또는 루트의 `start.bat` 더블클릭 — 가상환경(루트 `.venv` 또는 `backend\.venv`)을 자동으로 켜고, 백엔드는 `127.0.0.1` 로만 열림.

### 새 PC 설치 (처음부터) — 회사 PC와 같은 구조로 맞춤
**0) 프로그램 설치** (Visual Studio 는 실행에 필요 없음). PowerShell 에서:
```powershell
winget install --id Git.Git -e
winget install --id Python.Python.3.13 -e
winget install --id OpenJS.NodeJS.LTS -e
```
winget 이 안 되면 직접 설치: Git for Windows / Python 3.13 (설치 첫 화면 **"Add python.exe to PATH" 체크**) / Node.js LTS.
설치 후 **PowerShell 을 새로 열고** 확인:
```powershell
git --version
python --version
node --version
```
PowerShell 에서 `.venv\Scripts\Activate` 가 "스크립트를 실행할 수 없습니다" 로 막히면 (한 번만):
```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

**1) 코드 받기** (저장소가 비공개면 GitHub 로그인 창이 뜸)
```powershell
mkdir C:\claude
cd C:\claude
git clone -b claude/dazzling-darwin-et76zj https://github.com/csb0012/stock_app.git
```

**2) git 으로 안 넘어오는 파일 복사** — 회사 PC에서 USB/메신저로 가져와 **`C:\claude\stock_app\backend\`** 에 넣기
- `backend\.env` — KIS 키·계좌번호·SECRET_KEY (필수, **절대 커밋 금지**)
- `backend\stock_app.db` — 로그인 계정, 관심종목, 투자종목, 예측 검증 기록 (안 옮기면 4번에서 계정 새로 생성)
- `backend\.secret_key` — 회사 PC에 이 파일이 있으면 같이 복사 (없으면 자동 생성되고 한 번 재로그인)
- 복사하지 않는 것: `.venv`, `node_modules` (새로 설치), `.kis_token.json`·`master_cache.json` (자동 생성)

**3) 백엔드 패키지** — 가상환경은 회사 PC와 같이 루트(`C:\claude\stock_app\.venv`)에 만든다
```powershell
cd C:\claude\stock_app
python -m venv .venv
.venv\Scripts\Activate
cd backend
pip install -r requirements.txt
```

**4) (DB 를 안 옮겼을 때만) 계정 만들기**
```powershell
python create_admin.py <아이디> <비밀번호>
```

**5) 프론트엔드 패키지** (새 PowerShell 창)
```powershell
cd C:\claude\stock_app\frontend
npm install
```

**6) 실행** — `C:\claude\stock_app\start.bat` 더블클릭 → 브라우저에서 `http://localhost:5173`

최종 폴더 구조:
```
C:\claude\stock_app\
├─ .venv\                 ← 3번에서 생성
├─ start.bat
├─ backend\
│  ├─ .env                ← 회사 PC에서 복사
│  ├─ stock_app.db        ← 회사 PC에서 복사
│  ├─ .secret_key         ← 있으면 복사
│  └─ app\ ...
└─ frontend\
   └─ node_modules\       ← 5번에서 생성
```

### 점검용
- KIS 연결 테스트: `http://localhost:8000/api/stocks/test/kis`
- 종목 검색 테스트: `http://localhost:8000/api/stocks/search?q=삼성전자`
- 백엔드가 `KIS_APP_KEY 가 backend/.env 에 설정되지 않았습니다` 로 안 뜨면 → `backend\.env` 확인
- 종목마스터 캐시: `backend\app\data\master_cache.json` (하루 1회 KIS에서 자동 갱신, 지우면 다음 실행 때 다시 받음)
- KIS 토큰 저장 파일: `backend\.kis_token.json` (재시작해도 23시간 재사용. 키를 바꾸면 자동으로 새로 받음)
- 예측 검증 API: `http://localhost:8000/api/predictions/review?days=30` (호출 시 장 끝난 예측 채점)
- 백엔드 시작 로그 `[repair] 종목코드 복구 ...` = 잘못 저장된 종목코드를 자동으로 고친 것
- 장 운영 상태: `http://localhost:8000/api/market/status` (사이드바 하단에도 표시)
- 로그인 토큰 서명 키: `backend\.secret_key` (`.env` 의 SECRET_KEY 가 예시값이면 자동 생성. 다른 PC로 옮길 때 같이 복사하면 재로그인 불필요)
- 계정 추가: 회원가입 API는 계정이 하나라도 있으면 막힘 → `cd backend` 후 `python create_admin.py <아이디> <비밀번호>`
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

## 알려진 이슈 / 확인 필요
- [ ] KIS 순위 API(거래량순위 `FHPST01710000`, 등락률순위 `FHPST01700000`) 파라미터 실서버 검증 필요 — 이제 실패하면 KIS 오류 메시지가 종목탐색 화면에 그대로 뜸
- [ ] KIS 종목마스터 파일 형식(국내 고정폭 227/221자, 미국 탭 구분) 실서버 파일로 검증 필요 — 형식이 다르면 시작 시 "종목마스터 형식이 예상과 다릅니다" 오류
- [ ] 미국 스크리너는 `yf.screen` 필요 → yfinance 0.2.54 이상 (`pip install -r requirements.txt` 가 버전 맞춰 설치)
- [ ] 국내 AI 추천은 KIS를 종목마다 호출해서 첫 로딩 10~20초 (이후 15초 갱신은 현재가만 받아 빠름)
- [ ] 예측은 화면을 열었을 때만 기록됨 — 장 마감 후 앱을 안 열면 장중 마지막으로 본 확률이 채점 대상
- [ ] 뉴스 분위기는 키워드 개수 기반이라 정확도 한계 있음 (예: "하락 우려 해소" 를 악재로 셀 수 있음)
- [ ] 네이버 금융 뉴스 페이지 구조가 바뀌면 뉴스 요인이 "뉴스 조회 실패 — 중립"으로 표시됨
- [ ] 이번 업데이트 후 첫 실행 시 SECRET_KEY 가 예시값이었다면 한 번 로그아웃됨 (정상)
- [ ] 장 운영 시간은 정규장 기준 (국내 09:00~15:30, 미국 09:30~16:00 현지) — 시간외·프리마켓 미반영, 국내 수능일 등 개장 지연 미반영
- [ ] 예측 확률 모델은 규칙 기반 — "예측 검증 > 지표별 적중률" 이 쌓이면 가중치 조정 필요
- [ ] 미국 종목 가격은 yfinance 기준 (장중 15분 지연 가능), PER/PBR 0 표시
- [x] ~~투자종목 합계 KR(₩)+US($) 환율 없이 합산~~ → 통화별 분리 + 원화 환산 총합
- [x] ~~단기 추천 KOSDAQ fallback 동기 호출~~ → 국내는 KIS로 조회해서 해당 없음
- [x] ~~국내 추천 가격이 yfinance 종가~~ → KIS 실시간
- [x] ~~국내 PER/PBR 0 고정~~ → KIS 값 사용

## 다음 할 일 후보
- 예측 검증 결과로 지표 가중치 조정 (적중률 낮은 요인 비중 축소)
- KIS 실시간 웹소켓으로 현재가 수신 (지금은 15초 폴링)
- 미국 시세도 KIS 해외시세로 전환 검토
- Electron 데스크탑 래퍼
