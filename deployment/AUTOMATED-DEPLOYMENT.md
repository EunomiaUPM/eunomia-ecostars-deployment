# Automated Deployment with GitHub Actions

This document explains how the CI/CD pipeline works for the EDACCIT Ecostars pilot deployment. The workflow automates SSH-based deployment of all three machines whenever code is pushed to `main`.

---

## How it works

The workflow file lives at [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml).

```
Push to main  ──►  resolve environment
                        │
                        ▼
                  deploy-heimdall         ← Machine A (must finish first)
                  (Heimdall + Keycloak)
                        │
               ┌────────┴────────┐
               ▼                 ▼
     deploy-provider       deploy-consumer
     (Machine B via SSH)   (Machine C via SSH)
                                 │
                           DS-Agent stack
                                 │
                        (prod only) Client Stack
                        (NiFi, Metabase, Postgres)
```

**Heimdall runs first.** Provider and Consumer only start once Heimdall has successfully deployed — this mirrors the required startup order for the dataspace. Provider and Consumer then deploy in parallel.

Each job connects to its target machine over SSH and runs:

1. `git reset --hard origin/main` — syncs the repo on the machine.
2. `docker login quay.io` — authenticates to pull updated images.
3. `docker compose pull` — downloads the latest images.
4. `docker compose up -d --remove-orphans` — recreates only containers whose image or config changed.

---

## Triggers

| Event | Environment deployed |
|---|---|
| Push to `main` | `prod` (automatic) |
| Manual run (`workflow_dispatch`) | `prod` or `mini` (your choice) |

To trigger a manual run: go to **Actions → Deploy → Run workflow** in the GitHub UI and select the target environment.

---

## Images pulled per machine

| Machine | Images |
|---|---|
| A — Heimdall | `quay.io/eunomia_upm/heimdall`, `quay.io/keycloak/keycloak` |
| B — Provider | `quay.io/eunomia_upm/ds-agent` |
| C — Consumer | `quay.io/eunomia_upm/ds-agent`, `apache/nifi`, `metabase/metabase`, `postgres` |

---

## Prerequisites

### On each target machine

- Docker Engine ≥ 24 and Docker Compose ≥ 2.20 installed.
- The repository cloned at a fixed path (e.g. `/opt/ecostars`).
- The SSH user has permission to run `docker` and `git` commands.
- Vault certificates and env files already placed (see the prod `README.md`). These are **not** managed by this workflow — configure them once manually before the first deploy.
- On Machine C, the `services/consumer-client-stack/.env` file must be present (copy and fill from `.env.template`).

### In the GitHub repository

- The two GitHub Environments (`prod` and `mini`) created under **Settings → Environments**.
- All secrets listed below added to each environment.

---

## GitHub Secrets

Add these secrets under **Settings → Environments → `prod`** (and repeat for `mini` if needed).

| Secret | Description |
|---|---|
| `HEIMDALL_HOST` | IP address or hostname of Machine A |
| `HEIMDALL_USER` | SSH username on Machine A |
| `HEIMDALL_SSH_KEY` | Private SSH key for Machine A (PEM format, full contents) |
| `HEIMDALL_SSH_PORT` | SSH port on Machine A — omit if 22 |
| `PROVIDER_HOST` | IP address or hostname of Machine B |
| `PROVIDER_USER` | SSH username on Machine B |
| `PROVIDER_SSH_KEY` | Private SSH key for Machine B (PEM format, full contents) |
| `PROVIDER_SSH_PORT` | SSH port on Machine B — omit if 22 |
| `CONSUMER_HOST` | IP address or hostname of Machine C |
| `CONSUMER_USER` | SSH username on Machine C |
| `CONSUMER_SSH_KEY` | Private SSH key for Machine C (PEM format, full contents) |
| `CONSUMER_SSH_PORT` | SSH port on Machine C — omit if 22 |
| `DEPLOY_PATH` | Absolute path to the cloned repo on each machine, e.g. `/opt/ecostars` |
| `QUAY_USER` | quay.io username |
| `QUAY_PASSWORD` | quay.io password or robot token |

