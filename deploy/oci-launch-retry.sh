#!/usr/bin/env bash
# Oracle Cloud Shell 에서 실행 — Ampere 무료 VM 을 자리가 날 때까지 자동으로 다시 만들어 봄
#   "Out of capacity for shape VM.Standard.A1.Flex" 오류 대응
#
# 하는 일 (이미 있으면 건너뜀):
#   1) 공개 서브넷이 없으면 네트워크(VCN·인터넷 게이트웨이·서브넷) 생성
#   2) 서브넷에 80/443 허용 규칙(보안 목록 stock-web) 추가 — setup-cloud.md 의 "80·443 열기" 를 대신함
#   3) SSH 키가 없으면 Cloud Shell 에 생성 (개인키는 나중에 PC 로 다운로드)
#   4) VM.Standard.A1.Flex 1 OCPU / 2GB, Ubuntu 24.04 생성을 성공할 때까지 반복 (기본 90초 간격)
#
# 사용: bash oci-launch-retry.sh            (간격 바꾸기: INTERVAL=120 bash oci-launch-retry.sh)
set -uo pipefail
NAME=stock-app
SHAPE=VM.Standard.A1.Flex
OCPUS=1
MEM_GB=2
INTERVAL=${INTERVAL:-90}
KEY=${KEY:-$HOME/.ssh/oci_rsa}   # Cloud Shell 은 FIPS 모드라 ed25519 키가 안 됨 → RSA

say() { echo "[$(date +%H:%M:%S)] $*"; }
q() { oci "$@" --raw-output 2>/dev/null; }

# --- 기본 정보 ---
T=${OCI_TENANCY:-}
[ -z "$T" ] && T=$(q iam availability-domain list --query 'data[0]."compartment-id"')
[ -z "$T" ] && { say "테넌시 OCID 를 못 찾음 — Cloud Shell 에서 실행했는지 확인"; exit 1; }
AD=$(q iam availability-domain list --compartment-id "$T" --query 'data[0].name')
say "가용 도메인: $AD"

# 이미 만들어진 VM 이 있으면 끝
existing=$(q compute instance list --compartment-id "$T" --display-name "$NAME" \
  --query 'data[?"lifecycle-state"!=`TERMINATED`] | [0].id')
if [ -n "$existing" ] && [ "$existing" != "null" ]; then
  say "이미 $NAME VM 이 있음: $existing"
  INSTANCE=$existing
