# Heimdall - Production Deployment Guide

This guide walks you through deploying Heimdall in production mode. Several services depend on each other, so follow the steps **in order** - do not skip ahead. It is recommended to have multiple terminals open simultaneously.

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

These live in `/vault/heimdall/config/`. Replace every `.example` file with the real certificate and remove the `.example` extension so they end in `.pem`. All files must be in PEM format (both RSA and Elliptic Curve are supported).

| File                  | Description                                                                                                                                                          |
| --------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `vault-ca.pem`        | Full certificate chain including root                                                                                                                                |
| `vault-cert.pem`      | Your own domain certificate                                                                                                                                          |
| `root-ca.pem`         | Root issuer certificate (usually called `Issuer.cer` - convert it to PEM format)                                                                                     |
| `vault-key.pem`       | Private key associated with your certificate. May look like `-----BEGIN EC PRIVATE KEY-----`                                                                         |
| `vault-key-pkcs8.pem` | Same private key converted to PKCS8 format (`-----BEGIN PRIVATE KEY-----`). Convert with: `openssl pkcs8 -topk8 -nocrypt -in vault-key.pem -out vault-key-pkcs8.pem` |

### Ecosystem certificates and secrets

These live in `/vault/heimdall/secrets/`. They are loaded into Vault automatically on first startup. For each `.example` file in that directory, remove the `.example` extension.

There are two types of files:

**Certificate files** (`.pem.example` → `.pem`): Only RSA format is supported at this time. The example files already contain valid self-generated RSA certificates - you can leave them as-is to get started, or replace them with your own.

**Credential files** (`.json.example` → `.json`): These contain connection credentials used by Heimdall internally.

- `db.json` - database credentials. If you changed the values in `db.env`, make sure they match here too.
- `wallet.json` - wallet credentials. **The example values will not work** as they reference existing external accounts. Replace them with your own wallet credentials before launching.

---

## Step 2 - Base environment files

Fill in the environment files that do not depend on other services yet. All files live in `./static/envs/`. Rename each `.example` file by removing the `.example` extension.

> Files ending in `.env.ps1.example` or `.env.sh.example` do not need to be touched.

### `db.env`

Credentials for the main Heimdall database. Use whatever values you want, or leave them as they are - just remember them, as they must match `db.json` in `/vault/heimdall/secrets/`.

```env
POSTGRES_PASSWORD=mini_heimdall
POSTGRES_USER=mini_heimdall
POSTGRES_DB=mini_heimdall
```

### `keycloak.db.env`

Credentials for the Keycloak internal database. The default values (`heimdall_keycloak`) can be left as-is or changed - if you change them, update `keycloak.env` accordingly. Note that `PGDATA` must remain unchanged.

```env
POSTGRES_DB=heimdall_keycloak
POSTGRES_USER=heimdall_keycloak
POSTGRES_PASSWORD=heimdall_keycloak
PGDATA=/var/lib/postgresql/data/pgdata
```

### `keycloak.env`

```env
# Admin credentials - remember these for the Keycloak UI setup (Points B and C)
KEYCLOAK_ADMIN=heimdall_keycloak        # can be changed
KEYCLOAK_ADMIN_PASSWORD=heimdall_keycloak  # can be changed

# Your domain without https:// prefix
KC_HOSTNAME=your.domain.com

# Database connection - update the DB name if you changed it in keycloak.db.env
KC_DB_URL=jdbc:postgresql://keycloak_postgres:5432/heimdall_keycloak
KC_DB=postgres
KC_DB_USERNAME=heimdall_keycloak
KC_DB_PASSWORD=heimdall_keycloak

# Leave these as-is
KC_HTTPS_CERTIFICATE_FILE=/etc/x509/https/vault-ca.pem
KC_HTTPS_CERTIFICATE_KEY_FILE=/etc/x509/https/vault-key-pkcs8.pem
```

---

## Step 3 - Application configuration

Edit `/static/config/heimdall/prod/basic_dataspace_authority.yaml`:

| Line | Change                                                     |
| ---- | ---------------------------------------------------------- |
| 6    | Replace `your_domain` with `your.domain.com`               |
| 38   | Replace `your_domain` with `your.domain.com`               |
| 41   | Replace `your_domain` with `your.domain.com`               |
| 55   | Replace `change_me` with your desired dataspace identifier |

---

## Step 4 - Partial first launch

Start only Vault, Keycloak and their databases. Heimdall and the proxy are not started yet - they depend on configuration obtained in the next steps.

```bash
docker compose -f docker-compose.heimdall.yaml up heimdall-vault keycloak keycloak_postgres heimdall-db -d
```

Wait a few seconds for all services to be ready before proceeding.

---

## Step 5 - Initialize and unseal Vault

> **Important:** This step is only done once. Vault data is persisted in `/vault/heimdall/data` - as long as this volume exists, you will never need to reinitialize.

In a new terminal, run:

```bash
docker exec heimdall-vault vault operator init -address=https://your.domain.com:8200
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
docker exec heimdall-vault vault operator unseal -address=https://your.domain.com:8200 UNSEAL_KEY_1
docker exec heimdall-vault vault operator unseal -address=https://your.domain.com:8200 UNSEAL_KEY_2
docker exec heimdall-vault vault operator unseal -address=https://your.domain.com:8200 UNSEAL_KEY_3
```

