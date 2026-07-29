"""题库管理 API — 教师专用 CRUD"""

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.knowledge_point import KnowledgePoint
from app.models.question import Question
from app.models.user import User
from app.schemas.common import ResponseBase
from app.schemas.knowledge import (
    QuestionCreate,
    QuestionListResponse,
    QuestionOut,
    QuestionUpdate,
)

router = APIRouter()


def _role_guard(current_user: User) -> None:
    """仅教师/管理员可操作"""
    if current_user.role != "teacher" and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅教师或管理员可管理题库",
        )


async def _enrich_question(db: AsyncSession, q: Question) -> QuestionOut:
    """补充题目的知识点名称"""
    kp_names: List[str] = []
    for kp_id in (q.kp_ids or []):
        try:
            result = await db.execute(
                select(KnowledgePoint.name).where(KnowledgePoint.id == uuid.UUID(kp_id))
            )
            name = result.scalar_one_or_none()
            if name:
                kp_names.append(name)
        except ValueError:
            pass

    return QuestionOut(
        id=str(q.id),
        code=q.code,
        kp_ids=q.kp_ids or [],
        kp_names=kp_names,
        subject=q.subject,
        difficulty=q.difficulty,
        type=q.type,
        title=q.title,
        options=q.options or [],
        correct_option_id=q.correct_option_id,
        expected_time_sec=q.expected_time_sec,
        explanation=q.explanation,
        is_active=q.is_active,
        created_at=q.created_at.replace(tzinfo=None) if q.created_at else None,
        updated_at=q.updated_at.replace(tzinfo=None) if q.updated_at else None,
    )


# ── GET /questions — 题目列表 ──────────────────────────