else
  # --- 1) 네트워크 ---
  SUBNET=$(q network subnet list --compartment-id "$T" \
    --query 'data[?"prohibit-public-ip-on-vnic"==`false` && "lifecycle-state"==`AVAILABLE`] | [0].id')
  if [ -z "$SUBNET" ] || [ "$SUBNET" = "null" ]; then
    say "공개 서브넷이 없어 새로 만듦"
    VCN=$(q network vcn create --compartment-id "$T" --cidr-blocks '["10.0.0.0/16"]' --display-name stock-vcn \
      --dns-label stockvcn --wait-for-state AVAILABLE --query data.id)
    IGW=$(q network internet-gateway create --compartment-id "$T" --vcn-id "$VCN" --is-enabled true \
      --display-name stock-igw --wait-for-state AVAILABLE --query data.id)
    RT=$(q network vcn get --vcn-id "$VCN" --query 'data."default-route-table-id"')
    oci network route-table update --rt-id "$RT" --force \
      --route-rules "[{\"destination\":\"0.0.0.0/0\",\"destinationType\":\"CIDR_BLOCK\",\"networkEntityId\":\"$IGW\"}]" >/dev/null
    SUBNET=$(q network subnet create --compartment-id "$T" --vcn-id "$VCN" --cidr-block 10.0.0.0/24 \
      --display-name stock-subnet --dns-label stocksub --wait-for-state AVAILABLE --query data.id)
  fi
  [ -z "$SUBNET" ] || [ "$SUBNET" = "null" ] && { say "서브넷 생성 실패"; exit 1; }
  say "서브넷: $SUBNET"

  # --- 2) 80/443 허용 ---
  VCN=$(q network subnet get --subnet-id "$SUBNET" --query 'data."vcn-id"')
  WEB_SL=$(q network security-list list --compartment-id "$T" --vcn-id "$VCN" --display-name stock-web --query 'data[0].id')
  if [ -z "$WEB_SL" ] || [ "$WEB_SL" = "null" ]; then
    rule() { echo "{\"source\":\"0.0.0.0/0\",\"protocol\":\"$1\",\"isStateless\":false,\"$2\":{\"destinationPortRange\":{\"min\":$3,\"max\":$3}}}"; }
    WEB_SL=$(q network security-list create --compartment-id "$T" --vcn-id "$VCN" --display-name stock-web \
      --egress-security-rules '[]' \
      --ingress-security-rules "[$(rule 6 tcpOptions 80),$(rule 6 tcpOptions 443),$(rule 17 udpOptions 443)]" \
      --wait-for-state AVAILABLE --query data.id)
    say "80/443 허용 규칙 생성: $WEB_SL"
  fi
  SLS=$(oci network subnet get --subnet-id "$SUBNET" --query 'data."security-list-ids"' 2>/dev/null)
  if ! echo "$SLS" | grep -q "$WEB_SL"; then
    NEW=$(echo "$SLS" | jq -c --arg id "$WEB_SL" '. + [$id]')
    oci network subnet update --subnet-id "$SUBNET" --security-list-ids "$NEW" --force >/dev/null \
      && say "서브넷에 80/443 규칙 연결"
  fi

  # --- 3) SSH 키 ---
  if [ ! -f "$KEY.pub" ]; then
    mkdir -p "$(dirname "$KEY")"
    ssh-keygen -t rsa -b 4096 -N "" -f "$KEY" -q || { say "ssh-keygen 실패"; exit 1; }
    say "SSH 키 생성: $KEY (개인키) / $KEY.pub"
  fi

  # --- 4) 이미지 ---
  IMG=$(q compute image list --compartment-id "$T" --operating-system "Canonical Ubuntu" \
    --operating-system-version "24.04" --shape "$SHAPE" --sort-by TIMECREATED --sort-order DESC --limit 1 \
    --query 'data[0].id')
  [ -z "$IMG" ] || [ "$IMG" = "null" ] && { say "Ubuntu 24.04 (ARM) 이미지를 못 찾음"; exit 1; }
  say "이미지: $IMG"

  # --- 5) 자리가 날 때까지 반복 ---
  n=0
  while true; do
    n=$((n + 1))
    out=$(oci compute instance launch --availability-domain "$AD" --compartment-id "$T" \
      --shape "$SHAPE" --shape-config "{\"ocpus\":$OCPUS,\"memoryInGBs\":$MEM_GB}" \
      --image-id "$IMG" --subnet-id "$SUBNET" --assign-public-ip true \
      --display-name "$NAME" --ssh-authorized-keys-file "$KEY.pub" \
      --query data.id --raw-output 2>&1)
    if [[ "$out" == ocid1.instance* ]]; then
      INSTANCE=$out
      say "성공! ($n 번째 시도) $INSTANCE"
      break
    elif echo "$out" | grep -qi "capacity"; then
      say "$n 번째: 자리 없음 — ${INTERVAL}초 후 다시"
      sleep "$INTERVAL"
    elif echo "$out" | grep -qi "TooManyRequests\|429"; then
      say "$n 번째: 요청이 너무 잦음 — 5분 쉼"
      sleep 300
    elif echo "$out" | grep -qi "LimitExceeded\|limit"; then
      say "무료 한도 초과 오류 — 이미 다른 Ampere VM 이 있는지 콘솔에서 확인:"; echo "$out" | tail -5; exit 1
    else
      say "다른 오류 — 중단:"; echo "$out" | tail -8; exit 1
    fi
  done
fi

# --- 공인 IP ---
say "VM 이 켜지길 기다리는 중..."
oci compute instance get --instance-id "$INSTANCE" --wait-for-state RUNNING >/dev/null 2>&1
IP=""
for _ in $(seq 1 30); do
  IP=$(q compute instance list-vnics --instance-id "$INSTANCE" --query 'data[0]."public-ip"')
  [ -n "$IP" ] && [ "$IP" != "null" ] && break
  sleep 10
done
echo
echo "=============================================="
echo " 서버 공인 IP: $IP"
echo " 다음: docs/setup-cloud.md 2단계(DuckDNS)부터 진행"
echo " SSH 개인키: Cloud Shell 오른쪽 위 ⚙(또는 ≡) → Download → $KEY"
echo "   → PC 의 C:\\Users\\내이름\\.ssh\\oracle.key 로 저장"
echo "   (Cloud Shell 에서 바로 접속도 가능: ssh -i $KEY ubuntu@$IP)"
echo "=============================================="
