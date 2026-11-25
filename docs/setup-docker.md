# 설치·실행 — Docker 방식 (집 PC)

**Python·Node.js 를 PC에 설치하지 않는다.** venv(`python -m venv`), `pip install`, `npm install` 도 하지 않는다.
Python 3.13 / Node 22 는 Docker 이미지 안에 들어 있다.

> 회사 PC처럼 Python 을 직접 설치해서 쓰는 방법은 [setup-local.md](setup-local.md) — 두 방법을 섞지 말 것.

---

## 처음 한 번 (설치)

### 1. 프로그램 2개 설치 — Docker Desktop, Git
PowerShell 에서:
```powershell
winget install --id Docker.DockerDesktop -e
```
```powershell
winget install --id Git.Git -e
```
`winget` 을 찾을 수 없다고 나오면 직접 받아서 설치:
- Docker Desktop: https://www.docker.com/products/docker-desktop/ → Download for Windows **AMD64** (Intel·AMD CPU 모두 AMD64, 스냅드래곤 노트북만 ARM64)
- Git: https://git-scm.com/download/win → 설치 화면 기본값으로 Next

Docker Desktop 설치가 `"Virtual Machine Platform" ... is not enabled` 로 실패하면:
**관리자 권한** PowerShell(시작 → powershell → 관리자 권한으로 실행)에서 아래 실행 → **재부팅** → 설치 파일 다시 실행
```powershell
wsl --install
```
재부팅 후에도 가상화 오류가 나면: 작업 관리자 → 성능 → CPU → "가상화: 사용" 인지 확인, 아니면 BIOS 에서 Intel VT-x / AMD SVM 켜기.

### 2. Docker Desktop 켜기
시작 메뉴 → Docker Desktop 실행 → 왼쪽 아래 **"Engine running"** 될 때까지 대기.
PowerShell 을 **새로 열고** 확인:
```powershell
git --version
docker --version
```

### 3. 코드 받기
```powershell
mkdir C:\claude
cd C:\claude
git clone -b claude/dazzling-darwin-et76zj https://github.com/csb0012/stock_app.git
```

### 4. 회사 PC에서 파일 복사 → `C:\claude\stock_app\backend\` 에 넣기
| 파일 | 내용 |
|---|---|
| `.env` | KIS 키·계좌번호 (**필수**, 절대 커밋 금지). 회원가입·비밀번호 찾기 메일·문자를 쓰려면 `SMTP_*`·`SMS_*` (`docs/setup-cloud.md` 7-1·7-2) |
| `stock_app.db` | 로그인 계정, 관심종목, 투자종목, 예측 검증 기록 |
| `.secret_key` | 회사 PC에 있을 때만 (없으면 자동 생성 + 한 번 재로그인) |

`.env` 처럼 점으로 시작하는 파일이 탐색기에서 안 보이면: 보기 → 표시 → 숨긴 항목 체크.

### 5. 실행
`C:\claude\stock_app\start-docker.bat` 더블클릭 → 처음엔 3~10분 빌드 → 브라우저 `http://localhost:5173` 자동으로 열림.

DB 를 안 옮겼다면 계정 만들기 (실행 중인 상태에서):
```powershell
cd C:\claude\stock_app
docker compose exec backend python create_admin.py <아이디> <비밀번호>
```

최종 폴더 구조:
```
C:\claude\stock_app\
├─ start-docker.bat      ← 이걸로 실행
├─ docker-compose.yml
├─ backend\
│  ├─ .env               ← 회사 PC에서 복사
│  ├─ stock_app.db       ← 회사 PC에서 복사
│  └─ .secret_key        ← 있으면 복사
└─ frontend\             (node_modules 없음 — Docker 안에 있음)
```

---

## 매일 쓰는 명령

| 하고 싶은 것 | 방법 |
|---|---|
| 켜기 | Docker Desktop 켜고 `start-docker.bat` 더블클릭 |
| 끄기 | `cd C:\claude\stock_app` 후 `docker compose down` |
| 백엔드 로그 보기 | `docker compose logs -f backend` |
| 최신 코드 받기 | `git pull origin claude/dazzling-darwin-et76zj` (코드는 자동 반영) |
| pull 후 `requirements.txt`·`package.json` 이 바뀌었을 때 | `start-docker.bat` 다시 실행 (이미지 재빌드) |
| 계정 추가 | `docker compose exec backend python create_admin.py <아이디> <비밀번호>` |

push 된 코드는 테스트를 마친 것이다 (수정 → 충분한 테스트 → push → pull, [PROGRESS.md](../PROGRESS.md) 맨 위 규칙). pull 후 화면이 이상하면 PROGRESS.md 의 최근 작업 이력 `검증:` 줄과 "알려진 이슈"의 실서버 미검증 항목부터 확인한다.

⚠️ 같은 PC에서 `start.bat`(직접 설치 방식)과 동시에 켜지 말 것 — 포트 8000·5173 충돌.
