# StockApp - AI 주식 분석 플랫폼

## 처음 설치

### 1. 백엔드 환경 설정
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
# .env 파일을 열어 KIS API 키 등 입력
```

### 2. 필수 API 키 발급 (전부 무료)
| 서비스 | 발급 경로 | 용도 |
|--------|----------|------|
| KIS API | [apiportal.koreainvestment.com](https://apiportal.koreainvestment.com) | 국내/미국 주식 |
| Finnhub | [finnhub.io](https://finnhub.io) | 경제 캘린더 |
| DART | [opendart.fss.or.kr](https://opendart.fss.or.kr) | 한국 공시 |
| FRED | [fred.stlouisfed.org/docs/api](https://fred.stlouisfed.org/docs/api/api_key.html) | 미국 경제 지표 |

### 3. 첫 계정 생성
```bash
cd backend
python create_admin.py 내아이디 내비밀번호
```

### 4. 프론트엔드
```bash
cd frontend
npm install
```

## 실행
```
start.bat 더블클릭
```
또는 각각:
```bash
# 백엔드
cd backend && python -m uvicorn app.main:app --reload

# 프론트엔드
cd frontend && npm run dev
```

접속: http://localhost:5173

## Google Authenticator 등록
1. 로그인 후 (우선 비밀번호만으로 가능)
2. `GET /api/auth/setup-totp` 호출 → QR 코드 발급
3. Google Authenticator 앱에서 QR 스캔
4. `POST /api/auth/enable-totp` {"totp_code": "123456"} 로 활성화
5. 이후 로그인 시 항상 6자리 코드 요구

## 나중에 Windows 데스크탑 앱 (Electron)
```bash
npm install -g electron
# 별도 electron 래퍼 추가 예정
```
