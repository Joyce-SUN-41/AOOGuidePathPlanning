"""教师端 API — 班级学情总览、学生列表、薄弱知识点、趋势、预警"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.cache import cache_get, cache_set
from app.core.database import get_db
from app.models.cehui import CehuiRecord
from app.models.learning_path import LearningPath
from app.models.user import User
from app.schemas.common import ResponseBase

router = APIRouter()

# 教师聚合看板缓存 TTL（秒）
_TEACHER_DASHBOARD_TTL = 30

# ═══════════════════════════════════════════════════════
#  辅助函数
# ═══════════════════════════════════════════════════════


def _ensure_teacher(user: User) -> None:
    """确认当前用户是教师或超级管理员"""
    if user.role != "teacher" and not user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅教师可访问该接口",
        )


def _student_summary(
    s: User,
    cehui: Optional[CehuiRecord] = None,
    path: Optional[LearningPath] = None,
) -> Dict[str, Any]:
    """将 DB 学生数据转为前端 StudentSummary 格式"""
    overall = cehui.overall_score if cehui else None
    cl = cehui.cognitive_load or {} if cehui else {}
    overall_load = (
        cl.get("overall", 0)
        if isinstance(cl, dict)
        else (cl.overall if hasattr(cl, "overall") else 0)
    )
    path_data = path.path_data or {} if path else {}

    return {
        "id": str(s.id),
        "name": s.username,
        "nickname": s.nickname or s.username,
        "avgMastery": round(overall / 100, 2) if overall is not None else 0.0,
        "cognitiveLoad": round(float(overall_load), 2) if overall_load else 0.0,
        "pathCompletion": path_data.get("completionPercent", 0) if path else 0,
        "lastActiveDate": s.updated_at.isoformat() if s.updated_at else None,
        "completedTasks": path_data.get("completedTasks", 0) if path else 0,
        "totalTasks": path_data.get("totalTasks", 0) if path else 0,
        "weakPointCount": len(cehui.weak_points or []) if cehui and cehui.weak_points else 0,
        "subject": cehui.subject if cehui else "—",
        "overallScore": overall or 0,
    }


# ═══════════════════════════════════════════════════════
#  GET /teacher/class-overview
# ═══════════════════════════════════════════════════════


@router.get(
    "/class-overview",
    response_model=ResponseBase,
    summary="获取班级概览统计数据",
)
async def get_class_overview(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回班级总体指标"""
    _ensure_teacher(current_user)

    # 统计学生总数
    count_result = await db.execute(
        select(func.count(User.id)).where(User.role == "student")
    )
    total = count_result.scalar() or 0

    # 统计有测绘的学生
    diag_result = await db.execute(
        select(CehuiRecord)
        .where(CehuiRecord.student_id.in_(
            select(User.id).where(User.role == "student")
        ))
    )
    cehuis = diag_result.scalars().all()

    # 聚合指标
    scores = [d.overall_score for d in cehuis if d.overall_score is not None]
    loads: List[float] = []
    for d in cehuis:
        cl = d.cognitive_load or {}
        if isinstance(cl, dict):
            ov = cl.get("overall", 0)
        elif hasattr(cl, "overall"):
            ov = cl.overall
        else:
            ov = 0
        loads.append(float(ov))

    # 路径完成率
    path_result = await db.execute(
        select(LearningPath).where(
            LearningPath.student_id.in_(
                select(User.id).where(User.role == "student")
            )
        )
    )
    paths = path_result.scalars().all()
    completions = [
        (p.path_data or {}).get("completionPercent", 0) for p in paths
    ]

    return ResponseBase(data={
        "totalStudents": total,
        "avgMastery": round(sum(scores) / len(scores) / 100, 2) if scores else 0.0,
        "avgCognitiveLoad": round(sum(loads) / len(loads), 2) if loads else 0.0,
        "avgPathCompletion": round(sum(completions) / len(completions), 1) if completions else 0,
        "highLoadCount": sum(1 for v in loads if v > 0.7),
        "lowMasteryCount": sum(1 for v in scores if v < 60),
    })


# ═══════════════════════════════════════════════════════
#  GET /teacher/students
# ═══════════════════════════════════════════════════════


