"""示例 Celery 异步任务

实际使用时，在此模块定义所有 Celery task 并注册到 celery_app
"""

import logging
import time

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3)
def example_long_task(self, data: dict) -> dict:
    """示例：长时间运行的异步任务"""
    task_id = self.request.id
    logger.info("Task started: id=%s, data=%s", task_id, data)

    try:
        # 模拟长时间处理
        time.sleep(2)

        result = {
            "task_id": task_id,
            "status": "completed",
            "processed": len(data),
        }
        logger.info("Task completed: id=%s", task_id)
        return result
    except Exception as exc:
        logger.error("Task failed: id=%s, error=%s", task_id, exc)
        raise self.retry(exc=exc, countdown=10)
