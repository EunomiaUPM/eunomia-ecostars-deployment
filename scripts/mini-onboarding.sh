#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(dirname "$0")"
source "$SCRIPT_DIR/lib.sh"

echo -e "\n======================================"
echo "         FULL ONBOARDING"
echo "======================================"

log_step "Linking wallets"
curl_raw POST "$AUTHORITY_URL/api/v1/wallet/link" >/dev/null
curl_raw POST "$CONSUMER_URL/api/v1/wallet/link" >/dev/null
curl_raw POST "$PROVIDER_URL/api/v1/wallet/link" >/dev/null
log_success "Wallets linked"

PARTICIPANT_URL="$CONSUMER_URL" PARTICIPANT_SLUG="consumer" \
    bash "$SCRIPT_DIR/register-with-authority.sh"

PARTICIPANT_URL="$PROVIDER_URL" PARTICIPANT_SLUG="provider" \
    bash "$SCRIPT_DIR/register-with-authority.sh"

bash "$SCRIPT_DIR/authenticate-participants.sh"

echo -e "\n======================================"
echo "   ONBOARDING FINISHED SUCCESSFULLY"
echo "======================================"
