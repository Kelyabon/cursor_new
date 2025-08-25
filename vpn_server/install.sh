#!/usr/bin/env bash
set -euo pipefail

# Simple, non-interactive installer for edge node: Xray (VLESS+Reality) + vpn-agent
# Usage: cd /root/<folder> && bash install.sh

#############################
# Helpers
#############################
log() { echo "[install] $*"; }
err() { echo "[install][error] $*" >&2; }
die() { err "$*"; exit 1; }

require_root() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    die "Скрипт должен выполняться от root"
  fi
}

has_cmd() { command -v "$1" >/dev/null 2>&1; }

ensure_apt_packages() {
  if has_cmd apt-get; then
    export DEBIAN_FRONTEND=noninteractive
    log "apt-get update"
    apt-get update -y
    log "Устанавливаю зависимости"
    apt-get install -y --no-install-recommends \
      ca-certificates curl jq unzip tar uuid-runtime socat procps gettext-base iproute2 iputils-ping python3 python3-venv
  else
    die "Неподдерживаемая ОС: требуется Debian/Ubuntu (apt)"
  fi
}

#############################
# Env and defaults
#############################
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Optional .env next to installer
if [[ -f "$SCRIPT_DIR/.env" ]]; then
  # shellcheck disable=SC1090
  source "$SCRIPT_DIR/.env"
fi

# Defaults (can be overridden via .env)
XRAY_PORT="${XRAY_PORT:-443}"
XRAY_VLESS_ID="${XRAY_VLESS_ID:-}"
REALITY_PRIVATE_KEY="${REALITY_PRIVATE_KEY:-}"
REALITY_PUBLIC_KEY="${REALITY_PUBLIC_KEY:-}"
REALITY_SHORT_ID="${REALITY_SHORT_ID:-}"
REALITY_SERVER_NAME="${REALITY_SERVER_NAME:-www.cloudflare.com}"

# Central API settings for agent
CENTRAL_API_BASE="${CENTRAL_API_BASE:-}"
SERVER_ID="${SERVER_ID:-$(hostname || echo edge)}"
SERVER_TOKEN="${SERVER_TOKEN:-}"
HEARTBEAT_INTERVAL="${HEARTBEAT_INTERVAL:-30}"
PING_TARGET="${PING_TARGET:-1.1.1.1}"

#############################
# Steps
#############################
require_root
ensure_apt_packages

log "Включаю сетевой тюнинг (BBR, sysctl)"
SYSCTL_SRC="$SCRIPT_DIR/sysctl/99-xray-tuning.conf"
[[ -f "$SYSCTL_SRC" ]] || die "Отсутствует $SYSCTL_SRC"
install -m 0644 "$SYSCTL_SRC" /etc/sysctl.d/99-xray-tuning.conf
sysctl --system >/dev/null 2>&1 || true

log "Создаю пользователя xray (если нет)"
if ! id -u xray >/dev/null 2>&1; then
  useradd --system --no-create-home --shell /usr/sbin/nologin xray || true
fi

log "Устанавливаю Xray из официального инсталлятора"
if ! has_cmd xray; then
  bash -c "curl -fsSL https://raw.githubusercontent.com/XTLS/Xray-install/main/install-release.sh | bash -s -- --without-geodata --no-color" || die "Не удалось установить Xray"
fi

install -d -o xray -g xray /etc/xray
install -d -o xray -g xray /var/log/xray

log "Генерация ключей Reality (если не заданы)"
if [[ -z "$REALITY_PRIVATE_KEY" || -z "$REALITY_PUBLIC_KEY" ]]; then
  mapfile -t keys < <(xray x25519 2>/dev/null | sed 's/\r$//')
  # Expect lines like: "Private key: ..." and "Public key: ..."
  REALITY_PRIVATE_KEY=$(printf '%s\n' "${keys[@]}" | awk -F': ' '/Private key/ {print $2; exit}')
  REALITY_PUBLIC_KEY=$(printf '%s\n' "${keys[@]}" | awk -F': ' '/Public key/ {print $2; exit}')
  [[ -n "$REALITY_PRIVATE_KEY" && -n "$REALITY_PUBLIC_KEY" ]] || die "Не удалось сгенерировать Reality ключи"
