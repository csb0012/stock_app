#!/usr/bin/env bash
# 클라우드 서버 코드 업데이트 — 저장소 폴더에서:  bash deploy/update.sh
set -euo pipefail
cd "$(dirname "$0")/.."
COMPOSE="sudo docker compose -f docker-compose.cloud.yml"
git pull origin claude/dazzling-darwin-et76zj
$COMPOSE up -d --build      # 화면 다시 빌드, requirements.txt 가 바뀌었으면 백엔드 이미지도 다시
$COMPOSE restart backend    # 백엔드 코드는 폴더 연결이라 재시작만 하면 반영
$COMPOSE ps
