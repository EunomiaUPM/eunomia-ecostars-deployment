# Prod Deployment

This folder contains the production deployment for the Eunomia framework. Unlike the [mini deployment](../mini/README.md), this mode is designed for real servers with a domain name, TLS certificates, and production-grade secrets management through HashiCorp Vault.

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

## Prerequisites: Walt.id Wallet

Both components depend on the **public walt.id wallet API** - no local deployment is required. Production credentials in `wallet.json` must point to real accounts registered on the public walt.id platform.

> [!IMPORTANT]
> The example `wallet.json` files in `/vault/*/secrets/` reference existing test accounts and **will not work in production**. You must replace them with credentials from your own walt.id accounts before launching.
