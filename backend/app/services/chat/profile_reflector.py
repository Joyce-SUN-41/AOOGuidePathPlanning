"""问答画像回流与反思判定服务（建议 9 / 建议 10）

建议 9 反思框:
  - reflect(): 针对可复制素材，调用 Agent 判定学生是否真读懂，返回对错反馈与追问。

建议 10 问答画像回流驱动重规划:
  - summarize_profile(): 会话结束时，从对话提取结构化掌握度增量，写入
    StudentCognitiveProfile.mastery_deltas（仅增量，不碰 StudentKnowledge），
    落 CognitiveProfileEvent(type=chat_reflection)。显著时触发 trigger_replan。
  - trigger_replan(): 融合 = 测绘基线 + 问答增量，调用 AOO 重规划生成待采纳新版本，
    复用 _persist_results 的 plan_type=update_vN 版本机制。

设计红线（数据真实性）:
  - 绝不回写 StudentKnowledge（客观掌握度）；回流只写 mastery_deltas（相对增量）。
  - 仅授权会话才执行提炼与重规划。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.cognitive_profile import (
    CognitiveProfileEvent,
    StudentCognitiveProfile,
)
from app.models.learning_path import LearningPath
from app.models.student_knowledge import StudentKnowledge
from app.services.agent import get_agent_service
from app.services.agent.session_manager import get_session_manager
from app.tasks.aoo_optimization import run_aoo_optimization_sync

logger = logging.getLogger(__name__)

# 显著度阈值: |sum(delta_mastery)| 超过该值才触发重规划
SIGNIFICANCE_THRESHOLD = 0.3
# delta 上下限（与 schema 约束一致）
DELTA_MIN, DELTA_MAX = -0.2, 0.2

# 反思判定指令（建议 9）
REFLECT_INSTRUCTION_TMPL = """以下是学生刚收到的学习素材：
--- 素材开始 ---
{material}
--- 素材结束 ---

学生提问：{question}

请判断学生是否真正读懂了这段素材。要求：
1. 给出结论 understood（true=读懂 / false=未读懂，仅基于学生提问判断，不轻信）；
2. 给一句对错反馈 feedback（指出其理解偏差在哪，但**不要直接把答案改好**，只点明方向）；
3. 给一句追问 follow_up，引导学生自己补全理解。

严格只输出如下 JSON，不要输出任何额外文字：
{{"understood": <bool>, "feedback": "<str>", "follow_up": "<str>"}}"""


def _safe_json_load(text: str) -> Optional[Dict[str, Any]]:
    """从模型输出中稳妥提取 JSON（容错：去代码块、找首个大括号）。"""
    if not text:
        return None
    cleaned = text.strip()
    # 去除 ```json ... ``` 包裹
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    # 退而求其次：截取首个 { 到最后一个 }
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


def _clamp_delta(value: float) -> float:
    return max(DELTA_MIN, min(DELTA_MAX, value))


# ============================================================
# 建议 9 — 反思判定
# ============================================================


async def reflect(
    session_id: str,
    question: str,
    material: str,
) -> Tuple[bool, str, str]:
    """调用 Agent 判定学生是否读懂素材。

    Returns:
        (understood, feedback, follow_up)
    解析失败时返回 (False, 兜底反馈, "")
    """
    instruction = REFLECT_INSTRUCTION_TMPL.format(
        material=material[:8000], question=question[:2000]
    )
    service = get_agent_service()
    try:
        result = await service.chat(
            session_id=session_id,
            message=instruction,
            user_id="reflect-gate",
        )
    except Exception as exc:
        logger.error("反思判定调用 Agent 失败: %s", exc)
        return False, "未能识别你的理解，请换种方式再问一次。", ""

    content = result.get("content", "") if isinstance(result, dict) else ""
    parsed = _safe_json_load(content)
    if not parsed:
        logger.warning("反思判定 JSON 解析失败, 原文: %s", content[:300])
        return False, "没能识别你的理解，请换种方式再问一次。", ""

    understood = bool(parsed.get("understood", False))
    feedback = str(parsed.get("feedback", "")).strip()
    follow_up = str(parsed.get("follow_up", "")).strip()
    return understood, feedback, follow_up


# ============================================================
# 建议 10 — 问答画像提炼 + 重规划
# ============================================================


SUMMARIZE_INSTRUCTION = """请从下面的师生对话中，识别学生在哪些知识点上的掌握度发生了变化（变好或变差）。
只基于对话中**明确暴露**的信号判断，严禁编造。

