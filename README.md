# Ecostars Deployment

This repository contains the artifacts and scripts to deploy and test the **Ecostars** pilot on top of the **Eunomia** dataspace framework. The pilot models a sustainability-data exchange: a **Provider** publishes hotel sustainability metrics (energy, water, waste, etc.) and a **Consumer** ingests them — both as participants of an Eunomia-governed dataspace.

---

## Architecture

Two layers of components work together: the dataspace infrastructure provided by Eunomia, and the Ecostars-specific services that exercise the pilot.

```text
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
    │    Provider    │                       │    Consumer     │
    │  (Mock Server) │                       │  (Ingestion)    │
    │  Go + Keycloak │                       │ FastAPI + PG    │
    └────────────────┘                       └────────┬────────┘
                                                      │
                                              ┌───────▼────────┐
                                              │   Metabase     │
                                              └────────────────┘
```

### Dataspace layer (Eunomia)

- [**Eunomia DS-Agent**](https://github.com/EunomiaUPM/ds-agent): Dataspace Agents that handle core DSP logic for each participant.
- [**Heimdall**](https://github.com/EunomiaUPM/heimdall): Dataspace Authority and Clearing House that governs onboarding and compliance.

### Ecostars layer

- **Provider**: A Go mock server exposing hotel data via static and dynamic APIs, protected by Keycloak.
- **Consumer**: A FastAPI ingestion service that persists data into PostgreSQL and exposes it through Metabase.

---

## Requirements

- Docker and Docker Compose (or Docker Desktop)
- `curl` and `jq` installed (needed for the catalog script)
- Permissions to execute scripts (`chmod +x`)
- The following local ports must be free:

| Port    | Service                  |
| ------- | ------------------------ |
| `1500`  | Heimdall                 |
| `1100`  | Consumer DS-Agent        |
| `1200`  | Provider DS-Agent        |
| `8080`  | Keycloak                 |
| `8081`  | Provider static API      |
| `8082`  | Provider dynamic API     |
| `8083`  | Keycloak (dev)           |
| `8000`  | Consumer ingestion API   |
| `3000`  | Metabase                 |
| `5440`  | PostgreSQL               |
| `18080` | NiFi Registry (optional) |

---

## Setup

Three independent stacks must be running simultaneously. Start them in order.

### 1 — Dataspace infrastructure (Mini deployment)

Brings up Heimdall (authority) and both dataspace agents. Split into three Compose files inside [`deployment/mini/`](deployment/mini/):

```bash
docker compose -f deployment/mini/docker-compose.mini.heimdall.yaml up -d
docker compose -f deployment/mini/docker-compose.mini.provider.yaml up -d
docker compose -f deployment/mini/docker-compose.mini.consumer.yaml up -d
```

### 2 — Provider stack

The provider mock server, Keycloak, and their databases:

```bash
docker compose -f services/provider-final-system/docker-compose.yaml up -d
```

### 3 — Consumer stack

The consumer ingestion service and its dependencies. Use the `nonifi` variant unless you have a dedicated server for NiFi (it has high RAM requirements):

```bash
docker compose -f services/consumer-client-stack/docker-compose.nonifi.yaml up -d
```

### 4 — Populate the catalog

Once all three stacks are up, run the catalog population script from the repo root. It creates the dataset, distributions, policies, and connector templates/instances on the provider agent:

```bash
bash scripts/populate_catalog.sh
```

The script targets the provider agent at `http://127.0.0.1:1200` by default. Override any variable if your setup differs:

| Variable              | Default                            | Description                  |
| --------------------- | ---------------------------------- | ---------------------------- |
| `DATA_SPACE_PROVIDER` | `http://127.0.0.1:1200`            | Provider agent URL           |
| `STATIC_API`          | `http://host.docker.internal:8081` | Provider static API (hotels) |
| `DYNAMIC_API`         | `http://host.docker.internal:8082` | Provider dynamic API         |

```bash
DATA_SPACE_PROVIDER=http://127.0.0.1:1200 \
STATIC_API=http://host.docker.internal:8081 \
DYNAMIC_API=http://host.docker.internal:8082 \
bash scripts/populate_catalog.sh
```

The script creates the full catalog in one shot: dataset → distributions (pull + push) → policies → connector templates and instances. It uses the **OAuth2 variant** (`c`) of the push connector, which authenticates against Keycloak at `http://host.docker.internal:8083` with `testuser` / `password`.

---

## Usage

### Contract negotiation and data transfer

Use the Eunomia DS-Agent UI to initiate a DSP-compliant contract negotiation and transfer session:

| Agent    | URL                      |
| -------- | ------------------------ |
| Provider | `http://127.0.0.1:1200`  |
| Consumer | `http://127.0.0.1:1100`  |

![Contract negotiation](static/docs/negotiation.png)

After negotiation, trigger a transfer to move data through the dataplane:

![Dataplane transfer](static/docs/dataplane.png)

### Consumer ingestion endpoints

The ingestion service ([`services/consumer-client-stack/`](services/consumer-client-stack/)) exposes two endpoints:

**`POST /consumer-ingestion/pull`** — on-demand bulk fetch. Calls the given URL and upserts the returned hotels and measures into the database:

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

![Ingestion infrastructure](static/docs/ingestion.png)

### Metabase dashboards

The Metabase dashboard queries the transactional database directly and provides charts for hotel counts, measures, and metric time series:

![Metabase dashboard](static/docs/metabase.png)

![Metabase dashboard](static/docs/metabase2.png)

| Service           | URL                          |
| ----------------- | ---------------------------- |
| Ingestion Service | `http://localhost:8000`      |
| Swagger UI        | `http://localhost:8000/docs` |
| Metabase          | `http://localhost:3000`      |
| PostgreSQL        | `localhost:5440`             |

---

## Configuration

### DID method

Depending on the environment, the Decentralized Identifier (DID) method changes. While **GAIA-X officially only supports `did:web`**, Eunomia allows flexibility for local testing:

- **Mini / local**: Uses **`did:jwk`**. Since `did:web` requires a public domain, it is not suitable for local-only environments.
- **Production**: Uses **`did:web`** to remain compliant with GAIA-X standards.

> [!TIP]
> Heimdall is designed to work as a Clearing House using `did:jwk` in local/mini mode, allowing you to test the full compliance flow without DNS or web server setup.

### External dependencies

This project depends on the **public [walt.id](https://walt.id) wallet API** for credential management. Mini deployments use a local walt.id stack; production deployments point to the public hosted service.

---

## GAIA-X Compliance

By default, Eunomia operates in a generic dataspace mode. To make the deployment **GAIA-X compliant**, apply the following three changes to **both** the Provider Agent and the Consumer Agent.

### 1 — Verification configuration

In each Agent config YAML, update the `verify_req_config` block to require a GAIA-X Label Credential:

```yaml
verify_req_config:
  is_cert_allowed: false
  vcs_requested: [gx:LabelCredential]
```

### 2 — GAIA-X connectivity

Add (or update) the `gaia_config` block pointing to the Heimdall instance:

```yaml
gaia_config:
  api:
    protocol: "http"   # mini: http | prod: https
    url: "url"         # mini: host.docker.internal | prod: your.domain.com
    port: null         # mini: 1500 (Heimdall port) | prod: null
```

### 3 — Heimdall startup command

In the Docker Compose file, change the `command` for both the `heimdall` and `heimdall-setup` services:

```yaml
command:
  - setup
  - --env-file
  - /app/static/config/eco_authority.yaml
```

> [!NOTE]
> The `eco_authority.yaml` config activates **all** Heimdall roles simultaneously: GAIA-X Clearing House, Clearing House Proxy, Legal Authority, and Dataspace Authority. In a real-world ecosystem a single entity should not assume all these roles — this multi-role configuration is strictly for **development and testing**.
