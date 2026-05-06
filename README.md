# **Ecostars Deployment**

This repository contains artifacts and scripts to deploy and test the **Ecostars** pilot on top of the **Eunomia** dataspace framework. It includes example certificates for authority, provider, and consumer, a central docker-compose file, and automation scripts in Bash or PowerShell.

The pilot models a sustainability-data exchange in the tourism sector: a **Provider** publishes hotel sustainability metrics (energy, water, waste, etc.) and a **Consumer** ingests them — both as participants of an Eunomia-governed dataspace.

## **Components**

This deployment orchestrates two layers of components: the dataspace infrastructure provided by Eunomia, and the Ecostars-specific services that exercise the pilot.

### Dataspace layer (Eunomia)

- **[Eunomia Agents](https://github.com/EunomiaUPM/ds-agent)**: The Dataspace Agents that handle the core logic for participants. Both the Ecostars Provider and Consumer sit behind their own agent.
- **[Heimdall](https://github.com/EunomiaUPM/heimdall)**: The Dataspace Authority and Clearing House that governs onboarding and compliance.

### Ecostars layer

- **[Ecostars Provider (Mock Server)](./services/provider/README.md)**: A Go service exposing a static REST API for hotels and yearly measures, plus a PubSub dynamic API for real-time metric updates. Protected by Keycloak. Click the link for the specific guide.
- **[Ecostars Consumer (Ingestion Service)](./services/consumer/README.md)**: A FastAPI microservice that pulls bulk data and receives push notifications from the Provider, persisting everything into PostgreSQL for Metabase dashboards. Click the link for the specific guide.

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

## **Deployment Methods**

There are two main ways to deploy this environment:

1. **[Mini Deployment](./deployment/mini/README.md)**: A lightweight deployment using Docker Compose, intended for local development and demos. Click the link to see the specific guide.
2. **[Prod Deployment](./deployment/prod/README.md)**: Production deployment with TLS, Vault, and Keycloak. Click the link to see the specific guide.

## **Requirements**

- Docker and docker-compose (or Docker Desktop)
- Permissions to execute scripts (`chmod +x`)
- Free local ports: `1500` (Heimdall), `8080` (Keycloak), `8081` (Provider static API), `8082` (Provider dynamic API), `8000` (Consumer ingestion), `3000` (Metabase), `5440` (PostgreSQL), `18080` (NiFi Registry)

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
├── README.md                       # this file
├── deployment/
│   ├── mini/                       # local docker-compose deployment
│   │   └── README.md
│   └── prod/                       # TLS + Vault + Keycloak deployment
│       └── README.md
├── services/
│   ├── provider/                   # Ecostars Mock Server (Go)
│   │   └── README.md
│   └── consumer/                   # Ecostars Ingestion Service (FastAPI)
│       └── README.md
└── certs/                          # example certificates (authority, provider, consumer)
```
