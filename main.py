import argparse
import json
import logging
import re
import sys
from contextlib import asynccontextmanager

import asyncpg
import requests
import uvicorn
import yaml
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi_limiter.depends import RateLimiter
from pyrate_limiter import Duration, Limiter, Rate


class JsonFormatter(logging.Formatter):
    def format(self, record):
        _record = record
        _log_record = {
            "time": self.formatTime(_record, "%Y-%m-%d %H:%M:%S"),
            "level": _record.levelname,
            "message": _record.getMessage(),
            "logger": _record.name
        }

        return json.dumps(_log_record)


parser = argparse.ArgumentParser(
    description="A script to process config and secret files"
)

parser.add_argument(
    '--config',
    type=str,
    default='../tmp/config.yaml',
    help='Path to the configuration in yaml file (default: ../tmp/config.yaml)'
)

parser.add_argument(
    '--secret',
    type=str,
    default='../tmp/secrets.json',
    help='Path to the secret/credentials in json file (default: ../tmp/secrets.json)'
)

args = parser.parse_args()

with open(args.secret) as file:
    db_config = json.load(file)

with open(args.config) as file:
    log_level = yaml.safe_load(file)["log_level"]

logger = logging.getLogger("rickandmorty-app")
handler = logging.StreamHandler(stream=sys.stdout)
handler.setFormatter(JsonFormatter())
logger.addHandler(handler)
logger.setLevel(log_level)

def rget(url, payload):
    _url = url
    _payload = payload

    try:
        _r = requests.get(_url, _payload)

        if _r.status_code == requests.codes.ok:
            logger.info('Sucussfully requested API')
            return _r

        else:
            logger.error('Request status not OK')
            _r.raise_for_status()

    except requests.exceptions.HTTPError as _err:
        logger.error(_err)

    return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # postgres://user:pass@host:port/database?option=value
    _dsn = "postgres://{}:{}@{}:5432/postgres".format(
        db_config['user'],
        db_config['password'],
        db_config['host']
    )
    try:
        app.state.pool = await asyncpg.create_pool(_dsn)
    except (asyncpg.PostgresError, OSError) as _err:
        logger.error(f'Failed to connect to DB: {_err}')
        raise SystemExit(1)

    async with app.state.pool.acquire() as _conn:
        _dbname = db_config['dbname']

        _exists = await _conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", _dbname
        )

        if not _exists:
            await _conn.execute(f'CREATE DATABASE "{_dbname}"')
            logger.info('Sucussfully created DB')

    yield

    await app.state.pool.close()


app = FastAPI(lifespan=lifespan)


@app.post("/sync", dependencies=[Depends(RateLimiter(limiter=Limiter(Rate(2, Duration.SECOND * 5))))])
async def sync_data(source_url: str, resource: str):
    _base_character_url = f"https://{source_url}/api/{resource}"
    _payload = {
        "species": "Human",
        "status": "alive",
        "origin": "Earth"
    }
    _array_of_dicts = []

    _get = rget(url=_base_character_url, payload=_payload)

    while _get and (_get.json()['info']['next'] or _get.json()['results']):
        _next = _get.json()['info']['next']
        _array_of_dicts += _get.json()['results']

        if _next:
            _get = rget(url=_next, payload={})
        else:
            break

    _conn = await asyncpg.connect(
        host=db_config['host'],
        user=db_config['user'],
        database=db_config['dbname'],
        password=db_config['password'],
    )

    try:
        _query = "CREATE TABLE IF NOT EXISTS character (id SERIAL PRIMARY KEY, data JSONB)"
        await _conn.execute(_query)
        logger.info('Sucussfully created table')

        _array_of_dicts = [(_item['id'], json.dumps(_item),) for _item in _array_of_dicts]

        _query = "INSERT INTO character (id, data) VALUES ($1, $2) ON CONFLICT (id) DO NOTHING"
        await _conn.executemany(
            _query,
            _array_of_dicts
        )

        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={"status": "success", "records_synced": len(_array_of_dicts)}
        )
    except asyncpg.exceptions.DataError as _err:
        raise HTTPException(status_code=400, detail=f"Invalid data format: {str(_err)}")
    finally:
        await _conn.close()


@app.get("/data", dependencies=[Depends(RateLimiter(limiter=Limiter(Rate(2, Duration.SECOND * 5))))])
async def get_data(sort_field: str, sort_order: str):
    _pattern = r"^(ASC|DESC)$"
    if not re.match(_pattern, sort_order, re.IGNORECASE):
        raise HTTPException(status_code=400, detail="Sort order must be ASC or DESC")

    _pattern = r"^(id|data)$"
    if not re.match(_pattern, sort_field, re.IGNORECASE):
        raise HTTPException(status_code=400, detail="Sort field must be id or data")

    _conn = await asyncpg.connect(
        host=db_config['host'],
        user=db_config['user'],
        database=db_config['dbname'],
        password=db_config['password'],
    )

    try:
        _query = f"SELECT id, data FROM character ORDER BY {sort_field} {sort_order}"

        _rows = await _conn.fetch(_query)

        logger.error('Sucussfully fetched data')

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=[_row['data'] for _row in _rows]
        )
    finally:
        await _conn.close()


@app.get("/db-mon", dependencies=[Depends(RateLimiter(limiter=Limiter(Rate(2, Duration.SECOND * 5))))])
async def monitoring(aspect: str):
    match aspect:
        case "conn":
            try:
                _conn = await asyncpg.connect(
                    host=db_config['host'],
                    user=db_config['user'],
                    database=db_config['dbname'],
                    password=db_config['password'],
                )

                _query = "SELECT 1"

                await _conn.fetch(_query)

                await _conn.close()

                return JSONResponse(
                    status_code=status.HTTP_200_OK,
                    content={}
                )
            except (asyncpg.PostgresError, OSError) as _err:
                logger.error(_err)
                return JSONResponse(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    content={}
                )
            finally:
                await _conn.close()
        case "records":
            try:
                _conn = await asyncpg.connect(
                    host=db_config['host'],
                    user=db_config['user'],
                    database=db_config['dbname'],
                    password=db_config['password'],
                )

                _query = "SELECT COUNT(*) FROM character;"

                _records = await _conn.fetch(_query)

                await _conn.close()

                return JSONResponse(
                    status_code=status.HTTP_200_OK,
                    content={"records": _records}
                )
            except (asyncpg.PostgresError, OSError) as _err:
                logger.error(_err)
                return JSONResponse(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    content={}
                )
            finally:
                await _conn.close()
        case _:
            raise HTTPException(status_code=400, detail="Unrecognized aspect")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
