import logging
import uuid
from typing import Any

from celery import Celery

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db import SessionLocal
from app.models import Task
from app.task_service import TERMINAL, update_task
from app.workflows import create_demo_graph

settings = get_settings()
celery_app = Celery("contract_drafting", broker=settings.redis_url)
celery_app.conf.update(
    include=["app.preview_tasks"],
    beat_schedule={
        "expire-document-previews": {
            "task": "contract_drafting.cleanup_previews",
            "schedule": 300.0,
        }
    },
    task_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,
    broker_connection_retry_on_startup=True,
    broker_connection_timeout=3,
    broker_transport_options={"socket_connect_timeout": 3, "socket_timeout": 3},
    worker_prefetch_multiplier=1,
    task_soft_time_limit=60,
    task_time_limit=75,
    worker_hijack_root_logger=False,
)
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)


@celery_app.task(name="contract_drafting.demo")
def run_demo(task_id: str) -> None:
    ident = uuid.UUID(task_id)
    with SessionLocal() as session:
        task = session.get(Task, ident)
        if task is None or task.status in TERMINAL:
            return
        data, request_id = task.input, task.request_id

    def report(progress: int, message: str) -> None:
        update_task(ident, "running", "progress", {"progress": progress, "message": message})

    try:
        report(5, "后台任务已启动")
        output: dict[str, Any] = create_demo_graph(report).invoke(data)
        update_task(
            ident,
            "succeeded",
            "completed",
            {"progress": 100, "message": "示例流程完成", "result": output["result"]},
            result=output["result"],
        )
        logger.info("task completed", extra={"task_id": task_id, "request_id": request_id})
    except Exception as exc:
        message = str(exc) if isinstance(exc, ValueError) else "任务执行失败，请查看后台日志"
        update_task(ident, "failed", "failed", {"message": message}, error=message)
        logger.error(
            "task failed",
            extra={"task_id": task_id, "request_id": request_id, "error_type": type(exc).__name__},
        )
