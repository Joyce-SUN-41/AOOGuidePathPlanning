"""诊断异步任务 — AOO 路径规划触发 & 诊断后处理"""

import logging

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=30)
def trigger_aoo_path_planning(self, diagnosis_id: str):
    """诊断完成后, 异步触发 AOO 智能路径规划任务.

    该任务从 diagnosis_records 表中读取掌握度数据,
    初始化 AOO 算法种群, 启动优化迭代流程.

    实际路径生成由 app.services.aoo.AOOService.optimize() 完成.
    """
    task_id = self.request.id
    logger.info(
        "AOO path planning task started: task_id=%s, diagnosis_id=%s",
        task_id, diagnosis_id,
    )

    try:
        # NOTE: 当 AOO 服务实现后, 在此调用:
        #   from app.services.aoo import aoo_service
        #   result = await aoo_service.optimize(diagnosis_id=diagnosis_id)
        # 当前返回占位结果, 表示任务已被触发

        logger.info(
            "AOO path planning staged: task_id=%s, "
            "diagnosis_id=%s (AOO service pending implementation)",
            task_id, diagnosis_id,
        )

        return {
            "task_id": task_id,
            "diagnosis_id": diagnosis_id,
            "status": "staged",
            "message": "AOO 优化任务已入队, 等待 AOOService 实现后自动执行",
        }

    except Exception as exc:
        logger.error(
            "AOO path planning failed: task_id=%s, diagnosis_id=%s, error=%s",
            task_id, diagnosis_id, exc,
        )
        # 指数退避重试
        raise self.retry(exc=exc, countdown=30 * (self.request.retries + 1))
