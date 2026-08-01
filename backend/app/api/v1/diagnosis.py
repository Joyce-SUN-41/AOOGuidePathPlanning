"""诊断 API — 认知诊断测验 提交 / 获取题目 / 历史查询"""

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.diagnosis import DiagnosisRecord
from app.models.user import User
from app.schemas.common import ResponseBase
from app.schemas.diagnosis import (
    DiagnosisBrief,
    DiagnosisHistoryResponse,
    DiagnosisQuestion,
    DiagnosisResultResponse,
    DiagnosisSubmitRequest,
    QuestionsResponse,
    RawDiagnosisResult,
)
from app.services.diagnosis import diagnosis_service

logger = logging.getLogger(__name__)

router = APIRouter()


# ── GET /questions — 获取诊断题目 ──────────────────────

@router.get(
    "/questions",
    response_model=ResponseBase[QuestionsResponse],
    summary="获取诊断题目",
)
async def get_questions(
    count: int = Query(default=15, ge=5, le=30, description="题目数量"),
    subject: str = Query(default="人工智能导论", description="学科"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取诊断题库, 优先从数据库读取, 降级到内置 Mock 数据"""
    # 尝试从 DB 加载
    try:
        bank = await diagnosis_service.get_question_bank_from_db(db, subject=subject)
        if not bank:
            bank = diagnosis_service.get_question_bank()  # fallback
    except Exception:
        bank = diagnosis_service.get_question_bank()

    questions = bank[:count]

    question_schemas = [
        DiagnosisQuestion(
            id=q["id"],
            topic=q["topic"],
            kp_id=q["kp_id"],
            difficulty=q["difficulty"],
            title=q["title"],
            options=q["options"],
            type=q["type"],
            correct_option_id=q["correct_option_id"],
            expected_time_sec=q["expected_time_sec"],
        )
        for q in questions
    ]

    return ResponseBase(
        data=QuestionsResponse(
            questions=question_schemas,
            total=len(question_schemas),
            subject=subject,
            estimated_duration_min=max(5, len(question_schemas) * 20 // 60),
        )
    )


# ── POST /submit — 提交诊断答案 ────────────────────────

@router.post(
    "/submit",
    response_model=ResponseBase[DiagnosisResultResponse],
    summary="提交诊断测验结果",
)
async def submit_diagnosis(
    request: DiagnosisSubmitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """提交诊断答案, 计算掌握度和认知负荷, 持久化结果.

    同时自动触发异步 AOO 路径规划任务.
    """
    # 权限校验: student_id 必须与当前登录用户一致
    student_id = request.student_id or current_user.id
    if str(student_id) != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="不能替其他学生提交诊断",
        )

    # 1. 加载题库 (优先DB)
    try:
        bank = await diagnosis_service.get_question_bank_from_db(db, subject=request.subject)
        if not bank:
            bank = diagnosis_service.get_question_bank()
    except Exception:
        bank = diagnosis_service.get_question_bank()

    # 2. 执行诊断分析
    mastery_levels, cognitive_load, analyses, kp_map = diagnosis_service.diagnose(
        answers=request.answers,
        subject=request.subject,
        grade=request.grade,
        bank=bank,
    )

    if not analyses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无有效答案可分析, 请检查 question_id 是否正确",
        )

    # 3. 加载知识点名称映射
    kp_name_map = await diagnosis_service._load_kp_name_map(db)

    # 4. 持久化到数据库
    record = await diagnosis_service.persist_results(
        db=db,
        student_id=student_id,
        answers=request.answers,
        mastery_levels=mastery_levels,
        cognitive_load=cognitive_load,
        analyses=analyses,
        kp_map=kp_map,
        subject=request.subject,
        grade=request.grade,
        kp_name_map=kp_name_map,
    )

    # 5. 触发异步 AOO 路径规划 (Celery 优先, 同步兜底)
    diagnosis_id = str(record.id)
    student_id_str = str(student_id) if not isinstance(student_id, str) else student_id
    cognitive_load_overall = getattr(cognitive_load, "overall", 0.0)
    try:
        from app.tasks.diagnosis import trigger_aoo_path_planning
        trigger_aoo_path_planning.delay(
            diagnosis_id=diagnosis_id,
            student_id=student_id_str,
            mastery_levels=mastery_levels,
            cognitive_load=cognitive_load_overall,
        )
        logger.info(
            "AOO path planning triggered for diagnosis_id=%s, "
            "student=%s, kps=%d, load=%.2f",
            diagnosis_id, student_id_str,
            len(mastery_levels), cognitive_load_overall,
        )
    except Exception as exc:
        logger.warning(
            "Celery 不可用, 使用同步执行兜底触发 AOO: %s", exc
        )
        # ── 同步兜底: 后台线程执行 AOO 优化 ──
        try:
            from app.tasks.aoo_optimization import run_aoo_optimization_sync
            sync_id = run_aoo_optimization_sync(
                diagnosis_id=diagnosis_id,
                student_id=student_id_str,
                mastery_levels=mastery_levels,
                cognitive_load=cognitive_load_overall,
            )
            logger.info(
                "AOO sync path planning started: task_id=%s diagnosis=%s",
                sync_id, diagnosis_id,
            )
        except Exception as sync_exc:
            logger.error(
                "AOO 同步执行也失败, 平台将以无路径状态返回: %s", sync_exc
            )

    # 6. 构建完整响应
    result_response = diagnosis_service.build_response(record)

    return ResponseBase(
        message="诊断完成",
        data=result_response,
    )


# ── GET /latest — 获取最新诊断结果 ──────────────────────

@router.get(
    "/latest",
    response_model=ResponseBase[Optional[DiagnosisResultResponse]],
    summary="获取最新诊断结果",
)
async def get_latest_diagnosis(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前学生的最新诊断结果；若从未诊断则返回 null(200)"""
    result = await db.execute(
        select(DiagnosisRecord)
        .where(DiagnosisRecord.student_id == current_user.id)
        .order_by(desc(DiagnosisRecord.created_at))
        .limit(1)
    )
    record = result.scalar_one_or_none()

    if not record:
        return ResponseBase[Optional[DiagnosisResultResponse]](data=None)

    return ResponseBase[Optional[DiagnosisResultResponse]](
        data=diagnosis_service.build_response(record)
    )


# ── GET /history — 获取诊断历史列表(兼容路径，必须放在 /{diagnosis_id} 之前) ─

@router.get(
    "/history",
    response_model=ResponseBase[DiagnosisHistoryResponse],
    summary="获取诊断历史列表(兼容路径)",
)
async def get_diagnosis_history_compat(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=10, ge=1, le=50, description="每页数量"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await get_diagnosis_history(page, page_size, db, current_user)


# ── GET /{diagnosis_id} — 获取诊断详情 ─────────────────

@router.get(
    "/{diagnosis_id}",
    response_model=ResponseBase[DiagnosisResultResponse],
    summary="获取指定诊断详情",
)
async def get_diagnosis_detail(
    diagnosis_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取指定 ID 的诊断详情"""
    try:
        uid = uuid.UUID(diagnosis_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无效的诊断 ID 格式",
        )

    result = await db.execute(
        select(DiagnosisRecord).where(DiagnosisRecord.id == uid)
    )
    record = result.scalar_one_or_none()

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="诊断记录不存在",
        )

    # 只能查看自己的诊断
    if str(record.student_id) != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权查看他人的诊断记录",
        )

    return ResponseBase(data=diagnosis_service.build_response(record))


# ── GET /history — 获取诊断历史 ────────────────────────

@router.get(
    "",
    response_model=ResponseBase[DiagnosisHistoryResponse],
    summary="获取诊断历史列表",
)
async def get_diagnosis_history(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=10, ge=1, le=50, description="每页数量"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前学生的诊断历史列表 (分页)"""
    # 总数
    count_result = await db.execute(
        select(func.count(DiagnosisRecord.id)).where(
            DiagnosisRecord.student_id == current_user.id
        )
    )
    total = count_result.scalar() or 0

    # 分页查询
    records_result = await db.execute(
        select(DiagnosisRecord)
        .where(DiagnosisRecord.student_id == current_user.id)
        .order_by(desc(DiagnosisRecord.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    records = records_result.scalars().all()

    items = [
        DiagnosisBrief(
            id=str(r.id),
            created_at=r.created_at.replace(tzinfo=None),
            subject=r.subject,
            overall_score=r.overall_score,
            weak_point_count=len(r.weak_points),
        )
        for r in records
    ]

    return ResponseBase(
        data=DiagnosisHistoryResponse(items=items, total=total)
    )


# ── DELETE /{diagnosis_id} — 删除诊断记录 ─────────────────

@router.delete(
    "/{diagnosis_id}",
    response_model=ResponseBase,
    summary="删除诊断记录",
)
async def delete_diagnosis(
    diagnosis_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除指定诊断记录 (仅本人)"""
    try:
        uid = uuid.UUID(diagnosis_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无效的诊断 ID 格式",
        )

    result = await db.execute(
        select(DiagnosisRecord).where(DiagnosisRecord.id == uid)
    )
    record = result.scalar_one_or_none()

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="诊断记录不存在",
        )

    if str(record.student_id) != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权删除他人的诊断记录",
        )

    await db.delete(record)
    await db.commit()

    return ResponseBase(message="诊断记录已删除")
