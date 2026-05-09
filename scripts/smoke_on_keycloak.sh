#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
KEYCLOAK="${KEYCLOAK:-http://127.0.0.1:8083}"
STATIC_API="${STATIC_API:-http://127.0.0.1:8081}"
DYNAMIC_API="${DYNAMIC_API:-http://127.0.0.1:8082}"

# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------
log()  { printf '\033[0;32m%s\033[0m\n' "$*"; }
warn() { printf '\033[0;33m%s\033[0m\n' "$*"; }
err()  { printf '\033[0;31m%s\033[0m\n' "$*" >&2; }

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
get_token() {
  curl -sf -X POST \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "client_id=ecostars-client&client_secret=ecostars-secret&username=testuser&password=password&grant_type=password" \
    "${KEYCLOAK}/realms/ecostars/protocol/openid-connect/token" \
    | jq -r '.access_token'
}

# ---------------------------------------------------------------------------
# Token
# ---------------------------------------------------------------------------
log "==> Authenticating with Keycloak..."
TOKEN=$(get_token)
echo "    token = ${TOKEN:0:10}...${TOKEN: -10}"

# ---------------------------------------------------------------------------
# Connect to static API to get data
# ---------------------------------------------------------------------------
log "==> Fetching hotels data from static API..."
curl -sf -H "Authorization: Bearer ${TOKEN}" ${STATIC_API}/hotels/1

echo \n
log "==> All done!"

log "==> Copying token to clipboard..."
echo "${TOKEN}"
echo "${TOKEN}" | pbcopy
