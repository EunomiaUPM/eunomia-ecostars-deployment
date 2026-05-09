#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/lib.sh"

# PARTICIPANT_URL  — URL del participante a registrar (requerido)
# PARTICIPANT_SLUG — nombre identificativo para logs (por defecto: "participant")
PARTICIPANT_URL="${PARTICIPANT_URL:?PARTICIPANT_URL is required}"
PARTICIPANT_SLUG="${PARTICIPANT_SLUG:-participant}"

log_step "Registering $PARTICIPANT_SLUG with authority"

AUTH_DID=$(curl_raw GET "$AUTHORITY_URL/.well-known/did.json" | jq -r '.id')

BODY=$(jq -n \
    --arg url "$DOCKER_AUTHORITY_URL/api/v1/gate/access" \
    --arg id  "$AUTH_DID" \
    --arg slug "authority" \
    --arg vc_type "DataSpaceParticipant_jwt_vc_json" \
    --arg method "cert" \
    '{url:$url, id:$id, slug:$slug, vc_type:$vc_type, method:$method, auto: true}')

curl_raw POST "$PARTICIPANT_URL/api/v1/vc-request/beg" "$BODY" >/dev/null
log_success "$PARTICIPANT_SLUG registered successfully"
