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
    response_model=ResponseBase,
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

    # 5. 触发异步 AOO 路径规划
    diagnosis_id = str(record.id)
    try:
        from app.tasks.diagnosis import trigger_aoo_path_planning
        trigger_aoo_path_planning.delay(diagnosis_id=diagnosis_id)
        logger.info(
            "AOO path planning triggered for diagnosis_id=%s", diagnosis_id
        )
    except Exception as exc:
        logger.warning(
            "Failed to trigger AOO task (Celery may be offline): %s", exc
        )

    # 6. 构建响应
    weak_kp_ids = [
        kp_id for kp_id, v in mastery_levels.items() if v < 0.6
    ]

    # 雷达图原始数据
    radar_data_raw = {
        diagnosis_service._get_kp_name(kp_id, kp_name_map): v
        for kp_id, v in mastery_levels.items()
    }

    # 构建完整响应 (优先返回富文本)
    result_response = diagnosis_service.build_response(record)

    return ResponseBase(
        message="诊断完成",
        data={
            # 简化字段 (兼容旧 API)
            "mastery_levels": mastery_levels,
            "cognitive_load": cognitive_load.overall,
            "weak_points": weak_kp_ids,
            "diagnosis_id": diagnosis_id,
            "radar_data": radar_data_raw,
            # 完整响应
            "result": result_response.model_dump(mode="json"),
        },
    )


# ── GET /latest — 获取最新诊断结果 ──────────────────────

@router.get(
    "/latest",
    response_model=ResponseBase[DiagnosisResultResponse],
    summary="获取最新诊断结果",
)
async def get_latest_diagnosis(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前学生的最新诊断结果"""
    result = await db.execute(
        select(DiagnosisRecord)
        .where(DiagnosisRecord.student_id == current_user.id)
        .order_by(desc(DiagnosisRecord.created_at))
        .limit(1)
    )
    record = result.scalar_one_or_none()

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到诊断记录, 请先完成一次诊断测验",
        )

    return ResponseBase(data=diagnosis_service.build_response(record))


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
