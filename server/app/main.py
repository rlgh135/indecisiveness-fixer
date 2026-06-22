from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import check_db
from app.redis_client import check_redis, close_redis


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_redis()


app = FastAPI(title="Indecisveness Fixer API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    db_ok = await check_db()
    redis_ok = await check_redis()
    status = "ok" if db_ok and redis_ok else "degraded"
    return {"status": status, "db": db_ok, "redis": redis_ok}
