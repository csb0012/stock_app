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

### 점검용
- KIS 연결 테스트: `http://localhost:8000/api/stocks/test/kis`
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

## 알려진 이슈 / 확인 필요
- [ ] KIS 급등/급하향 API(`FHPST01700000`, `/ranking/fluctuation`) 및 거래대금(`FID_DIV_CLS_CODE=1`) 파라미터 실서버 검증 안 됨 — 실패 시 yfinance fallback으로 동작
- [ ] 투자종목 상단 합계가 KR(₩)과 US($)를 환율 변환 없이 그대로 합산함 → 환율 적용 필요
- [ ] 단기 추천에서 KOSDAQ fallback(`.KQ`) 다운로드가 동기 호출이라 응답이 느려질 수 있음
- [ ] 추천 가격은 yfinance 종가 기준(장중 실시간 아님)
- [ ] PER/PBR이 추천에서 0으로 고정됨 (yfinance 배치 전환으로 KIS 값 미사용)

## 다음 할 일 후보
- 투자종목 합계 환율 반영
- Electron 데스크탑 래퍼
