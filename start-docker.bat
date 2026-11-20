@echo off
chcp 65001 > nul
cd /d "%~dp0"

docker info > nul 2>&1
if errorlevel 1 (
  echo [오류] Docker Desktop 이 실행 중이 아닙니다. Docker Desktop 을 먼저 켜세요.
  pause
  exit /b 1
)
if not exist "backend\.env" (
  echo [오류] backend\.env 가 없습니다. 회사 PC에서 복사하거나 backend\.env.example 을 복사해 KIS 키를 넣으세요.
  pause
  exit /b 1
)

echo [StockApp] Docker 로 시작 중... (처음엔 이미지 빌드로 몇 분 걸림)
docker compose up -d --build
if errorlevel 1 (
  pause
  exit /b 1
)

echo.
echo 프론트: http://localhost:5173
echo 백엔드 로그 보기: docker compose logs -f backend
echo 끄기: docker compose down
timeout /t 3 /nobreak > nul
start http://localhost:5173
