# **Ecostars Deployment**

This repository contains artifacts and scripts to deploy and test the **Ecostars** pilot on top of the **Eunomia** dataspace framework. It includes example certificates for authority, provider, and consumer, Docker Compose files for each stack, and automation scripts in Bash or PowerShell.

The pilot models a sustainability-data exchange in the tourism sector: a **Provider** publishes hotel sustainability metrics (energy, water, waste, etc.) and a **Consumer** ingests them — both as participants of an Eunomia-governed dataspace.

## **Development Quickstart**

For local development, three independent stacks need to be running simultaneously.

### 1 — Dataspace infrastructure (Mini deployment)

The mini deployment brings up Heimdall (authority) and both dataspace agents (provider-side and consumer-side). It is split into three Compose files inside [`deployment/mini/`](./deployment/mini/):

```bash
docker compose -f deployment/mini/docker-compose.mini.heimdall.yaml up -d
docker compose -f deployment/mini/docker-compose.mini.provider.yaml up -d
docker compose -f deployment/mini/docker-compose.mini.consumer.yaml up -d
```

### 2 — Consumer client stack

The consumer ingestion service and its dependencies. Use the `nonifi` variant (no NiFi registry):

```bash
docker compose -f services/consumer-client-stack/docker-compose.nonifi.yaml up -d
```

### 3 — Provider final system

The provider mock server, Keycloak, and their databases:

```bash
docker compose -f services/provider-final-system/docker-compose.yaml up -d
```

### 4 — Populate the catalog

Once all three stacks are up, run the catalog population script from the repo root. It creates the dataset, distributions, policies, and connector templates/instances on the provider agent:

```bash
bash scripts/populate_catalog.sh
```

The script targets the provider agent at `http://127.0.0.1:1200` by default. Override any of the three environment variables if your setup differs:

| Variable | Default | Description |
| --- | --- | --- |
| `DATA_SPACE_PROVIDER` | `http://127.0.0.1:1200` | Provider agent URL |
| `STATIC_API` | `http://host.docker.internal:8081` | Provider static API (hotels) |
| `DYNAMIC_API` | `http://host.docker.internal:8082` | Provider dynamic API (metrics) |

Example with overrides:

```bash
DATA_SPACE_PROVIDER=http://127.0.0.1:1200 \
STATIC_API=http://host.docker.internal:8081 \
DYNAMIC_API=http://host.docker.internal:8082 \
bash scripts/populate_catalog.sh
```

The script creates the full catalog in one shot: dataset → distributions (pull + push) → policies → connector templates and instances. It uses the **OAuth2 variant** (`c`) of the push connector, which authenticates against Keycloak at `http://host.docker.internal:8083` using the `testuser` / `password` credentials.

**Requirements:** `curl` and `jq` must be installed.

---

## **Components**

This deployment orchestrates two layers of components: the dataspace infrastructure provided by Eunomia, and the Ecostars-specific services that exercise the pilot.

![Full system architecture](static/docs/image_a.png)

### Dataspace layer (Eunomia)

