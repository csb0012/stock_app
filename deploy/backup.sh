#!/usr/bin/env bash
# DB 백업 — 저장소 폴더에서:  bash deploy/backup.sh   → backups/stock_app-날짜.db (최근 14개 보관)
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p backups
ts=$(date +%Y%m%d-%H%M)
# 실행 중에도 안전하게 복사 (SQLite 온라인 백업)
sudo docker compose -f docker-compose.cloud.yml exec -T backend \
  python -c "import sqlite3; s=sqlite3.connect('stock_app.db'); d=sqlite3.connect('/app/backup.tmp'); s.backup(d); d.close()"
mv backend/backup.tmp "backups/stock_app-$ts.db"
ls -1t backups/stock_app-*.db | tail -n +15 | xargs -r rm --
echo "backups/stock_app-$ts.db"
