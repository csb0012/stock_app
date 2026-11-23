# 설치·실행 — 직접 설치 방식 (회사 PC)

Python 3.13 과 Node.js 를 PC에 직접 설치하고, 가상환경(venv)에서 실행한다.

> Python 버전 맞추기가 번거로우면 [setup-docker.md](setup-docker.md) (Docker 방식) — 두 방법을 섞지 말 것.

---

## 처음 한 번 (설치)

### 1. 프로그램 3개 설치 — Git, Python 3.13, Node.js LTS
PowerShell 에서 (Visual Studio 는 필요 없음):
```powershell
winget install --id Git.Git -e
```
```powershell
winget install --id Python.Python.3.13 -e
```
```powershell
winget install --id OpenJS.NodeJS.LTS -e
```
`winget` 이 없으면 직접 설치: Git for Windows / Python 3.13 (설치 첫 화면 **"Add python.exe to PATH" 체크**) / Node.js LTS.

PowerShell 을 **새로 열고** 확인:
```powershell
git --version
python --version
node --version
```

### 2. 코드 받기
```powershell
mkdir C:\claude
cd C:\claude
git clone -b claude/dazzling-darwin-et76zj https://github.com/csb0012/stock_app.git
```

### 3. 비밀·데이터 파일 → `C:\claude\stock_app\backend\`
- 다른 PC에서 옮길 때: `.env`, `stock_app.db`, `.secret_key`(있으면) 복사
- 처음 만드는 경우: `backend\.env.example` 을 `backend\.env` 로 복사해서 KIS 키·계좌번호 입력

### 4. 백엔드 패키지 — 가상환경은 루트 `C:\claude\stock_app\.venv`
```powershell
cd C:\claude\stock_app
python -m venv .venv
.venv\Scripts\Activate
cd backend
pip install -r requirements.txt
```
`Activate` 에서 "스크립트를 실행할 수 없습니다" 가 나오면 한 번만:
```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```
DB 를 안 옮겼다면 계정 만들기 (가상환경 켜진 상태, backend 폴더에서):
```powershell
python create_admin.py <아이디> <비밀번호>
```

### 5. 프론트엔드 패키지 (새 PowerShell 창)
```powershell
cd C:\claude\stock_app\frontend
npm install
```

### 6. 실행
`C:\claude\stock_app\start.bat` 더블클릭 → 브라우저 `http://localhost:5173`

최종 폴더 구조:
```
C:\claude\stock_app\
├─ .venv\                ← 4번에서 생성
├─ start.bat             ← 이걸로 실행
├─ backend\
│  ├─ .env
│  ├─ stock_app.db
│  └─ .secret_key        (있으면)
└─ frontend\
   └─ node_modules\      ← 5번에서 생성
```

---

## 매일 쓰는 명령

**켜기:** `start.bat` 더블클릭 (가상환경 자동 활성화). 수동으로 켜려면:
```powershell
cd C:\claude\stock_app
.venv\Scripts\Activate
cd backend
python -m uvicorn app.main:app --reload --port 8000
```
```powershell
cd C:\claude\stock_app\frontend
npm run dev
```

**최신 코드 받기:**
```powershell
cd C:\claude\stock_app
git pull origin claude/dazzling-darwin-et76zj
```
push 된 코드는 테스트를 마친 것이다 (수정 → 충분한 테스트 → push → pull, [PROGRESS.md](../PROGRESS.md) 맨 위 규칙). pull 후 화면이 이상하면 PROGRESS.md 의 최근 작업 이력 `검증:` 줄과 "알려진 이슈"의 실서버 미검증 항목부터 확인한다.

pull 후 `requirements.txt` 가 바뀌었으면 (가상환경 켜진 상태):
```powershell
cd C:\claude\stock_app\backend
pip install -r requirements.txt
```
⚠️ `--upgrade` 붙이지 말 것 — bcrypt 가 5.x 로 올라가 로그인이 500 오류로 깨짐. 로그인이 갑자기 안 되면 `pip install "bcrypt==4.0.1"` 후 재시작.

pull 후 `package.json` 이 바뀌었으면:
```powershell
cd C:\claude\stock_app\frontend
npm install
```

**계정 추가:** 가상환경 켜고 `cd C:\claude\stock_app\backend` 후 `python create_admin.py <아이디> <비밀번호>`
