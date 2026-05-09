#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/lib.sh"

invoke_curl_json() {
    local method="${1:-GET}"
    local url="$2"
    local body="${3:-}"
    local response http_code body_response

    if [ -n "$body" ]; then
        response=$(curl -s -w "\n%{http_code}" -X "$method" "$url" \
            -H "Content-Type: application/json" -d "$body")
    else
        response=$(curl -s -w "\n%{http_code}" -X "$method" "$url" \
            -H "Content-Type: application/json")
    fi

    http_code=$(echo "$response" | tail -n1)
    body_response=$(echo "$response" | sed '$d')

    if [ "$http_code" -ge 200 ] && [ "$http_code" -lt 300 ]; then
        log_success "OK: $method $url -> $http_code"
    else
        echo -e "\033[31mERROR: $method $url -> $http_code\n$body_response\033[0m" >&2
        exit 1
    fi

    echo "$body_response"
}

echo -e "\n\033[0;36m======================================\033[0m"
echo -e "\033[0;36m        GAIA LOCAL FLOW\033[0m"
echo -e "\033[0;36m======================================\033[0m"

log_step "STEP 1 - Linking wallets"
invoke_curl_json POST "$CONSUMER_URL/api/v1/wallet/link" >/dev/null
invoke_curl_json POST "$PROVIDER_URL/api/v1/wallet/link" >/dev/null
invoke_curl_json POST "$AUTHORITY_URL/api/v1/wallet/link" >/dev/null

log_step "STEP 2 - Retrieving DIDs"
CONSUMER_DID=$(invoke_curl_json GET "$CONSUMER_URL/.well-known/did.json" | jq -r '.id')
PROVIDER_DID=$(invoke_curl_json GET "$PROVIDER_URL/.well-known/did.json" | jq -r '.id')
AUTHORITY_DID=$(invoke_curl_json GET "$AUTHORITY_URL/.well-known/did.json" | jq -r '.id')
log_info "Consumer DID:  $CONSUMER_DID"
log_info "Provider DID:  $PROVIDER_DID"
log_info "Authority DID: $AUTHORITY_DID"

log_step "STEP 3 - Requesting Legal VC"
LEGAL_BODY=$(jq -n \
    --arg url "$DOCKER_AUTHORITY_URL/api/v1/gate/access" \
    --arg id  "$AUTHORITY_DID" \
    '{url:$url, id:$id, slug:"authority", vc_type:"gx_VatId_jwt_vc_json", method:"cert", auto:true}')
invoke_curl_json POST "$CONSUMER_URL/api/v1/vc-request/beg" "$LEGAL_BODY" >/dev/null

log_step "STEP 6 - Generating Gaia VCs"
invoke_curl_json POST "$CONSUMER_URL/api/v1/gaia/credential/generate" >/dev/null

log_step "STEP 7 - Requesting Label VC"
LABEL_BODY=$(jq -n \
    --arg url "$DOCKER_AUTHORITY_URL/api/v1/gate/access" \
    --arg id  "$AUTHORITY_DID" \
    '{url:$url, id:$id, slug:"authority", vc_type:"gx_LabelCredential_jwt_vc_json", method:"oidc4vp", auto:true}')
invoke_curl_json POST "$CONSUMER_URL/api/v1/vc-request/beg" "$LABEL_BODY" >/dev/null

log_step "STEP 8 - Talking to Provider"
PROVIDER_BODY=$(jq -n \
    --arg url "$DOCKER_PROVIDER_URL/api/v1/gate/access" \
    --arg id  "$PROVIDER_DID" \
    '{url:$url, id:$id, slug:"provider", actions:["talk"], auto:true}')
invoke_curl_json POST "$CONSUMER_URL/api/v1/onboard/provider" "$PROVIDER_BODY" >/dev/null

echo -e "\n\033[0;32m======================================\033[0m"
echo -e "\033[0;32m     GAIA FLOW COMPLETED\033[0m"
echo -e "\033[0;32m======================================\033[0m"