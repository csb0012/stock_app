# 클라우드 서버에 올리기 (24시간 켜두기, 무료)

PC를 켜두지 않아도 앱이 계속 돌아가게 한다. 예를 들어 08:20 장 시작 전 예측, 30분마다 채점, 하루 한 번 백테스트가 PC 없이 돈다.
회사 PC·집 PC·휴대폰에서는 **브라우저로 `https://내이름.duckdns.org` 에 접속**만 하면 된다.

## 무엇을 쓰나

| 항목 | 서비스 | 비용 |
|---|---|---|
| 서버 | **Oracle Cloud Always Free** — Ampere(ARM) VM, 일본(오사카·도쿄) 리전 | 무료 한도 안에서 0원 |
| 주소 + HTTPS | **DuckDNS** 무료 서브도메인 + Caddy 자동 인증서(Let's Encrypt) | 0원 |
| 실행 | 이 저장소의 `docker-compose.cloud.yml` + `deploy/` 스크립트 | — |

다른 "무료 호스팅"(Render, Koyeb 등)은 접속이 없으면 잠들거나(15분~1시간) 재시작 때 파일이 지워져서
08:20 자동 예측·SQLite DB 를 쓰는 이 앱에는 맞지 않는다. 계속 켜져 있는 무료 서버는 Oracle·Google Cloud 의 무료 VM 정도다.

### 꼭 알아둘 조건
- **가입에 신용카드 필요** (본인 확인용 소액 승인 후 취소). 무료 한도 안에서만 쓰면 청구되지 않는다.
- 2026년 8월부터 Ampere 무료 한도가 **2 OCPU / 12GB 메모리**로 줄었다. 한도를 넘는 VM 은 정지·삭제될 수 있으니 크게 만들지 말 것.
- **유휴 회수:** Oracle 은 7일 동안 아래 **세 가지가 모두** 20% 미만인 무료 VM 을 회수할 수 있다.
  - CPU 사용률(95퍼센타일)
  - 네트워크 사용률
  - 메모리 사용률 (Ampere A1 에만 적용)

  → **하나라도 20%를 넘으면 유휴가 아니다.** 그래서 이 문서는 VM 을 **1 OCPU / 2GB** 로 작게 만든다.
  - 이 앱(백엔드 약 200~300MB + Caddy + Docker + OS)이 평소에 2GB 중 35~45% 를 쓰므로 메모리 조건으로 유휴에서 빠진다.
  - CPU 를 일부러 돌리는 꼼수는 필요 없다. 게다가 하루 한 번 잠깐 돌리는 정도로는 95퍼센타일 기준을 못 넘는다. 일주일의 5% 이상, 즉 하루 약 1시간 12분 이상 20% 넘게 돌려야 한다.
  - VM 을 크게(예: 6GB) 만들면 같은 사용량이 10% 남짓이 되어 회수 대상이 될 수 있다.
  - 설치 후 일주일쯤 지나 콘솔 VM 화면 → **Metrics → Memory Utilization** 이 20% 위인지 확인한다. 이 그래프가 비어 있으면 VM 화면의 **Oracle Cloud Agent → Compute Instance Monitoring** 을 켠다.
  - 피하려면 계정을 **종량제(Pay As You Go)로 업그레이드**하는 방법이 알려져 있다. 무료 한도 안이면 여전히 0원이다.
  - 업그레이드했다면 **예산 알림**(Billing → Budgets, 예: 1달러)을 꼭 걸어둔다.
  - 회수돼도 DB 를 매일 백업하므로(아래 "백업"), PC 로 받아 두면 다시 만들 수 있다.
- **홈 리전은 가입할 때 한 번 정하면 못 바꾼다.** 무료 VM 은 홈 리전에만 만들 수 있다.
  - 2026-11 현재 무료 가입 목록에 한국(서울·춘천) 리전이 없다(무료 자리 부족으로 막혀 있는 것으로 보임).
  - 한국에서 가장 가까운 **Japan Central (Osaka)** 를 고른다. 도쿄는 무료 자리 부족 사례가 더 많이 보고되어 있어서 오사카를 먼저 권장한다.
    오사카가 안 되면 **Japan East (Tokyo)** 를 고른다.
  - 한국과의 지연은 약 30ms 로, 화면을 쓰는 데 체감 차이는 없다.
  - **KIS API 를 해외 IP 에서 부르는 것은 실서버로 확인 전.** 설치 후 서버에서 아래 명령으로 바로 확인한다:
    `sudo docker compose -f docker-compose.cloud.yml exec backend python -c "import asyncio;from app.services.kis_api import kis_client;print(asyncio.run(kis_client.get_kr_stock_price('005930')))"`
    삼성전자 현재가가 나오면 정상이다.
  - Ampere 자리가 없으면 "Out of capacity" 오류가 날 수 있다. 시간을 두고 다시 시도한다.

## 1. Oracle Cloud 가입·VM 만들기
1. https://www.oracle.com/cloud/free/ → 가입 (홈 리전: Japan Central (Osaka), 안 되면 Japan East (Tokyo))
2. 콘솔 → **Compute → Instances → Create instance**
   - Image: **Canonical Ubuntu 24.04**
   - Shape: **Ampere → VM.Standard.A1.Flex, OCPU 1, Memory 2GB** (메모리를 늘리지 말 것 — 위 "유휴 회수" 참고)
     - Ampere 가 계속 안 되면 **VM.Standard.E2.1.Micro**(AMD, 1GB, 무료)를 쓴다. 스크립트가 스왑을 자동으로 추가한다. (메모리 조건은 A1 에만 적용되므로 이 경우엔 유휴 회수 위험이 남음 → 종량제 업그레이드 고려)
   - Networking: 기본 VCN, **Assign a public IPv4 address** 체크
   - SSH keys: **Generate a key pair for me → Save private key** (예: `oracle.key` 를 `C:\Users\내이름\.ssh\` 에 저장)
3. 만든 VM 화면에서 **Public IP address** 를 적어둔다 (아래 `서버IP`)
4. 인터넷에서 80/443 열기: VM 화면의 Subnet → **Security Lists → Default Security List → Add Ingress Rules**
   - Source CIDR `0.0.0.0/0`, IP Protocol `TCP`, Destination Port Range `80,443` → 저장
   - 서버 안 방화벽은 `setup-server.sh` 가 연다

## 1-1. 요금 안전장치 (1달러라도 나가면 메일 알림)
- **종량제(Pay As You Go)로 업그레이드하지 않은 무료 계정은 요금이 청구되지 않는다.**
  - 30일 체험 크레딧이 끝나면 유료 자원은 멈추고, Always Free 자원만 남는다.
  - 이 문서는 메모리 조건으로 유휴 회수를 피하므로(위 참고) 업그레이드할 필요가 없다. **업그레이드 버튼을 누르지 않는 것이 가장 확실한 차단**이다.
- 그래도 안전장치로 **예산 알림**을 걸어둔다. Oracle 예산은 **알림만** 보내고 자원을 자동으로 멈추지는 않는다.
  1. 콘솔 왼쪽 위 메뉴(≡) → **Billing & Cost Management(청구 및 비용 관리) → Budgets(예산) → Create Budget(예산 생성)**
  2. 아래처럼 입력한다:

     | 항목 | 값 |
     |---|---|
     | Name | `free-guard` |
     | Budget scope | Compartment |
     | Target compartment | 맨 위 루트(계정 이름, `(root)`) |
     | Schedule | Monthly |
     | Budget amount | `1` (계정 통화가 원화면 `1000`) |
  3. 같은 화면의 **Budget alert rule** 을 입력한다:

     | 항목 | 값 |
     |---|---|
     | Threshold metric | **Actual spend** (실제 사용액) |
     | Threshold type | Percentage of budget |
     | Threshold % | `1` → 1센트라도 쓰면 알림 |
     | Email recipients | 받을 메일 주소 |
  4. **Create** — 알림 규칙을 하나 더 만들어 **Forecast spend**(예상 사용액) 100% 도 걸어두면, 쓰기 전에 미리 알 수 있다.
- 예산은 몇 시간 간격으로 계산되므로 알림이 즉시 오지는 않는다.
- 이상한 금액이 보이면 **Cost Analysis(비용 분석)** 에서 어느 자원인지 확인한다. 무료 자원에는 **Always Free** 표시가 붙어 있다.

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
저장소가 공개(public)라서 바로 받을 수 있다. KIS 키 같은 비밀 파일은 저장소에 없다.
```bash
sudo apt-get update && sudo apt-get install -y git
git clone -b claude/dazzling-darwin-et76zj https://github.com/csb0012/stock_app.git ~/stock_app
```
(저장소를 비공개로 바꾸면 이 방법이 막힌다. 그때는 서버에서 `ssh-keygen` 으로 키를 만들어 GitHub **Settings → Deploy keys** 에 읽기 전용으로 등록하고, `git@github.com:csb0012/stock_app.git` 로 받는다.)

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
- **2단계 인증(Google Authenticator)을 켜는 것을 권장한다** (인터넷 공개): 앱 오른쪽 위 **내 아이디(마이페이지)** → 2단계 인증 → 켜기 →
  QR 을 휴대폰 앱으로 스캔 → 6자리 입력 → 확인. 끌 때도 같은 곳에서 지금 코드를 입력한다. 휴대폰을 잃어버렸으면 서버에서
  `sudo docker compose -f docker-compose.cloud.yml exec backend python create_admin.py --reset-totp <아이디>` 로 끈다 (관심종목·투자종목은 그대로).
- 앱 로그인을 5번 틀리면 그 IP 는 15분 동안 차단된다.
- **마이페이지에서 이메일 또는 휴대폰을 인증해 둔다** — 비밀번호를 잊었을 때 로그인 화면 '비밀번호 찾기'로 코드를 받아 바꿀 수 있다 (아래 7-1 메일 · 7-2 문자 설정 필요).
  메일을 못 쓰면 서버에서 `sudo docker compose -f docker-compose.cloud.yml exec backend python create_admin.py --reset-password <아이디> <새 비밀번호>`.

## 7-0. 보안 체크리스트 (인터넷에 공개하기 전에 꼭)
앱에 들어 있는 보호 장치 (따로 할 일 없음):
- **접속 비밀번호(Caddy) 12자 이상** — 설치 스크립트가 짧으면 거부. 앱 로그인 앞의 첫 관문
- **로그인 대입 공격 차단**: 같은 IP 10분 안 5번 틀리면 15분 차단 + **같은 계정 15분 안 10번 틀리면(어느 IP 든) 그 계정 15분 잠금** (잠기면 인증된 이메일로 알림)
- **유출된 비밀번호 차단**: 가입·비밀번호 변경 때 다른 사이트에서 털린 비밀번호 목록(Have I Been Pwned)에 있으면 거부.
  로그인 때 지금 비밀번호가 목록에 있으면 모든 화면 위에 빨간 경고 → 바꾸면 사라짐.
  비밀번호는 밖으로 안 나감 — 해시 앞 5글자만 보내고 비교는 서버 안에서 (`PWNED_CHECK=false` 로 끔)
- **처음 보는 IP 로그인 알림 메일**: 인증된 이메일 + 7-1 메일 설정이 있으면 (`LOGIN_ALERT=false` 로 끔). 모르는 로그인이면 바로 비밀번호 변경 + 모든 기기 로그아웃
- **2단계 인증 코드는 한 번만** 쓸 수 있음 (훔쳐본 코드로 다시 로그인 불가)
- **브라우저 보안 정책(CSP 등)**: 다른 곳 스크립트·페이지 안 스크립트를 막아 화면에 이상한 글이 끼어들어도 로그인 토큰을 못 훔쳐 감 (`deploy/Caddyfile`)
- **자동 보안 업데이트**(우분투 보안 패치 매일), KIS 키·DB 파일은 이 계정만 읽기(600), SSH 비밀번호 로그인이 켜져 있으면 경고 — 설치 스크립트가 함

직접 할 일:
1. 앱 계정 **비밀번호를 다른 사이트와 다르게** (12자 이상 권장 — 단어 3~4개 이어 붙이기가 외우기 쉬움)
2. 마이페이지 → **2단계 인증 켜기** — 비밀번호가 새어도 휴대폰 코드 없이는 못 들어옴. 가장 효과가 큼
3. 마이페이지 → **이메일 인증** + 7-1 메일 설정 — 잠금·새 IP 알림, 비밀번호 찾기에 필요
4. 혼자 쓰면 내 계정을 만든 뒤 `backend/.env` 에 `SIGNUP_OPEN=false` → `sudo docker compose -f docker-compose.cloud.yml restart backend`
5. KIS 키·`.env`·`oracle.key` 는 채팅·메신저·git 에 올리지 않기. PC 의 `oracle.key` 를 잃어버리면 서버에 못 들어가니 USB 등에 백업

## 7-1. 메일 설정 (회원가입·비밀번호 찾기 인증 코드) — 네이버 메일
- 회원가입은 **이메일 인증만 하면 누구나** 가능하다 (가입한 사람도 내 KIS 키로 시세를 조회하므로 호출 한도를 같이 씀).
  다만 클라우드는 앞에 Caddy 접속 비밀번호가 있어 그 비밀번호를 아는 사람만 가입 화면까지 올 수 있다. 가입을 막으려면 `.env` 에 `SIGNUP_OPEN=false`.
- 네이버 메일 → 환경설정 → **POP3/IMAP 설정 → IMAP/SMTP 설정 → SMTP 사용: 사용함** → 저장
- 네이버 2단계 인증을 쓰고 있으면: 네이버 내정보 → 보안설정 → 2단계 인증 → **애플리케이션 비밀번호** 생성 → 아래 `SMTP_PASSWORD` 에 넣는다
- 서버 `backend/.env` 에 추가 (PC 에서 쓰는 `.env` 에도 같게):
  ```
  SMTP_HOST=smtp.naver.com
  SMTP_PORT=465
  SMTP_USER=내아이디@naver.com
  SMTP_PASSWORD=네이버 비밀번호 또는 애플리케이션 비밀번호
  ```
  → `sudo docker compose -f docker-compose.cloud.yml restart backend`
- 확인: 로그인 화면 → 회원가입 → 내 다른 메일로 '인증 코드 받기'. 오류 문구가 뜨면 그대로 확인 (예: "메일 계정 로그인 실패" = SMTP 사용 설정·비밀번호 문제).
  Oracle Cloud 는 25번 포트를 막지만 465/587 은 쓸 수 있다. 465 가 안 되면 `SMTP_PORT=587`.
- Gmail 을 쓰려면 `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=465`, 구글 계정 **앱 비밀번호**.

## 7-2. 휴대폰 문자 인증 (선택) — 솔라피
이메일 대신 휴대폰 번호로 가입·비밀번호 찾기·로그인을 하려면 문자 발송 업체 계정이 필요하다 (안 하면 화면의 '휴대폰으로 인증' 탭만 '준비 안 됨').
- [solapi.com](https://solapi.com) 가입 → 잔액 충전 (단문 1건 약 20원)
- 콘솔 → **발신번호 관리**에서 문자를 보낼 번호를 등록·인증 (내 휴대폰 번호 가능 — 등록 안 된 번호로는 통신사가 막음)
- 콘솔 → **API Key 관리**에서 API Key·API Secret 발급
- 서버 `backend/.env` 에 추가:
  ```
  SMS_API_KEY=발급받은 API Key
  SMS_API_SECRET=발급받은 API Secret
  SMS_FROM=01012345678
  SMS_DAILY_LIMIT=50
  ```
  → `sudo docker compose -f docker-compose.cloud.yml restart backend`
- 확인: 회원가입 → '휴대폰으로 인증' → 내 번호로 '인증 코드 받기'. "문자 접수 실패"면 발신번호 등록·잔액, "계정 인증 실패"면 키를 확인.
- `SMS_DAILY_LIMIT` = 하루 최대 발송 건수 (누가 계속 눌러 요금이 나가는 것 방지, 0 = 제한 없음). 키는 채팅·git 에 올리지 말 것 (`.env` 는 git 제외).
- **회사 PC·집 PC 에서는 이제 `start.bat` / `start-docker.bat` 를 켜지 않는다.** 이유는 두 가지다.
  - 같은 KIS 키로 두 곳이 동시에 호출하면 초당 호출 제한(EGW00201)에 더 자주 걸린다.
  - 데이터(관심종목·예측 기록)가 두 곳으로 갈라진다.

## 자주 쓰는 명령어 (서버, `cd ~/stock_app` 에서)
| 하는 일 | 명령 |
|---|---|
| 코드 업데이트 (git pull + 재빌드 + 재시작) | `bash deploy/update.sh` — push 된 코드는 테스트를 마친 것 (PROGRESS.md 맨 위 규칙) |
| 상태 보기 | `sudo docker compose -f docker-compose.cloud.yml ps` |
| 로그 보기 | `sudo docker compose -f docker-compose.cloud.yml logs -f --tail 100 backend` |
| 재시작 | `sudo docker compose -f docker-compose.cloud.yml restart` |
| 끄기 | `sudo docker compose -f docker-compose.cloud.yml down` |
| DB 백업 (수동) | `bash deploy/backup.sh` → `backups/stock_app-날짜.db` |
| 접속 비밀번호 바꾸기 | `rm deploy/auth.caddy && bash deploy/setup-server.sh` |
| 도메인 바꾸기 | `rm deploy/.env && bash deploy/setup-server.sh` |

## 백업
- `setup-server.sh` 가 **매일 04:00(서버 시간)** DB 백업을 예약한다(crontab). `~/stock_app/backups/` 에 최근 14개를 보관한다.
  - Oracle Ubuntu 이미지의 서버 시간은 기본 UTC 라서 한국 시간으로는 **13:00** 이다 (앱 컨테이너만 `TZ=Asia/Seoul`). 서버 시간은 `timedatectl` 로 확인.
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
- **Out of capacity (VM 생성 실패)** — Ampere 무료 자리가 꽉 찬 것이다. 수시로 자리가 나므로 **자동 재시도 스크립트**를 쓴다.
  1. Oracle 콘솔 오른쪽 위 **>_ (Cloud Shell)** 아이콘 → 터미널을 연다
  2. 스크립트를 받는다: `curl -fsSLO https://raw.githubusercontent.com/csb0012/stock_app/claude/dazzling-darwin-et76zj/deploy/oci-launch-retry.sh`
  3. Cloud Shell 에서 `bash oci-launch-retry.sh` 를 실행한다. 스크립트가 하는 일:
     - 네트워크를 만든다.
     - 80/443 을 연다 (= 1단계 4번을 대신함).
     - SSH 키를 만든다.
     - 90초마다 VM 생성을 재시도한다. 성공하면 공인 IP 를 알려 준다.
  4. 성공하면 Cloud Shell ⚙ → **Download** → `/home/<이름>/.ssh/oci_rsa` 를 받아 PC 의 `C:\Users\내이름\.ssh\oracle.key` 로 저장한다. 이후 3단계부터 진행한다.
  - **Cloud Shell 은 몇 시간 지나면 세션이 끊긴다** (브라우저에 '사이트에서 나가시겠습니까?' 가 뜨고 재시도도 멈춤). 며칠 걸릴 수 있으니
    아래 **"PC 에서 자동 재시도"** 로 집 PC 의 Docker 에서 돌리는 것을 권장한다. 끊긴 뒤 다시 실행해도 이미 만든 네트워크·규칙은 건너뛴다.
  - 그래도 며칠째 안 되면 두 가지 방법이 있다:
    - **종량제로 업그레이드**: 무료 자원은 그대로 0원이고, 자리 배정이 잘 된다는 사례가 많다. 예산 알림을 걸어 둔 상태여야 한다.
    - **E2.1.Micro**(AMD 1GB)로 만든다 — 자리가 거의 항상 있다. 재시도 스크립트에 `MICRO=1` 을 주면 이 모양으로 만든다.
      1GB 라 설치 스크립트가 스왑 2GB 를 붙이고, 첫 빌드 20~30분·AI 모의투자 1년 시뮬레이션 수 분~10분 이상으로 느리다.

### PC 에서 자동 재시도 (Cloud Shell 이 끊길 때 — 집 PC Docker)
PC 가 켜져 있는 동안 계속 재시도한다. Docker Desktop 만 있으면 되고 Python·OCI CLI 를 PC 에 설치하지 않는다.

1. **Oracle API 키 만들기** (PC 에서 Oracle 에 로그인하는 열쇠):
   콘솔 오른쪽 위 프로필 아이콘 → **My profile(내 프로필)** → 왼쪽 아래 **API keys** → **Add API key** →
   **Generate API key pair** → **Download private key** (`.pem` 파일) → **Add** → 나오는 **Configuration file preview** 내용을 복사해 둔다.
2. **PC 에 파일 두 개 두기** (PowerShell):
   ```powershell
   mkdir $env:USERPROFILE\.oci
   ```
   - 받은 `.pem` 파일을 탐색기에서 `C:\Users\내이름\.oci\oci_api_key.pem` 으로 이름을 바꿔 옮긴다.
   - 설정 파일(확장자 없음)을 만들고 메모장으로 연다:
     ```powershell
     New-Item -ItemType File $env:USERPROFILE\.oci\config
     ```
     ```powershell
     notepad $env:USERPROFILE\.oci\config
     ```
     1번에서 복사한 내용을 붙여 넣고, **`key_file=` 줄만 `key_file=~/.oci/oci_api_key.pem` 으로 바꿔** 저장한다
     (Docker 안에서 읽는 경로라 `C:\...` 가 아니라 이 모양이어야 함). `region=` 은 홈 리전(예: `ap-osaka-1`) 그대로.
3. **재시도 시작** — Docker Desktop 을 켜고, 최신 코드를 받은 뒤(`git pull`) 저장소 폴더에서:
   ```powershell
   cd C:\claude\stock_app
   ```
   ```powershell
   docker run -d --name oci-retry -v "$env:USERPROFILE\.oci:/root/.oci" -v "${PWD}\deploy:/w" -w /w -e KEY=/root/.oci/stock_ssh_key -e OCI_CLI_SUPPRESS_FILE_PERMISSIONS_WARNING=True python:3.12-slim bash -c "pip install -q --root-user-action=ignore --disable-pip-version-check oci-cli && tr -d '\r' < oci-launch-retry.sh > /tmp/retry.sh && bash /tmp/retry.sh"
   ```
   - `tr -d '\r'` = Windows 로 받은 스크립트의 줄 끝(`\r\n`)을 리눅스 형식으로 정리. 빼면 `set: pipefail: invalid option name`·`syntax error near unexpected token 'else'` 오류.
   - AMD 1GB(E2.1.Micro)로 만들려면 `-e KEY=...` 앞에 `-e MICRO=1` 을 넣는다.
   - 진행 보기: `docker logs -f oci-retry` (Ctrl+C 는 보기만 멈춤, 재시도는 계속). 처음 1~2분은 OCI CLI 설치.
   - "Oracle 로그인(API 키) 실패" 가 나오면 2번의 config 내용(특히 `key_file`·`region`)과 `.pem` 파일 위치를 확인하고, `docker rm oci-retry` 후 다시 실행.
4. **PC 가 절전 모드로 들어가면 멈춘다** → 재시도하는 동안 절전 끄기 (전원 연결 시 '절전 안 함'):
   ```powershell
   powercfg /change standby-timeout-ac 0
   ```
   PC 를 껐다 켰으면 `docker rm oci-retry` 후 3번 명령을 다시 실행한다 (만든 네트워크·SSH 키는 그대로 다시 씀).
5. **성공하면** 로그 마지막에 `서버 공인 IP` 가 나온다. SSH 개인키는 `C:\Users\내이름\.oci\stock_ssh_key` 에 있다 → 3단계용으로 복사:
   ```powershell
   Copy-Item $env:USERPROFILE\.oci\stock_ssh_key $env:USERPROFILE\.ssh\oracle.key
   ```
   ```powershell
   docker rm oci-retry
   ```
   이어서 위 **2. DuckDNS** 부터 진행한다 (80/443 은 스크립트가 이미 열었음). 성공한 뒤 절전 설정은 원래대로 돌려도 된다.
   API 키는 VM 을 만든 뒤엔 필요 없으니 콘솔 API keys 에서 지워도 된다.
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
