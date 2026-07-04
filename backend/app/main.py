import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.asyncio import Redis

from app.config import settings
from app.exceptions import APIError
from app.routers import (
    auth,
    dead_letter_queue,
    jobs,
    organizations,
    projects,
    queues,
    retry_policies,
    workers,
)
from app.websocket.hub import hub
from app.websocket.router import router as websocket_router
from app.websocket.subscriber import run_redis_subscriber

logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    await redis_client.ping()
    subscriber_task = asyncio.create_task(run_redis_subscriber(hub, redis_client))
    logger.info("Redis subscriber started")

    yield

    subscriber_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await subscriber_task
    await redis_client.aclose()
    logger.info("Redis subscriber stopped")


app = FastAPI(title="Distributed Job Scheduler", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(organizations.router)
app.include_router(projects.router)
app.include_router(queues.router)
app.include_router(retry_policies.router)
app.include_router(jobs.router)
app.include_router(workers.router)
app.include_router(dead_letter_queue.router)
app.include_router(websocket_router, prefix="/ws")


@app.exception_handler(APIError)
async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "details": {"errors": jsonable_encoder(exc.errors())},
            }
        },
    )


@app.get("/health")
async def health():
    return {"status": "ok"}
