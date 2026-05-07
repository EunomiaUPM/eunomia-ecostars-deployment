# Mini Deployment

This folder contains the "mini" deployment approach for the Rainbow framework, using Docker Compose files.

## Requirements

- Docker
- Docker Compose

## Prerequisites: Walt.id Wallet

Before lifting any of the local containers, you **MUST** start the walt.id identity wallet infrastructure first. This is a critical requirement.

```bash
git clone https://github.com/walt-id/waltid-identity.git
cd waltid-identity/docker-compose
docker compose up -d
```

> **Important:** Ensure the wallet services are completely functional before bringing up any other component.

## Deploying

To deploy the services, run `docker compose up -d` against each of the `docker-compose.*.yaml` files located in this directory.

For example:

```bash
docker compose -f docker-compose.mini.heimdall.yaml up -d
docker compose -f docker-compose.mini.provider.yaml up -d
docker compose -f docker-compose.mini.consumer.yaml up -d
```

## Entity URLs (Local Access)

Once deployed, you can access the different entities at the following URLs:

- **Wallet**: [http://localhost:7104/login](http://localhost:7104/login)
- **Heimdall**: [http://localhost:1500/admin/home](http://localhost:1500/admin/home)
- **Consumer**: [http://localhost:1100/admin/login](http://localhost:1100/admin/login)
- **Provider**: [http://localhost:1200/admin/login](http://localhost:1200/admin/login)

## Credentials

### Consumer & Provider web interface

- **User**: `eunomia`
- **Password**: `eunomia`

### Wallet

The credentials for the wallet follow a standard pattern: `mini_[role]@test.com` / `mini_[role]`.

- **Heimdall**: `mini_heimdal@test.com` / `mini_heimdall`
- **Other roles**: Replace `[role]` accordingly.

> [!NOTE]
> You can find credentials examples and configuration details in the repository at:
> `/vault/[role]/secrets/wallet.json.example`
