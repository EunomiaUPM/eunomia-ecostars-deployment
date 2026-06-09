#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/restart-lib.sh"
check_sshpass

restart_on_host \
    "DEV-DATASPACES (authority)" \
    "${AUTHORITY_SSH_USER:?}" \
    "${AUTHORITY_SSH_PASS:?}" \
    "${AUTHORITY_SSH_HOST:?}" \
    "${AUTHORITY_PATH:?}" \
    "${AUTHORITY_SERVICE:?}" \
    "${AUTHORITY_COMPOSE:?}"
