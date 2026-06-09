# Shared helpers for restart-*.sh scripts.
# Source this file; do NOT execute it directly.

_ENV_FILE="$(dirname "${BASH_SOURCE[0]}")/.env"
if [[ -f "$_ENV_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$_ENV_FILE"
fi
unset _ENV_FILE

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

rlog() { echo -e "${CYAN}[$(date '+%H:%M:%S')]${RESET} $*"; }
rok()  { echo -e "${GREEN}  ✓${RESET} $*"; }
rdie() { echo -e "${RED}  ✗ ERROR — $1:${RESET} $2" >&2; exit 1; }

check_sshpass() {
    command -v sshpass &>/dev/null \
        || rdie "general" "sshpass not found. Install with: sudo apt install sshpass  /  brew install hudochenkov/sshpass/sshpass"
}

# restart_on_host <label> <user> <pass> <host> <path> <service> <compose>
# Stops <service> + fafnir-wallet, removes fafnir-wallet, then docker compose up -d.
restart_on_host() {
    local label="$1" user="$2" pass="$3" host="$4" path="$5" service="$6" compose="$7"

    rlog "▶  ${BOLD}${label}${RESET} — ${user}@${host}"

    local remote_script
    remote_script=$(cat <<ENDSSH
set -e
cd "${path}"

docker stop "${service}" 2>/dev/null \
    && echo "    stopped: ${service}" \
    || echo "    (already stopped: ${service})"

docker stop fafnir-wallet 2>/dev/null \
    && echo "    stopped: fafnir-wallet" \
    || echo "    (already stopped: fafnir-wallet)"

docker rm fafnir-wallet 2>/dev/null \
    && echo "    removed: fafnir-wallet" \
    || echo "    (did not exist: fafnir-wallet)"

docker compose -f "${compose}" up -d
echo "--- Running containers ---"
docker compose -f "${compose}" ps
ENDSSH
    )

    sshpass -p "${pass}" ssh \
        -o StrictHostKeyChecking=no \
        -o ConnectTimeout=10 \
        "${user}@${host}" \
        bash -c "${remote_script}" \
    || rdie "${label}" "Remote execution failed"

    rok "${label} done."
    echo
}

# restart_with_volumes <label> <user> <pass> <host> <path> <compose>
# docker compose down -v (removes containers + volumes), then up -d.
restart_with_volumes() {
    local label="$1" user="$2" pass="$3" host="$4" path="$5" compose="$6"

    rlog "▶  ${BOLD}${label}${RESET} — ${user}@${host} (down -v)"

    local remote_script
    remote_script=$(cat <<ENDSSH
set -e
cd "${path}"

docker compose -f "${compose}" down -v
docker compose -f "${compose}" up -d
echo "--- Running containers ---"
docker compose -f "${compose}" ps
ENDSSH
    )

    sshpass -p "${pass}" ssh \
        -o StrictHostKeyChecking=no \
        -o ConnectTimeout=10 \
        "${user}@${host}" \
        bash -c "${remote_script}" \
    || rdie "${label}" "Remote execution failed"

    rok "${label} done."
    echo
}
