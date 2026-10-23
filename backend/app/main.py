import asyncio
import json
import logging
import re
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response, StreamingResponse
from redis import Redis
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.auth import CurrentUser, require_access, require_admin, require_owner
from app.auth import router as auth_router
from app.contract_drafts import router as contract_drafts_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.cover_names import router as cover_names_router
from app.db import SessionLocal, engine
from app.document_previews import router as document_previews_router
from app.models import Task, TaskEvent
from app.oa import router as oa_router
from app.schemas import DemoTaskInput, TaskCreated, TaskView
from app.storage import ObjectStorage
from app.task_service import TERMINAL, event_batch, update_task
from app.templates import router as template_router
from app.worker import run_demo

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)
app = FastAPI(
    title="合同起草 · 开发接口",
    dependencies=[Depends(require_access)],
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.include_router(auth_router)
app.include_router(template_router)
app.include_router(oa_router)
app.include_router(cover_names_router)
app.include_router(contract_drafts_router)
app.include_router(document_previews_router)


def error_response(request: Request, status: int, code: str, message: str) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "request_id": request_id}},
        headers={"X-Request-ID": request_id},
    )


@app.middleware("http")
async def request_context(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    incoming = request.headers.get("X-Request-ID", "")
    request.state.request_id = (
        incoming if re.fullmatch(r"[\w-]{1,64}", incoming) else uuid.uuid4().hex
    )
    try:
        response = await call_next(request)
    except Exception as exc:
        logger.error(
            "request failed",
            extra={"request_id": request.state.request_id, "error_type": type(exc).__name__},
        )
        response = error_response(request, 500, "internal_error", "服务暂时不可用")
    response.headers["X-Request-ID"] = request.state.request_id
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Authorization"
    logger.info(
        "request",
        extra={
            "request_id": request.state.request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
        },
    )
    return response


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    response = error_response(request, exc.status_code, f"http_{exc.status_code}", str(exc.detail))
    response.headers.update(exc.headers or {})
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    messages = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
    return error_response(request, 422, "validation_error", messages)


@app.get("/api/v1/health/live")
def live() -> dict[str, str]:
    return {"status": "ok", "service": "contract-drafting", "environment": settings.app_env}


@app.get("/api/v1/health/ready", dependencies=[Depends(require_admin)])
def ready() -> JSONResponse:
    dependencies: dict[str, dict[str, str]] = {}
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1 FROM tasks LIMIT 1"))
        dependencies["postgresql"] = {"status": "ok"}
    except Exception:
        dependencies["postgresql"] = {"status": "error", "message": "数据库或迁移不可用"}
    try:
        with Redis.from_url(
            settings.redis_url, socket_connect_timeout=2, socket_timeout=2
        ) as client:
            client.ping()
        dependencies["redis"] = {"status": "ok"}
    except Exception:
        dependencies["redis"] = {"status": "error", "message": "队列连接失败"}
    try:
        dependencies["minio"] = ObjectStorage().check()
    except Exception:
        dependencies["minio"] = {"status": "error", "message": "MinIO 测试 bucket 不可访问"}
    healthy = all(d["status"] != "error" for d in dependencies.values())
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={
            "status": "ready" if healthy else "not_ready",
            "dependencies": dependencies,
            "integrations": {
                "crm": "demo_only",
                "llm": "disabled",
                "oa": "configured" if settings.oa_configured else "not_configured",
            },
        },
    )


@app.post(
    "/api/v1/demo/tasks",
    response_model=TaskCreated,
    status_code=202,
    dependencies=[Depends(require_admin)],
)
def create_task(data: DemoTaskInput, request: Request, user: CurrentUser) -> TaskCreated:
    task_id = uuid.uuid4()
    with SessionLocal.begin() as session:
        session.add(
            Task(
                id=task_id,
                owner_sub=user.sub,
                input=data.model_dump(),
                status="queued",
                request_id=request.state.request_id,
            )
        )
        session.flush()
        session.add(
            TaskEvent(
                task_id=task_id,
                kind="progress",
                payload={"status": "queued", "progress": 0, "message": "等待后台执行"},
            )
        )
    try:
        run_demo.apply_async(args=[str(task_id)], task_id=str(task_id), retry=False)
    except Exception:
        update_task(
            task_id,
            "failed",
            "failed",
            {"message": "任务入队失败，请检查 Redis"},
            error="任务入队失败，请检查 Redis",
        )
        return TaskCreated(id=task_id, status="failed")
    return TaskCreated(id=task_id)


@app.get("/api/v1/tasks/{task_id}", response_model=TaskView)
def get_task(task_id: uuid.UUID, user: CurrentUser) -> TaskView:
    with SessionLocal() as session:
        task = session.get(Task, task_id)
        if task is None:
            raise HTTPException(404, "任务不存在")
        require_owner(task.owner_sub, user)
        return TaskView.model_validate(task)


@app.get("/api/v1/tasks/{task_id}/events")
async def task_events(
    task_id: uuid.UUID, request: Request, user: CurrentUser, after: int = 0
) -> Response:
    raw_cursor = request.headers.get("Last-Event-ID", str(after))
    try:
        cursor = int(raw_cursor)
        if cursor < 0:
            raise ValueError
    except ValueError:
        raise HTTPException(400, "事件游标必须为非负整数") from None
    # Verify before starting the stream so 404 remains a normal JSON error.
    await asyncio.to_thread(get_task, task_id, user)
    batch, status = await asyncio.to_thread(event_batch, task_id, cursor)
    if not batch and status in TERMINAL:
        return Response(status_code=204)  # EventSource must stop reconnecting.

    async def stream() -> AsyncIterator[str]:
        nonlocal cursor, batch, status
        heartbeat = time.monotonic()
        try:
            while not await request.is_disconnected():
                if time.time() >= user.expires_at:
                    break  # Reconnect with a refreshed bearer token.
                for event in batch:
                    cursor = event["id"]
                    payload = json.dumps(event["data"], ensure_ascii=False)
                    yield f"id: {cursor}\nevent: {event['event']}\ndata: {payload}\n\n"
                if status in TERMINAL and len(batch) < 100:
                    break
                if time.monotonic() - heartbeat >= settings.sse_heartbeat_seconds:
                    yield ": heartbeat\n\n"
                    heartbeat = time.monotonic()
                await asyncio.sleep(settings.sse_poll_seconds)
                batch, status = await asyncio.to_thread(event_batch, task_id, cursor)
                if status == "missing":
                    break
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(
                "event stream interrupted",
                extra={
                    "task_id": str(task_id),
                    "request_id": request.state.request_id,
                    "error_type": type(exc).__name__,
                },
            )
            # Closing without a terminal event lets EventSource reconnect with Last-Event-ID.
            return

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
