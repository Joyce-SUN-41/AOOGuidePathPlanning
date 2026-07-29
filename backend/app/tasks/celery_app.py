"""Celery 应用实例 — 异步任务队列配置"""

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "aoo_tasks",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.tasks.example",
        "app.tasks.diagnosis",
        "app.tasks.aoo_optimization",
    ],
)

# Celery 配置
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 单个任务最大30分钟
    task_soft_time_limit=25 * 60,  # 软超时25分钟
    worker_max_tasks_per_child=200,
    worker_prefetch_multiplier=1,
)
