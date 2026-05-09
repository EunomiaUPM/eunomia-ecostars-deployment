#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DATA_SPACE_PROVIDER="${DATA_SPACE_PROVIDER:-http://127.0.0.1:1200}"
#DATA_SPACE_PROVIDER=https://dev-dataspaces.dit.upm.es:1200
# STATIC_API="${STATIC_API:-http://127.0.0.1:8081}"
# DYNAMIC_API="${DYNAMIC_API:-http://127.0.0.1:8082}"
STATIC_API="${STATIC_API:-http://host.docker.internal:8081}"
DYNAMIC_API="${DYNAMIC_API:-http://host.docker.internal:8082}"
OPTION="c"

JSON_HEADER_CT="Content-Type: application/json"
PAYLOADS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/catalog-payloads"

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
provider_get()  { curl -sf -H "${JSON_HEADER_CT}"  "${DATA_SPACE_PROVIDER}${1}"; }
provider_post() { curl -sf -X POST -H "${JSON_HEADER_CT}"  -d "${2}" "${DATA_SPACE_PROVIDER}${1}"; }

# ---------------------------------------------------------------------------
# 1. Get main catalog ID
# ---------------------------------------------------------------------------
echo "==> Fetching main catalog..."
CATALOG_RESP=$(provider_get "/api/v1/catalog-agent/catalogs/main")
CATALOG_ID=$(echo "${CATALOG_RESP}" | jq -r '.id')
echo "    catalog_id = ${CATALOG_ID}"

# ---------------------------------------------------------------------------
# 2. Get main data service ID
# ---------------------------------------------------------------------------
echo "==> Fetching main data service..."
DATA_SERVICE_RESP=$(provider_get "/api/v1/catalog-agent/data-services/main")
DATA_SERVICE_ID=$(echo "${DATA_SERVICE_RESP}" | jq -r '.id')
echo "    data_service_id = ${DATA_SERVICE_ID}"

# ---------------------------------------------------------------------------
# 3. Create dataset
# ---------------------------------------------------------------------------
echo "==> Creating dataset..."
DATASET_PAYLOAD=$(jq \
  --arg catalogId "${CATALOG_ID}" \
  '.catalogId = $catalogId' \
  "${PAYLOADS_DIR}/01-dataset.json")

DATASET_RESP=$(provider_post "/api/v1/catalog-agent/datasets" "${DATASET_PAYLOAD}")
DATASET_ID=$(echo "${DATASET_RESP}" | jq -r '.id')
echo "    dataset_id = ${DATASET_ID}"

# ---------------------------------------------------------------------------
# 4. Create PULL distribution
# ---------------------------------------------------------------------------
echo "==> Creating PULL distribution..."
DIST_PULL_PAYLOAD=$(jq \
  --arg svc "${DATA_SERVICE_ID}" \
  --arg ds  "${DATASET_ID}" \
  '.dcatAccessService = $svc | .datasetId = $ds' \
  "${PAYLOADS_DIR}/02-distribution-pull.json")

DIST_PULL_RESP=$(provider_post "/api/v1/catalog-agent/distributions" "${DIST_PULL_PAYLOAD}")
DISTRIBUTION_PULL_ID=$(echo "${DIST_PULL_RESP}" | jq -r '.id')
echo "    distribution_pull_id = ${DISTRIBUTION_PULL_ID}"

# ---------------------------------------------------------------------------
# 5. Create PUSH distribution
# ---------------------------------------------------------------------------
echo "==> Creating PUSH distribution..."
DIST_PUSH_PAYLOAD=$(jq \
  --arg svc "${DATA_SERVICE_ID}" \
  --arg ds  "${DATASET_ID}" \
  '.dcatAccessService = $svc | .datasetId = $ds' \
  "${PAYLOADS_DIR}/03-distribution-push.json")

DIST_PUSH_RESP=$(provider_post "/api/v1/catalog-agent/distributions" "${DIST_PUSH_PAYLOAD}")
DISTRIBUTION_PUSH_ID=$(echo "${DIST_PUSH_RESP}" | jq -r '.id')
echo "    distribution_push_id = ${DISTRIBUTION_PUSH_ID}"

# ---------------------------------------------------------------------------
# 6. Create policy from template (policy-1)
# ---------------------------------------------------------------------------
echo "==> Instantiating policy from template (time-limited research access)..."
POLICY_TMPL_PAYLOAD=$(jq \
  --arg ds "${DATASET_ID}" \
  '.entityId = $ds' \
  "${PAYLOADS_DIR}/04-policy-template-instantiate.json")

