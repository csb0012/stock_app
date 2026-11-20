#!/usr/bin/env bash
# 클라우드 서버(Ubuntu 22.04/24.04) 처음 설치 — 저장소 폴더에서:  bash deploy/setup-server.sh
# 하는 일: Docker 설치 → (메모리 작으면) 스왑 → 방화벽 80/443 열기 → 도메인·비밀번호 설정 → 앱 실행
set -euo pipefail
cd "$(dirname "$0")/.."
COMPOSE="sudo docker compose -f docker-compose.cloud.yml"

echo "== 1/6 Docker 설치 확인"
if ! command -v docker >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y docker.io docker-compose-v2
  sudo systemctl enable --now docker
fi
sudo docker compose version >/dev/null || { echo "docker compose 가 없습니다: sudo apt-get install -y docker-compose-v2"; exit 1; }

echo "== 2/6 메모리 확인 (2GB 미만이면 스왑 2GB 추가)"
mem_mb=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)
if [ "$mem_mb" -lt 2000 ] && ! swapon --show | grep -q /swapfile; then
  sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
  grep -q /swapfile /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

echo "== 3/6 서버 안 방화벽에서 80/443 열기 (Oracle Ubuntu 이미지는 기본으로 막혀 있음)"
if sudo iptables -S INPUT 2>/dev/null | grep -q -- "-j REJECT"; then
  sudo iptables -C INPUT -p tcp -m multiport --dports 80,443 -j ACCEPT 2>/dev/null \
    || sudo iptables -I INPUT 1 -p tcp -m multiport --dports 80,443 -j ACCEPT
  sudo iptables -C INPUT -p udp --dport 443 -j ACCEPT 2>/dev/null \
    || sudo iptables -I INPUT 1 -p udp --dport 443 -j ACCEPT
  if command -v netfilter-persistent >/dev/null 2>&1; then sudo netfilter-persistent save; fi
fi

echo "== 4/6 KIS 키 파일 확인"
if [ ! -f backend/.env ]; then
  echo "backend/.env 가 없습니다. PC 의 C:\\claude\\stock_app\\backend\\.env 를 이 서버의 $(pwd)/backend/.env 로 복사한 뒤 다시 실행하세요."
  echo "(복사 방법: docs/setup-cloud.md 의 '파일 옮기기')"
  exit 1
fi
mkdir -p backend/app/data

echo "== 5/6 도메인·접속 비밀번호"
if [ ! -f deploy/.env ]; then
  read -rp "도메인 (예: mystock.duckdns.org): " domain
  echo "DOMAIN=$domain" > deploy/.env
fi
domain=$(grep '^DOMAIN=' deploy/.env | cut -d= -f2)
if [ ! -f deploy/auth.caddy ]; then
  echo "앱 로그인 앞에 한 번 더 묻는 접속 계정을 만듭니다 (브라우저가 처음 접속할 때 물어봄)"
  read -rp "  접속 아이디: " bu
  read -rsp "  접속 비밀번호 (12자 이상 권장): " bp; echo
  hash=$(sudo docker run --rm caddy:2.8-alpine caddy hash-password --plaintext "$bp")
  printf 'basic_auth {\n\t%s %s\n}\n' "$bu" "$hash" > deploy/auth.caddy
  chmod 600 deploy/auth.caddy
fi
my_ip=$(curl -s -4 --max-time 5 https://ifconfig.me || true)
dns_ip=$(getent hosts "$domain" | awk '{print $1}' | head -1 || true)
if [ -n "$my_ip" ] && [ "$my_ip" != "$dns_ip" ]; then
  echo "주의: $domain 이 가리키는 IP($dns_ip)가 이 서버 IP($my_ip)와 다릅니다 — DuckDNS 에서 IP 를 $my_ip 로 맞추세요."
  echo "      (맞지 않으면 HTTPS 인증서 발급이 실패합니다. 맞춘 뒤 bash deploy/update.sh)"
fi

# 매일 새벽 4시 DB 백업 (backups/ 에 최근 14개)
if ! crontab -l 2>/dev/null | grep -q "deploy/backup.sh"; then
  (crontab -l 2>/dev/null; echo "0 4 * * * cd $(pwd) && bash deploy/backup.sh >/dev/null 2>&1") | crontab -
fi

echo "== 6/6 실행 (처음엔 이미지 빌드로 5~10분)"
$COMPOSE up -d --build
echo
echo "완료: https://$domain"
echo "로그 보기: $COMPOSE logs -f --tail 100"