> You need to unseal Vault every time the container restarts.

The Vault UI is accessible at `https://your.domain.com:8200` using the root token.

---

## Step 6 - Complete `heimdall.env` - Point A

Now that Vault is initialized, you have the root token. Fill in `heimdall.env`:

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

# KV v2 mount name - can be anything, e.g. "heimdall"
VAULT_MOUNT=heimdall

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

## Step 7 - Configure Keycloak

Access the Keycloak admin panel at `https://your.domain.com:8443` using the credentials from Points B and C (`KEYCLOAK_ADMIN` and `KEYCLOAK_ADMIN_PASSWORD` in `keycloak.env`).

### Create the realm - Point F

- Click the dropdown in the top left (shows `master`) → **Create realm**
- Name: `heimdall` - can be changed. If changed, update `OAUTH2_PROXY_OIDC_ISSUER_URL` and `OAUTH2_PROXY_BACKEND_LOGOUT_URL` in `proxy.env` accordingly
- Click **Create**

### Create the client - Point D

- Go to **Clients** → **Create client**
- Client ID: `heimdall-client` - can be changed. If changed, update `OAUTH2_PROXY_CLIENT_ID` in `proxy.env`
- Client type: `OpenID Connect` → **Next**
- Enable `Client authentication` → **Next**
- Valid redirect URIs: `https://your.domain.com/oauth2/callback`
- Web origins: `https://your.domain.com`
- Click **Save**

### Copy the client secret - Point E

- Go to the **Credentials** tab of the client
- Copy the `Client secret` - you will need it in the next step

### Add the audience mapper

- Go to the **Client scopes** tab → click `heimdall-client-dedicated` (or the name from Point D with `-dedicated` suffix)
- Click **Add mapper** → **By configuration** → **Audience**
- Name: `heimdall-audience`
- Included Client Audience: `heimdall-client` (or the client ID from Point D)
- Add to ID token: **On**
- Add to access token: **On**
- Click **Save**

### Create users

- Go to **Users** → **Create user**
- Fill in Username and Email → **Create**
- Go to the **Credentials** tab → **Set password** → disable `Temporary`
- Go to the **Details** tab → enable `Email verified` → **Save**

### Activate the custom theme

- Go to **Realm settings** → **Themes** tab
- Set **Login theme** to `heimdall`
- Click **Save**

### Recommended security settings

- **Realm settings → Login**: disable `User registration` to prevent self-signup
- **Realm settings → Sessions**: set SSO Session Max to `30 minutes` and SSO Session Idle to `15 minutes`
- **Realm settings → Security defenses**: enable `Brute force detection`

---

## Step 8 - Complete `proxy.env` - Point E

Now that you have the Keycloak client secret, fill in `proxy.env`:

```env
# Leave as-is
OAUTH2_PROXY_CUSTOM_TEMPLATES_DIR=/templates
OAUTH2_PROXY_PROVIDER=keycloak-oidc

# Client ID from Point D
OAUTH2_PROXY_CLIENT_ID=heimdall-client

# Client secret from Point E
OAUTH2_PROXY_CLIENT_SECRET=your_client_secret_here

# Replace your.domain.com and your_realm with your domain and realm name from Point F
OAUTH2_PROXY_OIDC_ISSUER_URL=https://your.domain.com:8443/realms/your_realm
OAUTH2_PROXY_BACKEND_LOGOUT_URL=https://your.domain.com:8443/realms/your_realm/protocol/openid-connect/logout?id_token_hint={id_token}
OAUTH2_PROXY_REDIRECT_URL=https://your.domain.com/oauth2/callback

# Leave as-is
OAUTH2_PROXY_UPSTREAMS=http://heimdall:1500
OAUTH2_PROXY_EMAIL_DOMAINS=*

# Generate with: openssl rand -base64 32
OAUTH2_PROXY_COOKIE_SECRET=your_generated_secret_here

# Leave as-is
OAUTH2_PROXY_COOKIE_SECURE=true

# Your domain without https:// prefix
OAUTH2_PROXY_COOKIE_DOMAINS=your.domain.com

# Leave as-is
OAUTH2_PROXY_HTTPS_ADDRESS=0.0.0.0:4180
OAUTH2_PROXY_TLS_CERT_FILE=/certs/vault-ca.pem
OAUTH2_PROXY_TLS_KEY_FILE=/certs/vault-key-pkcs8.pem
OAUTH2_PROXY_SSL_INSECURE_SKIP_VERIFY=true
```

Generate the cookie secret with:

```bash
openssl rand -base64 24
```

---

## Step 9 - Full launch

With all environment files complete, start all services:

```bash
docker compose -f docker-compose.prod.yaml up -d
```

All services should now be running. Visit `https://your.domain.com/admin/home` - you should be redirected to the Keycloak login page.

---

## Vault maintenance

Every time the Vault container restarts, it needs to be unsealed again with 3 of the 5 unseal keys:

```bash
docker exec heimdall-vault vault operator unseal -address=https://your.domain.com:8200 UNSEAL_KEY_1
docker exec heimdall-vault vault operator unseal -address=https://your.domain.com:8200 UNSEAL_KEY_2
docker exec heimdall-vault vault operator unseal -address=https://your.domain.com:8200 UNSEAL_KEY_3
```
