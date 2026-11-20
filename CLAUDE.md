# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Personal stock investment web app — Korean (KOSPI/KOSDAQ) + US (NYSE/NASDAQ) markets. Backend: FastAPI + SQLite. Frontend: React + TypeScript + Vite. Local-only deployment on Windows PC; Electron desktop wrapper is a future goal.

## Running the App

**Windows (quickest):** double-click `start.bat` from the repo root — it opens two cmd windows, backend on 8000, frontend on 5173.

**Manually:**
```powershell
# Backend (from backend/ with .venv activated)
.venv\Scripts\Activate
python -m uvicorn app.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm run dev
```

## First-time Setup

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate
pip install -r requirements.txt
pip install "sqlalchemy[asyncio]" "bcrypt==4.0.1"   # required on Python 3.13
cp .env.example .env   # then fill in KIS_APP_KEY, KIS_APP_SECRET, KIS_ACCOUNT_NO

python create_admin.py <username> <password>         # create first user
```

```powershell
cd frontend
npm install
```

## Key Environment Variables (backend/.env)

| Variable | Required | Purpose |
|---|---|---|
| `KIS_APP_KEY` / `KIS_APP_SECRET` | Yes | KIS OAuth token |
| `KIS_ACCOUNT_NO` | Yes | Brokerage account |
| `KIS_IS_REAL` | — | `false` = mock server, `true` = real server |
| `SECRET_KEY` | Yes | JWT signing key |
| `FINNHUB_API_KEY` | Optional | Real economic calendar (mock used if absent) |

## Architecture

### Backend (`backend/app/`)

```
core/
  config.py      — Pydantic Settings (reads .env)
  database.py    — async SQLAlchemy + aiosqlite; init_db() called at startup
  security.py    — bcrypt hashing, JWT create/decode, TOTP via pyotp
models/
  user.py        — User (username, hashed_password, totp_secret, totp_enabled)
  watchlist.py   — WatchlistItem (user_id, symbol, market, name)
services/
  kis_api.py     — KISClient: token cache + KR/US price, history, volume-surge endpoints
  market_data.py — yfinance: index/macro data, bigtech; BeautifulSoup: Naver news; Finnhub: calendar
  analysis.py    — calc_technical_indicators(), predict_next_day(), classify_investment_style()
api/routes/
  auth.py        — /register, /login (TOTP-aware), /setup-totp, /enable-totp, /me
  stocks.py      — /kr/{symbol}, /us/{symbol}, /volume-surge, /recommendations/{longterm,shortterm}
  market.py      — /overview (indices + bigtech), /calendar
  watchlist.py   — CRUD for watchlist items
```

All routes are mounted under `/api` in `main.py`.

### Data flow for stock analysis

1. `kis_api.py` fetches OHLCV candles from KIS (falls back to `yfinance` for US stocks if KIS fails).
2. `analysis.calc_technical_indicators()` computes RSI, MACD, Bollinger Bands, MA20/60 from the candle list.
3. `analysis.predict_next_day()` applies rule-based scoring → probability (clamped 15–85%), target price (ATR-based), stop-loss.
4. `analysis.classify_investment_style()` returns `long_term_score` and `short_term_score`.

### Frontend (`frontend/src/`)

```
api/client.ts      — axios instance; Bearer token injected; 401 → redirect /login
store/auth.ts      — Zustand store: token + user
pages/             — Dashboard, Recommendations, Screener, Search, Watchlist, Calendar, Login
components/common/ — Layout (sidebar nav), ChangeTag, LoadingSpinner
index.css          — CSS custom properties: --bg-primary, --bg-secondary, --bg-card,
                     --accent (#4f8ef7), --green (#34d399), --red (#f87171), --text-muted
```

Vite proxies `/api` → `localhost:8000` (see `vite.config.ts`).

React Query is used for all data fetching. Auth state lives in Zustand (`store/auth.ts`).

### KIS API notes

- Real server: `https://openapi.koreainvestment.com:9443` (requires real brokerage account with API enabled)
- Mock server: `https://openapivts.koreainvestment.com:29443` (`KIS_IS_REAL=false`)
- Token is cached in-process for 23 hours; a fresh uvicorn start always re-fetches.
- Test endpoint (no auth): `GET /api/stocks/test/kis`

### Authentication

- JWT stored in `localStorage`, sent as `Authorization: Bearer …`.
- TOTP (Google Authenticator) is optional; enabled per-user via `/api/auth/setup-totp` → `/api/auth/enable-totp`.

## Git

Development branch: `claude/dazzling-darwin-et76zj`. Always pull this branch before editing on the local PC; push fixes here.
