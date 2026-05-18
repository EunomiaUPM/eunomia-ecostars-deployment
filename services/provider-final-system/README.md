# **Ecostars - Provider (Mock Server)**

The **Provider** of the Ecostars pilot. A Go 1.24 service that mocks the productive systems of an Ecostars-like organisation: it exposes hotel sustainability data and emits real-time metric updates. In the dataspace, this service sits behind the **Provider Agent** (Eunomia) and is consumed - under DSP negotiation - by the [Consumer](../consumer/README.md).

The service has two surfaces:

- A **static API** that returns long-lived entities (hotels, yearly measures).
- A **dynamic API** that drives a PubSub system, periodically updating metrics and notifying subscribers.

Both surfaces are protected by **Keycloak**.

## **Tech stack**

| Component  | Role                               |
| ---------- | ---------------------------------- |
| Go 1.24    | Language / runtime                 |
| Keycloak   | Bearer-token authentication        |
| PostgreSQL | Internal store for hotels/measures |
| Docker     | Containerisation                   |

## **Standalone usage**

You normally run this service as part of [`deployment/mini`](../../deployment/mini/README.md) or [`deployment/prod`](../../deployment/prod/README.md). For local development of the Provider itself:

### Static API

```bash
go run ./cmd fake     # seed mock entities
go run ./cmd serve    # start the static server
```

Quick check:

```bash
curl --location 'http://localhost:8081/hotels'
# [
#   {
#     "name": "distinctio",
#     "address": "Dicta qui commodi sequi beatae maiores.",
#     "city": "Los Angeles",
#     "measures": [
#       {
#         "ID": 1,
#         "hotel_id": 1,
#         "year": 2023,
#         "rooms": 1891,
#         ...
#       }
#     ]
#   }
# ]
```

### Dynamic API

```bash
go run ./cmd metrics

# 2025/10/28 15:06:41 Enqueued notification job for metric item ID 5
# 2025/10/28 15:06:41 updated metric item ID 5: new value 91.00
# ...
```

To subscribe to a topic:

```bash
curl --location 'http://localhost:8082/subscriptions/subscribe' \
  --header 'Content-Type: application/json' \
  --data '{
    "url": "http://localhost:1112/",
    "event_type": "hotel_water_usage"
  }'
```

Response:

```json
{
  "data": {
    "ID": 3,
    "url": "http://localhost:1112/",
    "event_type": "hotel_water_usage"
  },
  "message": "Subscribed successfully"
}
```

To unsubscribe:

```bash
curl --location --request POST 'http://localhost:8082/subscriptions/unsubscribe/1'
```

The notification body delivered to subscribers looks like:

```json
{
  "id": 5,
  "item_type": "hotel_waste_generated",
  "last_value": 32.71959530690623,
  "last_measured_at": "2025-10-28T00:00:00Z"
}
```

## **Docker**

Adjust `.env` (this is the same file the Compose stack reads):

```env
DATABASE_HOST=postgres
DATABASE_PORT=5432
DATABASE_USER=postgres
DATABASE_PASS=postgres
DATABASE_NAME=postgres

STATIC_SERVER_PORT=8081
STATIC_SERVER_HOST=static-api

DYNAMIC_SERVER_PORT=8082
DYNAMIC_SERVER_HOST=dynamic-api
```

Then:

```bash
docker compose up -d
```

## **Authentication & authorization**

Both `static-api` and `dynamic-api` are protected and require a valid Bearer Token issued by [Keycloak](https://www.keycloak.org/).

### Keycloak access

- **URL**: [http://localhost:8080](http://localhost:8080)
- **Admin Console**: [http://localhost:8080/admin](http://localhost:8080/admin)
- **Admin credentials**: `admin` / `admin` _(mini deployment only - replace in prod)_

### Default realm

The stack imports the `ecostars` realm on startup with:

- **Client ID**: `ecostars-client`
- **Client Secret**: `ecostars-secret`
- **Test user**: `testuser` / `password`

### Obtaining a token

```bash
export TOKEN=$(curl -s -X POST "http://localhost:8080/realms/ecostars/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "client_id=ecostars-client" \
  -d "client_secret=ecostars-secret" \
  -d "username=testuser" \
  -d "password=password" \
  -d "grant_type=password" | jq -r '.access_token')

curl -H "Authorization: Bearer $TOKEN" http://localhost:8081/hotels
```

## **Role in the dataspace**

In the Eunomia-governed flow:

1. The Provider Agent advertises a **DCAT catalog** entry that points at this service's `/hotels` (static) and `/subscriptions/*` (dynamic) endpoints.
2. A Consumer Agent **negotiates** access against an ODRL policy held by the Provider Agent.
3. Once the contract is in place, the Provider Agent **proxies** requests from the Consumer to this Mock Server, attaching the appropriate Bearer Token.
4. For real-time updates, the dynamic API pushes notifications to the negotiated callback URL (the Consumer Agent), which then forwards them to the Consumer's `/consumer-ingestion/push`.

This means **the Mock Server itself does not need to know about DSP**; it only needs to expose its REST surfaces and trust the Keycloak-issued tokens its Agent attaches.

## **Contributing**

Open an issue in the upstream repository to discuss changes before sending a PR.
