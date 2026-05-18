#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
# DATA_SPACE_PROVIDER=https://eunomia-provider.dit.upm.es
DATA_SPACE_PROVIDER=http://localhost:1200

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../services/provider-final-system/.env"

# Load configuration from .env if available, otherwise fall back to env vars / defaults.
if [[ -f "${ENV_FILE}" ]]; then
  # API  - ESDS_API base URL
  # API_KEY - bearer token
  ESDS_API="$(grep -E '^API=' "${ENV_FILE}" | cut -d= -f2-)"
  API_KEY="$(grep  -E '^API_KEY=' "${ENV_FILE}" | cut -d= -f2-)"
else
  echo "WARNING: .env not found at ${ENV_FILE}" >&2
  echo "         Falling back to env vars / defaults." >&2
  ESDS_API="${ESDS_API:-http://host.docker.internal:8081}"
  API_KEY="${API_KEY:-}"
fi

JSON_HEADER_CT="Content-Type: application/json"
PAYLOADS_DIR="${SCRIPT_DIR}/catalog-payloads"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
provider_get()  { curl -sf -H "${JSON_HEADER_CT}" "${DATA_SPACE_PROVIDER}${1}"; }
provider_post() { curl -sf -X POST -H "${JSON_HEADER_CT}" -d "${2}" "${DATA_SPACE_PROVIDER}${1}"; }

# ---------------------------------------------------------------------------
# 1. Catalog + data service
# ---------------------------------------------------------------------------
echo "==> Fetching main catalog..."
CATALOG_ID=$(provider_get "/api/v1/catalog-agent/catalogs/main" | jq -r '.id')
echo "    catalog_id = ${CATALOG_ID}"

echo "==> Fetching main data service..."
DATA_SERVICE_ID=$(provider_get "/api/v1/catalog-agent/data-services/main" | jq -r '.id')
echo "    data_service_id = ${DATA_SERVICE_ID}"

# ---------------------------------------------------------------------------
# 2. Datasets
# ---------------------------------------------------------------------------
echo "==> Creating environmental dataset..."
DATASET_ENV_PAYLOAD=$(jq --arg catalogId "${CATALOG_ID}" '.catalogId = $catalogId' \
  "${PAYLOADS_DIR}/01-dataset-environmental.json")
DATASET_ENV_ID=$(provider_post "/api/v1/catalog-agent/datasets" "${DATASET_ENV_PAYLOAD}" | jq -r '.id')
echo "    dataset_environmental_id = ${DATASET_ENV_ID}"

echo "==> Creating social dataset..."
DATASET_SOC_PAYLOAD=$(jq --arg catalogId "${CATALOG_ID}" '.catalogId = $catalogId' \
  "${PAYLOADS_DIR}/02-dataset-social.json")
DATASET_SOC_ID=$(provider_post "/api/v1/catalog-agent/datasets" "${DATASET_SOC_PAYLOAD}" | jq -r '.id')
echo "    dataset_social_id = ${DATASET_SOC_ID}"

# ---------------------------------------------------------------------------
# 3. Distributions
# ---------------------------------------------------------------------------
echo "==> Creating environmental PULL distribution..."
DIST_ENV_PULL_ID=$(jq --arg svc "${DATA_SERVICE_ID}" --arg ds "${DATASET_ENV_ID}" \
  '.dcatAccessService = $svc | .datasetId = $ds' \
  "${PAYLOADS_DIR}/03-distribution-pull-environmental.json" \
  | provider_post "/api/v1/catalog-agent/distributions" "$(cat -)" | jq -r '.id')
echo "    distribution_env_pull_id = ${DIST_ENV_PULL_ID}"

echo "==> Creating environmental PUSH distribution..."
DIST_ENV_PUSH_ID=$(jq --arg svc "${DATA_SERVICE_ID}" --arg ds "${DATASET_ENV_ID}" \
  '.dcatAccessService = $svc | .datasetId = $ds' \
  "${PAYLOADS_DIR}/04-distribution-push-environmental.json" \
  | provider_post "/api/v1/catalog-agent/distributions" "$(cat -)" | jq -r '.id')
echo "    distribution_env_push_id = ${DIST_ENV_PUSH_ID}"

echo "==> Creating social PULL distribution..."
DIST_SOC_PULL_ID=$(jq --arg svc "${DATA_SERVICE_ID}" --arg ds "${DATASET_SOC_ID}" \
  '.dcatAccessService = $svc | .datasetId = $ds' \
  "${PAYLOADS_DIR}/05-distribution-pull-social.json" \
  | provider_post "/api/v1/catalog-agent/distributions" "$(cat -)" | jq -r '.id')
echo "    distribution_soc_pull_id = ${DIST_SOC_PULL_ID}"

echo "==> Creating social PUSH distribution..."
DIST_SOC_PUSH_ID=$(jq --arg svc "${DATA_SERVICE_ID}" --arg ds "${DATASET_SOC_ID}" \
  '.dcatAccessService = $svc | .datasetId = $ds' \
  "${PAYLOADS_DIR}/06-distribution-push-social.json" \
  | provider_post "/api/v1/catalog-agent/distributions" "$(cat -)" | jq -r '.id')
echo "    distribution_soc_push_id = ${DIST_SOC_PUSH_ID}"

# ---------------------------------------------------------------------------
# 4. Policies - environmental dataset
# ---------------------------------------------------------------------------
echo "==> Instantiating policy template for environmental dataset..."
jq --arg ds "${DATASET_ENV_ID}" '.entityId = $ds' "${PAYLOADS_DIR}/07-policy-template-instantiate.json" \
  | provider_post "/api/v1/catalog-agent/policy-templates/instantiate-odrl-offer" "$(cat -)" | jq .

