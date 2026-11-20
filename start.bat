@echo off
chcp 65001 > nul
echo [StockApp] 서버 시작 중...

:: 가상환경 위치 찾기 (루트 .venv 또는 backend\.venv)
set "VENV="
if exist "%~dp0.venv\Scripts\activate.bat" set "VENV=%~dp0.venv"
if exist "%~dp0backend\.venv\Scripts\activate.bat" set "VENV=%~dp0backend\.venv"
if "%VENV%"=="" (
  echo [오류] 가상환경을 찾지 못했습니다. PROGRESS.md 의 "최초 설치"를 먼저 진행하세요.
  pause
  exit /b 1
)

:: 백엔드 — 127.0.0.1 로만 열어서 같은 네트워크의 다른 PC에서 접속 못 하게 함
start "StockApp Backend" cmd /k "cd /d "%~dp0backend" && call "%VENV%\Scripts\activate.bat" && python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"

:: 2초 대기 후 프론트엔드
timeout /t 2 /nobreak > nul
start "StockApp Frontend" cmd /k "cd /d "%~dp0frontend" && npm run dev"

echo.
echo 백엔드:  http://localhost:8000
echo 프론트:  http://localhost:5173
echo API 문서: http://localhost:8000/docs
echo.
