# Prod Deployment

This folder contains the production deployment for the Eunomia framework. Unlike the [standalone deployment](../standalone/README.md), this mode is designed for real servers with a domain name, TLS certificates, and production-grade secrets management through HashiCorp Vault.

---

## Overview

There are two independent components you can deploy:

| Component    | Role                                                                                             | Guide                        |
| ------------ | ------------------------------------------------------------------------------------------------ | ---------------------------- |
| **Heimdall** | Dataspace Authority - manages participants, issues credentials, and enforces governance policies | [heimdall.md](./heimdall.md) |
| **Agent**    | Participant node - acts as a data provider, consumer, or both within the dataspace               | [agent.md](./agent.md)       |

Each component has its own Docker Compose file and its own Vault instance. They can be deployed on separate servers or on the same machine.

> [!IMPORTANT]
> **Deploy Heimdall first.** Agents need to register with a running Heimdall instance to obtain their Verifiable Credentials before they can participate in the dataspace.

---

## Requirements

- Docker and Docker Compose installed on the server
- A domain name pointing to your server
- TLS certificates for your domain in PEM format

---

## Quick Start

1. **Deploy Heimdall** → follow [heimdall.md](./heimdall.md)
2. **Deploy one or more Agents** → follow [agent.md](./agent.md)

---

## Wallet: Fafnir

Each component runs its own [Fafnir](https://github.com/EunomiaUPM/fafnir-wallet) wallet (`rmenendez8/fafnir:v0.2.0`) inside its compose file, so there is no external wallet service or account to set up. The wallet stores its keys and DID in the component's own database and is reachable only on the compose network.

## Images

| Component | Image |
| --------- | ----- |
| Heimdall | `quay.io/eunomia_upm/heimdall:v1.5.0` |
| Agent | `quay.io/eunomia_upm/ds-agent:v0.4.0` |
| Wallet | `rmenendez8/fafnir:v0.2.0` |

All three are amd64 only. `./eunomia images --env prod --check` lists newer tags in the registries.
