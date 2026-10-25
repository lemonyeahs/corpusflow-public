import os

from celery import Celery  # type: ignore[import-untyped]

from corpusflow.core.config import load_settings

settings = load_settings()
celery_app = Celery(
    "corpusflow",
    broker=settings.redis_url.get_secret_value(),
    backend=settings.redis_url.get_secret_value(),
)
celery_app.conf.update(
    task_default_queue=os.environ.get("CF_TASK_QUEUE", "celery"),
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=True,
    task_time_limit=300,
)
celery_app.autodiscover_tasks(["corpusflow.worker"])