provider_post "/api/v1/catalog-agent/policy-templates/instantiate-odrl-offer" "${POLICY_TMPL_PAYLOAD}" | jq .

# ---------------------------------------------------------------------------
# 7. Create policies directly via API
# ---------------------------------------------------------------------------
echo "==> Creating ODRL policy: commercial use with attribution and time window..."
POLICY_COMMERCIAL_PAYLOAD=$(jq \
  --arg ds "${DATASET_ID}" \
  '.entityId = $ds' \
  "${PAYLOADS_DIR}/05-policy-commercial.json")

provider_post "/api/v1/catalog-agent/odrl-policies" "${POLICY_COMMERCIAL_PAYLOAD}" | jq .

echo "==> Creating ODRL policy: research-only access with 6-month trial window..."
POLICY_RESEARCH_PAYLOAD=$(jq \
  --arg ds "${DATASET_ID}" \
  '.entityId = $ds' \
  "${PAYLOADS_DIR}/06-policy-research-trial.json")

provider_post "/api/v1/catalog-agent/odrl-policies" "${POLICY_RESEARCH_PAYLOAD}" | jq .

# ---------------------------------------------------------------------------
# 8. Create PULL connector template
# ---------------------------------------------------------------------------
echo "==> Creating PULL connector template..."
CONN_PULL_TMPL_PAYLOAD=$(cat "${PAYLOADS_DIR}/07${OPTION}-connector-template-pull.json")

CONN_PULL_TMPL_RESP=$(provider_post "/api/v1/connector/templates" "${CONN_PULL_TMPL_PAYLOAD}")
CONN_PULL_NAME=$(echo "${CONN_PULL_TMPL_RESP}" | jq -r '.name')
CONN_PULL_VERSION=$(echo "${CONN_PULL_TMPL_RESP}" | jq -r '.version')
echo "    pull_connector_template = ${CONN_PULL_NAME}  v${CONN_PULL_VERSION}"

# ---------------------------------------------------------------------------
# 9. Instantiate PULL connector
# ---------------------------------------------------------------------------
echo "==> Creating PULL connector instance..."
CONN_PULL_INST_PAYLOAD=$(jq \
  --arg name      "${CONN_PULL_NAME}" \
  --arg version   "${CONN_PULL_VERSION}" \
  --arg distId    "${DISTRIBUTION_PULL_ID}" \
  --arg staticApi "${STATIC_API}" \
  '.templateName = $name | .templateVersion = $version | .distributionId = $distId | .parameters.ACCESS_URL = $staticApi' \
  "${PAYLOADS_DIR}/08${OPTION}-connector-instance-pull.json")

provider_post "/api/v1/connector/instances" "${CONN_PULL_INST_PAYLOAD}" | jq .

# ---------------------------------------------------------------------------
# 10. Create PUSH connector template
# ---------------------------------------------------------------------------
echo "==> Creating PUSH connector template..."
CONN_PUSH_TMPL_PAYLOAD=$(cat "${PAYLOADS_DIR}/09${OPTION}-connector-template-push.json")

CONN_PUSH_TMPL_RESP=$(provider_post "/api/v1/connector/templates" "${CONN_PUSH_TMPL_PAYLOAD}")
CONN_PUSH_NAME=$(echo "${CONN_PUSH_TMPL_RESP}" | jq -r '.name')
CONN_PUSH_VERSION=$(echo "${CONN_PUSH_TMPL_RESP}" | jq -r '.version')
echo "    push_connector_template = ${CONN_PUSH_NAME}  v${CONN_PUSH_VERSION}"

# ---------------------------------------------------------------------------
# 11. Instantiate PUSH connector
# ---------------------------------------------------------------------------
echo "==> Creating PUSH connector instance..."
CONN_PUSH_INST_PAYLOAD=$(jq \
  --arg name       "${CONN_PUSH_NAME}" \
  --arg version    "${CONN_PUSH_VERSION}" \
  --arg distId     "${DISTRIBUTION_PUSH_ID}" \
  --arg dynamicApi "${DYNAMIC_API}" \
  '.templateName = $name | .templateVersion = $version | .distributionId = $distId
   | .parameters.SUB_URL   = ($dynamicApi + "/subscriptions/subscribe")
   | .parameters.UNSUB_URL = ($dynamicApi + "/subscriptions/unsubscribe")' \
  "${PAYLOADS_DIR}/10${OPTION}-connector-instance-push.json")

provider_post "/api/v1/connector/instances" "${CONN_PUSH_INST_PAYLOAD}" | jq .

echo ""
echo "Done! Catalog populated successfully."