---

## Setting up SSH access

Do this once per target machine before the first automated deploy.

**1. Generate a dedicated key pair** (on your local machine):

```bash
ssh-keygen -t ed25519 -C "github-actions-heimdall" -f ~/.ssh/ga_heimdall
ssh-keygen -t ed25519 -C "github-actions-provider"  -f ~/.ssh/ga_provider
ssh-keygen -t ed25519 -C "github-actions-consumer"  -f ~/.ssh/ga_consumer
```

**2. Install the public key on each machine:**

```bash
ssh-copy-id -i ~/.ssh/ga_heimdall.pub <user>@<heimdall-host>
ssh-copy-id -i ~/.ssh/ga_provider.pub <user>@<provider-host>
ssh-copy-id -i ~/.ssh/ga_consumer.pub <user>@<consumer-host>
```

**3. Copy the private key contents into the GitHub secret.**

```bash
cat ~/.ssh/ga_heimdall   # → paste into HEIMDALL_SSH_KEY
cat ~/.ssh/ga_provider   # → paste into PROVIDER_SSH_KEY
cat ~/.ssh/ga_consumer   # → paste into CONSUMER_SSH_KEY
```

The key must start with `-----BEGIN OPENSSH PRIVATE KEY-----`.

---

## First-time machine setup

The workflow assumes the repository is already cloned on each machine. Run this once per machine:

```bash
git clone <repo-url> /opt/ecostars
cd /opt/ecostars
# Place vault certs and env files as described in deployment/prod/README.md
```

On Machine C, also prepare the client stack env file:

```bash
cp /opt/ecostars/services/consumer-client-stack/.env.template \
   /opt/ecostars/services/consumer-client-stack/.env
# Fill in the required values
```

After that, every push to `main` handles updates automatically.

---

## Compose files used per environment

| Environment | Machine A — Heimdall | Machine B — Provider | Machine C — Consumer |
|---|---|---|---|
| `prod` | `deployment/prod/docker-compose.heimdall.yaml` | `deployment/prod/docker-compose.provider.yaml` | `deployment/prod/docker-compose.consumer.yaml` + `services/consumer-client-stack/docker-compose.yaml` |
| `mini` | `deployment/mini/docker-compose.mini.heimdall.yaml` | `deployment/mini/docker-compose.mini.provider.yaml` | `deployment/mini/docker-compose.mini.consumer.yaml` |

The Consumer Client Stack (NiFi, NiFi Registry, Metabase, Postgres) is only deployed in `prod`. The `mini` environment does not include it.

---

## Deployment order reminder

If deploying from scratch, order matters:

1. **Machine A** — deploy Heimdall. Agents cannot register with the dataspace until this is running.
2. **Machine B** — deploy Provider and run the catalog ingestion script.
3. **Machine C** — deploy Consumer DS-Agent, then the Client Stack.
4. **Onboarding** — run `scripts/mini-onboarding.sh` (or the prod equivalent).

The workflow enforces this order automatically: Heimdall finishes before Provider and Consumer start.

---

## Manual fallback

If GitHub Actions is unavailable, deploy manually from each machine:

```bash
# Machine A — Heimdall
cd /opt/ecostars
git pull origin main
docker compose -f deployment/prod/docker-compose.heimdall.yaml pull
docker compose -f deployment/prod/docker-compose.heimdall.yaml up -d --remove-orphans

# Machine B — Provider
cd /opt/ecostars
git pull origin main
docker compose -f deployment/prod/docker-compose.provider.yaml pull
docker compose -f deployment/prod/docker-compose.provider.yaml up -d --remove-orphans

# Machine C — Consumer DS-Agent
cd /opt/ecostars
git pull origin main
docker compose -f deployment/prod/docker-compose.consumer.yaml pull
docker compose -f deployment/prod/docker-compose.consumer.yaml up -d --remove-orphans

# Machine C — Consumer Client Stack (prod only)
cd /opt/ecostars/services/consumer-client-stack
docker compose pull
docker compose up -d --remove-orphans
```