@router.get(
    "",
    response_model=ResponseBase[QuestionListResponse],
    summary="获取题库列表",
)
async def list_questions(
    subject: Optional[str] = Query(default=None, description="学科"),
    difficulty: Optional[int] = Query(default=None, ge=1, le=5, description="难度"),
    kp_id: Optional[str] = Query(default=None, description="知识点ID"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询题库列表 (分页)"""
    # 基础查询
    base = select(Question)
    count_base = select(func.count(Question.id))

    if subject:
        base = base.where(Question.subject == subject)
        count_base = count_base.where(Question.subject == subject)
    if difficulty:
        base = base.where(Question.difficulty == difficulty)
        count_base = count_base.where(Question.difficulty == difficulty)
    if kp_id:
        base = base.where(Question.kp_ids.contains([kp_id]))
        count_base = count_base.where(Question.kp_ids.contains([kp_id]))

    base = base.order_by(Question.difficulty, Question.code)

    # 总数
    total_result = await db.execute(count_base)
    total = total_result.scalar() or 0

    # 分页
    result = await db.execute(base.offset((page - 1) * page_size).limit(page_size))
    questions = result.scalars().all()

    items = []
    for q in questions:
        items.append(await _enrich_question(db, q))

    return ResponseBase(
        data=QuestionListResponse(
            items=items, total=total, page=page, page_size=page_size
        )
    )


# ── GET /questions/{question_id} — 题目详情 ─────────────

@router.get(
    "/{question_id}",
    response_model=ResponseBase[QuestionOut],
    summary="获取题目详情",
)
async def get_question(
    question_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取单题详情"""
    try:
        uid = uuid.UUID(question_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的题目 ID")

    result = await db.execute(select(Question).where(Question.id == uid))
    q = result.scalar_one_or_none()
    if not q:
        raise HTTPException(status_code=404, detail="题目不存在")

    return ResponseBase(data=await _enrich_question(db, q))


# ── POST /questions — 创建题目 ─────────────────────────

@router.post(
    "",
    response_model=ResponseBase[QuestionOut],
    status_code=status.HTTP_201_CREATED,
    summary="创建题目 (教师)",
)
async def create_question(
    data: QuestionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建新题目"""
    _role_guard(current_user)

    # 校验选项中的 correct_option_id 存在
    option_ids = [opt.id for opt in data.options]
    if data.correct_option_id not in option_ids:
        raise HTTPException(
            status_code=400,
            detail=f"正确选项 '{data.correct_option_id}' 不在选项列表 {option_ids} 中",
        )

    # 校验 code 唯一性
    existing = await db.execute(
        select(Question.id).where(Question.code == data.code)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"题目编号 '{data.code}' 已存在")

    q = Question(
        code=data.code,
        kp_ids=data.kp_ids,
        subject=data.subject,
        difficulty=data.difficulty,
        type=data.type,
        title=data.title,
        options=[opt.model_dump() for opt in data.options],
        correct_option_id=data.correct_option_id,
        expected_time_sec=data.expected_time_sec,
        explanation=data.explanation,
    )
    db.add(q)
    await db.commit()
    await db.refresh(q)

    return ResponseBase(
        message="题目创建成功",
        data=await _enrich_question(db, q),
    )


# ── PUT /questions/{question_id} — 更新题目 ─────────────

@router.put(
    "/{question_id}",
    response_model=ResponseBase[QuestionOut],
    summary="更新题目 (教师)",
)
async def update_question(
    question_id: str,
    data: QuestionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新题目"""
    _role_guard(current_user)

    try:
        uid = uuid.UUID(question_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的题目 ID")

    result = await db.execute(select(Question).where(Question.id == uid))
    q = result.scalar_one_or_none()
    if not q:
        raise HTTPException(status_code=404, detail="题目不存在")

    update_fields = data.model_dump(exclude_unset=True)
    # 特殊处理 options
    if "options" in update_fields:
        opts_raw = update_fields.pop("options")
        update_fields["options"] = [opt.model_dump() if hasattr(opt, "model_dump") else opt for opt in opts_raw]

    for field, value in update_fields.items():
        setattr(q, field, value)

    await db.commit()
    await db.refresh(q)

    return ResponseBase(
        message="题目更新成功",
        data=await _enrich_question(db, q),
    )


# ── DELETE /questions/{question_id} — 删除题目 ──────────

@router.delete(
    "/{question_id}",
    response_model=ResponseBase,
    summary="删除题目 (教师)",
)
async def delete_question(
    question_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除题目"""
    _role_guard(current_user)

    try:
        uid = uuid.UUID(question_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的题目 ID")

    result = await db.execute(select(Question).where(Question.id == uid))
    q = result.scalar_one_or_none()
    if not q:
        raise HTTPException(status_code=404, detail="题目不存在")

    await db.delete(q)
    await db.commit()

    return ResponseBase(message=f"题目 '{q.code}' 已删除")


# ── POST /questions/batch — 批量导入题目 ────────────────

@router.post(
    "/batch",
    response_model=ResponseBase,
    summary="批量导入题目 (教师)",
)
async def batch_create_questions(
    items: List[QuestionCreate],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批量导入题目 (可用于从 JSON 导入)"""
    _role_guard(current_user)

    created = 0
    skipped = 0
    for data in items:
        existing = await db.execute(
            select(Question.id).where(Question.code == data.code)
        )
        if existing.scalar_one_or_none():
            skipped += 1
            continue

        option_ids = [opt.id for opt in data.options]
        if data.correct_option_id not in option_ids:
            skipped += 1
            continue

        q = Question(
            code=data.code,
            kp_ids=data.kp_ids,
            subject=data.subject,
            difficulty=data.difficulty,
            type=data.type,
            title=data.title,
            options=[opt.model_dump() for opt in data.options],
            correct_option_id=data.correct_option_id,
            expected_time_sec=data.expected_time_sec,
            explanation=data.explanation,
        )
        db.add(q)
        created += 1

    await db.commit()

    return ResponseBase(
        message=f"批量导入完成: 创建 {created} 道, 跳过 {skipped} 道",
        data={"created": created, "skipped": skipped},
    )
