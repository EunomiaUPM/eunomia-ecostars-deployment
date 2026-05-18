# Eunomia Agent - Production Deployment Guide

This guide walks you through deploying an Eunomia Agent in production mode. Several services depend on each other, so follow the steps **in order** - do not skip ahead. For this tutorial we will be using the consumer variables, however, it can act as both consumer and provider at the same time.

---

## Prerequisites

- Docker and Docker Compose installed on the server
- A domain name pointing to your server (referred to as `your.domain.com` throughout this guide)
- TLS certificates for your domain (see Step 1)

---

## Step 1 - Certificates

Heimdall uses two kinds of certificates in production:

- **Domain certificates** - used for HTTPS (web traffic)
- **Ecosystem certificates** - used internally to generate Verifiable Credentials

### Domain certificates

These live in `/vault/consumer/config/`. Replace every `.example` file with the real certificate and remove the `.example` extension so they end in `.pem`. All files must be in PEM format (both RSA and Elliptic Curve are supported).

| File                  | Description                                                                                                                                                          |
| --------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `vault-ca.pem`        | Full certificate chain including root                                                                                                                                |
| `vault-cert.pem`      | Your own domain certificate                                                                                                                                          |
| `root-ca.pem`         | Root issuer certificate (usually called `Issuer.cer` - convert it to PEM format)                                                                                     |
| `vault-key.pem`       | Private key associated with your certificate. May look like `-----BEGIN EC PRIVATE KEY-----`                                                                         |
| `vault-key-pkcs8.pem` | Same private key converted to PKCS8 format (`-----BEGIN PRIVATE KEY-----`). Convert with: `openssl pkcs8 -topk8 -nocrypt -in vault-key.pem -out vault-key-pkcs8.pem` |

### Ecosystem certificates and secrets

These live in `/vault/consumer/secrets/`. They are loaded into Vault automatically on first startup. For each `.example` file in that directory, remove the `.example` extension.

There are two types of files:

**Certificate files** (`.pem.example` → `.pem`): Only RSA format is supported at this time. The example files already contain valid self-generated RSA certificates - you can leave them as-is to get started, or replace them with your own.

**Credential files** (`.json.example` → `.json`): These contain connection credentials used by the Agent internally.

- `db.json` - database credentials. If you changed the values in `db.env`, make sure they match here too.
- `wallet.json` - wallet credentials. **The example values will not work** as they reference existing external accounts. Replace them with your own wallet credentials before launching.

---

## Step 2 - Base environment files

Fill in the environment files that do not depend on other services yet. All files live in `/static/envs/`. Rename each `.example` file by removing the `.example` extension.

> Files ending in `.env.ps1.example` or `.env.sh.example` do not need to be touched.

### `db.env`

Credentials for the main Agent database. Use whatever values you want, or leave them as they are - just remember them, as they must match `db.json` in `/vault/consumer/secrets/`.

```env
POSTGRES_PASSWORD=mini_consumer
POSTGRES_USER=mini_consumer
POSTGRES_DB=mini_consumer
```

## Step 3 - Application configuration

Edit `/static/config/consumer/prod/core.consumer.yaml`:

| Line       | Change                                       |
| ---------- | -------------------------------------------- |
| 6          | Replace `your_domain` with `your.domain.com` |
| 89         | Replace `your_domain` with `your.domain.com` |
| 93         | Replace `your_domain` with `your.domain.com` |
| identifier |

---

## Step 4 - Partial first launch

Start only Vault and databases. The Agent is not started yet - it depends on the configuration obtained in the next steps.

```bash
docker compose -f docker-compose.consumer.yaml up consumer-vault consumer-redis consumer-db -d
```

Wait a few seconds for all services to be ready before proceeding.

---

## Step 5 - Initialize and unseal Vault

> **Important:** This step is only done once. Vault data is persisted in `/vault/consumer/data` - as long as this volume exists, you will never need to reinitialize.

