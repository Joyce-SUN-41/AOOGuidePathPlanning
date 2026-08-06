"""学情看板 API — 认知负荷趋势 / 学习日历 / AI 建议 / 概览"""

import asyncio
from datetime import date, datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.cache import cache_get, cache_set
from app.core.database import get_db
from app.models.cehui import CehuiRecord
from app.models.knowledge_point import KnowledgePoint
from app.models.learning_path import LearningPath
from app.models.user import User
from app.schemas.common import ResponseBase

router = APIRouter()

# 聚合统计缓存 TTL（秒）
_PLATFORM_STATS_TTL = 60
_OVERVIEW_TTL = 30


# ═══════════ GET /dashboard/platform-stats （公开） ════════


@router.get(
    "/platform-stats",
    response_model=ResponseBase,
    summary="平台公开统计数据（无需登录）",
)
async def get_platform_stats(db: AsyncSession = Depends(get_db)):
    """
    首页展示用的平台级聚合统计，均为数据库真实计数：
    - studentCount   注册用户数
    - pathCount      已生成学习路径数
    - knowledgePointCount 覆盖知识点数
    - cehuiCount 累计测绘次数

    该接口不返回任何用户隐私信息，仅为聚合计数，故不做鉴权。
    任一统计项查询失败时降级为 0，保证首页始终可渲染。
    """
    # 公开计数变化缓慢，加短 TTL 缓存降低数据库压力；命中失败则直查降级。
    cache_key = "cache:platform-stats"
    try:
        cached = await cache_get(cache_key)
        if cached is not None:
            return ResponseBase(data=cached)
    except Exception:  # noqa: BLE001
        pass

    async def _count(model) -> int:
        try:
            result = await db.execute(select(func.count()).select_from(model))
            return int(result.scalar() or 0)
        except Exception:  # noqa: BLE001 — 统计失败不应阻塞首页
            return 0

    data = {
        "studentCount": await _count(User),
        "pathCount": await _count(LearningPath),
        "knowledgePointCount": await _count(KnowledgePoint),
        "cehuiCount": await _count(CehuiRecord),
    }

    try:
        await cache_set(cache_key, data, ttl=_PLATFORM_STATS_TTL)
    except Exception:  # noqa: BLE001
        pass

    return ResponseBase(data=data)


# ═══════════ GET /dashboard/cognitive-load-trend ══════════


