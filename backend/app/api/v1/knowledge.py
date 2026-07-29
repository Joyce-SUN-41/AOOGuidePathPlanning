"""知识点管理 API — 教师专用 CRUD"""

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_current_superuser
from app.core.database import get_db
from app.models.knowledge_point import KnowledgePoint
from app.models.knowledge_graph import KnowledgeGraphEdge
from app.models.question import Question
from app.models.user import User
from app.schemas.common import ResponseBase
from app.schemas.knowledge import (
    KnowledgeGraphEdgeOut,
    KnowledgeGraphResponse,
    KnowledgePointBrief,
    KnowledgePointCreate,
    KnowledgePointDetail,
    KnowledgePointOut,
    KnowledgePointUpdate,
)

router = APIRouter()


def _role_guard(current_user: User) -> None:
    """仅教师/管理员可操作"""
    if current_user.role != "teacher" and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅教师或管理员可管理知识点",
        )


# ── GET /knowledge-points — 获取知识点列表 ──────────────

@router.get(
    "",
    response_model=ResponseBase[List[KnowledgePointOut]],
    summary="获取知识点列表",
)
async def list_knowledge_points(
    subject: Optional[str] = Query(default=None, description="学科筛选"),
    layer: Optional[str] = Query(default=None, description="层级筛选"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取所有知识点 (支持学科/层级筛选)  — 所有用户可读"""
    stmt = select(KnowledgePoint)
    if subject:
        stmt = stmt.where(KnowledgePoint.subject == subject)
    if layer:
        stmt = stmt.where(KnowledgePoint.layer == layer)
    stmt = stmt.order_by(KnowledgePoint.difficulty_level, KnowledgePoint.name)

    result = await db.execute(stmt)
    kps = result.scalars().all()

    items = []
    for kp in kps:
        prereq_ids = await _get_prerequisite_ids(db, kp.id)
        items.append(
            KnowledgePointOut(
                id=str(kp.id),
                name=kp.name,
                description=kp.description,
                subject=kp.subject,
                difficulty_level=kp.difficulty_level,
                layer=kp.layer,
                tags=kp.tags or [],
                parent_id=str(kp.parent_id) if kp.parent_id else None,
                prerequisites=prereq_ids,
                created_at=kp.created_at.replace(tzinfo=None) if kp.created_at else None,
            )
        )

    return ResponseBase(data=items)


async def _get_prerequisite_ids(db: AsyncSession, kp_id: uuid.UUID) -> List[str]:
    """获取某个知识点的所有前置知识点 ID"""
    result = await db.execute(
        select(KnowledgeGraphEdge.source_kp_id).where(
            KnowledgeGraphEdge.target_kp_id == kp_id
        )
    )
    return [str(r[0]) for r in result.all()]


# ── GET /knowledge-points/graph — 获取完整知识图谱 ──────

@router.get(
    "/graph",
    response_model=ResponseBase[KnowledgeGraphResponse],
    summary="获取知识图谱",
)
async def get_knowledge_graph(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取完整知识图谱 (节点 + 边)"""
    # 节点
    kp_result = await db.execute(select(KnowledgePoint).order_by(KnowledgePoint.difficulty_level))
    kps = kp_result.scalars().all()

    # 边
    edge_result = await db.execute(select(KnowledgeGraphEdge))
    edges = edge_result.scalars().all()

    # 名称映射
    name_map = {str(kp.id): kp.name for kp in kps}

    nodes = []
    for kp in kps:
        prereq_ids = await _get_prerequisite_ids(db, kp.id)
        nodes.append(
            KnowledgePointOut(
                id=str(kp.id),
                name=kp.name,
                description=kp.description,
                subject=kp.subject,
                difficulty_level=kp.difficulty_level,
                layer=kp.layer,
                tags=kp.tags or [],
                parent_id=str(kp.parent_id) if kp.parent_id else None,
                prerequisites=prereq_ids,
                created_at=kp.created_at.replace(tzinfo=None) if kp.created_at else None,
            )
        )

    edge_outs = [
        KnowledgeGraphEdgeOut(
            id=str(e.id),
            source_kp_id=str(e.source_kp_id),
            source_name=name_map.get(str(e.source_kp_id), ""),
            target_kp_id=str(e.target_kp_id),
            target_name=name_map.get(str(e.target_kp_id), ""),
            relation_type=e.relation_type,
        )
        for e in edges
    ]

    return ResponseBase(data=KnowledgeGraphResponse(nodes=nodes, edges=edge_outs))


# ── GET /knowledge-points/{kp_id} — 知识点详情 ─────────

@router.get(
    "/{kp_id}",
    response_model=ResponseBase[KnowledgePointDetail],
    summary="获取知识点详情",
)
async def get_knowledge_point_detail(
    kp_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取知识点详情 (含前后置关系 + 关联题目数)"""
    try:
        uid = uuid.UUID(kp_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的知识点 ID")

    result = await db.execute(
        select(KnowledgePoint).where(KnowledgePoint.id == uid)
    )
    kp = result.scalar_one_or_none()
    if not kp:
        raise HTTPException(status_code=404, detail="知识点不存在")

    # 前置
    prereq_result = await db.execute(
        select(KnowledgePoint).join(
            KnowledgeGraphEdge,
            KnowledgePoint.id == KnowledgeGraphEdge.source_kp_id,
        ).where(KnowledgeGraphEdge.target_kp_id == uid)
    )
    prereqs = prereq_result.scalars().all()

    # 后置
    depend_result = await db.execute(
        select(KnowledgePoint).join(
            KnowledgeGraphEdge,
            KnowledgePoint.id == KnowledgeGraphEdge.target_kp_id,
        ).where(KnowledgeGraphEdge.source_kp_id == uid)
    )
    dependents = depend_result.scalars().all()

    # 题目数
    q_count_result = await db.execute(
        select(func.count(Question.id)).where(
            Question.kp_ids.contains([str(uid)])
        )
    )
    question_count = q_count_result.scalar() or 0

    return ResponseBase(
        data=KnowledgePointDetail(
            id=str(kp.id),
            name=kp.name,
            description=kp.description,
            subject=kp.subject,
            difficulty_level=kp.difficulty_level,
            layer=kp.layer,
            tags=kp.tags or [],
            prerequisites=[
                KnowledgePointBrief(
                    id=str(p.id), name=p.name, subject=p.subject,
                    difficulty_level=p.difficulty_level, layer=p.layer,
                )
                for p in prereqs
            ],
            dependents=[
                KnowledgePointBrief(
                    id=str(d.id), name=d.name, subject=d.subject,
                    difficulty_level=d.difficulty_level, layer=d.layer,
                )
                for d in dependents
            ],
            question_count=question_count,
            created_at=kp.created_at.replace(tzinfo=None) if kp.created_at else None,
        )
    )


# ── POST /knowledge-points — 创建知识点 ─────────────────

@router.post(
    "",
    response_model=ResponseBase[KnowledgePointOut],
    status_code=status.HTTP_201_CREATED,
    summary="创建知识点 (教师)",
)
async def create_knowledge_point(
    data: KnowledgePointCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建新知识点并建立前置依赖"""
    _role_guard(current_user)

    kp = KnowledgePoint(
        name=data.name,
        description=data.description,
        subject=data.subject,
        difficulty_level=data.difficulty_level,
        layer=data.layer,
        tags=data.tags,
        parent_id=uuid.UUID(data.parent_id) if data.parent_id else None,
    )
    db.add(kp)
    await db.flush()

    # 建立前置依赖
    for prereq_id_str in data.prerequisites:
        try:
            prereq_uid = uuid.UUID(prereq_id_str)
            edge = KnowledgeGraphEdge(
                source_kp_id=prereq_uid,
                target_kp_id=kp.id,
                relation_type="prerequisite",
            )
            db.add(edge)
        except ValueError:
            continue

    await db.commit()
    await db.refresh(kp)

    prereq_ids = await _get_prerequisite_ids(db, kp.id)
    return ResponseBase(
        message="知识点创建成功",
        data=KnowledgePointOut(
            id=str(kp.id), name=kp.name, description=kp.description,
            subject=kp.subject, difficulty_level=kp.difficulty_level,
            layer=kp.layer, tags=kp.tags or [],
            parent_id=str(kp.parent_id) if kp.parent_id else None,
            prerequisites=prereq_ids,
            created_at=kp.created_at.replace(tzinfo=None) if kp.created_at else None,
        ),
    )


# ── PUT /knowledge-points/{kp_id} — 更新知识点 ───────────

@router.put(
    "/{kp_id}",
    response_model=ResponseBase[KnowledgePointOut],
    summary="更新知识点 (教师)",
)
async def update_knowledge_point(
    kp_id: str,
    data: KnowledgePointUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新知识点信息及前置依赖"""
    _role_guard(current_user)

    try:
        uid = uuid.UUID(kp_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的知识点 ID")

    result = await db.execute(
        select(KnowledgePoint).where(KnowledgePoint.id == uid)
    )
    kp = result.scalar_one_or_none()
    if not kp:
        raise HTTPException(status_code=404, detail="知识点不存在")

    # 更新字段
    update_fields = data.model_dump(exclude_unset=True, exclude={"prerequisites"})
    for field, value in update_fields.items():
        if field == "parent_id" and value:
            setattr(kp, field, uuid.UUID(value))
        else:
            setattr(kp, field, value)

    # 更新前置依赖: 删旧建新
    if data.prerequisites is not None:
        await db.execute(
            select(KnowledgeGraphEdge).where(
                KnowledgeGraphEdge.target_kp_id == uid
            )
        )
        existing_edges = (await db.execute(
            select(KnowledgeGraphEdge).where(
                KnowledgeGraphEdge.target_kp_id == uid
            )
        )).scalars().all()
        for edge in existing_edges:
            await db.delete(edge)

        for prereq_id_str in data.prerequisites:
            try:
                prereq_uid = uuid.UUID(prereq_id_str)
                if prereq_uid == uid:
                    continue  # 不自引用
                edge = KnowledgeGraphEdge(
                    source_kp_id=prereq_uid,
                    target_kp_id=uid,
                    relation_type="prerequisite",
                )
                db.add(edge)
            except ValueError:
                continue

    await db.commit()
    await db.refresh(kp)

    prereq_ids = await _get_prerequisite_ids(db, kp.id)
    return ResponseBase(
        message="知识点更新成功",
        data=KnowledgePointOut(
            id=str(kp.id), name=kp.name, description=kp.description,
            subject=kp.subject, difficulty_level=kp.difficulty_level,
            layer=kp.layer, tags=kp.tags or [],
            parent_id=str(kp.parent_id) if kp.parent_id else None,
            prerequisites=prereq_ids,
            created_at=kp.created_at.replace(tzinfo=None) if kp.created_at else None,
        ),
    )


# ── DELETE /knowledge-points/{kp_id} — 删除知识点 ───────

@router.delete(
    "/{kp_id}",
    response_model=ResponseBase,
    summary="删除知识点 (教师)",
)
async def delete_knowledge_point(
    kp_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除知识点及其关联的所有图谱边"""
    _role_guard(current_user)

    try:
        uid = uuid.UUID(kp_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的知识点 ID")

    result = await db.execute(
        select(KnowledgePoint).where(KnowledgePoint.id == uid)
    )
    kp = result.scalar_one_or_none()
    if not kp:
        raise HTTPException(status_code=404, detail="知识点不存在")

    # 检查是否有关联题目
    q_count = (await db.execute(
        select(func.count(Question.id)).where(
            Question.kp_ids.contains([str(uid)])
        )
    )).scalar() or 0
    if q_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"该知识点关联了 {q_count} 道题目，请先解除关联或删除题目",
        )

    await db.delete(kp)
    await db.commit()

    return ResponseBase(message=f"知识点 '{kp.name}' 已删除")
