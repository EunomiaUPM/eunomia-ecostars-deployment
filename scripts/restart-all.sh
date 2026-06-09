#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(dirname "$0")"
source "$SCRIPT_DIR/restart-lib.sh"
check_sshpass

echo
echo -e "${BOLD}════════════════════════════════════════════${RESET}"
echo -e "${BOLD}  Service restart — $(date '+%Y-%m-%d %H:%M')${RESET}"
echo -e "${BOLD}════════════════════════════════════════════${RESET}"
echo

declare -A PIDS SCRIPTS
SCRIPTS[authority]="restart-authority.sh"
SCRIPTS[consumer]="restart-consumer.sh"
SCRIPTS[provider]="restart-provider.sh"
SCRIPTS[consumer_client]="restart-consumer-client-stack.sh"

for key in "${!SCRIPTS[@]}"; do
    bash "$SCRIPT_DIR/${SCRIPTS[$key]}" &
    PIDS[$key]=$!
    rlog "Started ${SCRIPTS[$key]} (pid ${PIDS[$key]})"
done

FAILED=0
for key in "${!PIDS[@]}"; do
    if ! wait "${PIDS[$key]}"; then
        echo -e "${RED}  ✗ FAILED: ${SCRIPTS[$key]}${RESET}" >&2
        FAILED=1
    fi
done

if [[ $FAILED -ne 0 ]]; then
    echo -e "\n${RED}${BOLD}One or more restarts failed — skipping populate_catalog.${RESET}" >&2
    exit 1
fi

echo
echo -e "${GREEN}${BOLD}════════════════════════════════════════════${RESET}"
echo -e "${GREEN}${BOLD}  ✓ All 4 hosts completed OK                ${RESET}"
echo -e "${GREEN}${BOLD}════════════════════════════════════════════${RESET}"
echo

rlog "Running populate_catalog..."
bash "$SCRIPT_DIR/populate_catalog.sh"
