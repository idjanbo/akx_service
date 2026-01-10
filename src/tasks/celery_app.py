"""Celery configuration."""

from celery import Celery

from src.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "akx_tasks",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "src.tasks.callback",
        "src.tasks.blockchain",
        "src.tasks.orders",
        "src.tasks.exchange_rates",
        "src.tasks.telegram",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    result_expires=3600,
    task_default_retry_delay=60,
    task_max_retries=5,
    task_routes={
        "src.tasks.callback.*": {"queue": "callbacks"},
        "blockchain.*": {"queue": "blockchain"},
        "order.*": {"queue": "orders"},
        "exchange_rates.*": {"queue": "exchange_rates"},
    },
    beat_schedule={
        "confirm-transactions": {
            "task": "blockchain.confirm_transactions",
            "schedule": 30.0,
        },
        "sync-exchange-rates": {
            "task": "exchange_rates.sync_all",
            "schedule": 10.0,  # 每 10 秒检查一次，具体同步间隔由各源的 sync_interval 决定
        },
    },
)
