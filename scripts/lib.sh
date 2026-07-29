AUTHORITY_URL="${AUTHORITY_URL:-http://127.0.0.1:1500}"
CONSUMER_URL="${CONSUMER_URL:-http://127.0.0.1:1100}"
PROVIDER_URL="${PROVIDER_URL:-http://127.0.0.1:1200}"

DOCKER_AUTHORITY_URL="${DOCKER_AUTHORITY_URL:-http://host.docker.internal:1500}"
DOCKER_CONSUMER_URL="${DOCKER_CONSUMER_URL:-http://host.docker.internal:1100}"
DOCKER_PROVIDER_URL="${DOCKER_PROVIDER_URL:-http://host.docker.internal:1200}"

log_step()    { echo -e "\n\033[36m$1\033[0m" >&2; }
log_success() { echo -e "\033[32m$1\033[0m" >&2; }
log_error()   { echo -e "\033[31m$1\033[0m" >&2; exit 1; }
log_info()    { echo -e "\033[33m$1\033[0m" >&2; }

curl_raw() {
    local method=${1:-GET}
    local url=$2
    local body=${3:-}
    if [ -n "$body" ]; then
        curl -s -X "$method" "$url" -H "Content-Type: application/json" -d "$body"
    else
        curl -s -X "$method" "$url" -H "Content-Type: application/json"
    fi
}

# Like curl_raw, but aborts on any non-2xx response. Prefer it for anything
# that mutates state: curl_raw swallows errors, so failed steps go unnoticed
# and the script still reports success.
curl_checked() {
    local method=${1:-GET}
    local url=$2
    local body=${3:-}
    local out code
    out=$(mktemp)
    if [ -n "$body" ]; then
        code=$(curl -s -o "$out" -w '%{http_code}' -X "$method" "$url" \
            -H "Content-Type: application/json" -d "$body")
    else
        code=$(curl -s -o "$out" -w '%{http_code}' -X "$method" "$url" \
            -H "Content-Type: application/json")
    fi
    if [[ ! "$code" =~ ^2 ]]; then
        log_error "$method $url -> HTTP $code
$(head -c 400 "$out")"
    fi
    cat "$out"
    rm -f "$out"
}
