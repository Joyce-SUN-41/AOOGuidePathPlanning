"""诊断服务 — 认知诊断模型 (CDM) 与认知负荷计算

核心算法:
  1. IRT 2-PL 模型: 基于正确率 + 难度 + 区分度的掌握度估计
  2. DINA 模型 (可选): 基于知识点属性的离散掌握度
  3. 认知负荷: 答题时间偏差 + 连续错误模式

参考:
  - IRT (Item Response Theory): P(θ) = c + (1-c) / (1 + exp(-Da(θ-b)))
  - DINA: P(Y=1|α) = g^(1-η) * (1-s)^η
"""

import logging
import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cognitive_load_record import CognitiveLoadRecord
from app.models.diagnosis import DiagnosisRecord
from app.models.knowledge_point import KnowledgePoint
from app.models.question import Question
from app.models.student_knowledge import StudentKnowledge
from app.schemas.diagnosis import (
    CognitiveLoadProfile,
    DiagnosisResultResponse,
    MasteryItem,
    RadarPoint,
    SubmittedAnswer,
    WeakPoint,
)

logger = logging.getLogger(__name__)


def _coerce_uuid(value: Any) -> Optional[uuid.UUID]:
    """尝试将任意值转为 UUID，失败返回 None。
    用于兼容 mock 数据中的字符串 kp_id（如 "kp_001"）与数据库 UUID 列。
    """
    if isinstance(value, uuid.UUID):
        return value
    if isinstance(value, str):
        try:
            return uuid.UUID(value)
        except (ValueError, AttributeError):
            return None
    return None


# ── 默认知识点信息 (当数据库无记录时使用) ─────────────

_DEFAULT_KP_MAP: Dict[str, dict] = {
    "kp_001": {"name": "人工智能基础概念", "difficulty": 1},
    "kp_002": {"name": "机器学习基础", "difficulty": 2},
    "kp_003": {"name": "深度学习与神经网络", "difficulty": 3},
    "kp_004": {"name": "自然语言处理与大模型", "difficulty": 3},
    "kp_005": {"name": "AI伦理与前沿应用", "difficulty": 2},
}

# ── 题目答案映射 (Mock 题库正确选项 - AI 通识课) ───────

_CORRECT_ANSWER_MAP: Dict[str, str] = {
    "q001": "A", "q002": "B", "q003": "A",
    "q004": "C", "q005": "A", "q006": "B",
    "q007": "A", "q008": "A", "q009": "B",
    "q010": "A", "q011": "A", "q012": "A",
    "q013": "A", "q014": "A", "q015": "A",
}

