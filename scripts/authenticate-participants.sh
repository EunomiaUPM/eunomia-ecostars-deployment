#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/lib.sh"

PROVIDER_NICK="${PROVIDER_NICK:-provider}"

log_step "Authenticating consumer with provider ($PROVIDER_NICK)"

PROVIDER_DID=$(curl_raw GET "$PROVIDER_URL/.well-known/did.json" | jq -r '.id')

# Check for the token, not for the mate: an untokened mate row means the
# handshake never completed.
if curl_raw GET "$CONSUMER_URL/api/v1/mates/all" \
    | jq -e --arg id "$PROVIDER_DID" \
        'any(.[]?; .participant_id == $id and (.token // "") != "")' >/dev/null; then
    log_info "Consumer is already authenticated with the provider, skipping"
    exit 0
fi

# This is the GNAP handshake, and it is what mints the mate token. Creating
# the mate directly via POST /api/v1/mates is NOT equivalent: it only inserts
# the row, leaving it tokenless, and the provider then answers 401 to every
# DSP call (surfaced as 502 by the consumer BFF).
# Payload is ReachProvider, see crates/auth/src/types/entities/reacher.rs;
# actions accepts "talk" and "request-vc".
BODY=$(jq -n \
    --arg id   "$PROVIDER_DID" \
    --arg nick "$PROVIDER_NICK" \
    --arg url  "$DOCKER_PROVIDER_URL/api/v1/gate/access" \
    '{id:$id, nick:$nick, url:$url, actions:["talk"], auto:true}')

curl_checked POST "$CONSUMER_URL/api/v1/peer-connection/connect" "$BODY" >/dev/null
log_success "Authentication complete"
