"""对话即诊断适配器 — LLM诊断JSON → AOO输入参数

将星火大模型在对话中隐式评估的知识点掌握度、认知负荷、学习意图
转换为 AOO 引擎所需的标准输入参数，并与历史诊断数据融合。
遵循"大模型只做认知感知与语义翻译、AOO专注数学寻优与约束求解"的松耦合边界。

P0 修复要点 (2026-08-02):
  1. **统一键空间为 kp_id (UUID)** — LLM 输出的 kp_name 经 KnowledgePointResolver
     对齐到 kp_id 后才参与融合。对齐失败的信号直接丢弃，绝不塞入下游，
     避免中文名污染 AOO 的 focus_areas。
  2. **置信度语义纠正** — 低置信不再表现为 `level * 0.35`（那是篡改数值），
     而是"向先验回归": M = w·L_llm + (1-w)·M_prior。
  3. **weak_count 基于真实融合值** — 修复因数值被缩小导致的薄弱点高估、
     can_optimize 恒为真。
  4. **类型标注纠正** — student_id 是 UUID 而非 int。
  5. **无基线兜底** — 首次使用（无诊断记录）时以 StudentKnowledge 答题记录为主，
     问答修正仅作微弱先验，不报错、不阻断。
"""

from __future__ import annotations

import logging
import uuid as uuid_mod
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.cognitive_profile import (
    ChatMasteryProfile,
    CognitiveProfileEvent,
    StudentCognitiveProfile,
)
from app.models.diagnosis import DiagnosisRecord
from app.models.knowledge_point import KnowledgePoint
from app.models.student_knowledge import StudentKnowledge
from app.services.diagnosis.kp_resolver import KnowledgePointResolver

logger = logging.getLogger(__name__)

# ⓵ λ 动态调优（P3）:
#    问答信号对融合后掌握度的影响强度由环境变量 CHAT_PROFILE_LAMBDA 控制，
#    客观基线权重自动取 1 - λ。改 env 即可秒级调整主观信号权重，无需改代码。
#    无任何客观基线时，信号相对先验的权重取 min(λ, 0.5)（更保守，避免无依据主导）。
# ⓶ CHAT_PROFILE_MAX_DELTA（P3）:
#    单知识点相对诊断基线的偏移上限 δ_max，超界截断，防止单次对话噪声把路径带偏。
# ⓷ CHAT_PROFILE_PRIOR（P3）:
#    无任何基线时向该先验回归（而非归零），保持数据真实性。

# 权重常量保留为「默认值」参考；实际权重在 fuse_mastery / 认知负荷融合中实时读取 λ。
_LLM_WEIGHT_DEFAULT = 0.35
_EXAM_WEIGHT_DEFAULT = 0.65
_LLM_WEIGHT_NO_BASELINE_DEFAULT = 0.5

# 薄弱知识点判定阈值（与 OptimizationService.focus_areas 的 0.6 区分开：
# 这里是"是否值得触发一次重规划"的门槛，更严格）
WEAK_THRESHOLD = 0.5


def _lambda() -> float:
    """读取问答影响强度系数 λ ∈ [0,1]，越界则夹断到安全范围"""
    try:
        lam = float(getattr(settings, "CHAT_PROFILE_LAMBDA", _LLM_WEIGHT_DEFAULT))
    except (TypeError, ValueError):
        lam = _LLM_WEIGHT_DEFAULT
    return max(0.0, min(1.0, lam))


def _max_delta() -> float:
    """读取单点最大偏移 δ_max"""
    try:
        val = float(getattr(settings, "CHAT_PROFILE_MAX_DELTA", 0.25))
    except (TypeError, ValueError):
        val = 0.25
    return max(0.0, min(1.0, val))


def _prior() -> float:
    """读取无基线时的回归先验掌握度"""
    try:
        val = float(getattr(settings, "CHAT_PROFILE_PRIOR", 0.5))
    except (TypeError, ValueError):
        val = 0.5
    return max(0.0, min(1.0, val))


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _now_iso() -> str:
    """当前 UTC 时间的 ISO 字符串（用于对话画像时间戳）"""
    return datetime.utcnow().isoformat()


def _is_uuid(value: str) -> bool:
    """判断字符串是否可解析为 UUID（用于决定 kp_id 列能否赋值）"""
    try:
        uuid_mod.UUID(str(value))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