@router.get(
    "/students",
    response_model=ResponseBase,
    summary="获取学生列表",
)
async def get_teacher_students(
    sort_by: str = Query(default="avgMastery", alias="sortBy"),
    order: str = Query(default="desc"),
    page: int = Query(default=1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(default=50, ge=1, le=200, description="每页数量，上限 200"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取学生列表 (分页 + 批量聚合最新测绘/路径，避免 N+1)"""
    _ensure_teacher(current_user)

    # 学生总数
    total = (
        await db.execute(
            select(func.count(User.id)).where(User.role == "student")
        )
    ).scalar() or 0

    # 分页取学生
    offset = (page - 1) * page_size
    result = await db.execute(
        select(User)
        .where(User.role == "student")
        .order_by(User.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    students = result.scalars().all()

    if not students:
        return ResponseBase(data={"students": [], "total": total, "page": page, "page_size": page_size})

    student_ids = [s.id for s in students]

    # 批量获取每个学生的「最新」测绘（按 created_at 取每组最大）
    diag_rows = (
        await db.execute(
            select(CehuiRecord)
            .where(CehuiRecord.student_id.in_(student_ids))
            .order_by(CehuiRecord.student_id, CehuiRecord.created_at.desc())
        )
    ).scalars().all()
    latest_diag: Dict[uuid.UUID, CehuiRecord] = {}
    for d in diag_rows:
        latest_diag.setdefault(d.student_id, d)

    # 批量获取每个学生的「最新」学习路径
    path_rows = (
        await db.execute(
            select(LearningPath)
            .where(LearningPath.student_id.in_(student_ids))
            .order_by(LearningPath.student_id, LearningPath.created_at.desc())
        )
    ).scalars().all()
    latest_path: Dict[uuid.UUID, LearningPath] = {}
    for p in path_rows:
        latest_path.setdefault(p.student_id, p)

    # 汇总
    items: List[Dict[str, Any]] = []
    for s in students:
        items.append(_student_summary(s, latest_diag.get(s.id), latest_path.get(s.id)))

    # 排序
    reverse = order.lower() == "desc"
    items.sort(key=lambda x: x.get(sort_by, 0) or 0, reverse=reverse)

    return ResponseBase(data={
        "students": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    })


# ═══════════════════════════════════════════════════════
#  GET /teacher/weak-knowledge-points
# ═══════════════════════════════════════════════════════


@router.get(
    "/weak-knowledge-points",
    response_model=ResponseBase,
    summary="获取全班共性薄弱知识点",
)
async def get_weak_kps(
    top_n: int = Query(default=5, alias="topN"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """聚合所有学生的薄弱知识点，按受影响人数降序"""
    _ensure_teacher(current_user)

    diag_result = await db.execute(
        select(CehuiRecord).where(
            CehuiRecord.student_id.in_(
                select(User.id).where(User.role == "student")
            )
        )
    )
    cehuis = diag_result.scalars().all()

    # 聚合薄弱知识点
    kp_agg: Dict[str, Dict[str, Any]] = {}
    for d in cehuis:
        weak_points = d.weak_points or []
        if isinstance(weak_points, list):
            for wp in weak_points:
                if isinstance(wp, dict):
                    kp_name = wp.get("knowledgePoint", wp.get("knowledge_point", ""))
                    mastery = wp.get("mastery", wp.get("currentMastery", 0.4))
                else:
                    kp_name = getattr(wp, "knowledge_point", getattr(wp, "knowledgePoint", ""))
                    mastery = getattr(wp, "mastery", getattr(wp, "currentMastery", 0.4))
                if not kp_name:
                    continue
                if kp_name not in kp_agg:
                    kp_agg[kp_name] = {"count": 0, "mastery_sum": 0.0}
                kp_agg[kp_name]["count"] += 1
                kp_agg[kp_name]["mastery_sum"] += float(mastery)

    items = sorted(
        [
            {
                "knowledgePoint": name,
                "studentCount": data["count"],
                "avgMastery": round(data["mastery_sum"] / data["count"], 2),
            }
            for name, data in kp_agg.items()
        ],
        key=lambda x: x["studentCount"],
        reverse=True,
    )[:top_n]

    return ResponseBase(data=items)


# ═══════════════════════════════════════════════════════
#  GET /teacher/mastery-trend
# ═══════════════════════════════════════════════════════


@router.get(
    "/mastery-trend",
    response_model=ResponseBase,
    summary="获取全班掌握度变化趋势",
)
async def get_mastery_trend(
    days: int = Query(default=30),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回每日平均掌握度与测绘人数"""
    _ensure_teacher(current_user)

    diag_result = await db.execute(
        select(CehuiRecord).where(
            CehuiRecord.student_id.in_(
                select(User.id).where(User.role == "student")
            )
        ).order_by(CehuiRecord.created_at.asc())
    )
    cehuis = diag_result.scalars().all()

    # 按日期聚合
    date_map: Dict[str, List[float]] = {}
    for d in cehuis:
        if not d.created_at:
            continue
        date_key = d.created_at.strftime("%Y-%m-%d")
        if date_key not in date_map:
            date_map[date_key] = []
        if d.overall_score is not None:
            date_map[date_key].append(d.overall_score)

    items = sorted(
        [
            {
                "date": date_key,
                "avgMastery": round(sum(vals) / len(vals) / 100, 2) if vals else 0,
                "cehuiCount": len(vals),
            }
            for date_key, vals in date_map.items()
        ],
        key=lambda x: x["date"],
    )[-days:]

    return ResponseBase(data=items)


# ═══════════════════════════════════════════════════════
#  GET /teacher/alerts
# ═══════════════════════════════════════════════════════


@router.get(
    "/alerts",
    response_model=ResponseBase,
    summary="获取预警学生列表",
)
async def get_alerts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回需要重点关注的学生（高认知负荷 / 低掌握度）"""
    _ensure_teacher(current_user)

    student_result = await db.execute(
        select(User).where(User.role == "student")
    )
    students = student_result.scalars().all()
    if not students:
        return ResponseBase(data=[])

    student_ids = [s.id for s in students]

    # 批量拉取每个学生的最新测绘（按 student_id 分组取每组 created_at 最大）
    diag_rows = (
        await db.execute(
            select(CehuiRecord)
            .where(CehuiRecord.student_id.in_(student_ids))
            .order_by(CehuiRecord.student_id, CehuiRecord.created_at.desc())
        )
    ).scalars().all()
    latest_diag: Dict[uuid.UUID, CehuiRecord] = {}
    for d in diag_rows:
        latest_diag.setdefault(d.student_id, d)

    alerts: List[Dict[str, Any]] = []
    for s in students:
        diag = latest_diag.get(s.id)
        if diag is None:
            continue

        cl = diag.cognitive_load or {}
        overall_load = (
            cl.get("overall", 0)
            if isinstance(cl, dict)
            else (cl.overall if hasattr(cl, "overall") else 0)
        )
        mastery = (diag.overall_score or 0) / 100

        if float(overall_load) > 0.7 or mastery < 0.4:
            reason = (
                "both" if (float(overall_load) > 0.7 and mastery < 0.4)
                else "highLoad" if float(overall_load) > 0.7
                else "lowMastery"
            )
            severity = "danger" if reason == "both" else "warning"
            alerts.append({
                "studentId": str(s.id),
                "name": s.username,
                "nickname": s.nickname or s.username,
                "avgMastery": round(mastery, 2),
                "cognitiveLoad": round(float(overall_load), 2),
                "reason": reason,
                "severity": severity,
            })

    return ResponseBase(data=alerts)


# ═══════════════════════════════════════════════════════
#  GET /teacher/students/{student_id}
# ═══════════════════════════════════════════════════════


@router.get(
    "/students/{student_id}",
    response_model=ResponseBase,
    summary="获取单个学生学情详情",
)
async def get_student_detail(
    student_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回单个学生的知识点掌握度、认知负荷、薄弱点等详情"""
    _ensure_teacher(current_user)

    student_result = await db.execute(
        select(User).where(User.id == uuid.UUID(student_id), User.role == "student")
    )
    student = student_result.scalar_one_or_none()
    if not student:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="学生不存在")

    diag_result = await db.execute(
        select(CehuiRecord)
        .where(CehuiRecord.student_id == student.id)
        .order_by(CehuiRecord.created_at.desc())
        .limit(1)
    )
    diag = diag_result.scalar_one_or_none()

    path_result = await db.execute(
        select(LearningPath)
        .where(LearningPath.student_id == student.id)
        .order_by(LearningPath.created_at.desc())
        .limit(1)
    )
    path = path_result.scalar_one_or_none()

    summary = _student_summary(student, diag, path)

    cl = diag.cognitive_load if diag else None
    if isinstance(cl, dict):
        cl_obj = {
            "memoryLoad": cl.get("memoryLoad", cl.get("memory_load", 0)),
            "attentionLoad": cl.get("attentionLoad", cl.get("attention_load", 0)),
            "processingLoad": cl.get("processingLoad", cl.get("processing_load", 0)),
            "overall": cl.get("overall", 0),
        }
    elif cl:
        cl_obj = {
            "memoryLoad": getattr(cl, "memoryLoad", getattr(cl, "memory_load", 0)),
            "attentionLoad": getattr(cl, "attentionLoad", getattr(cl, "attention_load", 0)),
            "processingLoad": getattr(cl, "processingLoad", getattr(cl, "processing_load", 0)),
            "overall": getattr(cl, "overall", 0),
        }
    else:
        cl_obj = {"memoryLoad": 0, "attentionLoad": 0, "processingLoad": 0, "overall": 0}

    weak_points = diag.weak_points if diag else []
    mastery_levels = []
    if isinstance(weak_points, list):
        for wp in weak_points:
            if isinstance(wp, dict):
                m = wp.get("mastery", wp.get("currentMastery", 0))
                mastery_levels.append({
                    "knowledgePoint": wp.get("knowledgePoint", wp.get("knowledge_point", "")),
                    "mastery": float(m) if m else 0.4,
                    "level": "weak" if float(m or 0) < 0.4 else "developing" if float(m or 0) < 0.6 else "proficient",
                    "confidence": wp.get("confidence", 0.7),
                })
            else:
                m = getattr(wp, "mastery", getattr(wp, "currentMastery", 0))
                mastery_levels.append({
                    "knowledgePoint": getattr(wp, "knowledgePoint", getattr(wp, "knowledge_point", "")),
                    "mastery": float(m) if m else 0.4,
                    "level": "weak" if float(m or 0) < 0.4 else "developing" if float(m or 0) < 0.6 else "proficient",
                    "confidence": getattr(wp, "confidence", 0.7),
                })

    weak_points_list = []
    if isinstance(weak_points, list):
        for wp in weak_points:
            if isinstance(wp, dict):
                weak_points_list.append({
                    "knowledgePoint": wp.get("knowledgePoint", wp.get("knowledge_point", "")),
                    "reason": wp.get("reason", ""),
                    "severity": wp.get("severity", "moderate"),
                    "suggestedRemediation": wp.get("suggestedRemediation", wp.get("suggested_remediation", "")),
                })
            else:
                weak_points_list.append({
                    "knowledgePoint": getattr(wp, "knowledgePoint", getattr(wp, "knowledge_point", "")),
                    "reason": getattr(wp, "reason", ""),
                    "severity": getattr(wp, "severity", "moderate"),
                    "suggestedRemediation": getattr(wp, "suggestedRemediation", getattr(wp, "suggested_remediation", "")),
                })

    return ResponseBase(data={
        "summary": summary,
        "overallScore": diag.overall_score if diag else 0,
        "subject": diag.subject if diag else "—",
        "masteryLevels": mastery_levels,
        "cognitiveLoad": cl_obj,
        "weakPoints": weak_points_list,
    })


# ═══════════════════════════════════════════════════════
#  GET /teacher/dashboard  (聚合接口)
# ═══════════════════════════════════════════════════════


@router.get(
    "/dashboard",
    response_model=ResponseBase,
    summary="获取教师仪表盘聚合数据",
)
async def get_dashboard_data(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """一次性返回所有仪表盘所需数据（聚合 overview / students / weakKps / masteryTrend / alerts）"""
    _ensure_teacher(current_user)

    # 按教师隔离的短 TTL 缓存；命中失败静默降级为直查。
    cache_key = f"cache:teacher-dashboard:{current_user.id}"
    try:
        cached = await cache_get(cache_key)
        if cached is not None:
            return ResponseBase(data=cached)
    except Exception:  # noqa: BLE001
        pass

    # ── 1. 学生基础查询 ──
    student_result = await db.execute(
        select(User).where(User.role == "student")
    )
    students = student_result.scalars().all()
    student_ids = [s.id for s in students]

    if not students:
        return ResponseBase(data={
            "overview": {"totalStudents": 0, "avgMastery": 0, "avgCognitiveLoad": 0,
                         "avgPathCompletion": 0, "highLoadCount": 0, "lowMasteryCount": 0},
            "students": [], "weakKps": [], "masteryTrend": [], "alerts": [],
        })

    # ── 2. 批量获取测绘和路径 ──
    all_diag_result = await db.execute(
        select(CehuiRecord)
        .where(CehuiRecord.student_id.in_(student_ids))
        .order_by(CehuiRecord.created_at.desc())
    )
    all_diags = all_diag_result.scalars().all()

    all_path_result = await db.execute(
        select(LearningPath)
        .where(LearningPath.student_id.in_(student_ids))
        .order_by(LearningPath.created_at.desc())
    )
    all_paths = all_path_result.scalars().all()

    # 每个学生取最新一条测绘和路径
    student_diag: Dict[uuid.UUID, CehuiRecord] = {}
    for d in all_diags:
        if d.student_id not in student_diag:
            student_diag[d.student_id] = d

    student_path: Dict[uuid.UUID, LearningPath] = {}
    for p in all_paths:
        if p.student_id not in student_path:
            student_path[p.student_id] = p

    # ── 3. 聚合 overview 指标 ──
    scores = [d.overall_score for d in student_diag.values() if d.overall_score is not None]
    loads: List[float] = []
    for d in student_diag.values():
        cl = d.cognitive_load or {}
        if isinstance(cl, dict):
            ov = cl.get("overall", 0)
        elif hasattr(cl, "overall"):
            ov = cl.overall
        else:
            ov = 0
        loads.append(float(ov))

    completions = [
        (p.path_data or {}).get("completionPercent", 0) for p in student_path.values()
    ]

    overview = {
        "totalStudents": len(students),
        "avgMastery": round(sum(scores) / len(scores) / 100, 2) if scores else 0.0,
        "avgCognitiveLoad": round(sum(loads) / len(loads), 2) if loads else 0.0,
        "avgPathCompletion": round(sum(completions) / len(completions), 1) if completions else 0,
        "highLoadCount": sum(1 for v in loads if v > 0.7),
        "lowMasteryCount": sum(1 for v in scores if v < 60),
    }

    # ── 4. 学生列表 ──
    student_items = []
    for s in students:
        diag = student_diag.get(s.id)
        path = student_path.get(s.id)
        student_items.append(_student_summary(s, diag, path))

    # ── 5. 薄弱知识点聚合 ──
    kp_agg: Dict[str, Dict[str, Any]] = {}
    for d in student_diag.values():
        weak_points = d.weak_points or []
        if isinstance(weak_points, list):
            for wp in weak_points:
                if isinstance(wp, dict):
                    kp_name = wp.get("knowledgePoint", wp.get("knowledge_point", ""))
                    mastery = wp.get("mastery", wp.get("currentMastery", 0.4))
                else:
                    kp_name = getattr(wp, "knowledge_point", getattr(wp, "knowledgePoint", ""))
                    mastery = getattr(wp, "mastery", getattr(wp, "currentMastery", 0.4))
                if not kp_name:
                    continue
                if kp_name not in kp_agg:
                    kp_agg[kp_name] = {"count": 0, "mastery_sum": 0.0}
                kp_agg[kp_name]["count"] += 1
                kp_agg[kp_name]["mastery_sum"] += float(mastery)

    weak_kps = sorted(
        [
            {"knowledgePoint": n, "studentCount": d["count"],
             "avgMastery": round(d["mastery_sum"] / d["count"], 2)}
            for n, d in kp_agg.items()
        ],
        key=lambda x: x["studentCount"], reverse=True,
    )[:5]

    # ── 6. 掌握度趋势 (按日期聚合) ──
    date_map: Dict[str, List[float]] = {}
    for d in all_diags:
        if not d.created_at:
            continue
        date_key = d.created_at.strftime("%Y-%m-%d")
        date_map.setdefault(date_key, []).append(d.overall_score or 0)

    mastery_trend = sorted(
        [
            {"date": k, "avgMastery": round(sum(v) / len(v) / 100, 2) if v else 0,
             "cehuiCount": len(v)}
            for k, v in date_map.items()
        ],
        key=lambda x: x["date"],
    )[-30:]

    # ── 7. 预警列表 ──
    alerts: List[Dict[str, Any]] = []
    for s in students:
        diag = student_diag.get(s.id)
        if not diag:
            continue
        cl = diag.cognitive_load or {}
        overall_load = (
            cl.get("overall", 0) if isinstance(cl, dict)
            else (cl.overall if hasattr(cl, "overall") else 0)
        )
        mastery = (diag.overall_score or 0) / 100
        if float(overall_load) > 0.7 or mastery < 0.4:
            reason = (
                "both" if (float(overall_load) > 0.7 and mastery < 0.4)
                else "highLoad" if float(overall_load) > 0.7
                else "lowMastery"
            )
            alerts.append({
                "studentId": str(s.id), "name": s.username,
                "nickname": s.nickname or s.username,
                "avgMastery": round(mastery, 2),
                "cognitiveLoad": round(float(overall_load), 2),
                "reason": reason,
                "severity": "danger" if reason == "both" else "warning",
            })

    dashboard_data = {
        "overview": overview,
        "students": student_items,
        "weakKps": weak_kps,
        "masteryTrend": mastery_trend,
        "alerts": alerts,
    }

    try:
        await cache_set(cache_key, dashboard_data, ttl=_TEACHER_DASHBOARD_TTL)
    except Exception:  # noqa: BLE001
        pass

    return ResponseBase(data=dashboard_data)
