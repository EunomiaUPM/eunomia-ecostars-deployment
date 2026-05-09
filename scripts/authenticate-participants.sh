#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/lib.sh"

# CONSUMER_URL   — URL del consumer (por defecto: lib.sh)
# PROVIDER_URL   — URL del provider (por defecto: lib.sh)
# PROVIDER_SLUG  — slug del provider (por defecto: "provider")
PROVIDER_SLUG="${PROVIDER_SLUG:-provider}"

log_step "Authenticating consumer with provider ($PROVIDER_SLUG)"

PROVIDER_DID=$(curl_raw GET "$PROVIDER_URL/.well-known/did.json" | jq -r '.id')

BODY=$(jq -n \
    --arg url  "$DOCKER_PROVIDER_URL/api/v1/gate/access" \
    --arg id   "$PROVIDER_DID" \
    --arg slug "$PROVIDER_SLUG" \
    '{url:$url, id:$id, slug:$slug, actions:["talk"], auto: true}')

curl_raw POST "$CONSUMER_URL/api/v1/onboard/provider" "$BODY" >/dev/null
log_success "Authentication complete"