echo "==> Creating commercial ODRL policy for environmental dataset..."
jq --arg ds "${DATASET_ENV_ID}" '.entityId = $ds' "${PAYLOADS_DIR}/08-policy-commercial.json" \
  | provider_post "/api/v1/catalog-agent/odrl-policies" "$(cat -)" | jq .

echo "==> Creating research-trial ODRL policy for environmental dataset..."
jq --arg ds "${DATASET_ENV_ID}" '.entityId = $ds' "${PAYLOADS_DIR}/09-policy-research-trial.json" \
  | provider_post "/api/v1/catalog-agent/odrl-policies" "$(cat -)" | jq .

# ---------------------------------------------------------------------------
# 5. Policies - social dataset
# ---------------------------------------------------------------------------
echo "==> Instantiating policy template for social dataset..."
jq --arg ds "${DATASET_SOC_ID}" '.entityId = $ds' "${PAYLOADS_DIR}/07-policy-template-instantiate.json" \
  | provider_post "/api/v1/catalog-agent/policy-templates/instantiate-odrl-offer" "$(cat -)" | jq .

echo "==> Creating commercial ODRL policy for social dataset..."
jq --arg ds "${DATASET_SOC_ID}" '.entityId = $ds' "${PAYLOADS_DIR}/08-policy-commercial.json" \
  | provider_post "/api/v1/catalog-agent/odrl-policies" "$(cat -)" | jq .

echo "==> Creating research-trial ODRL policy for social dataset..."
jq --arg ds "${DATASET_SOC_ID}" '.entityId = $ds' "${PAYLOADS_DIR}/09-policy-research-trial.json" \
  | provider_post "/api/v1/catalog-agent/odrl-policies" "$(cat -)" | jq .

# ---------------------------------------------------------------------------
# 6. Connector templates (shared across both datasets)
# ---------------------------------------------------------------------------
echo "==> Creating PULL connector template..."
CONN_PULL_TMPL_RESP=$(provider_post "/api/v1/connector/templates" "$(cat "${PAYLOADS_DIR}/10-connector-template-pull.json")")
CONN_PULL_NAME=$(echo "${CONN_PULL_TMPL_RESP}" | jq -r '.name')
CONN_PULL_VERSION=$(echo "${CONN_PULL_TMPL_RESP}" | jq -r '.version')
echo "    pull_connector_template = ${CONN_PULL_NAME}  v${CONN_PULL_VERSION}"

echo "==> Creating PUSH connector template..."
CONN_PUSH_TMPL_RESP=$(provider_post "/api/v1/connector/templates" "$(cat "${PAYLOADS_DIR}/11-connector-template-push.json")")
CONN_PUSH_NAME=$(echo "${CONN_PUSH_TMPL_RESP}" | jq -r '.name')
CONN_PUSH_VERSION=$(echo "${CONN_PUSH_TMPL_RESP}" | jq -r '.version')
echo "    push_connector_template = ${CONN_PUSH_NAME}  v${CONN_PUSH_VERSION}"

# ---------------------------------------------------------------------------
# 7. Connector instances
# ---------------------------------------------------------------------------
sub_conn_pull() {
  local file="$1" distId="$2"
  jq \
    --arg name    "${CONN_PULL_NAME}" \
    --arg version "${CONN_PULL_VERSION}" \
    --arg distId  "${distId}" \
    --arg esdsApi "${ESDS_API}" \
    --arg token   "${API_KEY}" \
    '.templateName = $name | .templateVersion = $version | .distributionId = $distId
     | (.parameters.ACCESS_URL) |= gsub("__ESDS_API__"; $esdsApi)
     | .parameters.TOKEN = $token' \
    "$file"
}

sub_conn_push() {
  local file="$1" distId="$2"
  jq \
    --arg name    "${CONN_PUSH_NAME}" \
    --arg version "${CONN_PUSH_VERSION}" \
    --arg distId  "${distId}" \
    --arg esdsApi "${ESDS_API}" \
    --arg token   "${API_KEY}" \
    '.templateName = $name | .templateVersion = $version | .distributionId = $distId
     | (.parameters.SUB_URL) |= gsub("__ESDS_API__"; $esdsApi)
     | .parameters.TOKEN = $token' \
    "$file"
}

echo "==> Creating environmental PULL connector instance..."
provider_post "/api/v1/connector/instances" \
  "$(sub_conn_pull "${PAYLOADS_DIR}/12-connector-instance-pull-environmental.json" "${DIST_ENV_PULL_ID}")" | jq .

echo "==> Creating social PULL connector instance..."
provider_post "/api/v1/connector/instances" \
  "$(sub_conn_pull "${PAYLOADS_DIR}/13-connector-instance-pull-social.json" "${DIST_SOC_PULL_ID}")" | jq .

echo "==> Creating environmental PUSH connector instance..."
provider_post "/api/v1/connector/instances" \
  "$(sub_conn_push "${PAYLOADS_DIR}/14-connector-instance-push-environmental.json" "${DIST_ENV_PUSH_ID}")" | jq .

echo "==> Creating social PUSH connector instance..."
provider_post "/api/v1/connector/instances" \
  "$(sub_conn_push "${PAYLOADS_DIR}/15-connector-instance-push-social.json" "${DIST_SOC_PUSH_ID}")" | jq .

echo ""
echo "Done! Catalog populated successfully."
