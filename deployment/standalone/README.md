# Standalone Deployment

All three participants of the Ecostars dataspace on a single host: Heimdall as the authority, plus the provider and consumer DS-Agents. Each one is a separate Compose project with its own Fafnir wallet, Postgres and (for the agents) Redis. Secrets use the fake file vault and identities are `did:jwk`, so nothing needs a domain, TLS or an external service.

## Requirements

- Docker with the Compose plugin
- Python 3.8+ for the `eunomia` CLI

## Deploying

From the repo root:

```bash
./eunomia up       # start, wait, onboard, populate the catalog
./eunomia e2e      # prove it works end to end
./eunomia down     # remove everything, identities included
```

The CLI brings the stacks up in dependency order with `--wait` and onboards them. To drive Compose by hand instead, start them in this order and then run `./eunomia onboard`:

```bash
docker compose -f deployment/standalone/docker-compose.standalone.heimdall.yaml up -d --wait
docker compose -f deployment/standalone/docker-compose.standalone.provider.yaml up -d --wait
docker compose -f deployment/standalone/docker-compose.standalone.consumer.yaml up -d --wait
```

| File                                      | Compose project      | Config                                                        |
| ----------------------------------------- | -------------------- | ------------------------------------------------------------- |
| `docker-compose.standalone.heimdall.yaml` | `ecostars-authority` | `static/config/heimdall/standalone/standalone.authority.yaml` |
| `docker-compose.standalone.provider.yaml` | `ecostars-provider`  | `static/config/provider/standalone/standalone.provider.yaml`  |
| `docker-compose.standalone.consumer.yaml` | `ecostars-consumer`  | `static/config/consumer/standalone/standalone.consumer.yaml`  |

Every container is named `ecostars-*`. The wallets publish no port: each agent reaches its own on the Compose network.

## Entity URLs

- **Heimdall**: [http://localhost:1500/admin/home](http://localhost:1500/admin/home)
- **Provider**: [http://localhost:1200/admin/login](http://localhost:1200/admin/login)
- **Consumer**: [http://localhost:1100/admin/login](http://localhost:1100/admin/login)

## Credentials

Consumer and provider web interface: `eunomia` / `eunomia`.

There are no wallet accounts: Fafnir has no login or UI, and stores the keys and DID of its participant in that participant's database.

## State

The databases have no volume, so `down` (or recreating a database container) wipes the catalog, the agreements and the onboarding. The DIDs and keys live in `vault/<participant>/secrets/` through a bind mount and survive that; `./eunomia down` removes them too unless you pass `--keep-identities`.
