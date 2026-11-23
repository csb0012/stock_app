#!/usr/bin/env bash
# push 전 전체 점검 — 저장소 루트에서:  bash scripts/check.sh   (화면 테스트 빼기: SKIP_E2E=1)
#  1) 백엔드 문법·import  2) 백엔드 단위·API 테스트(pytest, 외부 API 안 부름)
#  3) 프론트 타입 검사·빌드  4) 화면 테스트(Playwright, 가짜 API — e2e/smoke.mjs)
set -euo pipefail
cd "$(dirname "$0")/.."
step() { printf '\n== %s\n' "$1"; }

step "1/4 백엔드 문법·import"
(cd backend && python -m compileall -q app && \
  KIS_APP_KEY=${KIS_APP_KEY:-test} KIS_APP_SECRET=${KIS_APP_SECRET:-test} KIS_ACCOUNT_NO=${KIS_ACCOUNT_NO:-00000000-01} \
  python -c "import app.main" && echo "ok")

step "2/4 백엔드 테스트 (pytest)"
(cd backend && python -m pytest)

step "3/4 프론트 빌드 (tsc + vite)"
(cd frontend && npm run build --silent)

if [ "${SKIP_E2E:-}" = "1" ]; then
  step "4/4 화면 테스트 — 건너뜀 (SKIP_E2E=1)"
else
  step "4/4 화면 테스트 (Playwright, 가짜 API)"
  (cd frontend && node e2e/smoke.mjs)
fi
printf '\n모든 점검 통과\n'
