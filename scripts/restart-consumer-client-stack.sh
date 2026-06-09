#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/restart-lib.sh"
check_sshpass

restart_with_volumes \
    "CONSUMER-CLIENT-STACK" \
    "${CONSUMER_CLIENT_SSH_USER:?}" \
    "${CONSUMER_CLIENT_SSH_PASS:?}" \
    "${CONSUMER_CLIENT_SSH_HOST:?}" \
    "${CONSUMER_CLIENT_PATH:?}" \
    "${CONSUMER_CLIENT_COMPOSE:?}"