# 题目 → 知识点 → 预期时间 映射
_QUESTION_META: Dict[str, dict] = {
    f"q{i:03d}": {
        "kp_id": list(_DEFAULT_KP_MAP.keys())[(i - 1) // 3],
        "expected_time": 15.0 + ((i - 1) % 3) * 5.0,
        "difficulty": ((i - 1) % 3) + 1,
    }
    for i in range(1, 16)
}

# IRT 模型参数
D = 1.7  # scaling constant
GUESS_FLOOR = 0.1  # c: guessing parameter floor
DEFAULT_DISCRIMINATION = 1.0  # a: discrimination
MAX_IRT_ESTIMATION_ITERS = 50


# ── 数据类 ────────────────────────────────────────────

@dataclass
class AnswerAnalysis:
    """单题分析结果"""
    question_id: str
    kp_id: str
    selected_option: str
    time_spent: float
    is_correct: bool
    expected_time: float
    difficulty: int


@dataclass
class KpAnalysis:
    """知识点分析汇总"""
    kp_id: str
    name: str
    total: int = 0
    correct: int = 0
    avg_time_spent: float = 0.0
    avg_expected_time: float = 0.0
    questions: List[AnswerAnalysis] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total > 0 else 0.0

    @property
    def time_ratio(self) -> float:
        """实际用时 / 预期用时"""
        if self.avg_expected_time > 0 and self.total > 0:
            return self.avg_time_spent / self.avg_expected_time
        return 1.0


# ── IRT 2-PL 模型 ─────────────────────────────────────

def irt_probability(theta: float, a: float, b: float, c: float = GUESS_FLOOR) -> float:
    """IRT 2-PL: 给定能力 θ, 难度 b, 区分度 a, 猜测参数 c, 答对概率"""
    return c + (1 - c) / (1 + math.exp(-D * a * (theta - b)))


def _item_difficulty_dina(difficulty_1_to_5: int) -> float:
    """将 1-5 难度映射到 θ 尺度 [-2, 2]"""
    return (difficulty_1_to_5 - 3) * 0.8


def estimate_mastery_irt(analyses: List[AnswerAnalysis]) -> float:
    """使用 IRT 2-PL 模型估计单个知识点的掌握度 (θ).

    通过极大似然估计 (MLE) 优化 θ 参数.
    """
    if not analyses:
        return 0.0

    # 初始猜测: 基于正确率的起点
    theta = -2.0 + 4.0 * (sum(1 for a in analyses if a.is_correct) / len(analyses))
    theta = max(-3.0, min(3.0, theta))  # clamp

    discrim = DEFAULT_DISCRIMINATION

    for _ in range(MAX_IRT_ESTIMATION_ITERS):
        # 计算梯度: ∂logL/∂θ = Σ [r_i - P_i(θ)] * Da / [P_i(θ) * (1-P_i(θ))] * P_i'(θ)
        gradient = 0.0
        fisher_info = 0.0

        for a in analyses:
            b = _item_difficulty_dina(a.difficulty)
            p = irt_probability(theta, discrim, b)
            # r_i ∈ {0, 1}
            r = 1.0 if a.is_correct else 0.0
            # 修正: 梯度 = (r - p) * D * a * (p - c) / (p * (1-c))
            # 使用标准 IRT 梯度
            if 0.01 < p < 0.99:
                dp = D * discrim * (p - GUESS_FLOOR) * (1 - p) / (1 - GUESS_FLOOR)
                gradient += (r - p) * dp / (p * (1 - p))
                fisher_info += dp * dp / (p * (1 - p))

        if abs(gradient) < 1e-4:
            break

        # Newton-Raphson 更新
        if fisher_info > 1e-6:
            step = gradient / fisher_info
            theta += step
        else:
            theta += 0.05 * (1 if gradient > 0 else -1)

        theta = max(-3.0, min(3.0, theta))

    # 将 θ ∈ [-3, 3] 映射到掌握度 [0, 1]
    # 使用 logistic 变换
    return 1.0 / (1.0 + math.exp(-theta))


# ── DINA 模型 (Deterministic Input, Noisy "And" gate) ──

@dataclass
class DINAParams:
    """DINA 模型参数估计结果"""
    slip: float       # 粗心参数: P(答错 | 掌握了所有属性)
    guess: float      # 猜测参数: P(答对 | 未掌握所有属性)
    slips_per_kp: Dict[str, float] = field(default_factory=dict)
    guesses_per_kp: Dict[str, float] = field(default_factory=dict)
    converged: bool = False
    iterations: int = 0


def compute_slip_and_guess(kp_analyses: Dict[str, KpAnalysis]) -> Tuple[float, float]:
    """估计 DINA 模型的 slip (粗心) 和 guess (猜测) 参数 (全局均值).

    slip = P(答错 | 掌握了所有属性)
    guess = P(答对 | 未掌握所有属性)
    """
    return compute_slip_and_guess_detailed(kp_analyses)


def compute_slip_and_guess_detailed(kp_analyses: Dict[str, KpAnalysis]) -> Tuple[float, float]:
    """详细版 slip/guess 估计 — 按知识点分别估计，再取加权平均"""
    kp_slips: Dict[str, float] = {}
    kp_guesses: Dict[str, float] = {}

    # 按知识点分别估计
    for kp_id, kpa in kp_analyses.items():
        if kpa.total < 2:
            continue

        s_count = 0
        s_total = 0
        g_count = 0
        g_total = 0

        for a in kpa.questions:
            if a.is_correct and a.difficulty >= 3:
                # 答对难题 → 可能是掌握了 → 如果其他简单题答错说明有 slip
                pass
            elif not a.is_correct and a.difficulty <= 2:
                # 简单题答错 → 更可能是 slip（粗心）
                s_count += 1
                s_total += 1
            elif a.is_correct and a.difficulty <= 2:
                # 简单题答对 → 如果不掌握也可能猜对
                g_total += 1
            else:
                # 难题答错 → 更可能是没掌握
                s_total += 1

        # 基于答题模式的 slip/guess 估计
        if s_total > 0:
            kp_slips[kp_id] = min(0.5, max(0.0, s_count / s_total))
        else:
            kp_slips[kp_id] = 0.1

        if g_total > 0:
            kp_guesses[kp_id] = min(0.5, max(0.0, g_count / g_total))
        else:
            kp_guesses[kp_id] = 0.25

    # 加权平均（按答题数加权）
    total_q = sum(kpa.total for kpa in kp_analyses.values())
    if total_q == 0:
        return 0.1, 0.25

    slip = sum(
        kp_slips.get(kp_id, 0.1) * kpa.total
        for kp_id, kpa in kp_analyses.items()
    ) / total_q

    guess = sum(
        kp_guesses.get(kp_id, 0.25) * kpa.total
        for kp_id, kpa in kp_analyses.items()
    ) / total_q

    return round(min(max(slip, 0.0), 0.5), 3), round(min(max(guess, 0.0), 0.5), 3)


def dina_probability(
    alpha: List[float],  # 属性掌握向量 [0/1, ...]
    q_matrix: List[int],  # Q矩阵行（题目需要哪些属性）[0/1, ...]
    slip: float,
    guess: float,
) -> float:
    """DINA 模型: 给定属性掌握向量 α 和 Q矩阵, 计算答对概率.

    η = ∏ α_k^{q_k}  (And gate: 必须掌握所有所需属性)
    P(Y=1 | α) = guess^(1-η) * (1-slip)^η

    Args:
        alpha: 属性掌握向量 [α₁, α₂, ...], α_k ∈ {0, 1}
        q_matrix: Q矩阵行 [q₁, q₂, ...], q_k ∈ {0, 1}
        slip: 粗心参数
        guess: 猜测参数

    Returns:
        答对概率 P ∈ [0, 1]
    """
    # η ∈ {0, 1}: 是否掌握了题目需要的所有属性
    eta = 1.0
    for a, q in zip(alpha, q_matrix):
        if q == 1 and a < 0.5:
            eta = 0.0
            break

    # P = (1-slip)^η * guess^(1-η)
    if eta > 0.5:
        return 1.0 - slip
    else:
        return guess


def estimate_mastery_dina(
    analyses: List[AnswerAnalysis],
    slip: float = 0.1,
    guess: float = 0.25,
    n_attributes: int = 1,
) -> Tuple[List[float], float]:
    """使用 DINA 模型估计属性掌握度.

    当 n_attributes == 1 时退化为单维掌握度估计。
    使用极大似然估计 (MLE) 搜索最佳属性掌握向量。

    Args:
        analyses: 答题分析列表
        slip: 全局 slip 参数
        guess: 全局 guess 参数
        n_attributes: 属性维度

    Returns:
        (alpha_vector, log_likelihood)
    """
    if not analyses:
        return ([0.0] * max(n_attributes, 1)), 0.0

    if n_attributes == 1:
        # 单维: 直接扫 α ∈ {0, 1}
        alpha0 = [0.0]
        alpha1 = [1.0]

        ll0 = 0.0
        ll1 = 0.0

        for a in analyses:
            q_row = [1]  # 单维：题目总是考察这个属性
            p0 = dina_probability(alpha0, q_row, slip, guess)
            p1 = dina_probability(alpha1, q_row, slip, guess)

            r = 1.0 if a.is_correct else 0.0
            ll0 += r * math.log(max(p0, 1e-10)) + (1 - r) * math.log(max(1 - p0, 1e-10))
            ll1 += r * math.log(max(p1, 1e-10)) + (1 - r) * math.log(max(1 - p1, 1e-10))

        if ll1 >= ll0:
            return alpha1, ll1
        else:
            return alpha0, ll0

    # 多维: 穷举搜索（属性数 ≤ 5 时可行）
    best_alpha = [0.0] * n_attributes
    best_ll = float('-inf')

    for mask in range(1 << n_attributes):
        alpha = [1.0 if (mask >> i) & 1 else 0.0 for i in range(n_attributes)]
        ll = 0.0

        for a in analyses:
            # 简化: 每个题目考察所有属性 (全 1 Q矩阵)
            q_row = [1] * n_attributes
            p = dina_probability(alpha, q_row, slip, guess)
            r = 1.0 if a.is_correct else 0.0
            ll += r * math.log(max(p, 1e-10)) + (1 - r) * math.log(max(1 - p, 1e-10))

        if ll > best_ll:
            best_ll = ll
            best_alpha = alpha

    return best_alpha, best_ll


def estimate_dina_params_em(
    kp_analyses: Dict[str, KpAnalysis],
    n_iterations: int = 20,
    tol: float = 1e-4,
) -> DINAParams:
    """使用 EM 算法估计 DINA 模型的 slip/guess 参数。

    这是一个简化版 EM：
    - E-step: 在给定当前参数下，估计每个知识点的属性掌握概率
    - M-step: 在给定属性掌握概率下，更新 slip/guess

    Args:
        kp_analyses: 知识点答题分析汇总
        n_iterations: 最大迭代次数
        tol: 收敛阈值

    Returns:
        DINAParams 估计结果
    """
    if not kp_analyses:
        return DINAParams(slip=0.1, guess=0.25)

    # 初始化参数
    slip = 0.1
    guess = 0.25
    prev_slip = 0.0
    prev_guess = 0.0

    # 收集所有题目分析
    all_analyses: List[AnswerAnalysis] = []
    for kpa in kp_analyses.values():
        all_analyses.extend(kpa.questions)

    n = len(all_analyses)
    if n == 0:
        return DINAParams(slip=0.1, guess=0.25)

    # EM 迭代
    for it in range(n_iterations):
        # E-step: 估计每个知识点的 P(α=1)
        kp_alpha_prob: Dict[str, float] = {}
        for kp_id, kpa in kp_analyses.items():
            alpha1, ll1 = estimate_mastery_dina(kpa.questions, slip, guess, n_attributes=1)
            kp_alpha_prob[kp_id] = alpha1[0]  # P(α=1)

        # M-step: 更新 slip, guess
        # slip = E[# 答错且 α=1] / E[# α=1]
        # guess = E[# 答对且 α=0] / E[# α=0]
        slip_num = 0.0
        slip_den = 0.0
        guess_num = 0.0
        guess_den = 0.0

        for a in all_analyses:
            alpha = kp_alpha_prob.get(a.kp_id, 0.5)
            r = 1.0 if a.is_correct else 0.0

            # 软计数
            slip_num += (1 - r) * alpha        # 答错 × P(掌握)
            slip_den += alpha                   # P(掌握)
            guess_num += r * (1 - alpha)        # 答对 × P(未掌握)
            guess_den += (1 - alpha)            # P(未掌握)

        new_slip = slip_num / max(slip_den, 1e-6)
        new_guess = guess_num / max(guess_den, 1e-6)

        new_slip = min(max(new_slip, 0.0), 0.5)
        new_guess = min(max(new_guess, 0.0), 0.5)

        # 检查收敛
        if abs(new_slip - slip) < tol and abs(new_guess - guess) < tol:
            slip = new_slip
            guess = new_guess
            return DINAParams(
                slip=round(slip, 3),
                guess=round(guess, 3),
                converged=True,
                iterations=it + 1,
            )

        slip = new_slip
        guess = new_guess

    return DINAParams(
        slip=round(slip, 3),
        guess=round(guess, 3),
        converged=False,
        iterations=n_iterations,
    )


# ── 认知负荷计算 ──────────────────────────────────────

def compute_cognitive_load(analyses: List[AnswerAnalysis]) -> CognitiveLoadProfile:
    """多维度认知负荷计算.

    三个维度:
      1. memory_load:     实际用时超出预期的比例
      2. attention_load:  错误率 (尤其考虑难易题分布)
      3. processing_load: 时间波动 + 错误模式复杂度
    """
    if not analyses:
        return CognitiveLoadProfile(
            memory_load=0.0, attention_load=0.0, processing_load=0.0, overall=0.0
        )

    n = len(analyses)

    # ---- 记忆负荷: 答题时间偏差 ----
    time_ratios = [
        max(0.5, a.time_spent / max(a.expected_time, 1.0))
        for a in analyses
    ]
    avg_time_ratio = sum(time_ratios) / n
    # ratio ∈ [0.5, inf) → [0, 1] using logistic
    memory_load = min(1.0, 1.0 / (1.0 + math.exp(-2.5 * (avg_time_ratio - 1.2))))

    # ---- 注意力负荷: 错误模式 + 难易题对比 ----
    error_rate = sum(1 for a in analyses if not a.is_correct) / n
    # 简单题 (difficulty <= 2) 的错误加权更高
    easy_errors = sum(
        1 for a in analyses if not a.is_correct and a.difficulty <= 2
    )
    easy_total = sum(1 for a in analyses if a.difficulty <= 2)
    easy_error_rate = easy_errors / easy_total if easy_total > 0 else 0.0

    attention_load = min(1.0, error_rate * 0.6 + easy_error_rate * 0.4)

    # ---- 加工负荷: 时间波动 + 连续错误 ----
    if n > 1:
        time_variance = sum((r - avg_time_ratio) ** 2 for r in time_ratios) / n
        time_std = math.sqrt(time_variance)
        processing_from_variance = min(1.0, time_std / 1.5)
    else:
        processing_from_variance = 0.0

    # 连续错误检测
    max_consecutive = 0
    current_consecutive = 0
    for a in analyses:
        if not a.is_correct:
            current_consecutive += 1
            max_consecutive = max(max_consecutive, current_consecutive)
        else:
            current_consecutive = 0
    processing_from_consecutive = min(1.0, max_consecutive / 5.0)

    processing_load = (
        processing_from_variance * 0.5 + processing_from_consecutive * 0.5
    )

    # ---- 综合负荷: 加权平均 ----
    overall = (memory_load * 0.3 + attention_load * 0.4 + processing_load * 0.3)

    return CognitiveLoadProfile(
        memory_load=round(memory_load, 3),
        attention_load=round(attention_load, 3),
        processing_load=round(processing_load, 3),
        overall=round(overall, 3),
    )


def compute_max_consecutive_errors(analyses: List[AnswerAnalysis]) -> int:
    """计算最大连续错误数"""
    max_consecutive = 0
    current = 0
    for a in analyses:
        if not a.is_correct:
            current += 1
            max_consecutive = max(max_consecutive, current)
        else:
            current = 0
    return max_consecutive


# ── 掌握度分级 ────────────────────────────────────────

def classify_mastery_level(value: float) -> str:
    """将掌握度映射到等级"""
    if value >= 0.85:
        return "excellent"
    elif value >= 0.70:
        return "proficient"
    elif value >= 0.50:
        return "developing"
    else:
        return "weak"


# ── 置信度估计 ─────────────────────────────────────────

def estimate_confidence(n_questions: int, accuracy: float) -> float:
    """基于答题数量的置信度经验估计 (非 Wilson score interval)"""
    if n_questions == 0:
        return 0.1
    # 随着题目数增加，置信度趋近于 1
    base = min(1.0, n_questions / 10.0)
    # 准确率极端值 (0 或 1) 置信度较低
    consistency_penalty = 1.0 - abs(accuracy - 0.5) * 0.3
    return round(base * consistency_penalty, 3)


# ── AI 诊断摘要生成 ────────────────────────────────────

def generate_summary(
    mastery_levels: Dict[str, float],
    cognitive_load: CognitiveLoadProfile,
    kp_names: Dict[str, str],
) -> str:
    """生成自然语言诊断摘要"""
    avg_mastery = (
        sum(mastery_levels.values()) / len(mastery_levels)
        if mastery_levels else 0.0
    )

    # 整体评级
    if avg_mastery >= 0.85:
        overall = "优秀 — 您对该学科的知识点掌握非常扎实,具备了良好的知识结构。"
    elif avg_mastery >= 0.70:
        overall = "熟练 — 大部分知识点掌握良好,建议针对薄弱环节做针对性提升。"
    elif avg_mastery >= 0.50:
        overall = "发展中 — 建议加强基础知识的理解和练习,逐步提升知识体系的完整性。"
    else:
        overall = "薄弱 — 需要系统性地重新学习基础知识,建议从最薄弱的环节开始。"

    # 认知负荷分析
    if cognitive_load.overall > 0.6:
        load_desc = "认知负荷较高,答题过程中可能感到吃力,建议适当放慢学习节奏。"
    elif cognitive_load.overall > 0.35:
        load_desc = "认知负荷适中,目前的挑战在可接受范围内,学习状态良好。"
    else:
        load_desc = "认知负荷较低,题目相对轻松,可以考虑适当增加挑战难度。"

    # 薄弱点
    weak = [
        (kp_id, v) for kp_id, v in mastery_levels.items() if v < 0.6
    ]
    if weak:
        weak_list = "、".join(
            kp_names.get(kp_id, kp_id) for kp_id, _ in sorted(weak, key=lambda x: x[1])
        )
        weak_desc = f"薄弱知识点集中在: {weak_list},建议优先攻克这些内容。"
    else:
        weak_desc = "暂无明显的薄弱知识点,可以保持现有学习状态。"

    return f"{overall} {load_desc} {weak_desc}"


# ── 薄弱点生成 ─────────────────────────────────────────

def generate_weak_points(
    mastery_levels: Dict[str, float],
    kp_names: Dict[str, str],
    kp_analyses: Dict[str, KpAnalysis],
) -> List[WeakPoint]:
    """生成薄弱点列表 (按严重度排序)"""
    weak_points: List[WeakPoint] = []

    for kp_id, mastery in sorted(mastery_levels.items(), key=lambda x: x[1]):
        if mastery >= 0.6:
            continue  # 掌握度达标

        name = kp_names.get(kp_id, kp_id)
        kpa = kp_analyses.get(kp_id)

        if mastery < 0.3:
            severity = "severe"
            reason = "该知识点掌握程度严重不足,多数相关题目答错,需要从基础开始重新学习"
            suggestion = "建议: 先观看基础教学视频,完成课后习题,确保理解核心概念后再做进阶练习"
        elif mastery < 0.5:
            severity = "moderate"
            reason = "该知识点掌握程度中等偏下,存在明显的知识盲区"
            suggestion = "建议: 针对性地做专项练习,重点攻克常错题型,结合错题本回顾"
        else:
            severity = "mild"
            reason = "该知识点掌握程度尚可,但仍有提升空间,个别题目存在理解偏差"
            suggestion = "建议: 做2-3道经典难题巩固,注意审题和解题步骤的规范性"

        # 补充答题时间分析
        if kpa and kpa.time_ratio > 1.5:
            reason += f" (答题耗时是预期的 {kpa.time_ratio:.1f} 倍,可能存在速度瓶颈)"
            suggestion = suggestion.rstrip("。") + ",适当提高解题速度"

        weak_points.append(WeakPoint(
            kp_id=kp_id,
            knowledge_point=name,
            reason=reason,
            severity=severity,
            suggested_remediation=suggestion,
        ))

    return weak_points


# ── 主服务类 ───────────────────────────────────────────

class DiagnosisService:
    """认知诊断服务 — 封装 CDM 模型计算与结果持久化"""

    @staticmethod
    def _get_kp_name(kp_id: str, kp_name_map: Optional[Dict[str, str]] = None) -> str:
        if kp_name_map and kp_id in kp_name_map:
            return kp_name_map[kp_id]
        return _DEFAULT_KP_MAP.get(kp_id, {}).get("name", kp_id)

    @staticmethod
    async def _load_kp_name_map(db: AsyncSession) -> Dict[str, str]:
        """从数据库加载知识点名称映射表"""
        result = await db.execute(select(KnowledgePoint.id, KnowledgePoint.name).limit(100))
        return {str(row[0]): row[1] for row in result}

    @staticmethod
    async def _load_kp_map_from_db(db: AsyncSession) -> Dict[str, dict]:
        """从数据库加载知识点映射表 (含难度)"""
        result = await db.execute(select(KnowledgePoint).limit(100))
        kps = result.scalars().all()
        return {
            str(kp.id): {"name": kp.name, "difficulty": kp.difficulty_level}
            for kp in kps
        }

    def __init__(self, db: AsyncSession | None = None):
        self.db = db

    # ── 题目获取 ───────────────────────────────────────

    @staticmethod
    async def get_question_bank_from_db(db: AsyncSession, subject: Optional[str] = None) -> List[dict]:
        """从数据库获取题目 (活跃状态), 转换为旧格式 dict 列表"""
        stmt = select(Question).where(Question.is_active == True)  # noqa: E712
        if subject:
            stmt = stmt.where(Question.subject == subject)
        stmt = stmt.order_by(Question.difficulty, Question.code)
        result = await db.execute(stmt)
        questions = result.scalars().all()

        # 加载所有关联知识点名称
        all_kp_ids = set()
        for q in questions:
            for kp_id in (q.kp_ids or []):
                all_kp_ids.add(kp_id)

        kp_name_map: Dict[str, str] = {}
        if all_kp_ids:
            kp_result = await db.execute(
                select(KnowledgePoint.id, KnowledgePoint.name)
                .where(KnowledgePoint.id.in_([uuid.UUID(x) for x in all_kp_ids]))
            )
            for row in kp_result:
                kp_name_map[str(row[0])] = row[1]

        bank = []
        for q in questions:
            # 关联的知识点名称
            primary_kp_id = str(q.kp_ids[0]) if q.kp_ids else ""
            topic_name = kp_name_map.get(primary_kp_id, q.subject)
            bank.append({
                "id": q.code,  # 用 code 作为外部 ID
                "db_id": str(q.id),
                "topic": topic_name,
                "kp_id": primary_kp_id,
                "kp_ids": q.kp_ids or [],
                "difficulty": q.difficulty,
                "type": q.type,
                "title": q.title,
                "options": q.options or [],
                "correct_option_id": q.correct_option_id,
                "expected_time_sec": float(q.expected_time_sec),
                "explanation": q.explanation,
            })
        return bank

    def get_question_bank(self) -> List[dict]:
        """获取内置 Mock 题库 (降级方案, 当 DB 无数据时使用)"""
        bank = [
            # kp_001: 一元二次方程
            {
                "id": "q001", "topic": "一元二次方程", "kp_id": "kp_001",
                "difficulty": 1, "type": "single", "correct_option_id": "B",
                "expected_time_sec": 15.0,
                "title": "方程 x² - 5x + 6 = 0 的解是？",
                "options": [
                    {"id": "A", "text": "x=1 或 x=6", "weight": 0.0},
                    {"id": "B", "text": "x=2 或 x=3", "weight": 1.0},
                    {"id": "C", "text": "x=-2 或 x=-3", "weight": 0.0},
                    {"id": "D", "text": "x=1 或 x=5", "weight": 0.0},
                ],
            },
            {
                "id": "q002", "topic": "一元二次方程", "kp_id": "kp_001",
                "difficulty": 2, "type": "single", "correct_option_id": "C",
                "expected_time_sec": 18.0,
                "title": "若关于 x 的方程 x² + kx + 4 = 0 有两个相等的实根, 则 k = ?",
                "options": [
                    {"id": "A", "text": "k=2", "weight": 0.0},
                    {"id": "B", "text": "k=-4", "weight": 0.0},
                    {"id": "C", "text": "k = ±4", "weight": 1.0},
                    {"id": "D", "text": "k = ±2", "weight": 0.0},
                ],
            },
            {
                "id": "q003", "topic": "一元二次方程", "kp_id": "kp_001",
                "difficulty": 3, "type": "single", "correct_option_id": "A",
                "expected_time_sec": 22.0,
                "title": "已知方程 2x² + 3x - 5 = 0 的两根为 α 和 β, 则 α² + β² = ?",
                "options": [
                    {"id": "A", "text": "29/4", "weight": 1.0},
                    {"id": "B", "text": "13/2", "weight": 0.0},
                    {"id": "C", "text": "9", "weight": 0.0},
                    {"id": "D", "text": "25/4", "weight": 0.0},
                ],
            },
            # kp_002: 函数图像与性质
            {
                "id": "q004", "topic": "函数图像与性质", "kp_id": "kp_002",
                "difficulty": 2, "type": "single", "correct_option_id": "D",
                "expected_time_sec": 17.0,
                "title": "函数 y = x² - 4x + 3 的顶点坐标是？",
                "options": [
                    {"id": "A", "text": "(1, 0)", "weight": 0.0},
                    {"id": "B", "text": "(4, 3)", "weight": 0.0},
                    {"id": "C", "text": "(2, 1)", "weight": 0.0},
                    {"id": "D", "text": "(2, -1)", "weight": 1.0},
                ],
            },
            {
                "id": "q005", "topic": "函数图像与性质", "kp_id": "kp_002",
                "difficulty": 3, "type": "single", "correct_option_id": "A",
                "expected_time_sec": 20.0,
                "title": "函数 f(x) = log₂(x+1) 的定义域是？",
                "options": [
                    {"id": "A", "text": "x > -1", "weight": 1.0},
                    {"id": "B", "text": "x ≥ 0", "weight": 0.0},
                    {"id": "C", "text": "x > 1", "weight": 0.0},
                    {"id": "D", "text": "x ∈ R", "weight": 0.0},
                ],
            },
            {
                "id": "q006", "topic": "函数图像与性质", "kp_id": "kp_002",
                "difficulty": 4, "type": "single", "correct_option_id": "C",
                "expected_time_sec": 25.0,
                "title": "设 f(x) 是奇函数, 且当 x>0 时 f(x)=x²-2x, 则 f(-1)=?",
                "options": [
                    {"id": "A", "text": "-3", "weight": 0.0},
                    {"id": "B", "text": "-1", "weight": 0.0},
                    {"id": "C", "text": "3", "weight": 1.0},
                    {"id": "D", "text": "1", "weight": 0.0},
                ],
            },
            # kp_003: 三角恒等变换
            {
                "id": "q007", "topic": "三角恒等变换", "kp_id": "kp_003",
                "difficulty": 3, "type": "single", "correct_option_id": "B",
                "expected_time_sec": 20.0,
                "title": "sin(π/6) 的值是？",
                "options": [
                    {"id": "A", "text": "√3/2", "weight": 0.0},
                    {"id": "B", "text": "1/2", "weight": 1.0},
                    {"id": "C", "text": "√2/2", "weight": 0.0},
                    {"id": "D", "text": "1", "weight": 0.0},
                ],
            },
            {
                "id": "q008", "topic": "三角恒等变换", "kp_id": "kp_003",
                "difficulty": 4, "type": "single", "correct_option_id": "A",
                "expected_time_sec": 24.0,
                "title": "sin²α + cos²α = ?",
                "options": [
                    {"id": "A", "text": "1", "weight": 1.0},
                    {"id": "B", "text": "0", "weight": 0.0},
                    {"id": "C", "text": "sin(2α)", "weight": 0.0},
                    {"id": "D", "text": "cos(2α)", "weight": 0.0},
                ],
            },
            {
                "id": "q009", "topic": "三角恒等变换", "kp_id": "kp_003",
                "difficulty": 5, "type": "single", "correct_option_id": "D",
                "expected_time_sec": 30.0,
                "title": "若 tanα = 2, 则 sin(2α) = ?",
                "options": [
                    {"id": "A", "text": "2/5", "weight": 0.0},
                    {"id": "B", "text": "1/5", "weight": 0.0},
                    {"id": "C", "text": "3/5", "weight": 0.0},
                    {"id": "D", "text": "4/5", "weight": 1.0},
                ],
            },
            # kp_004: 数列与递推
            {
                "id": "q010", "topic": "数列与递推", "kp_id": "kp_004",
                "difficulty": 2, "type": "single", "correct_option_id": "C",
                "expected_time_sec": 16.0,
                "title": "等差数列 {aₙ} 中, a₁=2, d=3, 则 a₅ = ?",
                "options": [
                    {"id": "A", "text": "11", "weight": 0.0},
                    {"id": "B", "text": "15", "weight": 0.0},
                    {"id": "C", "text": "14", "weight": 1.0},
                    {"id": "D", "text": "17", "weight": 0.0},
                ],
            },
            {
                "id": "q011", "topic": "数列与递推", "kp_id": "kp_004",
                "difficulty": 3, "type": "single", "correct_option_id": "B",
                "expected_time_sec": 20.0,
                "title": "等比数列 {aₙ} 中, a₁=3, q=2, 则前4项和 S₄ = ?",
                "options": [
                    {"id": "A", "text": "24", "weight": 0.0},
                    {"id": "B", "text": "45", "weight": 1.0},
                    {"id": "C", "text": "48", "weight": 0.0},
                    {"id": "D", "text": "93", "weight": 0.0},
                ],
            },
            {
                "id": "q012", "topic": "数列与递推", "kp_id": "kp_004",
                "difficulty": 4, "type": "single", "correct_option_id": "A",
                "expected_time_sec": 26.0,
                "title": "已知递推公式 aₙ₊₁ = 2aₙ - 1, a₁ = 2, 则 aₙ 的通项公式？",
                "options": [
                    {"id": "A", "text": "aₙ = 2ⁿ⁻¹ + 1", "weight": 1.0},
                    {"id": "B", "text": "aₙ = 2ⁿ - 1", "weight": 0.0},
                    {"id": "C", "text": "aₙ = 2ⁿ⁺¹ - 1", "weight": 0.0},
                    {"id": "D", "text": "aₙ = 3·2ⁿ⁻¹ - 1", "weight": 0.0},
                ],
            },
            # kp_005: 概率与统计
            {
                "id": "q013", "topic": "概率与统计", "kp_id": "kp_005",
                "difficulty": 2, "type": "single", "correct_option_id": "D",
                "expected_time_sec": 14.0,
                "title": "掷一枚骰子, 出现偶数点的概率是？",
                "options": [
                    {"id": "A", "text": "1/3", "weight": 0.0},
                    {"id": "B", "text": "2/3", "weight": 0.0},
                    {"id": "C", "text": "1/6", "weight": 0.0},
                    {"id": "D", "text": "1/2", "weight": 1.0},
                ],
            },
            {
                "id": "q014", "topic": "概率与统计", "kp_id": "kp_005",
                "difficulty": 3, "type": "single", "correct_option_id": "C",
                "expected_time_sec": 18.0,
                "title": "一组数据: 2, 4, 4, 6, 8, 10, 12 的中位数是？",
                "options": [
                    {"id": "A", "text": "4", "weight": 0.0},
                    {"id": "B", "text": "5", "weight": 0.0},
                    {"id": "C", "text": "6", "weight": 1.0},
                    {"id": "D", "text": "7", "weight": 0.0},
                ],
            },
            {
                "id": "q015", "topic": "概率与统计", "kp_id": "kp_005",
                "difficulty": 4, "type": "single", "correct_option_id": "A",
                "expected_time_sec": 24.0,
                "title": "从5个红球和3个白球中随机取2球, 恰取到1红1白的概率？",
                "options": [
                    {"id": "A", "text": "15/28", "weight": 1.0},
                    {"id": "B", "text": "3/14", "weight": 0.0},
                    {"id": "C", "text": "5/14", "weight": 0.0},
                    {"id": "D", "text": "13/28", "weight": 0.0},
                ],
            },
        ]
        return bank

    def get_question_by_id(self, question_id: str, bank: Optional[List[dict]] = None) -> Optional[dict]:
        """根据 ID 获取单题 (优先使用传入的 bank)"""
        questions = bank if bank else self.get_question_bank()
        for q in questions:
            if q["id"] == question_id or q.get("db_id") == question_id:
                return q
        return None

    # ── 答案分析 ───────────────────────────────────────

    def analyze_answers(
        self, answers: List[SubmittedAnswer], bank: Optional[List[dict]] = None
    ) -> Tuple[List[AnswerAnalysis], Dict[str, KpAnalysis]]:
        """分析所有提交答案, 返回每题分析和知识点汇总"""
        analyses: List[AnswerAnalysis] = []
        kp_map: Dict[str, KpAnalysis] = {}
        question_bank = bank if bank else self.get_question_bank()

        for ans in answers:
            question = self.get_question_by_id(ans.question_id, question_bank)
            if not question:
                logger.warning("Unknown question_id: %s, skipping", ans.question_id)
                continue

            kp_id = question["kp_id"]
            correct_option = question["correct_option_id"]
            is_correct = (ans.selected_option == correct_option)
            difficulty = question["difficulty"]
            expected_time = question["expected_time_sec"]

            analysis = AnswerAnalysis(
                question_id=ans.question_id,
                kp_id=kp_id,
                selected_option=ans.selected_option,
                time_spent=ans.time_spent,
                is_correct=is_correct,
                expected_time=expected_time,
                difficulty=difficulty,
            )
            analyses.append(analysis)

            # 知识点汇总
            if kp_id not in kp_map:
                kp_map[kp_id] = KpAnalysis(
                    kp_id=kp_id,
                    name=question["topic"],
                )
            kpa = kp_map[kp_id]
            kpa.total += 1
            if is_correct:
                kpa.correct += 1
            kpa.questions.append(analysis)

        # 计算平均时间
        for kpa in kp_map.values():
            if kpa.total > 0:
                kpa.avg_time_spent = sum(
                    q.time_spent for q in kpa.questions
                ) / kpa.total
                kpa.avg_expected_time = sum(
                    q.expected_time for q in kpa.questions
                ) / kpa.total

        return analyses, kp_map

    # ── 主诊断流程 ──────────────────────────────────────

    def diagnose(
        self,
        answers: List[SubmittedAnswer],
        subject: str = "mathematics",
        grade: str = "",
        bank: Optional[List[dict]] = None,
    ) -> Tuple[
        Dict[str, float],          # mastery_levels {kp_id: value}
        CognitiveLoadProfile,       # cognitive_load
        List[AnswerAnalysis],      # full analysis
        Dict[str, KpAnalysis],     # per-KP analysis
    ]:
        """核心诊断方法: 分析答案 → 计算掌握度 + 认知负荷"""
        analyses, kp_map = self.analyze_answers(answers, bank)

        # 1. IRT 掌握度估计
        mastery_levels: Dict[str, float] = {}
        for kp_id, kpa in kp_map.items():
            mastery = estimate_mastery_irt(kpa.questions)
            mastery_levels[kp_id] = round(mastery, 3)

        # 2. 认知负荷
        cognitive_load = compute_cognitive_load(analyses)

        return mastery_levels, cognitive_load, analyses, kp_map

    # ── 结果持久化 ──────────────────────────────────────

    async def persist_results(
        self,
        db: AsyncSession,
        student_id: uuid.UUID,
        answers: List[SubmittedAnswer],
        mastery_levels: Dict[str, float],
        cognitive_load: CognitiveLoadProfile,
        analyses: List[AnswerAnalysis],
        kp_map: Dict[str, KpAnalysis],
        subject: str,
        grade: str,
        kp_name_map: Optional[Dict[str, str]] = None,
    ) -> DiagnosisRecord:
        """将诊断结果写入数据库 (diagnosis_records + student_knowledge
        + cognitive_load_records 三张表), 返回主记录"""
        if kp_name_map is None:
            kp_name_map = {}

        # ── 生成雷达图数据 ──
        radar_data_raw = {
            self._get_kp_name(kp_id, kp_name_map): v
            for kp_id, v in mastery_levels.items()
        }

        # ── 构建 mastery JSON (用于 JSONB 存储) ──
        mastery_json = {}
        for kp_id, value in mastery_levels.items():
            name = self._get_kp_name(kp_id, kp_name_map)
            kpa = kp_map.get(kp_id)
            n_questions = kpa.total if kpa else 0
            accuracy = kpa.accuracy if kpa else 0.0
            mastery_json[kp_id] = {
                "mastery": value,
                "level": classify_mastery_level(value),
                "confidence": estimate_confidence(n_questions, accuracy),
                "name": name,
            }

        # ── 构建薄弱点列表 ──
        kp_names = {
            kp_id: self._get_kp_name(kp_id, kp_name_map) for kp_id in mastery_levels
        }
        weak_points_list = generate_weak_points(
            mastery_levels, kp_names, kp_map
        )
        weak_points_json = [
            {
                "kp_id": wp.kp_id,
                "knowledge_point": wp.knowledge_point,
                "reason": wp.reason,
                "severity": wp.severity,
                "suggested_remediation": wp.suggested_remediation,
            }
            for wp in weak_points_list
        ]

        # ── 生成摘要 ──
        summary = generate_summary(mastery_levels, cognitive_load, kp_names)

        # ── 答题记录 JSON ──
        answers_json = [
            {
                "question_id": a.question_id,
                "kp_id": a.kp_id,
                "selected_option": a.selected_option,
                "time_spent": a.time_spent,
                "is_correct": a.is_correct,
                "difficulty": a.difficulty,
                "expected_time": a.expected_time,
            }
            for a in analyses
        ]

        # ── 创建 DiagnosisRecord ──
        record = DiagnosisRecord(
            student_id=student_id,
            subject=subject,
            grade=grade,
            answers=answers_json,
            mastery_levels=mastery_json,
            cognitive_load=cognitive_load.model_dump(),
            cognitive_load_index=cognitive_load.overall,
            weak_points=weak_points_json,
            radar_data=radar_data_raw,
            overall_score=round(
                sum(mastery_levels.values()) / max(len(mastery_levels), 1) * 100, 1
            ),
            learning_style="逻辑推理型",  # 可从答案模式推断
            summary=summary,
            total_questions=len(analyses),
            correct_count=sum(1 for a in analyses if a.is_correct),
            average_time_spent=round(
                sum(a.time_spent for a in analyses) / max(len(analyses), 1), 1
            ),
            expected_average_time=round(
                sum(a.expected_time for a in analyses) / max(len(analyses), 1), 1
            ),
            consecutive_errors=compute_max_consecutive_errors(analyses),
        )
        db.add(record)

        # ── 更新 StudentKnowledge ──
        now = datetime.utcnow()
        for kp_id, value in mastery_levels.items():
            # 尝试将 kp_id 转为 UUID；mock 数据使用字符串格式 (如 "kp_001")，
            # 此时仅写入 DiagnosisRecord，不更新 StudentKnowledge 表
            kp_uuid = _coerce_uuid(kp_id)
            if kp_uuid is None:
                logger.debug(
                    "Skipping StudentKnowledge update for non-UUID kp_id=%s", kp_id
                )
                continue

            # Try update existing
            result = await db.execute(
                select(StudentKnowledge).where(
                    StudentKnowledge.student_id == student_id,
                    StudentKnowledge.kp_id == kp_uuid,
                )
            )
            sk = result.scalar_one_or_none()
            if sk:
                # 加权平均更新 (新结果占 70% 权重)
                sk.mastery_level = round(
                    sk.mastery_level * 0.3 + value * 0.7, 3
                )
                sk.last_assessed_at = now
            else:
                # Insert new
                sk = StudentKnowledge(
                    student_id=student_id,
                    kp_id=kp_uuid,
                    mastery_level=value,
                    last_assessed_at=now,
                )
                db.add(sk)

        # ── 记录认知负荷 ──
        load_record = CognitiveLoadRecord(
            student_id=student_id,
            load_score=cognitive_load.overall,
            context="diagnostic",
            recorded_at=now,
        )
        db.add(load_record)

        await db.flush()
        await db.refresh(record)

        logger.info(
            "Diagnosis persisted: id=%s, student=%s, mastery_avg=%.2f, load=%.2f",
            record.id, student_id,
            sum(mastery_levels.values()) / max(len(mastery_levels), 1),
            cognitive_load.overall,
        )

        return record

    # ── 构建完整响应 ────────────────────────────────────

    def build_response(self, record: DiagnosisRecord) -> DiagnosisResultResponse:
        """从 DB 记录构建前端可用的完整响应"""
        mastery_items = [
            MasteryItem(
                knowledge_point=info["name"],
                kp_id=kp_id,
                mastery=info["mastery"],
                level=info["level"],
                confidence=info["confidence"],
            )
            for kp_id, info in record.mastery_levels.items()
        ]

        weak_points = [
            WeakPoint(**wp) for wp in record.weak_points
        ]

        radar_points = [
            RadarPoint(dimension=dim, value=val)
            for dim, val in record.radar_data.items()
        ]

        return DiagnosisResultResponse(
            id=str(record.id),
            user_id=str(record.student_id),
            created_at=record.created_at.replace(tzinfo=None),
            subject=record.subject,
            grade=record.grade,
            mastery_levels=mastery_items,
            cognitive_load=CognitiveLoadProfile(**record.cognitive_load),
            learning_style=record.learning_style,
            weak_points=weak_points,
            overall_score=record.overall_score,
            summary=record.summary,
            radar_data=radar_points,
            cognitive_load_index=record.cognitive_load_index,
        )


# ── 模块级单例 ─────────────────────────────────────────

diagnosis_service = DiagnosisService()
