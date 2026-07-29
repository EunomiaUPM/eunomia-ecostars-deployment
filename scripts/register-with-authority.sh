#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/lib.sh"

PARTICIPANT_URL="${PARTICIPANT_URL:?PARTICIPANT_URL is required}"
PARTICIPANT_NICK="${PARTICIPANT_NICK:-participant}"

log_step "Registering $PARTICIPANT_NICK with authority"

VC_TYPE="DataSpaceParticipant_jwt_vc_json"

AUTH_DID=$(curl_raw GET "$AUTHORITY_URL/.well-known/did.json" | jq -r '.id')

# /vc-request/beg never deduplicates: every call files a fresh petition with
# the authority, so without this guard each run piles up another one.
if curl_raw GET "$PARTICIPANT_URL/api/v1/vc-request/all" \
    | jq -e --arg id "$AUTH_DID" --arg vc "$VC_TYPE" \
        'any(.[]?; .participant_id == $id
                   and .status == "Finalized"
                   and (.vc_type_config // [] | index($vc)))' >/dev/null; then
    log_info "$PARTICIPANT_NICK already holds the credential, skipping"
    exit 0
fi

# The field is "nick", not "slug": sending "slug" fails with
# HTTP 400 "Error extracting Json payload".
BODY=$(jq -n \
    --arg url "$DOCKER_AUTHORITY_URL/api/v1/gate/access" \
    --arg id  "$AUTH_DID" \
    --arg nick "authority" \
    --arg vc_type "$VC_TYPE" \
    --arg method "cert" \
    '{url:$url, id:$id, nick:$nick, vc_type:$vc_type, method:$method, auto: true}')

curl_checked POST "$PARTICIPANT_URL/api/v1/vc-request/beg" "$BODY" >/dev/null
log_success "$PARTICIPANT_NICK registered successfully"