输出严格 JSON（不要额外文字）：
{
  "deltas": [{"kp_id": "<知识点ID字符串>", "delta_mastery": <float, -0.2~0.2>}],
  "new_weak_points": ["<新识别的薄弱知识点ID>"],
  "confidence": <float, 0~1>
}
若无法判断任何变化，返回空列表与 confidence=0。"""


async def _extract_profile_from_dialog(
    session_id: str,
) -> Tuple[List[Dict[str, float]], List[str], float]:
    """调用 Agent 从对话历史提取结构化画像。返回 (deltas, weak_points, confidence)。"""
    session_mgr = get_session_manager()
    history = await session_mgr.get_history(session_id, limit=200)
    if not history:
        return [], [], 0.0

    dialog_text = "\n".join(
        f"{m.get('role', 'user')}: {m.get('content', '')}" for m in history
    )
    instruction = (
        SUMMARIZE_INSTRUCTION
        + "\n\n--- 对话开始 ---\n"
        + dialog_text[:12000]
        + "\n--- 对话结束 ---"
    )
    service = get_agent_service()
    try:
        result = await service.chat(
            session_id=session_id,
            message=instruction,
            user_id="profile-reflector",
        )
    except Exception as exc:
        logger.error("画像提炼调用 Agent 失败: %s", exc)
        return [], [], 0.0

    content = result.get("content", "") if isinstance(result, dict) else ""
    parsed = _safe_json_load(content)
    if not parsed:
        logger.warning("画像提炼 JSON 解析失败, 原文: %s", content[:300])
        return [], [], 0.0

    raw_deltas = parsed.get("deltas", []) or []
    deltas: List[Dict[str, float]] = []
    for d in raw_deltas:
        kp_id = str(d.get("kp_id", "")).strip()
        try:
            delta = _clamp_delta(float(d.get("delta_mastery", 0.0)))
        except (TypeError, ValueError):
            continue
        if kp_id and abs(delta) > 1e-6:
            deltas.append({"kp_id": kp_id, "delta_mastery": delta})

    weak = [str(x).strip() for x in (parsed.get("new_weak_points", []) or []) if str(x).strip()]
    try:
        confidence = max(0.0, min(1.0, float(parsed.get("confidence", 0.0))))
    except (TypeError, ValueError):
        confidence = 0.0
    return deltas, weak, confidence


async def _write_mastery_deltas(
    db: AsyncSession,
    student_id,
    deltas: List[Dict[str, float]],
    confidence: float,
    new_weak: List[str],
) -> None:
    """写 StudentCognitiveProfile.mastery_deltas（仅增量，不碰 StudentKnowledge）。"""
    if not deltas:
        return
    now_iso = datetime.now(timezone.utc).isoformat()
    profile = (
        await db.scalar(
            select(StudentCognitiveProfile).where(
                StudentCognitiveProfile.student_id == student_id
            )
        )
    )
    if profile is None:
        profile = StudentCognitiveProfile(student_id=student_id, mastery_deltas={})
        db.add(profile)
        await db.flush()

    stored = dict(profile.mastery_deltas or {})
    for d in deltas:
        kp_id = d["kp_id"]
        delta = d["delta_mastery"]
        prev = stored.get(kp_id, {"delta": 0.0, "confidence": 0.0, "n": 0})
        # 覆盖写（按 kp_id 取最新一次会话提炼，避免重复累加）
        stored[kp_id] = {
            "delta": round(float(prev.get("delta", 0.0)) + delta, 4),
            "confidence": round(max(float(prev.get("confidence", 0.0)), confidence), 4),
            "n": int(prev.get("n", 0)) + 1,
            "last_at": now_iso,
        }
    profile.mastery_deltas = stored
    profile.chat_signal_count = (profile.chat_signal_count or 0) + len(deltas)
    profile.last_chat_at = datetime.now(timezone.utc)
    db.add(profile)

    # 可观测事件
    db.add(
        CognitiveProfileEvent(
            student_id=student_id,
            event_type="chat_reflection",
            payload={
                "deltas": deltas,
                "new_weak_points": new_weak,
                "confidence": confidence,
            },
            reasoning=(
                f"会话提炼：识别出 {len(deltas)} 个知识点掌握度变化，"
                f"置信度 {confidence:.2f}"
            ),
        )
    )


async def _sync_chat_mastery_profile(
    db: AsyncSession,
    student_id,
) -> None:
    """将「测绘基线 + 已落库 mastery_deltas」融合结果同步写入 ChatMasteryProfile。

    对话画像抽屉（/rag/chat-profile → adapter.get_chat_profile）读取的是
    ChatMasteryProfile.mastery（绝对掌握度视图）。而 summarize_profile 原本只写
    StudentCognitiveProfile.mastery_deltas（相对增量），导致两者脱节、抽屉永远为空。

    此处补齐：用与重规划相同的「基线 + 增量」融合结果回填 ChatMasteryProfile，
    使「对话画像」抽屉能真实展示由问答提炼出的掌握特点。
    """
    from app.models.cognitive_profile import ChatMasteryProfile as _CMP

    corrected = await _build_corrected_mastery(db, student_id, [])
    if not corrected:
        return

    profile = (
        await db.scalar(
            select(_CMP).where(_CMP.student_id == student_id)
        )
    )
    if profile is None:
        profile = _CMP(student_id=student_id, mastery={})
        db.add(profile)
        await db.flush()

    now_iso = datetime.now(timezone.utc).isoformat()
    mastery_view = dict(profile.mastery or {})
    for kp_id, level in corrected.items():
        prev = mastery_view.get(kp_id) or {}
        # 置信度随融合次数累积提升（封顶 0.95，保留不确定性）
        new_n = int(prev.get("n", 0)) + 1
        new_conf = round(min(0.95, max(float(prev.get("confidence", 0.5)), 0.5 + 0.15 * new_n)), 4)
        mastery_view[kp_id] = {
            "level": round(float(level), 4),
            "confidence": new_conf,
            "n": new_n,
            "last_at": now_iso,
            "source": "chat",
        }
    profile.mastery = mastery_view
    profile.chat_signal_count = (profile.chat_signal_count or 0) + 1
    profile.last_chat_at = datetime.now(timezone.utc)
    profile.updated_at = datetime.now(timezone.utc)
    db.add(profile)


async def _build_corrected_mastery(
    db: AsyncSession,
    student_id,
    deltas: List[Dict[str, float]],
) -> Dict[str, float]:
    """融合 = 测绘基线(StudentKnowledge) + 问答增量(mastery_deltas)，clamp 到 [0,1]。"""
    baseline_rows = (
        await db.scalars(
            select(StudentKnowledge).where(StudentKnowledge.student_id == student_id)
        )
    ).all()
    baseline = {str(r.kp_id): float(r.mastery_level) for r in baseline_rows}

    # 取已落库的 mastery_deltas（含本次刚写的）
    profile = (
        await db.scalar(
            select(StudentCognitiveProfile).where(
                StudentCognitiveProfile.student_id == student_id
            )
        )
    )
    stored_deltas = profile.mastery_deltas if profile else {}

    corrected: Dict[str, float] = {}
    all_kp = set(baseline) | set(stored_deltas)
    for kp in all_kp:
        base = baseline.get(kp, 0.0)
        delta = float((stored_deltas.get(kp) or {}).get("delta", 0.0))
        corrected[kp] = max(0.0, min(1.0, base + delta))
    return corrected


async def trigger_replan(
    db: AsyncSession,
    student_id,
) -> Tuple[bool, Optional[int]]:
    """融合画像后触发 AOO 重规划，生成待采纳新版本（plan_type=update_vN）。

    Returns:
        (replanned, new_version)
    """
    corrected = await _build_corrected_mastery(db, student_id, [])
    if not corrected:
        return False, None

    # 当前生效路径作父版本
    active = (
        await db.scalar(
            select(LearningPath)
            .where(
                LearningPath.student_id == student_id,
                LearningPath.is_active.is_(True),
            )
            .order_by(LearningPath.version.desc())
        )
    )
    parent_path_id = str(active.id) if active else None
    diagnosis_id = str(active.diagnosis_id) if (active and active.diagnosis_id) else str(student_id)

    # 复用同步执行函数（后台线程 + Redis 进度，前端可轮询）。
    # 该函数在内部线程执行 AOO，此处用 to_thread 避免阻塞事件循环。
    task_id = await asyncio.to_thread(
        run_aoo_optimization_sync,
        diagnosis_id=diagnosis_id,
        student_id=str(student_id),
        mastery_levels=corrected,
        cognitive_load=0.5,
        config=None,
        auto_adopt=False,
    )
    logger.info(
        "问答回流重规划已调度: student=%s parent=%s task=%s",
        student_id, parent_path_id, task_id,
    )
    # 新版本号由 _persist_results 计算；此处无法直接拿，返回 None 由调用方按需查库
    return True, None


async def summarize_profile(
    db: AsyncSession,
    session_id: str,
    user_id: str,
    authorized: bool = True,
) -> Dict[str, Any]:
    """会话结束提炼画像（建议 10 主入口）。

    仅授权时执行；显著时触发重规划（待采纳）。
    """
    result: Dict[str, Any] = {
        "deltas": [],
        "new_weak_points": [],
        "confidence": 0.0,
        "significant": False,
        "replanned": False,
        "new_version": None,
    }
    if not authorized:
        logger.info("会话未授权计入画像, 跳过提炼: session=%s", session_id)
        return result

    try:
        student_uuid = __import__("uuid").UUID(user_id)
    except (ValueError, AttributeError):
        student_uuid = None
    if student_uuid is None:
        logger.warning("无效 user_id, 跳过提炼: %s", user_id)
        return result

    deltas, weak, confidence = await _extract_profile_from_dialog(session_id)
    result["deltas"] = deltas
    result["new_weak_points"] = weak
    result["confidence"] = confidence

    total_abs = sum(abs(d["delta_mastery"]) for d in deltas)
    significant = total_abs > SIGNIFICANCE_THRESHOLD
    result["significant"] = significant

    if deltas:
        await _write_mastery_deltas(db, student_uuid, deltas, confidence, weak)
        # 同步绝对视图到 ChatMasteryProfile，使「对话画像」抽屉可见
        await _sync_chat_mastery_profile(db, student_uuid)
        await db.commit()

    if significant:
        replanned, new_version = await trigger_replan(db, student_uuid)
        result["replanned"] = replanned
        result["new_version"] = new_version
        if replanned:
            await db.commit()

    return result
