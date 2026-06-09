#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/restart-lib.sh"
check_sshpass

restart_on_host \
    "EUNOMIA-CONSUMER" \
    "${CONSUMER_SSH_USER:?}" \
    "${CONSUMER_SSH_PASS:?}" \
    "${CONSUMER_SSH_HOST:?}" \
    "${CONSUMER_PATH:?}" \
    "${CONSUMER_SERVICE:?}" \
    "${CONSUMER_COMPOSE:?}"
