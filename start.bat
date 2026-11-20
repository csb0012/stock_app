@echo off
echo [StockApp] 서버 시작 중...

:: 백엔드
start "StockApp Backend" cmd /k "cd backend && python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"

:: 2초 대기 후 프론트엔드
timeout /t 2 /nobreak > nul
start "StockApp Frontend" cmd /k "cd frontend && npm run dev"

echo.
echo 백엔드:  http://localhost:8000
echo 프론트:  http://localhost:5173
echo API 문서: http://localhost:8000/docs
echo.