- **[Eunomia Agents](https://github.com/EunomiaUPM/ds-agent)**: The Dataspace Agents that handle the core logic for participants. Both the Ecostars Provider and Consumer sit behind their own agent.
- **[Heimdall](https://github.com/EunomiaUPM/heimdall)**: The Dataspace Authority and Clearing House that governs onboarding and compliance.

### Ecostars layer

```plain
                              ┌─────────────┐
                              │  Heimdall   │  (Authority / Clearing House)
                              └──────┬──────┘
                                     │
                ┌────────────────────┴────────────────────┐
                │                                         │
        ┌───────▼────────┐                       ┌────────▼────────┐
        │ Provider Agent │  ◄── DSP transfer ──► │ Consumer Agent  │
        └───────┬────────┘                       └────────┬────────┘
                │                                         │
        ┌───────▼────────┐                       ┌────────▼────────┐
        │   Provider     │                       │    Consumer     │
        │  (Mock Server) │                       │  (Ingestion)    │
        │  Go + Keycloak │                       │ FastAPI + PG    │
        └────────────────┘                       └─────────────────┘
                                                          │
                                                  ┌───────▼────────┐
                                                  │   Metabase     │
                                                  └────────────────┘
```

---

### Provider — Mock Server

A Go service ([`services/provider-final-system/`](./services/provider-final-system/)) exposing two APIs, both protected by Keycloak.

**Static API** (`http://localhost:8081`) — hotels and their yearly sustainability measures:

```bash
curl -H "Authorization: Bearer $TOKEN" http://localhost:8081/hotels
```

**Dynamic API** (`http://localhost:8082`) — real-time metric simulation with a PubSub subscription system:

```bash
# Subscribe to metric updates
curl -X POST http://localhost:8082/subscriptions/subscribe \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"url": "http://your-callback/", "event_type": "hotel_waste_generated"}'

# Unsubscribe
curl -X POST http://localhost:8082/subscriptions/unsubscribe/1 \
  -H "Authorization: Bearer $TOKEN"
```

Subscribed endpoints receive push notifications like:

```json
{
  "id": 5,
  "item_type": "hotel_waste_generated",
  "last_value": 32.71,
  "last_measured_at": "2025-10-28T00:00:00Z"
}
```

#### Keycloak authentication

Both APIs require a valid Bearer token. Keycloak is exposed on port `8083` in the dev stack. The `ecostars` realm is imported automatically on startup with the following defaults:

| | |
| --- | --- |
| Admin console | `http://localhost:8083/admin` — `admin` / `admin` |
| Client ID | `ecostars-client` |
| Client Secret | `ecostars-secret` |
| Test user | `testuser` / `password` |

Obtain a token and use it:

```bash
export TOKEN=$(curl -s -X POST \
  "http://localhost:8083/realms/ecostars/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "client_id=ecostars-client&client_secret=ecostars-secret" \
  -d "username=testuser&password=password&grant_type=password" \
  | jq -r '.access_token')

curl -H "Authorization: Bearer $TOKEN" http://localhost:8081/hotels
```

---

### Consumer — Ingestion Service

A FastAPI microservice ([`services/consumer-client-stack/`](./services/consumer-client-stack/)) that persists data into PostgreSQL and exposes it through Metabase.

![Consumer data infrastructure](static/docs/image_b.png)

The service exposes two ingestion endpoints:

**`POST /consumer-ingestion/pull`** — on-demand bulk fetch. Calls the given URL, then upserts the returned hotels and measures into the database:

```json
{ "url": "http://host.docker.internal:8081/hotels" }
```

**`POST /consumer-ingestion/push`** — webhook for real-time metric updates, appended as immutable historical records:

```json
{
  "id": 7,
  "item_type": "hotel_energy_usage",
  "last_value": 71.74,
  "last_measured_at": "2026-02-23T00:00:00Z"
}
```

The Metabase dashboard (port `3000`) queries the transactional database directly and provides charts for hotel counts, measures, and metric time series:

![Metabase dashboard](static/docs/metabase.png)

| Service | URL |
| --- | --- |
| Ingestion Service | `http://localhost:8000` |
| Swagger UI | `http://localhost:8000/docs` |
| Metabase | `http://localhost:3000` |
| PostgreSQL | `localhost:5440` |

## **Requirements**

- Docker and docker-compose (or Docker Desktop)
- Permissions to execute scripts (`chmod +x`)
- Free local ports: `1500` (Heimdall), `8080` (Keycloak), `8081` (Provider static API), `8082` (Provider dynamic API), `8083` (Keycloak dev), `8000` (Consumer ingestion), `3000` (Metabase), `5440` (PostgreSQL), `18080` (NiFi Registry)

## **DID Configuration**

Depending on the environment, the Decentralized Identifier (DID) method changes. While **GAIA-X officially only supports `did:web`**, Eunomia allows flexibility for local testing:

- **Mini Deployment (Local)**: Uses **`did:jwk`**. Since `did:web` requires a public domain and resolving a `did.json` file, it is not suitable for local-only environments.
- **Prod Deployment**: Supports both, but **`did:web`** should be used to remain compliant with GAIA-X standards.

> [!TIP]
> Heimdall is specifically designed to work as a **Clearing House using `did:jwk`** in local/mini mode, allowing you to test the full compliance flow without needing complex DNS or web server setups.

## **External Dependencies**

This project depends on the **public walt.id wallet API** for credential management. Mini deployments use a local walt.id stack; production deployments point to the public hosted service. See the specific deployment guides for details.

The Ecostars layer adds two more external-facing dependencies, both deployed locally as containers:

- **PostgreSQL** — transactional store for the Consumer's ingested data.
- **Keycloak** — identity provider used by the Provider's APIs (default realm `ecostars` is imported on startup).

## **GAIA-X Compliance**

By default, Eunomia operates in a generic dataspace mode. To make the deployment **GAIA-X compliant**, the following three changes are required. They apply to **both** the Provider Agent and the Consumer Agent.

### 1 — Verification configuration

In each Agent config YAML, update the `verify_req_config` block to require a GAIA-X Label Credential:

```yaml
verify_req_config:
  is_cert_allowed: false
  vcs_requested: [gx:LabelCredential]
```

### 2 — GAIA-X connectivity

Add (or update) the `gaia_config` block pointing to the Heimdall instance. The values differ between Mini and Prod:

```yaml
gaia_config:
  api:
    protocol: "http" # mini: http | prod: https
    url: "url" # mini: host.docker.internal | prod: your.domain.com
    port: null # mini: 1500 (Heimdall port) | prod: null
```

### 3 — Heimdall startup command

In the Docker Compose file, change the `command` for **both** the `heimdall` and `heimdall-setup` services to use the GAIA-X ecosystem config:

```yaml
command:
  - setup
  - --env-file
  - /app/static/config/eco_authority.yaml
```

---

> [!NOTE]
> The `eco_authority.yaml` config activates **all** Heimdall roles simultaneously:
>
> - **GAIA-X Clearing House** — essentially a **Dataspace Authority specifically for the GAIA-X ecosystem**; it validates and signs compliance credentials on behalf of the ecosystem.
> - **Clearing House Proxy** — proxies requests to the Clearing House.
> - **Legal Authority** — issues legal-level credentials within the dataspace.
> - **Dataspace Authority** — governs participant onboarding and policy enforcement.
>
> In a **real-world ecosystem**, a single entity cannot (and should not) assume all these roles simultaneously as it would **centralize the system**, defeating the purpose of a decentralized architecture. This multi-role configuration is strictly intended for **development and testing** purposes.

## **Repository Structure**

```plain
ecostars-deployment/
├── README.md                                   # this file
├── deployment/
│   ├── mini/                                   # local docker-compose deployment
│   │   ├── docker-compose.mini.heimdall.yaml
│   │   ├── docker-compose.mini.provider.yaml
│   │   ├── docker-compose.mini.consumer.yaml
│   │   └── README.md
│   └── prod/                                   # TLS + Vault + Keycloak deployment
│       └── README.md
├── services/
│   ├── consumer-client-stack/                  # Consumer ingestion service + dependencies
│   │   └── docker-compose.nonifi.yaml          # dev variant (no NiFi)
│   └── provider-final-system/                  # Provider mock server + Keycloak
│       └── docker-compose.yaml
└── certs/                                      # example certificates (authority, provider, consumer)
```
