# 클라우드 서버에 올리기 (24시간 켜두기, 무료)

PC를 켜두지 않아도 앱이 계속 돌아가게 한다. 예를 들어 08:20 장 시작 전 예측, 30분마다 채점, 하루 한 번 백테스트가 PC 없이 돈다.
회사 PC·집 PC·휴대폰에서는 **브라우저로 `https://내이름.duckdns.org` 에 접속**만 하면 된다.

## 무엇을 쓰나

| 항목 | 서비스 | 비용 |
|---|---|---|
| 서버 | **Oracle Cloud Always Free** — Ampere(ARM) VM, 한국(서울·춘천) 리전 | 무료 한도 안에서 0원 |
| 주소 + HTTPS | **DuckDNS** 무료 서브도메인 + Caddy 자동 인증서(Let's Encrypt) | 0원 |
| 실행 | 이 저장소의 `docker-compose.cloud.yml` + `deploy/` 스크립트 | — |

다른 "무료 호스팅"(Render, Koyeb 등)은 접속이 없으면 잠들거나(15분~1시간) 재시작 때 파일이 지워져서
08:20 자동 예측·SQLite DB 를 쓰는 이 앱에는 맞지 않는다. 계속 켜져 있는 무료 서버는 Oracle·Google Cloud 의 무료 VM 정도다.

### 꼭 알아둘 조건
- **가입에 신용카드 필요** (본인 확인용 소액 승인 후 취소). 무료 한도 안에서만 쓰면 청구되지 않는다.
- 2026년 8월부터 Ampere 무료 한도가 **2 OCPU / 12GB 메모리**로 줄었다. 이 앱은 **1 OCPU / 6GB** 로 충분하다. 한도를 넘는 VM 은 정지·삭제될 수 있으니 더 크게 만들지 말 것.
- **유휴 회수:** 무료 계정의 VM 은 7일 동안 CPU 사용률(95퍼센타일)이 20% 미만이면 Oracle 이 회수할 수 있다. 이 앱은 대부분 한가해서 해당될 수 있다.
  - 피하려면 계정을 **종량제(Pay As You Go)로 업그레이드**하는 방법이 알려져 있다. 무료 한도 안이면 여전히 0원이다.
  - 업그레이드했다면 **예산 알림**(Billing → Budgets, 예: 1달러)을 꼭 걸어둔다.
  - 회수돼도 DB 를 매일 백업하므로(아래 "백업"), PC 로 받아 두면 다시 만들 수 있다.
- **홈 리전은 가입할 때 한 번 정하면 못 바꾼다.** 무료 VM 은 홈 리전에만 만들 수 있다.
  - **South Korea Central (Seoul)** 또는 **South Korea North (Chuncheon)** 을 고른다. KIS API 를 국내 IP 에서 부르는 게 안전하다.
  - Ampere 자리가 없으면 "Out of capacity" 오류가 날 수 있다. 시간을 두고 다시 시도한다.

## 1. Oracle Cloud 가입·VM 만들기
1. https://www.oracle.com/cloud/free/ → 가입 (홈 리전: 서울 또는 춘천)
2. 콘솔 → **Compute → Instances → Create instance**
   - Image: **Canonical Ubuntu 24.04**
   - Shape: **Ampere → VM.Standard.A1.Flex, OCPU 1, Memory 6GB**
     - Ampere 가 계속 안 되면 **VM.Standard.E2.1.Micro**(AMD, 1GB, 무료)를 쓴다. 스크립트가 스왑을 자동으로 추가한다.
   - Networking: 기본 VCN, **Assign a public IPv4 address** 체크
   - SSH keys: **Generate a key pair for me → Save private key** (예: `oracle.key` 를 `C:\Users\내이름\.ssh\` 에 저장)
3. 만든 VM 화면에서 **Public IP address** 를 적어둔다 (아래 `서버IP`)
4. 인터넷에서 80/443 열기: VM 화면의 Subnet → **Security Lists → Default Security List → Add Ingress Rules**
   - Source CIDR `0.0.0.0/0`, IP Protocol `TCP`, Destination Port Range `80,443` → 저장
   - 서버 안 방화벽은 `setup-server.sh` 가 연다

## 2. DuckDNS 주소 만들기
1. https://www.duckdns.org → GitHub 또는 Google 로 로그인
2. sub domain 에 원하는 이름 입력(예: `mystock`) → **add domain**
3. 그 줄의 **current ip** 에 `서버IP` 입력 → **update ip**
4. 주소: `mystock.duckdns.org`

## 3. 서버 접속 (Windows PowerShell)
```powershell
# 키 파일 권한 정리 (한 번만 — 안 하면 ssh 가 키를 거부함)
icacls $env:USERPROFILE\.ssh\oracle.key /inheritance:r /grant:r "$($env:USERNAME):(R)"
ssh -i $env:USERPROFILE\.ssh\oracle.key ubuntu@서버IP
```
이후 `ubuntu@...:~$` 로 시작하는 줄은 서버에서 치는 명령이다.

## 4. 코드 받기 (서버)
저장소가 비공개여도 받을 수 있게 **읽기 전용 배포 키**를 쓴다. 이 키는 이 저장소 읽기만 가능하다.
```bash
ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519
cat ~/.ssh/id_ed25519.pub
```
출력된 한 줄을 GitHub 저장소 → **Settings → Deploy keys → Add deploy key** 에 붙여넣는다. **Allow write access 는 체크하지 않는다.**
```bash
sudo apt-get update && sudo apt-get install -y git
git clone -b claude/dazzling-darwin-et76zj git@github.com:csb0012/stock_app.git ~/stock_app
```
(처음 접속 시 `Are you sure you want to continue connecting` → `yes`)

## 5. 파일 옮기기 (PC → 서버, PC 의 PowerShell)
KIS 키(`.env`)는 git 에 없으므로 직접 복사한다.
- `stock_app.db`(관심종목·투자종목·예측 기록)를 복사하면 지금 데이터 그대로 이어서 쓸 수 있다.
- `.secret_key` 를 복사하면 로그인 상태를 유지할 수 있다.
```powershell
$KEY = "$env:USERPROFILE\.ssh\oracle.key"
scp -i $KEY C:\claude\stock_app\backend\.env ubuntu@서버IP:~/stock_app/backend/.env
scp -i $KEY C:\claude\stock_app\backend\stock_app.db ubuntu@서버IP:~/stock_app/backend/stock_app.db
scp -i $KEY C:\claude\stock_app\backend\.secret_key ubuntu@서버IP:~/stock_app/backend/.secret_key
```
`.secret_key` 가 없다는 오류는 무시해도 된다(서버에서 새로 만듦). **복사 전에 PC 에서 앱을 끄고** 복사한다(DB 를 쓰는 중이면 깨질 수 있음).

## 6. 설치·실행 (서버)
```bash
cd ~/stock_app
bash deploy/setup-server.sh
```
- 도메인을 물으면 `mystock.duckdns.org` 를 입력한다.
- **접속 아이디/비밀번호**를 물으면 새로 정한다.
  - 인터넷에 공개되므로 앱 로그인 앞에서 브라우저가 한 번 더 묻는 비밀번호다. 앱 계정과 달라도 된다. 12자 이상을 권장한다.
- 처음엔 이미지 빌드로 5~10분 걸린다. 끝나면 `완료: https://mystock.duckdns.org` 가 나온다.

## 7. 접속
- 브라우저에서 `https://mystock.duckdns.org` 를 연다 → 접속 아이디/비밀번호 → 앱 로그인 (PC 에서 쓰던 계정)
- **TOTP(Google Authenticator) 2단계 인증을 켜는 것을 권장한다** (인터넷 공개).
- 앱 로그인을 5번 틀리면 그 IP 는 15분 동안 차단된다.
- **회사 PC·집 PC 에서는 이제 `start.bat` / `start-docker.bat` 를 켜지 않는다.** 이유는 두 가지다.
  - 같은 KIS 키로 두 곳이 동시에 호출하면 초당 호출 제한(EGW00201)에 더 자주 걸린다.
  - 데이터(관심종목·예측 기록)가 두 곳으로 갈라진다.

## 자주 쓰는 명령어 (서버, `cd ~/stock_app` 에서)
| 하는 일 | 명령 |
|---|---|
| 코드 업데이트 (git pull + 재빌드 + 재시작) | `bash deploy/update.sh` |
| 상태 보기 | `sudo docker compose -f docker-compose.cloud.yml ps` |
| 로그 보기 | `sudo docker compose -f docker-compose.cloud.yml logs -f --tail 100 backend` |
| 재시작 | `sudo docker compose -f docker-compose.cloud.yml restart` |
| 끄기 | `sudo docker compose -f docker-compose.cloud.yml down` |
| DB 백업 (수동) | `bash deploy/backup.sh` → `backups/stock_app-날짜.db` |
| 접속 비밀번호 바꾸기 | `rm deploy/auth.caddy && bash deploy/setup-server.sh` |
| 도메인 바꾸기 | `rm deploy/.env && bash deploy/setup-server.sh` |

## 백업
- `setup-server.sh` 가 **매일 새벽 4시** DB 백업을 예약한다. `~/stock_app/backups/` 에 최근 14개를 보관한다.
- PC 로 가져오기 (PowerShell):
  ```powershell
  scp -i $env:USERPROFILE\.ssh\oracle.key "ubuntu@서버IP:~/stock_app/backups/*.db" C:\claude\stock_app\backups\
  ```

## 문제 해결
- **`https://` 접속이 안 됨 / 인증서 오류**
  - DuckDNS 의 IP 가 서버IP 와 같은지 확인한다.
  - Security List 에 80,443 이 열려 있는지 확인한다.
  - 로그 확인: `sudo docker compose -f docker-compose.cloud.yml logs web`
- **KIS 오류**: 로그 `logs backend` 를 본다. `backend/.env` 가 PC 와 같은지 확인한다(`KIS_IS_REAL` 포함).
- **Out of capacity (VM 생성 실패)**: 몇 시간 뒤에 다시 시도하거나, 다른 가용 도메인(AD)을 고르거나, E2.1.Micro 로 만든다.
- **VM 이 사라짐(유휴 회수)**: 위 "꼭 알아둘 조건" 참고. 다시 만들고 백업한 `stock_app.db` 를 복사한다.

## 구성
```
인터넷 ──443──> web (Caddy: HTTPS, 접속 비밀번호, 빌드된 화면, /api 전달)
                  └──> backend (FastAPI, 인터넷에 직접 안 열림) ── KIS / yfinance / 뉴스
```
- `docker-compose.cloud.yml`: backend + web
- `deploy/Dockerfile.web`: React 빌드 → Caddy
- `deploy/Caddyfile`: HTTPS·보안 헤더·접속 비밀번호(`deploy/auth.caddy`)·`/api` 프록시
- `deploy/.env`(도메인)와 `deploy/auth.caddy`(비밀번호 해시)는 서버에만 있고 git 에 올리지 않는다