@router.get(
    "/cognitive-load-trend",
    response_model=ResponseBase,
    summary="认知负荷历史趋势",
)
async def get_cognitive_load_trend(
    limit: int = Query(default=10, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取最近 N 次测绘的认知负荷数据"""
    result = await db.execute(
        select(CehuiRecord)
        .where(CehuiRecord.student_id == current_user.id)
        .order_by(desc(CehuiRecord.created_at))
        .limit(limit)
    )
    records = result.scalars().all()
    records = list(records)[::-1]  # 按时间升序

    trend: List[dict] = []
    for r in records:
        cl = r.cognitive_load or {}
        trend.append({
            "date": r.created_at.strftime("%Y-%m-%d") if r.created_at else "",
            "diagnosisId": str(r.id),
            "overall": cl.get("overall", 0),
            "memoryLoad": cl.get("memory_load", 0),
            "attentionLoad": cl.get("attention_load", 0),
            "processingLoad": cl.get("processing_load", 0),
            "overallScore": r.overall_score,
        })

    return ResponseBase(data=trend)


# ═══════════ GET /dashboard/calendar-activity ═════════════


@router.get(
    "/calendar-activity",
    response_model=ResponseBase,
    summary="学习日历活动",
)
async def get_calendar_activity(
    year: int = Query(ge=2020, le=2099),
    month: int = Query(ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取指定月份的每日学习活动数据"""
    # 从学习路径中提取任务时间分布作为近似学习活动
    result = await db.execute(
        select(LearningPath)
        .where(LearningPath.student_id == current_user.id)
        .order_by(desc(LearningPath.created_at))
        .limit(5)
    )
    paths = result.scalars().all()

    activity: List[dict] = []
    seen_dates = set()

    for path in paths:
        data = path.path_data or {}
        daily_tasks = data.get("dailyTasks", [])
        if not daily_tasks:
            continue

        created = path.created_at
        for day_idx, tasks in enumerate(daily_tasks):
            if not isinstance(tasks, list):
                continue
            day_date = created
            from datetime import timedelta
            day_date = created + timedelta(days=day_idx)

            if day_date.year != year or day_date.month != month:
                continue

            date_str = day_date.strftime("%Y-%m-%d")
            if date_str in seen_dates:
                continue
            seen_dates.add(date_str)

            kps = set()
            for t in tasks:
                if isinstance(t, dict):
                    kp = t.get("knowledgePoint", "")
                    if kp:
                        kps.add(kp)

            total_min = sum(
                t.get("estimatedMinutes", 0) for t in tasks if isinstance(t, dict)
            )

            activity.append({
                "date": date_str,
                "studyMinutes": total_min,
                "taskCount": len(tasks),
                "knowledgePoints": list(kps)[:3],
            })

    return ResponseBase(data=activity)


# ═══════════ GET /dashboard/suggestions ══════════════════


@router.get(
    "/suggestions",
    response_model=ResponseBase,
    summary="AI 学习建议",
)
async def get_suggestions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """基于最新测绘结果生成学习建议（简化版）"""
    result = await db.execute(
        select(CehuiRecord)
        .where(CehuiRecord.student_id == current_user.id)
        .order_by(desc(CehuiRecord.created_at))
        .limit(1)
    )
    record = result.scalar_one_or_none()

    if not record:
        return ResponseBase(code=200, message="暂无测绘数据", data=[])

    cl = record.cognitive_load or {}
    overall = cl.get("overall", 0)
    weak_points = record.weak_points or []

    suggestions: List[dict] = []

    # 薄弱点建议
    if isinstance(weak_points, list) and len(weak_points) > 0:
        first_kp = weak_points[0].get("knowledge_point", "") if isinstance(weak_points[0], dict) else ""
        suggestions.append({
            "category": "weakness",
            "title": "重点关注薄弱环节",
            "content": f"检测到 {len(weak_points)} 个薄弱知识点。建议优先从掌握度最低的内容入手，每天安排 30 分钟专项练习。",
            "priority": 1,
            "relatedKPs": [
                wp.get("knowledge_point", "")
                for wp in weak_points[:3]
                if isinstance(wp, dict)
            ],
        })

    # 认知负荷建议
    if overall > 0.6:
        suggestions.append({
            "category": "warning",
            "title": "认知负荷偏高",
            "content": "当前认知负荷指数处于较高水平，建议增加复习间隔，避免连续学习高难度内容。",
            "priority": 2,
        })

    # 通用建议
    suggestions.append({
        "category": "tip",
        "title": "交替学习法",
        "content": "研究表明交替学习不同知识点的效果优于集中学习单一内容。建议每天安排 2-3 个不同知识点的任务轮流进行。",
        "priority": 3,
    })

    suggestions.append({
        "category": "tip",
        "title": "定期复习策略",
        "content": "遵循艾宾浩斯遗忘曲线，学习后 1 天、2 天、4 天、7 天、15 天进行间隔复习。",
        "priority": 5,
    })

    suggestions.append({
        "category": "strength",
        "title": "保持优势领域",
        "content": f"当前综合评分 {record.overall_score:.0f} 分，继续按照学习路径稳步推进即可。",
        "priority": 4,
    })

    return ResponseBase(data=suggestions)


# ═══════════ GET /dashboard/overview ═════════════════════


@router.get(
    "/overview",
    response_model=ResponseBase,
    summary="看板概览数据",
)
async def get_overview(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取学情看板概览指标"""
    # 按用户隔离的短 TTL 缓存；命中失败静默降级为直查。
    try:
        cached = await cache_get(f"cache:overview:{current_user.id}")
        if cached is not None:
            return ResponseBase(data=cached)
    except Exception:  # noqa: BLE001
        pass

    # 并发拉取多个相互独立的聚合查询（最新测绘 / 最新路径 / 测绘数 / 路径数 / 全部测绘日期）
    async def _latest_diag() -> Optional[CehuiRecord]:
        r = await db.execute(
            select(CehuiRecord)
            .where(CehuiRecord.student_id == current_user.id)
            .order_by(desc(CehuiRecord.created_at))
            .limit(1)
        )
        return r.scalar_one_or_none()

    async def _latest_path() -> Optional[LearningPath]:
        r = await db.execute(
            select(LearningPath)
            .where(LearningPath.student_id == current_user.id)
            .order_by(desc(LearningPath.created_at))
            .limit(1)
        )
        return r.scalar_one_or_none()

    async def _diag_count() -> int:
        r = await db.execute(
            select(func.count(CehuiRecord.id)).where(
                CehuiRecord.student_id == current_user.id
            )
        )
        return int(r.scalar() or 0)

    async def _path_count() -> int:
        r = await db.execute(
            select(func.count(LearningPath.id)).where(
                LearningPath.student_id == current_user.id
            )
        )
        return int(r.scalar() or 0)

    async def _all_diag_dates() -> set:
        r = await db.execute(
            select(CehuiRecord.created_at)
            .where(CehuiRecord.student_id == current_user.id)
            .order_by(desc(CehuiRecord.created_at))
        )
        dates: set = set()
        for (created_at,) in r:
            if created_at:
                dates.add(created_at.date())
        return dates

    diag, path, total_cehuis, total_paths, diag_dates_set = await asyncio.gather(
        _latest_diag(),
        _latest_path(),
        _diag_count(),
        _path_count(),
        _all_diag_dates(),
    )

    # 计算总学习时长
    total_study_minutes = 0
    completed_tasks = 0
    total_tasks = 0
    mastered_kps = 0
    total_kps = 0

    if path:
        path_data = path.path_data or {}
        total_tasks = path_data.get("totalTasks", 0)
        total_estimated_hours = path_data.get("totalEstimatedHours", 0)
        # 从 path_data 获取真实完成数量，而非硬编码百分比
        completed_tasks = path_data.get("completedTasks", 0)
        percent = completed_tasks / total_tasks if total_tasks > 0 else 0
        total_study_minutes = int(total_estimated_hours * 60 * percent)

    if diag:
        mastery = diag.mastery_levels or {}
        total_kps = len(mastery)
        mastered_kps = sum(
            1 for v in (mastery.values() if isinstance(mastery, dict) else [])
            if isinstance(v, dict) and v.get("mastery", 0) >= 0.6
        )
        if path is None:
            total_study_minutes = int(diag.average_time_spent * diag.total_questions)

    streak = 0
    today = date.today()
    check_date = today
    while check_date in diag_dates_set:
        streak += 1
        check_date -= timedelta(days=1)
    # 如果今天还没有，但从昨天就开始连续学习，也算连续
    if streak == 0 and today - timedelta(days=1) in diag_dates_set:
        check_date = today - timedelta(days=1)
        while check_date in diag_dates_set:
            streak += 1
            check_date -= timedelta(days=1)

    overview_data = {
        "totalStudyMinutes": total_study_minutes,
        "completedTasks": completed_tasks,
        "totalTasks": total_tasks,
        "masteredKPs": mastered_kps,
        "totalKPs": total_kps,
        "streakDays": streak,
        "totalCehuis": total_cehuis,
        "totalPaths": total_paths,
        "lastStudyDate": diag.created_at.strftime("%Y-%m-%d") if diag and diag.created_at else "",
    }

    # 按用户隔离的短 TTL 缓存，命中失败静默降级为直查。
    try:
        await cache_set(
            f"cache:overview:{current_user.id}",
            overview_data,
            ttl=_OVERVIEW_TTL,
        )
    except Exception:  # noqa: BLE001
        pass

    return ResponseBase(data=overview_data)
