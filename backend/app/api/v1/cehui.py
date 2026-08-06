"""测绘 API — 学情测绘测验 提交 / 获取题目 / 历史查询"""

import logging
import random
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.cehui import CehuiRecord
from app.models.user import User
from app.schemas.common import ResponseBase
from app.schemas.cehui import (
    CehuiBrief,
    CehuiHistoryResponse,
    CehuiQuestion,
    CehuiResultResponse,
    CehuiSubmitRequest,
    LearningReadinessRequest,
    QuestionsResponse,
    RawCehuiResult,
    ReadinessProfile,
)
from app.services.cehui import cehui_service

logger = logging.getLogger(__name__)

router = APIRouter()


# ── GET /questions — 获取测绘题目 ──────────────────────

@router.get(
    "/questions",
    response_model=ResponseBase[QuestionsResponse],
    summary="获取测绘题目",
)
async def get_questions(
    count: int = Query(default=30, ge=1, le=200, description="抽取题目数量"),
    subject: str = Query(default="人工智能导论", description="学科"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取测绘题库, 优先从数据库读取, 其次读取 data/question_bank.json（1000 题大库）, 最后降级到内置 Mock 数据。

    机制:
      - 分层分级均衡组卷（建议 2）: 按知识点分桶 + 难度阶 50/30/20 配额, 保证抽出的题目有层次、覆盖多知识点。
      - 若知识图谱可用, 则采用图谱驱动采样（更准、可 seed 薄弱子树）。
      - 每道题的选项顺序随机打乱 (选项 id 与 correct_option_id 保持不变, 判分不受影响)
    """
    # 1. 尝试从 DB 加载（seed 后的 1000 题）
    try:
        bank = await cehui_service.get_question_bank_from_db(db, subject=subject)
        from_db = bool(bank)
    except Exception:
        bank = []
        from_db = False

    # 2. DB 为空时, 直接读取 question_bank.json（1000 题大库）, 确保题库一定生效
    if not bank:
        try:
            bank = cehui_service.get_question_bank_from_json()
            from_db = False
        except Exception as exc:
            logger.warning("读取 question_bank.json 失败: %s", exc)
            bank = []

    # 3. 仍为空则降级到内置 Mock
    if not bank:
        bank = cehui_service.get_question_bank()
        from_db = False

    # 图谱驱动均衡抽题：仅当题目来自 DB 且知识图谱可用时启用（图层更准、可 seed 薄弱子树）
    sampled = None
    allocation = {}
    graph_driven = False
    if from_db:
        try:
            graph = await cehui_service.load_graph(db, subject=subject)
            if not graph.is_empty():
                from app.services.cehui.graph_cehui import (
                    sample_questions_by_graph,
                )
                sampled, allocation = sample_questions_by_graph(
                    graph=graph, bank=bank, total=count
                )
                graph_driven = True
        except Exception as exc:
            logger.warning("图谱抽题失败，回退均衡组卷: %s", exc)
            sampled = None

    # 分层分级均衡组卷（建议 2）：无图谱 / Mock 模式 / 图谱抽题失败时的降级
    # —— 取代原有 random.sample 粗放抽题
    if sampled is None:
        from app.services.cehui.paper_assembler import assemble_balanced_paper

        try:
            sampled, allocation = assemble_balanced_paper(bank=bank, total=count)
        except Exception as exc:
            logger.warning("均衡组卷失败，回退随机抽题: %s", exc)
            if count >= len(bank):
                sampled = list(bank)
            else:
                sampled = random.sample(bank, count)

    # 每道题选项顺序随机打乱 (保持 option.id 与 correct_option_id 不变, 判分安全)
    for q in sampled:
        options = q.get("options") or []
        if options:
            shuffled_options = options[:]
            random.shuffle(shuffled_options)
            q["options"] = shuffled_options

    question_schemas = [
        CehuiQuestion(
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
        for q in sampled
    ]

    # 基于抽中题目真实 expected_time_sec 求和预估耗时（随题量自适应, 取代固定均值）
    total_seconds = sum(float(q.get("expected_time_sec") or 20.0) for q in sampled)
    estimated_min = max(1, int(round(total_seconds / 60)))

    return ResponseBase(
        data=QuestionsResponse(
            questions=question_schemas,
            total=len(question_schemas),
            subject=subject,
            estimated_duration_min=estimated_min,
            allocation=allocation,
            graph_driven=graph_driven,
        )
    )


# ── POST /submit — 提交测绘答案 ────────────────────────

@router.post(
    "/submit",
    response_model=ResponseBase[CehuiResultResponse],
    summary="提交测绘测验结果",
)
async def submit_cehui(
    request: CehuiSubmitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """提交测绘答案, 计算掌握度和认知负荷, 持久化结果.

    同时自动触发异步 AOO 路径规划任务.
    """
    # 权限校验: student_id 必须与当前登录用户一致
    student_id = request.student_id or current_user.id
    if str(student_id) != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="不能替其他学生提交测绘",
        )

    # 1. 加载题库 (优先DB)
    try:
        bank = await cehui_service.get_question_bank_from_db(db, subject=request.subject)
        if not bank:
            bank = cehui_service.get_question_bank()
    except Exception:
        bank = cehui_service.get_question_bank()

    # 2. 执行测绘分析
    mastery_levels, cognitive_load, analyses, kp_map = cehui_service.cehui(
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

    # 2.1 沿知识图谱传播掌握度（前置薄弱则下游降权）；无图谱时原值透传
    try:
        graph = await cehui_service.load_graph(db, subject=request.subject)
        if not graph.is_empty():
            from app.services.cehui.graph_cehui import propagate_mastery
            mastery_levels = propagate_mastery(mastery_levels, graph)
            logger.info(
                "图谱掌握度传播已应用, 知识点数=%d", len(mastery_levels)
            )
    except Exception as exc:
        logger.warning("图谱掌握度传播失败，使用原始掌握度: %s", exc)

    # 3. 加载知识点名称映射
    kp_name_map = await cehui_service._load_kp_name_map(db)

    # 4. 持久化到数据库
    record = await cehui_service.persist_results(
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
        style_items=[item.dict() for item in request.style_items] if request.style_items else None,
    )

    # 4.1 第三维「学习准备度」落库（建议 3）；为空则二维模式，不影响其他字段
    readiness_profile: dict = {}
    if request.readiness is not None:
        r = request.readiness
        # 条目9: 学科特异性效能锚定 —— 取维度一薄弱知识点（mastery<0.6）作为锚点
        weak_kp_ids = [kp for kp, v in mastery_levels.items() if v < 0.6]
        # 条目8: 纵向趋势 —— 取该生上一次测绘的准备度作为 prior
        prior_readiness = None
        try:
            prior_rec = await db.scalar(
                select(CehuiRecord)
                .where(
                    CehuiRecord.student_id == student_id,
                    CehuiRecord.id != record.id,
                )
                .order_by(CehuiRecord.created_at.desc())
                .limit(1)
            )
            if prior_rec and prior_rec.readiness_profile:
                prior_readiness = prior_rec.readiness_profile
        except Exception as exc:
            logger.debug("读取上一次准备度失败（不影响本次）: %s", exc)
        rp = cehui_service.compute_readiness_profile(
            [item.dict() for item in r.raw_items] if r.raw_items else [],
            weak_kp_ids=weak_kp_ids or None,
            prior=prior_readiness,
        )
        readiness_profile = {
            "motivation": rp["motivation"],
            "metacognition": rp["metacognition"],
            "self_efficacy": rp["self_efficacy"],
            "efficacy_by_kp": rp.get("efficacy_by_kp"),
            "trend": rp.get("trend"),
        }
        if r.raw_items:
            readiness_profile["raw_items"] = [item.dict() for item in r.raw_items]
        record.readiness_profile = readiness_profile
        await db.commit()

    # 4.2 学习风格落库（建议 4）；style_items 为空则保持"未评估"，规划器关闭风格偏置
    style_label = record.learning_style or "未评估"
    style_scores = (record.learning_style_profile or {}).get("scores", {}) if record.learning_style_profile else {}

    # 5. 触发异步 AOO 路径规划 (Celery 优先, 同步兜底)
    diagnosis_id = str(record.id)
    student_id_str = str(student_id) if not isinstance(student_id, str) else student_id
    cognitive_load_overall = getattr(cognitive_load, "overall", 0.0)
    # 把第三维自变量 + 学习风格经 config 透传给 AOO（建议 3/4 共用 config 通道）
    aoo_config: dict = {}
    if readiness_profile:
        aoo_config["readiness"] = {
            "motivation": readiness_profile["motivation"],
            "metacognition": readiness_profile["metacognition"],
            "self_efficacy": readiness_profile["self_efficacy"],
        }
    if style_label and style_label != "未评估":
        aoo_config["learning_style"] = {
            "label": style_label,
            "scores": style_scores,
        }
    try:
        from app.tasks.cehui import trigger_aoo_path_planning
        trigger_aoo_path_planning.delay(
            diagnosis_id=diagnosis_id,
            student_id=student_id_str,
            mastery_levels=mastery_levels,
            cognitive_load=cognitive_load_overall,
            config=aoo_config or None,
        )
        logger.info(
            "AOO path planning triggered for diagnosis_id=%s, "
            "student=%s, kps=%d, load=%.2f, readiness=%s",
            diagnosis_id, student_id_str,
            len(mastery_levels), cognitive_load_overall,
            bool(aoo_config),
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
                config=aoo_config or None,
            )
            logger.info(
                "AOO sync path planning started: task_id=%s cehui=%s",
                sync_id, diagnosis_id,
            )
        except Exception as sync_exc:
            logger.error(
                "AOO 同步执行也失败, 平台将以无路径状态返回: %s", sync_exc
            )

    # 6. 构建完整响应
    result_response = cehui_service.build_response(record)

    return ResponseBase(
        message="测绘完成",
        data=result_response,
    )


# ── POST /readiness — 学习准备度自陈量表（建议 3 第三维）──

@router.post(
    "/readiness",
    response_model=ResponseBase[ReadinessProfile],
    summary="提交学习准备度自陈量表，产出第三维画像",
)
async def submit_readiness(
    request: LearningReadinessRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """轻量自陈量表（5-8 题 likert 1-5）聚合为学习准备度画像。

    产出 {motivation, metacognition, self_efficacy} 0-1。
    不强制绑定测绘：可独立填写，结果回写该生最新一条测绘记录（若无则新建占位记录），
    供后续 AOO 规划作为第三维自变量。
    """
    raw_items = [item.dict() for item in request.items]
    profile = cehui_service.compute_readiness_profile(raw_items)

    readiness_obj = ReadinessProfile(
        motivation=profile["motivation"],
        metacognition=profile["metacognition"],
        self_efficacy=profile["self_efficacy"],
        raw_items=request.items,
    )

    # 回写最新测绘记录（若存在）；否则新建一条仅含 readiness 的占位记录
    result = await db.execute(
        select(CehuiRecord)
        .where(CehuiRecord.student_id == current_user.id)
        .order_by(desc(CehuiRecord.created_at))
        .limit(1)
    )
    record = result.scalar_one_or_none()
    if record is not None:
        record.readiness_profile = {
            "motivation": profile["motivation"],
            "metacognition": profile["metacognition"],
            "self_efficacy": profile["self_efficacy"],
            "raw_items": raw_items,
        }
        await db.commit()
    else:
        placeholder = CehuiRecord(
            student_id=current_user.id,
            subject=request.subject,
            mastery_levels={},
            cognitive_load={},
            weak_points={},
            radar_data={},
            learning_style="未评估",
            readiness_profile={
                "motivation": profile["motivation"],
                "metacognition": profile["metacognition"],
                "self_efficacy": profile["self_efficacy"],
                "raw_items": raw_items,
            },
        )
        db.add(placeholder)
        await db.commit()

    return ResponseBase(
        message="学习准备度评估完成",
        data=readiness_obj,
    )


# ── GET /latest — 获取最新测绘结果 ──────────────────────

@router.get(
    "/latest",
    response_model=ResponseBase[Optional[CehuiResultResponse]],
    summary="获取最新测绘结果",
)
async def get_latest_cehui(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前学生的最新测绘结果；若从未测绘则返回 null(200)"""
    result = await db.execute(
        select(CehuiRecord)
        .where(CehuiRecord.student_id == current_user.id)
        .order_by(desc(CehuiRecord.created_at))
        .limit(1)
    )
    record = result.scalar_one_or_none()

    if not record:
        return ResponseBase[Optional[CehuiResultResponse]](data=None)

    return ResponseBase[Optional[CehuiResultResponse]](
        data=cehui_service.build_response(record)
    )


# ── GET /history — 获取测绘历史列表(兼容路径，必须放在 /{diagnosis_id} 之前) ─

@router.get(
    "/history",
    response_model=ResponseBase[CehuiHistoryResponse],
    summary="获取测绘历史列表(兼容路径)",
)
async def get_cehui_history_compat(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=10, ge=1, le=50, description="每页数量"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await get_cehui_history(page, page_size, db, current_user)


# ── GET /{diagnosis_id} — 获取测绘详情 ─────────────────

@router.get(
    "/{diagnosis_id}",
    response_model=ResponseBase[CehuiResultResponse],
    summary="获取指定测绘详情",
)
async def get_cehui_detail(
    diagnosis_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取指定 ID 的测绘详情"""
    try:
        uid = uuid.UUID(diagnosis_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无效的测绘 ID 格式",
        )

    result = await db.execute(
        select(CehuiRecord).where(CehuiRecord.id == uid)
    )
    record = result.scalar_one_or_none()

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="测绘记录不存在",
        )

    # 只能查看自己的测绘
    if str(record.student_id) != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权查看他人的测绘记录",
        )

    return ResponseBase(data=cehui_service.build_response(record))


# ── GET /history — 获取测绘历史 ────────────────────────

@router.get(
    "",
    response_model=ResponseBase[CehuiHistoryResponse],
    summary="获取测绘历史列表",
)
async def get_cehui_history(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=10, ge=1, le=50, description="每页数量"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前学生的测绘历史列表 (分页)"""
    # 总数
    count_result = await db.execute(
        select(func.count(CehuiRecord.id)).where(
            CehuiRecord.student_id == current_user.id
        )
    )
    total = count_result.scalar() or 0

    # 分页查询
    records_result = await db.execute(
        select(CehuiRecord)
        .where(CehuiRecord.student_id == current_user.id)
        .order_by(desc(CehuiRecord.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    records = records_result.scalars().all()

    items = [
        CehuiBrief(
            id=str(r.id),
            created_at=r.created_at.replace(tzinfo=None),
            subject=r.subject,
            overall_score=r.overall_score,
            weak_point_count=len(r.weak_points),
        )
        for r in records
    ]

    return ResponseBase(
        data=CehuiHistoryResponse(items=items, total=total)
    )


# ── DELETE /{diagnosis_id} — 删除测绘记录 ─────────────────

@router.delete(
    "/{diagnosis_id}",
    response_model=ResponseBase,
    summary="删除测绘记录",
)
async def delete_cehui(
    diagnosis_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除指定测绘记录 (仅本人)"""
    try:
        uid = uuid.UUID(diagnosis_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无效的测绘 ID 格式",
        )

    result = await db.execute(
        select(CehuiRecord).where(CehuiRecord.id == uid)
    )
    record = result.scalar_one_or_none()

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="测绘记录不存在",
        )

    if str(record.student_id) != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权删除他人的测绘记录",
        )

    await db.delete(record)
    await db.commit()

    return ResponseBase(message="测绘记录已删除")
