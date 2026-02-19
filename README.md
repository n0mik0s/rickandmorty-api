# Rick and Morty Data Sync Service

An asynchronous FastAPI service that extracts character data from the Rick and Morty API, persists it into a PostgreSQL `JSONB` store, and provides monitoring capabilities.

## Technical Architecture

-   **Runtime**: Python 3.10+ (Asynchronous I/O via `asyncio`).
    
-   **Web Framework**: `FastAPI` with `uvicorn`.
    
-   **Database**: `PostgreSQL` using `asyncpg` for non-blocking operations.
    
-   **Rate Limiting**: `pyrate-limiter` (In-memory backend). No external cache (Redis) required for single-worker deployments.
    
-   **Logging**: Custom `JsonFormatter` for structured, machine-readable logs.
    

* * *

## Configuration

The application expects configuration via CLI arguments.

### 1\. `config.yaml`

YAML

    log_level: "INFO"

### 2\. `secrets.json`

JSON

    {
      "host": "your_host",
      "user": "postgres_user",
      "password": "your_password",
      "dbname": "rick_morty_db"
    }

* * *

## Installation & Startup

### Using `uv` (Recommended)

`uv` is an extremely fast Python package and project manager. You can run the app without manually managing virtual environments:

1.  **Run directly**:
    
    Bash
    
        uv run main.py --config ./config.yaml --secret ./secrets.json
    
    _(Note: `uv` will automatically create a `.venv` and install dependencies listed in your `pyproject.toml` or script metadata)._
    
2.  **Install dependencies to local environment**:
    
    Bash
    
        uv pip install fastapi uvicorn requests asyncpg pyrate-limiter fastapi-limiter PyYAML
        OR
        uv add fastapi uvicorn requests asyncpg pyrate-limiter fastapi-limiter PyYAML
    

### Using standard `pip`

Bash

    pip install fastapi uvicorn requests asyncpg pyrate-limiter fastapi-limiter PyYAML
    python main.py --config ./config.yaml --secret ./secrets.json

* * *

## API Documentation

### Data Operations

| **Method** | **Endpoint** | **Params** | **Description** |
| --- | --- | --- | --- |
| `POST` | `/sync` | `source_url`, `resource` | Fetches "Alive Humans from Earth" and upserts to DB. |
| `GET` | `/data` | `sort_field`, `sort_order` | Returns character data. Fields: `id`, `data`. Sort order could be `ASC` or `DESC`|

### Monitoring

| **Method** | **Endpoint** | **Param** | **Description** |
| --- | --- | --- | --- |
| `GET` | `/db-mon` | `aspect=conn` | Verifies active DB connectivity. |
| `GET` | `/db-mon` | `aspect=records` | Returns total record count in `character` table. |

> **Rate Limit**: All endpoints are limited to 2 requests per 5 seconds per worker instance (handled in-memory).