class DiagnosisAdapter:
    """LLM 对话诊断 → AOO 优化参数 适配器

    职责:
    1. 解析 LLM 在对话中产出的诊断 JSON 块
    2. 将 LLM 输出的知识点名称对齐到系统唯一键 kp_id
    3. 与用户历史答题诊断数据进行置信度加权融合（向先验回归）
    4. 生成 AOO 引擎所需的标准输入（掌握度向量 + 认知负荷 + 优化偏好）
    5. 当满足优化条件时触发 AOO 异步任务
    """

    def __init__(
        self,
        user_id: Union[uuid_mod.UUID, str],
        db: AsyncSession,
    ) -> None:
        # student_id 在 ORM 中是 UUID，历史签名标注为 int 属于错误
        self.user_id: uuid_mod.UUID = (
            user_id if isinstance(user_id, uuid_mod.UUID)
            else uuid_mod.UUID(str(user_id))
        )
        self.db = db
        self.resolver = KnowledgePointResolver(db)

    # ------------------------------------------------------------
    # 基线数据加载
    # ------------------------------------------------------------

    @staticmethod
    def _extract_mastery_flat(mastery_levels: dict) -> Dict[str, float]:
        """将 JSONB 嵌套结构 {kp_id: {mastery, level, confidence, name}} 展平为 {kp_id: level}"""
        flat: Dict[str, float] = {}
        for kp_id, data in (mastery_levels or {}).items():
            if isinstance(data, dict):
                lv = data.get("level") if "level" in data else data.get("mastery")
                if lv is not None:
                    try:
                        flat[str(kp_id)] = _clamp01(float(lv))
                    except (TypeError, ValueError):
                        continue
            else:
                try:
                    flat[str(kp_id)] = _clamp01(float(data))
                except (TypeError, ValueError):
                    continue
        return flat

    async def get_latest_exam_baseline(self) -> Optional[Dict[str, Any]]:
        """获取用户最近一次答题诊断数据作为客观基线"""
        stmt = (
            select(DiagnosisRecord)
            .where(DiagnosisRecord.student_id == self.user_id)
            .order_by(DiagnosisRecord.created_at.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        record = result.scalar_one_or_none()
        if not record:
            return None

        # mastery_levels 是 JSONB {kp_id: {mastery, level, confidence, name}}
        raw_mastery = getattr(record, "mastery_levels", {}) or {}
        flat_mastery = self._extract_mastery_flat(raw_mastery)

        # cognitive_load 是 JSONB, cognitive_load_index 是纯 float — AOO 任务需要 float
        load_index = getattr(record, "cognitive_load_index", None)
        if load_index is None or load_index == 0.0:
            raw_load = getattr(record, "cognitive_load", {}) or {}
            if isinstance(raw_load, dict):
                load_index = raw_load.get("overall", 0.5)
            else:
                load_index = 0.5

        return {
            "diagnosis_id": str(record.id),
            "mastery_levels": flat_mastery,
            "cognitive_load": float(load_index),
            "created_at": record.created_at.isoformat() if record.created_at else None,
        }

    async def get_practice_mastery(self) -> Dict[str, float]:
        """加载答题记录掌握度 {kp_id: level} — 无诊断基线时的兜底来源

        StudentKnowledge 是客观答题沉淀数据，本适配器**只读不写**，
        严禁用主观问答信号污染（数据真实性底线）。
        """
        try:
            result = await self.db.execute(
                select(StudentKnowledge).where(
                    StudentKnowledge.student_id == self.user_id
                )
            )
            return {
                str(r.kp_id): _clamp01(float(r.mastery_level))
                for r in result.scalars().all()
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("[adapter] 加载答题掌握度失败: %s", exc)
            return {}

    async def get_chat_profile(self) -> Dict[str, Any]:
        """读取该生「仅来自智能问答」梳理出的知识点掌握特点

        Returns:
            {
                "exists": bool,
                "chat_signal_count": int,
                "last_chat_at": str | None,
                "updated_at": str | None,
                "items": [                          # 按置信度降序、再按最近时间排序
                    {
                        "kp_id": str,
                        "kp_name": str,
                        "level": float,             # 对话梳理出的掌握度 [0,1]
                        "confidence": float,        # 置信度 [0,1]
                        "n": int,                   # 被对话修正次数
                        "last_at": str,             # 最近更新时间 ISO
                        "source": str,              # "chat"
                    },
                    ...
                ],
            }
        """
        empty = {
            "exists": False,
            "chat_signal_count": 0,
            "last_chat_at": None,
            "updated_at": None,
            "items": [],
        }
        try:
            profile = await self.db.scalar(
                select(ChatMasteryProfile).where(
                    ChatMasteryProfile.student_id == self.user_id
                )
            )
            if not profile or not profile.mastery:
                return empty

            # 批量取知识点名称，避免 N+1
            kp_ids = [uuid_mod.UUID(k) for k in profile.mastery.keys() if _is_uuid(k)]
            name_map: Dict[str, str] = {}
            if kp_ids:
                kp_rows = await self.db.execute(
                    select(KnowledgePoint.id, KnowledgePoint.name).where(
                        KnowledgePoint.id.in_(kp_ids)
                    )
                )
                name_map = {str(r[0]): r[1] for r in kp_rows.all()}

            items = []
            for kp_id, data in profile.mastery.items():
                if not isinstance(data, dict):
                    continue
                items.append({
                    "kp_id": kp_id,
                    "kp_name": name_map.get(kp_id, "未知知识点"),
                    "level": round(float(data.get("level", 0.5)), 4),
                    "confidence": round(float(data.get("confidence", 0.5)), 4),
                    "n": int(data.get("n", 1)),
                    "last_at": data.get("last_at"),
                    "source": data.get("source", "chat"),
                })
            # 按置信度降序，其次按 level 升序（薄弱且高置信优先展示）
            items.sort(key=lambda x: (-x["confidence"], x["level"]))

            return {
                "exists": True,
                "chat_signal_count": int(profile.chat_signal_count or 0),
                "last_chat_at": profile.last_chat_at.isoformat() if profile.last_chat_at else None,
                "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
                "items": items,
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("[adapter] 读取对话画像失败: %s", exc)
            return empty

    # ------------------------------------------------------------
    # 信号对齐
    # ------------------------------------------------------------

    async def resolve_estimates(
        self,
        chat_estimates: List[Dict[str, Any]],
    ) -> Tuple[Dict[str, float], List[str]]:
        """将 LLM 的 [{kp_name, level}] 对齐为 {kp_id: level}

        对齐失败的名称一律丢弃并返回，供上层记录可观测性日志。
        同一 kp_id 被多次提及时取平均，避免后者覆盖前者。
        """
        buckets: Dict[str, List[float]] = {}
        unresolved: List[str] = []

        for estimate in chat_estimates or []:
            if not isinstance(estimate, dict):
                continue
            # 兼容 LLM 直接回填 kp_id 的白名单模式
            raw_key = (
                estimate.get("kp_id")
                or estimate.get("kp_name")
                or ""
            )
            raw_key = str(raw_key).strip()
            level = estimate.get("level", None)
            if not raw_key or level is None:
                continue
            try:
                level = _clamp01(float(level))
            except (TypeError, ValueError):
                continue

            kp_id = await self.resolver.resolve(raw_key)
            if not kp_id:
                unresolved.append(raw_key)
                continue
            buckets.setdefault(kp_id, []).append(level)

        resolved = {
            kid: round(sum(vals) / len(vals), 4)
            for kid, vals in buckets.items()
        }
        return resolved, unresolved

    # ------------------------------------------------------------
    # 融合
    # ------------------------------------------------------------

    def fuse_mastery(
        self,
        chat_mastery: Dict[str, float],
        base_mastery: Dict[str, float],
        *,
        has_baseline: bool = True,
    ) -> Dict[str, float]:
        """将 LLM 推测掌握度与客观基线掌握度融合（键空间统一为 kp_id）

        Args:
            chat_mastery: {kp_id: level} — 已对齐的 LLM 评估
            base_mastery: {kp_id: level} — 诊断 / 答题记录客观基线
            has_baseline: 是否存在正式诊断基线，影响 LLM 权重

        Returns:
            {kp_id: level} 融合后的掌握度向量

        置信度语义: 低置信 = **向先验回归**，而非把数值乘小。
            有基线:  M = (1-λ)·M_base + λ·L_llm        （λ = CHAT_PROFILE_LAMBDA 实时读取）
            无基线:  M = min(λ,0.5)·L_llm + (1-min(λ,0.5))·prior
        """
        fused: Dict[str, float] = dict(base_mastery)
        prior = _prior()
        lam = _lambda()
        llm_w = lam if has_baseline else min(lam, 0.5)  # 无基线时更保守

        for kp_id, level in chat_mastery.items():
            if kp_id in fused:
                # 有客观观测 → 加权融合（λ 实时控制主观信号强度）
                fused[kp_id] = round(
                    (1.0 - llm_w) * fused[kp_id] + llm_w * level, 4
                )
            else:
                # 无客观观测 → 向先验回归（而非 level * 0.35 的数值篡改）
                fused[kp_id] = round(
                    llm_w * level + (1.0 - llm_w) * prior, 4
                )

        return fused

    def determine_optimization_preference(
        self,
        learning_intent: str = "",
    ) -> Dict[str, Any]:
        """根据学习意图映射 AOO 优化偏好

        AOO 引擎支持三种优化偏好: efficiency / balanced / robustness
        对应 Pareto 三路径: 效率型 / 平衡型 / 稳健型
        """
        intent_map = {
            "skill_improve": {"preference": "efficiency", "alpha_bias": 0.6},
            "deep_dive": {"preference": "balanced", "alpha_bias": 0.4},
            "basic_review": {"preference": "robustness", "alpha_bias": 0.5},
            "quick_fix": {"preference": "efficiency", "alpha_bias": 0.7},
        }
        return intent_map.get(
            learning_intent,
            {"preference": "balanced", "alpha_bias": 0.5},
        )

    # ------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------

    async def build_aoo_params(self, chat_diagnosis: Dict[str, Any]) -> Dict[str, Any]:
        """从对话诊断 JSON 构建 AOO 标准输入参数

        Returns:
            {
                "has_baseline": bool,          # 是否有正式诊断基线
                "baseline_source": str,        # diagnosis | practice | none
                "diagnosis_id": str | None,    # 关联的诊断记录 ID
                "mastery_levels": dict,        # {kp_id: level} 融合后的掌握度向量
                "cognitive_load": float,       # 认知负荷
                "optimization_preference": dict,
                "can_optimize": bool,          # 是否满足优化条件
                "weak_count": int,
                "weak_kp_ids": list[str],
                "learning_intent": str,
                "resolved_count": int,         # 成功对齐的 LLM 信号数
                "unresolved_names": list[str], # 未对齐被丢弃的名称（可观测性）
            }
        """
        baseline = await self.get_latest_exam_baseline()
        has_baseline = baseline is not None

        chat_estimates = chat_diagnosis.get("mastery_estimates", []) or []
        chat_cognitive_load = chat_diagnosis.get("cognitive_load", 0.5)
        learning_intent = chat_diagnosis.get("learning_intent", "")
        needs_optimization = bool(chat_diagnosis.get("needs_optimization", False))

        try:
            chat_cognitive_load = _clamp01(float(chat_cognitive_load))
        except (TypeError, ValueError):
            chat_cognitive_load = 0.5

        # 1) 键空间对齐: kp_name → kp_id（P0 核心修复）
        chat_mastery, unresolved = await self.resolve_estimates(chat_estimates)
        if unresolved:
            logger.info(
                "[adapter] %d 个 LLM 知识点信号未能对齐已丢弃: %s | user=%s",
                len(unresolved), unresolved, self.user_id,
            )

        # 2) 选取客观基线: 诊断优先 → 答题记录兜底（首次使用场景）
        if has_baseline and baseline:
            base_mastery = baseline.get("mastery_levels", {})
            base_load = float(baseline.get("cognitive_load", 0.5))
            baseline_source = "diagnosis"
        else:
            base_mastery = await self.get_practice_mastery()
            base_load = 0.5
            baseline_source = "practice" if base_mastery else "none"

        # 3) 融合（统一 kp_id 键空间）
        fused_mastery = self.fuse_mastery(
            chat_mastery, base_mastery, has_baseline=has_baseline
        )

        # 4) 认知负荷融合（λ 同步控制主观信号权重）
        if has_baseline:
            lam = _lambda()
            fused_cognitive_load = round(
                (1.0 - lam) * base_load + lam * chat_cognitive_load, 4
            )
        else:
            fused_cognitive_load = round(chat_cognitive_load, 4)

        optimization_pref = self.determine_optimization_preference(learning_intent)

        # 5) 薄弱点判定 — 只统计本轮 LLM 真实提及且成功对齐的知识点，
        #    避免历史全量掌握度把 weak_count 撑大导致 can_optimize 恒为真
        weak_kp_ids = [
            kp_id for kp_id in chat_mastery
            if fused_mastery.get(kp_id, 1.0) < WEAK_THRESHOLD
        ]
        weak_count = len(weak_kp_ids)

        # LLM 明确标记需要优化，且确有可用信号；或检测到 2+ 薄弱点
        can_optimize = (
            (needs_optimization and bool(chat_mastery))
            or weak_count >= 2
        )

        logger.info(
            "[adapter] 参数构建完成 | user=%s | baseline=%s | 对齐=%d/%d "
            "| weak=%d | can_optimize=%s",
            self.user_id, baseline_source,
            len(chat_mastery), len(chat_estimates),
            weak_count, can_optimize,
        )

        result = {
            "has_baseline": has_baseline,
            "baseline_source": baseline_source,
            "diagnosis_id": baseline["diagnosis_id"] if baseline else None,
            "mastery_levels": fused_mastery,
            "cognitive_load": fused_cognitive_load,
            "optimization_preference": optimization_pref,
            "can_optimize": can_optimize,
            "weak_count": weak_count,
            "weak_kp_ids": weak_kp_ids,
            "learning_intent": learning_intent,
            "resolved_count": len(chat_mastery),
            "unresolved_names": unresolved,
        }

        # P1: best-effort 落库问答增量 + 可观测性事件（含 reasoning）
        #     不阻断主链路；任何异常仅记日志，保证 AOO 入参照常返回
        # P3: CHAT_PROFILE_ENABLED 总开关关闭时，连信号落库一并跳过（完整关闭画像）
        profile_enabled = bool(getattr(settings, "CHAT_PROFILE_ENABLED", True))
        if profile_enabled:
            try:
                await self._persist_chat_signal(
                    chat_mastery=chat_mastery,
                    base_mastery=base_mastery,
                    fused_mastery=fused_mastery,
                    has_baseline=has_baseline,
                    baseline_source=baseline_source,
                    unresolved=unresolved,
                    can_optimize=can_optimize,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[adapter] 问答信号落库失败(不影响 AOO): %s | user=%s",
                    exc, self.user_id,
                )

        return result

    # ------------------------------------------------------------
    # P1: 问答增量落库 + 可观测性事件
    # ------------------------------------------------------------

    async def _persist_chat_signal(
        self,
        chat_mastery: Dict[str, float],
        base_mastery: Dict[str, float],
        fused_mastery: Dict[str, float],
        *,
        has_baseline: bool,
        baseline_source: str,
        unresolved: List[str],
        can_optimize: bool,
    ) -> None:
        """沉淀问答增量到 student_cognitive_profiles，并写 cognitive_profile_event

        数据真实性底线: 绝不写 StudentKnowledge（客观答题数据）。
        融合仅在内存进行，本方法只把「相对增量」存进 mastery_deltas，
        供后续融合作为微弱先验复用。每个对齐知识点生成一条带 reasoning 的事件。
        """
        if not chat_mastery and not unresolved:
            return  # 无信号可落

        # ---- 写认知画像 (mastery_deltas) ----
        # 读取或新建画像行
        profile = await self.db.scalar(
            select(StudentCognitiveProfile).where(
                StudentCognitiveProfile.student_id == self.user_id
            )
        )
        if profile is None:
            profile = StudentCognitiveProfile(student_id=self.user_id)
            self.db.add(profile)

        deltas = dict(profile.mastery_deltas or {})
        lambda_w = _lambda()
        delta_cap = _max_delta()

        for kp_id, llm_level in chat_mastery.items():
            base_val = base_mastery.get(kp_id)
            fused_val = fused_mastery.get(kp_id, llm_level)
            if base_val is not None:
                # 相对增量 = 融合后 - 客观基线（单点偏移截断，防噪声带偏）
                raw_delta = fused_val - float(base_val)
                delta = round(max(-delta_cap, min(delta_cap, raw_delta)), 4)
                capped_note = "" if abs(raw_delta - delta) < 1e-6 else "（已被 δ_max 截断）"
                reason = (
                    f"知识点 {kp_id} 本轮对话评估为 {llm_level:.2f}，"
                    f"叠加客观基线 {base_val:.2f}（权重 λ={lambda_w:.2f}），"
                    f"融合后为 {fused_val:.2f}，相对增量 {delta:+.2f}{capped_note}。"
                )
            else:
                # 无客观观测 → 向先验回归，不记绝对增量，仅记信号强度
                delta = 0.0
                reason = (
                    f"知识点 {kp_id} 仅有对话评估 {llm_level:.2f}，"
                    f"无客观基线，按 λ={lambda_w:.2f} 向先验回归为 {fused_val:.2f}，"
                    f"不生成绝对增量（仅作微弱先验）。"
                )

            prev = deltas.get(kp_id) or {}
            new_n = int(prev.get("n", 0)) + 1
            # 增量做滑动平均，权重随样本数稀释，避免单次噪声主导
            prev_delta = float(prev.get("delta", 0.0))
            blended_delta = round(
                (prev_delta * (new_n - 1) + delta) / new_n, 4
            ) if new_n else delta
            deltas[kp_id] = {
                "delta": blended_delta,
                "confidence": lambda_w,
                "n": new_n,
                "last_at": "now()",
            }

            self.db.add(
                CognitiveProfileEvent(
                    student_id=self.user_id,
                    event_type="chat_signal",
                    kp_id=uuid_mod.UUID(kp_id) if _is_uuid(kp_id) else None,
                    payload={
                        "kp_id": kp_id,
                        "llm_level": llm_level,
                        "base_level": base_val,
                        "fused_level": fused_val,
                        "delta": delta,
                        "lambda": lambda_w,
                        "has_baseline": has_baseline,
                        "baseline_source": baseline_source,
                    },
                    reasoning=reason,
                )
            )

        profile.mastery_deltas = deltas
        profile.chat_signal_count = int(profile.chat_signal_count or 0) + 1
        # last_chat_at 用 DB now() 由 server_default 维护，这里不赋 Python 值

        # ---- 未对齐信号事件（可观测性）----
        if unresolved:
            self.db.add(
                CognitiveProfileEvent(
                    student_id=self.user_id,
                    event_type="unresolved_signal",
                    payload={"unresolved_names": unresolved},
                    reasoning=(
                        f"检测到 {len(unresolved)} 个对话知识点未能对齐到知识图谱"
                        f"（{unresolved}），已丢弃，未参与融合。建议核查 LLM 输出质量。"
                    ),
                )
            )

        # ---- 无基线兜底事件 ----
        if baseline_source == "none":
            self.db.add(
                CognitiveProfileEvent(
                    student_id=self.user_id,
                    event_type="baseline_fallback",
                    payload={"chat_mastery": chat_mastery},
                    reasoning=(
                        "用户尚未完成任何诊断答题，无客观基线。"
                        "本次以对话问答为微弱先验（λ 权重下向 0.5 先验回归），"
                        "不回写 StudentKnowledge，数据真实性已守住。"
                    ),
                )
            )

        # ---- 融合/触发事件 ----
        self.db.add(
            CognitiveProfileEvent(
                student_id=self.user_id,
                event_type="fusion",
                payload={
                    "can_optimize": can_optimize,
                    "has_baseline": has_baseline,
                    "baseline_source": baseline_source,
                    "resolved_count": len(chat_mastery),
                    "unresolved_count": len(unresolved),
                },
                reasoning=(
                    f"完成对话信号融合：基线来源={baseline_source}，"
                    f"成功对齐 {len(chat_mastery)} 个、丢弃 {len(unresolved)} 个；"
                    f"判定{'满足' if can_optimize else '不满足'}自动优化触发条件"
                    f"（λ={lambda_w}）。"
                ),
            )
        )

        # ---- P5: 沉淀「对话画像」(绝对掌握度视图) ----
        # 仅记录 LLM 本轮梳理出的 chat_mastery 估计作为该生对话掌握特点，
        # 与 StudentKnowledge (客观答题) / mastery_deltas (相对增量) 三者分离。
        # 置信度随提及次数累积 (n)，对同一 kp 取最近估计 + 置信度滑动提升。
        chat_profile = await self.db.scalar(
            select(ChatMasteryProfile).where(
                ChatMasteryProfile.student_id == self.user_id
            )
        )
        if chat_profile is None:
            chat_profile = ChatMasteryProfile(student_id=self.user_id)
            self.db.add(chat_profile)

        mastery_view = dict(chat_profile.mastery or {})
        now_iso = _now_iso()
        for kp_id, llm_level in chat_mastery.items():
            prev = mastery_view.get(kp_id) or {}
            new_n = int(prev.get("n", 0)) + 1
            # 置信度随样本数稀释提升，封顶 0.95（绝不 100%，保留不确定性）
            new_conf = round(min(0.95, 0.5 + 0.15 * new_n), 4)
            mastery_view[kp_id] = {
                "level": round(float(llm_level), 4),
                "confidence": new_conf,
                "n": new_n,
                "last_at": now_iso,
                "source": "chat",
            }
        chat_profile.mastery = mastery_view
        chat_profile.chat_signal_count = int(chat_profile.chat_signal_count or 0) + 1

        await self.db.flush()
