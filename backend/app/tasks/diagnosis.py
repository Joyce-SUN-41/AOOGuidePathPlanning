"""诊断异步任务 — AOO 路径规划触发 & 诊断后处理"""

import logging
from typing import Any, Dict, Optional

from app.tasks.celery_app import celery_app
from app.tasks.aoo_optimization import run_aoo_optimization

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=30)
def trigger_aoo_path_planning(
    self,
    diagnosis_id: str,
    student_id: str,
    mastery_levels: Dict[str, float],
    cognitive_load: float,
    config: Optional[Dict[str, Any]] = None,
):
    """诊断完成后, 异步触发 AOO 智能路径规划任务.

    将诊断数据转发给 run_aoo_optimization 任务,
    该任务调用 OptimizationService.run() 执行 AOO 算法并创建 LearningPath.
    """
    task_id = self.request.id
    logger.info(
        "AOO path planning triggered: task_id=%s diagnosis=%s student=%s kps=%d load=%.2f",
        task_id, diagnosis_id, student_id, len(mastery_levels), cognitive_load,
    )

    try:
        # 链式调用实际的 AOO 优化任务
        result = run_aoo_optimization.delay(
            diagnosis_id=diagnosis_id,
            student_id=student_id,
            mastery_levels=mastery_levels,
            cognitive_load=cognitive_load,
            config=config,
        )
        logger.info(
            "AOO optimization task dispatched: task_id=%s, child_task_id=%s",
            task_id, result.id,
        )
        return {
            "task_id": task_id,
            "diagnosis_id": diagnosis_id,
            "aoo_task_id": str(result.id),
            "status": "dispatched",
            "message": "AOO 优化任务已调度执行",
        }
    except Exception as exc:
        logger.error(
            "Failed to dispatch AOO task: task_id=%s, diagnosis_id=%s, error=%s",
            task_id, diagnosis_id, exc,
        )
        raise self.retry(exc=exc, countdown=30 * (self.request.retries + 1))
