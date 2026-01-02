"""AKX Crypto Payment Gateway - Celery configuration.

Uses Celery with Redis as message broker for background task processing.

Usage:
    # Start all workers
    celery -A src.workers.celery_app worker -l info

    # Start TRON scanner only
    celery -A src.workers.celery_app worker -Q tron -l info -c 1

    # Start beat scheduler
    celery -A src.workers.celery_app beat -l info
"""

from celery import Celery

from src.core.config import get_settings

settings = get_settings()

# Create Celery app
celery_app = Celery(
    "akx_workers",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "src.workers.chain_scanners.tron_scanner",
        "src.workers.chain_scanners.ethereum_scanner",
        "src.workers.chain_scanners.solana_scanner",
        "src.workers.tasks.order_expiry",
        "src.workers.tasks.webhooks",
        "src.workers.tasks.withdrawals",
        "src.workers.tasks.sweeper",
    ],
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Task routing - each chain has its own queue
    task_routes={
        "src.workers.chain_scanners.tron_scanner.*": {"queue": "tron"},
        "src.workers.chain_scanners.ethereum_scanner.*": {"queue": "ethereum"},
        "src.workers.chain_scanners.solana_scanner.*": {"queue": "solana"},
        "src.workers.tasks.*": {"queue": "common"},
    },
    # Task result expiration
    result_expires=3600,  # 1 hour
    # Worker settings
    worker_prefetch_multiplier=1,  # Process one task at a time per worker
    task_acks_late=True,  # Acknowledge after task completes
    task_reject_on_worker_lost=True,
    # Beat schedule (periodic tasks)
    beat_schedule={
        # TRON scanning every 10 seconds
        "scan-tron-blocks": {
            "task": "src.workers.chain_scanners.tron_scanner.scan_tron_blocks",
            "schedule": 10.0,
        },
        # Ethereum scanning every 15 seconds
        "scan-ethereum-blocks": {
            "task": "src.workers.chain_scanners.ethereum_scanner.scan_ethereum_blocks",
            "schedule": 15.0,
        },
        # Solana scanning every 5 seconds
        "scan-solana-blocks": {
            "task": "src.workers.chain_scanners.solana_scanner.scan_solana_blocks",
            "schedule": 5.0,
        },
        # Sweep funds every 5 minutes
        "sweep-funds": {
            "task": "src.workers.tasks.sweeper.sweep_funds",
            "schedule": 300.0,
        },
        # Retry webhooks every minute
        "retry-webhooks": {
            "task": "src.workers.tasks.webhooks.retry_webhooks",
            "schedule": 60.0,
        },
        # Process pending withdrawals every 30 seconds
        "process-withdrawals": {
            "task": "src.workers.tasks.withdrawals.process_pending_withdrawals",
            "schedule": 30.0,
        },
    },
)
