# **Ecostars - Consumer (Ingestion Service)**

The **Consumer** of the Ecostars pilot. A FastAPI microservice that acts as the data ingestion layer for the dataspace participant on the demand side. It handles both real-time metric updates (push) and on-demand bulk data retrieval (pull) from the [Provider](../provider/README.md), persisting everything into a PostgreSQL database consumed by Metabase.

In the dataspace, this service sits behind the **Consumer Agent** (Eunomia). The Consumer Agent negotiates the contract against the Provider Agent's catalog and then either calls `/pull` here (for bulk transfers) or forwards push notifications to `/push` (for streaming updates).

## **Architecture**

The service exposes two ingestion endpoints that mirror the two data interaction paradigms of the platform:

```
Provider Agent (Eunomia)
        │
        ├──── POST /consumer-ingestion/pull  ──►  Fetches hotels + measures  ──►  PostgreSQL
        │                                                                               │
        └──── POST /consumer-ingestion/push  ──►  Receives metric updates    ──►  PostgreSQL
                                                                                       │
                                                                                  Metabase
```

### `/pull` - On-demand bulk ingestion

Triggered manually or by a scheduler. Accepts a URL, calls it, and upserts the returned hotel and measure data into the database. Hotels are matched by `(name, city)`; measures are matched by `(hotel_id, year)`.

### `/push` - Real-time metric ingestion

Webhook endpoint that receives individual metric updates and appends them as immutable historical records to the `metric_items` table.

## **Tech stack**

| Component      | Role                                 |
| -------------- | ------------------------------------ |
| **FastAPI**    | API framework                        |
| **SQLModel**   | ORM + schema validation              |
| **PostgreSQL** | Transactional persistence            |
| **httpx**      | Async HTTP client for external calls |
| **Metabase**   | BI and dashboarding                  |
| **Docker**     | Containerisation                     |

## **Project structure**

```
consumer/
├── app/
│   ├── main.py           # App entrypoint, startup hooks
│   ├── db.py             # Engine, session, table creation
│   ├── models.py         # SQLModel table definitions
│   └── routers/
│       └── items.py      # /pull and /push endpoints
├── Dockerfile
└── requirements.txt
```

## **Standalone usage**

You normally run this service as part of [`deployment/mini`](../../deployment/mini/README.md) or [`deployment/prod`](../../deployment/prod/README.md). For local development of the Consumer itself:

1. Create a `.env` file under `services/consumer/`:

   ```env
   DATABASE_USER=postgres
   DATABASE_PASSWORD=postgres
   DATABASE_HOST=localhost
   DATABASE_PORT=5440
   DATABASE_NAME=postgres
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Run the service:

   ```bash
   uvicorn app.main:app --reload
   ```

API docs available at [http://localhost:8000/docs](http://localhost:8000/docs).

### Docker (full stack)

From the deployment directory:

```bash
docker compose up --build
```

This starts (mini deployment subset relevant to the Consumer):

| Service           | URL                          |
| ----------------- | ---------------------------- |
| Ingestion Service | `http://localhost:8000`      |
| Swagger UI        | `http://localhost:8000/docs` |
| PostgreSQL        | `localhost:5440`             |
| Metabase          | `http://localhost:3000`      |
| NiFi Registry     | `http://localhost:18080`     |

## **Environment variables**

All configuration is injected via environment variables. No `.env` file is needed when running in Docker - the deployment Compose file populates them.

| Variable            | Description                                | Default |
| ------------------- | ------------------------------------------ | ------- |
| `ENV`               | Set to `production` to skip `.env` loading | -       |
| `APP_PORT`          | Port the service listens on                | `8000`  |
| `DATABASE_USER`     | PostgreSQL user                            | -       |
| `DATABASE_PASSWORD` | PostgreSQL password                        | -       |
| `DATABASE_HOST`     | PostgreSQL host                            | -       |
| `DATABASE_PORT`     | PostgreSQL port                            | -       |
| `DATABASE_NAME`     | PostgreSQL database name                   | -       |

## **API reference**

### `POST /consumer-ingestion/pull`

Triggers a bulk fetch from an external URL and upserts hotels and their measures.

**Request body:**

```json
{
  "url": "https://example.com/api/hotels"
}
```

**Response:**

```json
{
  "source": "https://example.com/api/hotels",
  "total_received": 30,
  "summary": {
    "hotels_created": 25,
    "hotels_updated": 5,
    "measures_created": 90,
    "measures_updated": 10,
    "measures_skipped": 0
  }
}
```

### `POST /consumer-ingestion/push`

Receives a real-time metric update and inserts it as a new historical record.

**Request body:**

```json
{
  "id": 7,
  "item_type": "hotel_energy_usage",
  "last_value": 71.74,
  "last_measured_at": "2026-02-23T00:00:00Z"
}
```

**Response:**

```json
{
  "action": "created",
  "id": 42,
  "hotel_id": 7,
  "item_type": "hotel_energy_usage",
  "last_value": 71.74,
  "last_measured_at": "2026-02-23"
}
```

### `GET /health`

```json
{ "status": "ok" }
```

## **Data model**

```
hotels
  └── hotel_measures  (one hotel → many yearly measures)

metric_items          (append-only metric history, keyed by hotel_id)
```

## **Role in the dataspace**

The Consumer's responsibilities under the Eunomia flow:

1. **Discovery** - performed by the Consumer Agent, which queries the Provider Agent's DCAT catalog.
2. **Negotiation** - the Consumer Agent agrees an ODRL contract with the Provider Agent.
3. **Pull transfers** - when bulk data is needed, the Consumer Agent invokes `/pull` here with the negotiated, time-bounded URL pointing at the Provider's static API (proxied via the Provider Agent).
4. **Push transfers** - when streaming updates are negotiated, the Provider's dynamic API pushes notifications to the Consumer Agent, which forwards them to `/push` here.

This service does **not** speak DSP itself; it stays a normal HTTP API. All policy enforcement, identity exchange and contract bookkeeping happen one layer above, in the Consumer Agent.

## **Deployment notes**

See `docker-compose.yml` under [`deployment/mini`](../../deployment/mini/README.md) or [`deployment/prod`](../../deployment/prod/README.md). The `consumer-ingestion` service depends on `transactional-db` with a health check, so the app will only start once PostgreSQL is ready.

To recreate the database schema from scratch, set `drop_first=True` in `create_db_and_tables()` on first startup - **development only**.