In a new terminal, run:

```bash
docker exec consumer-vault vault operator init -address=https://your.domain.com:8200
```

Even if port 8200 is not open externally, this will work - the command runs inside the container and NAT handles the routing.

> If it fails immediately, wait 30 seconds and try again - Vault may still be starting.

This will output something like:

```
Unseal Key 1: BSdFxMjI9gf7YawFej7kUhVJyal3wtLKhc41RXYiXH6P
Unseal Key 2: VQH6HzzPKTkqCIuozGo/Z7m3Y6DiiizYZtTOcgYetODm
Unseal Key 3: f7wf3ovX5th1UhNZZ9cwehVU47HEmzGPsH55zLFNapJi
Unseal Key 4: vVAjiyJiV3k4EYFJ8v1ECVgpDPR0id36s/dbrRGXELyZ
Unseal Key 5: 2t0kKBwj+UEi7oWIzXGko4uqR+cy9xTZs7N5/aoF6NAi

Initial Root Token: hvs.gpnaq703noTvBOJk0WnJkMcOKz
```

**Save these values somewhere safe - you will need them every time Vault restarts.**

### Unseal Vault

Vault starts sealed and must be unsealed with 3 of the 5 keys before it can be used:

```bash
docker exec consumer-vault vault operator unseal -address=https://your.domain.com:8200 UNSEAL_KEY_1
docker exec consumer-vault vault operator unseal -address=https://your.domain.com:8200 UNSEAL_KEY_2
docker exec consumer-vault vault operator unseal -address=https://your.domain.com:8200 UNSEAL_KEY_3
```

> You need to unseal Vault every time the container restarts.

The Vault UI is accessible at `https://your.domain.com:8200` using the root token.

---

## Step 6 - Complete `core.env` - Point A

Now that Vault is initialized, you have the root token. Fill in `core.env`:

```env
# Vault server address - port 8200 can be closed externally, NAT handles it internally
VAULT_ADDR=https://your.domain.com:8200

# Vault access token obtained in Step 5 - Point A
VAULT_TOKEN=hvs.your_root_token_here

# Skip TLS verification
VAULT_SKIP_VERIFY=false

# TLS configuration - leave as-is
VAULT_CACERT=/app/vault/config/vault-ca.pem
VAULT_CLIENT_CERT=/app/vault/config/vault-cert.pem
VAULT_CLIENT_KEY=/app/vault/config/vault-key.pem

# Local path to Vault config
VAULT_PATH=/app/vault/

# KV v2 mount name - can be anything, e.g. "consumer"
VAULT_MOUNT=consumer

# Secret paths - these act as internal paths, keep them private
VAULT_APP_DB=database/postgres
VAULT_APP_WALLET=wallet/main
VAULT_APP_PRIV_KEY=crypto/keys/private
VAULT_APP_PUB_PKEY=crypto/keys/public
VAULT_APP_CERT=crypto/certificates/main
VAULT_APP_CLIENT_CERT=crypto/certificates/vault-cert.pem
VAULT_APP_CLIENT_KEY=crypto/keys/vault-key.pem
VAULT_APP_ROOT_CLIENT_KEY=crypto/keys/vault-root-cert.pem
```

---

## Step 9 - Full launch

With all environment files complete, start all services:

```bash
docker compose -f docker-compose.consumer.yaml up -d
```

All services should now be running. Visit `https://your.domain.com/admin/login` - you should be redirected to the Keycloak login page.

---

## Vault maintenance

Every time the Vault container restarts, it needs to be unsealed again with 3 of the 5 unseal keys:

```bash
docker exec consumer-vault vault operator unseal -address=https://your.domain.com:8200 UNSEAL_KEY_1
docker exec consumer-vault vault operator unseal -address=https://your.domain.com:8200 UNSEAL_KEY_2
docker exec consumer-vault vault operator unseal -address=https://your.domain.com:8200 UNSEAL_KEY_3
```
