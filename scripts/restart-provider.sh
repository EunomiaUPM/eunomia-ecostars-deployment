#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/restart-lib.sh"
check_sshpass

restart_on_host \
    "EUNOMIA-PROVIDER" \
    "${PROVIDER_SSH_USER:?}" \
    "${PROVIDER_SSH_PASS:?}" \
    "${PROVIDER_SSH_HOST:?}" \
    "${PROVIDER_PATH:?}" \
    "${PROVIDER_SERVICE:?}" \
    "${PROVIDER_COMPOSE:?}"
