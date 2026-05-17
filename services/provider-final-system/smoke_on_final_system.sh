#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
# Load API_KEY (and anything else) from .env in the current directory.
if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  set -a; source .env; set +a
else
  warn=""; printf '\033[0;33m%s\033[0m\n' "WARN: .env not found in $(pwd); relying on environment."
fi

API="${API:-http://127.0.0.1:8081}"
ENDPOINT="${ENDPOINT:-/environmental}"   # or /esds/social
API_KEY="${API_KEY:-}"

# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------
log()  { printf '\033[0;32m%s\033[0m\n' "$*"; }
warn() { printf '\033[0;33m%s\033[0m\n' "$*"; }
err()  { printf '\033[0;31m%s\033[0m\n' "$*" >&2; }

# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------
if [[ -z "${API_KEY}" ]]; then
  err "API_KEY is empty. Set it in .env (API_KEY=...) or export it."
  exit 1
fi

log "==> Using API_KEY = ${API_KEY:0:6}...${API_KEY: -4}"
log "==> Target       = ${API}${ENDPOINT}"

# ---------------------------------------------------------------------------
# GET with Bearer
# ---------------------------------------------------------------------------
log "==> Fetching ${ENDPOINT}..."
HTTP_CODE=$(
  curl -sS -o /tmp/ecostars_response.json -w '%{http_code}' \
    -H "Authorization: Bearer ${API_KEY}" \
    -H "Accept: application/json" \
    "${API}${ENDPOINT}"
)

if [[ "${HTTP_CODE}" =~ ^2 ]]; then
  log "==> HTTP ${HTTP_CODE} — OK"
  if command -v jq >/dev/null 2>&1; then
    jq . /tmp/ecostars_response.json
  else
    cat /tmp/ecostars_response.json; echo
  fi
else
  err "==> HTTP ${HTTP_CODE} — request failed"
  cat /tmp/ecostars_response.json; echo
  exit 1
fi

log "==> All done!"