fi

if [[ -z "$REALITY_SHORT_ID" ]]; then
  if has_cmd openssl; then
    REALITY_SHORT_ID=$(openssl rand -hex 8)
  else
    REALITY_SHORT_ID=$(head -c 8 /dev/urandom | od -An -tx1 | tr -d ' \n')
  fi
fi

if [[ -z "$XRAY_VLESS_ID" ]]; then
  if has_cmd uuidgen; then
    XRAY_VLESS_ID=$(uuidgen)
  else
    XRAY_VLESS_ID=$(cat /proc/sys/kernel/random/uuid)
  fi
fi

log "Формирую /etc/xray/config.json из шаблона"
XRAY_TEMPLATE="$SCRIPT_DIR/templates/xray-config.json.tpl"
[[ -f "$XRAY_TEMPLATE" ]] || die "Отсутствует $XRAY_TEMPLATE"
export XRAY_PORT XRAY_VLESS_ID REALITY_PRIVATE_KEY REALITY_PUBLIC_KEY REALITY_SHORT_ID REALITY_SERVER_NAME
envsubst <"$XRAY_TEMPLATE" > /etc/xray/config.json

chown -R xray:xray /etc/xray /var/log/xray

log "Устанавливаю systemd unit для Xray"
UNIT_XRAY="$SCRIPT_DIR/daemons/xray.service"
[[ -f "$UNIT_XRAY" ]] || die "Отсутствует $UNIT_XRAY"
install -m 0644 "$UNIT_XRAY" /etc/systemd/system/xray.service

log "Готовлю окружение агента и unit"
install -d -o root -g root /etc/vpn-agent
cat >/etc/vpn-agent/agent.env <<EOF
CENTRAL_API_BASE=${CENTRAL_API_BASE}
SERVER_ID=${SERVER_ID}
SERVER_TOKEN=${SERVER_TOKEN}
HEARTBEAT_INTERVAL=${HEARTBEAT_INTERVAL}
XRAY_CONFIG=/etc/xray/config.json
XRAY_PORT=${XRAY_PORT}
PING_TARGET=${PING_TARGET}
AGENT_LISTEN=${AGENT_LISTEN}
EOF

log "Готовлю venv для Python-агента"
install -d -o root -g root /opt/vpn-agent
python3 -m venv /opt/vpn-agent/venv
source /opt/vpn-agent/venv/bin/activate
pip install --no-input --upgrade pip setuptools wheel
REQS_SRC="$SCRIPT_DIR/requirements.txt"
[[ -f "$REQS_SRC" ]] || die "Отсутствует $REQS_SRC"
pip install --no-input -r "$REQS_SRC"

PY_AGENT_SRC="$SCRIPT_DIR/vpn_agent.py"
[[ -f "$PY_AGENT_SRC" ]] || die "Отсутствует $PY_AGENT_SRC"
install -m 0755 "$PY_AGENT_SRC" /usr/local/bin/vpn_agent.py

log "Устанавливаю systemd unit для агента"
UNIT_AGENT="$SCRIPT_DIR/daemons/vpn-agent.service"
[[ -f "$UNIT_AGENT" ]] || die "Отсутствует $UNIT_AGENT"
install -m 0644 "$UNIT_AGENT" /etc/systemd/system/vpn-agent.service

log "Включаю и запускаю сервисы"
systemctl daemon-reload
systemctl enable --now xray.service
systemctl enable --now vpn-agent.service

log "Готово. Текущие параметры:"
echo "  XRAY_VLESS_ID=${XRAY_VLESS_ID}"
echo "  REALITY_PUBLIC_KEY=${REALITY_PUBLIC_KEY}"
echo "  REALITY_SHORT_ID=${REALITY_SHORT_ID}"
echo "  REALITY_SERVER_NAME=${REALITY_SERVER_NAME}"
echo "  Центральный API: ${CENTRAL_API_BASE:-<не задан>}"

exit 0


