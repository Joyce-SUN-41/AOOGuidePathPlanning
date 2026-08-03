# 燕麦智导（AOO Guide）—— 技术创新核心

> 本文档聚焦于项目的**核心技术创新点**，以讯飞星火大模型为智能交互中枢，以 AOO（Animated Oat Optimization）算法为路径优化引擎，系统总结两大引擎的架构设计、算法原理、工程实现与创新价值，共 15 个章节。

---

## 目录

1. [双引擎协同架构：LLM + AOO 的创新融合范式](#1-双引擎协同架构llm--aoo-的创新融合范式)
2. [AOO 燕麦动画优化算法：从自然现象到教育优化](#2-aoo-燕麦动画优化算法从自然现象到教育优化)
3. [教育场景定制适应度函数：五因子学习效果模型](#3-教育场景定制适应度函数五因子学习效果模型)
4. [Pareto 多目标前沿：三类差异化路径生成机制](#4-pareto-多目标前沿三类差异化路径生成机制)
5. [异步优化流水线：Celery + Redis 的实时进度反馈](#5-异步优化流水线celery--redis-的实时进度反馈)
6. [讯飞星火大模型集成：SparkClient 高可用客户端](#6-讯飞星火大模型集成sparkclient-高可用客户端)
7. [RAG 检索增强生成：六阶段知识库管线](#7-rag-检索增强生成六阶段知识库管线)
8. [讯飞星辰 Agent：具备工具调用能力的对话助手](#8-讯飞星辰-agent具备工具调用能力的对话助手)
9. [Agent 对话编排：SessionManager + SSE 流式架构](#9-agent-对话编排sessionmanager--sse-流式架构)
10. [认知诊断双模型融合：IRT 2-PL + DINA](#10-认知诊断双模型融合irt-2-pl--dina)
11. [认知负荷三维度计算：记忆/注意/加工的量化建模](#11-认知负荷三维度计算记忆注意加工的量化建模)
12. [前端 AOO 寻优可视化：ECharts 帧播放与种群动态](#12-前端-aoo-寻优可视化echarts-帧播放与种群动态)
13. [熔断器与多层容错机制：高可用保障设计](#13-熔断器与多层容错机制高可用保障设计)
14. [学习路径闭环数据流：从诊断到优化的完整链路](#14-学习路径闭环数据流从诊断到优化的完整链路)
15. [技术栈创新总结与对比分析](#15-技术栈创新总结与对比分析)

---

## 1. 双引擎协同架构：LLM + AOO 的创新融合范式

燕麦智导的核心架构由两大引擎协同驱动，形成"理解—优化—交付"的完整智能闭环：

```
┌──────────────────────────────────────────────────────────────────────┐
│                      双引擎协同架构                                  │
│                                                                      │
│  ┌──────────────────────────┐      ┌──────────────────────────────┐  │
│  │   讯飞星火LLM引擎          │      │     AOO路径优化引擎            │  │
│  │   (智能交互中枢)            │ ───→ │     (路径优化核心)            │  │
│  │                          │      │                              │  │
│  │  • 认知诊断AI摘要生成      │      │  • N=50, Dim=N_KP 种群初始化  │  │
│  │  • RAG知识问答 (NumPy向量)│      │  • 500代进化搜索              │  │
│  │  • Agent工具调用对话      │      │  • 探索+开发 六阶段算法        │  │
│  │  • 多轮上下文理解          │      │  • Pareto三路径输出           │  │
│  │  • SSE流式输出            │      │  • Celery异步解耦             │  │
│  └──────────┬───────────────┘      └──────────┬───────────────────┘  │
│             │                                  │                      │
│             ▼                                  ▼                      │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │                    数据闭环与协同                                │  │
│  │  Diagnosis → DiagnosisResult → AOO优化 → LearningPath          │  │
│  │       ↑                              ↓                          │  │
│  │       └──────── 反馈迭代 ←──── CognitiveLoad + Mastery          │  │
│  └─────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

### 1.1 协同机制

| 环节 | LLM 引擎角色 | AOO 引擎角色 |
|------|-------------|-------------|
| **认知诊断** | 生成自然语言诊断摘要，解释薄弱点原因 | 接收 mastery_levels 作为优化输入 |
| **路径生成** | 提供知识背景与学科上下文 | 500 代种群进化，输出最优学习顺序 |
| **知识问答** | 通过 RAG + NumPy 向量检索增强，给出溯源答案 | 不参与（纯检索+生成） |
| **Agent 对话** | 通过星辰 Agent 平台协调工具调用（路径规划/RAG问答） | 作为工具被 Agent 调用 |
| **反馈迭代** | 分析学生新诊断结果，更新学习建议 | 基于新的 mastery_levels 重新优化路径 |

### 1.2 创新点

1. **智能中枢 + 优化引擎的松耦合设计**：LLM 负责语言理解与生成，AOO 负责数学优化，职责清晰，互不干扰
2. **标准化数据契约**：诊断输出（mastery_levels, cognitive_load）直接作为 AOO 输入，无缝衔接
3. **两种 LLM 接入互补**：Spark（通用大模型）+ Xingchen Agent（工具调用）覆盖不同场景需求
4. **异步解耦**：AOO 优化（10-60s CPU 密集型）通过 Celery 异步执行，不影响 LLM API 响应

---

## 2. AOO 燕麦动画优化算法：从自然现象到教育优化

### 2.1 算法灵感来源

AOO（Animated Oat Optimization）算法灵感来源于燕麦种子的自然传播策略。燕麦种子通过**风传播、水传播、动物携带**实现大范围扩散（探索），到达适宜环境后通过**湿敏滚动**和**遇障碍弹射**进行局部精细定位（开发）。这一"先广泛探索、后精细开发"的双阶段策略完美对应于学习路径优化问题的求解需求。

### 2.2 算法六阶段数学建模

算法在 `AOOEngine` 类中实现（`backend/app/services/aoo/aoo_engine.py`），完整六阶段流程如下：

#### Phase 0: 种群初始化（公式 1-2）

```
X_i = LB + r_i ⊙ (UB - LB),  i = 1, 2, ..., N
```

- **N** = 50（可配置）个个体，每个个体是一个**Dim**维向量（Dim = 知识点数）
- 每个维度值 ∈ [0, 1]，通过 `argsort` 解码为标准的学习顺序排列
- 值越小 → 越早学习，值越大 → 越晚学习

#### Phase 1: 动态参数计算（公式 3）

```
m = 0.5 × (r / Dim)       # 种子质量
L = N × (r / Dim)         # 芒长
e = 0.5 × (r / Dim)       # 偏心系数
c = 1 - (t / T_max)³      # 动态调整因子（三次衰减）
```

**创新点**：参数 `c` 采用三次幂衰减而非线性衰减，使得算法在前期保持较大的搜索步长，后期快速收敛。`c` 的变化曲线从 1.0 快速下降到约 0.5，再缓慢趋近于 0，完美匹配"前期大范围探索→后期精细开发"的需求。

#### Phase 2: 探索阶段（公式 4-5）— 三组传播策略

探索概率采用**余弦退火**策略，从 0.3 逐渐降低到 0.05：

```
探索率(t) = 0.05 + (0.3 - 0.05) × 0.5 × (1 + cos(π × t / T_max))
```

种群按适应度排序后分为三等份，执行三种不同的传播策略：

| 组别 | 策略 | 公式 | 物理含义 |
|------|------|------|---------|
| 前 1/3（精英） | 风传播 | `X_new = X + (c/π)(2r - 1)UB` | 大范围均匀扩散 |
| 中 1/3 | 水传播 | `X_new = X + m·L·(X_r1 - X_r2)` | 随机方向漂流 |
| 后 1/3（弱势） | 动物传播 | `X_new = X + e·c·(X_best - X)` | 向最优个体靠拢 |

**创新点**：按适应度分层分配传播策略，精英个体负责探索新区域，弱势个体向最优解靠拢，确保种群多样性不丢失。

#### Phase 3: 开发阶段—滚动（公式 6-10）

对适应度高于平均值的个体执行 Lévy 飞行局部搜索：

```
R = m × L × (X_r1 - X_r2)
X_new(i) = X_best + R + c × Lévy(Dim) ⊙ X_best
```

Lévy 飞行采用 β=1.5 的稳定分布，通过 Mantegna 算法生成：

```
σ_u = [Γ(1+β)sin(πβ/2) / (Γ((1+β)/2)β·2^((β-1)/2))]^(1/β)
Lévy = σ · u / |v|^(1/β)
u ~ N(0, σ_u²),  v ~ N(0, 1)
```

**创新点**：使用 `math.gamma` 替代 scipy 依赖，零额外依赖实现标准 Lévy 飞行；β=1.5 的选取在全局搜索与局部收敛间取得平衡。

#### Phase 4: 开发阶段—弹射（公式 11-14）

对适应度低于平均值的个体执行抛体运动：

```
J = e × (X_best - X(i))
X_new(i) = X_best + J + c × Lévy(Dim) ⊙ X_best
```

**创新点**：滚动与弹射分别针对"优质个体"和"弱势个体"采取不同策略——优质个体在最优解周边精细搜索，弱势个体进行更大步长的跳跃逃离。

#### Phase 5: 边界约束 + 精英保留

- `np.clip(population, LB, UB)` 确保解空间约束
- **精英保留**：若历史全局最优优于当前代最差个体，则替换之
- **早停机制**：连续 50 代无改进（tolerance=1e-6）且种群多样性 < 0.01 时触发
- **种群快照**：每 10 代捕获一次种群快照（最多 50 个），供前端可视化回放

### 2.3 超参数体系

`AOOConfig` 提供约 30 个可调超参数，全部支持环境变量覆盖：

| 类别 | 参数 | 默认值 | 说明 |
|------|------|--------|------|
| 种群规模 | `population_size` | 50 | 种群个体数 |
| 迭代控制 | `max_iterations` | 500 | 最大进化代数 |
| 早停 | `early_stop_patience` | 50 | 停滞容忍代数 |
| Lévy 飞行 | `levy_beta` | 1.5 | 稳定分布参数 |
| 探索率 | `exploration_rate` | 0.3 | 初始探索概率 |
| 随机种子 | `seed` | 42 | 可复现实验 |

### 2.4 收敛指标

每代记录六个维度的收敛数据：

```
ConvergenceData {
  iterations:    [1, 2, 3, ...]        // 迭代轮次
  best_fitness:  [0.12, 0.25, ...]     // 每代最优适应度
  avg_fitness:   [0.05, 0.15, ...]     // 每代平均适应度
  diversity:     [0.8, 0.6, ...]       // 种群多样性 ∈ [0,1]
  median_fitness:[0.04, 0.13, ...]     // 每代中位数适应度
  q1_fitness:    [0.02, 0.08, ...]     // 每代 Q1 四分位数
  q3_fitness:    [0.08, 0.22, ...]     // 每代 Q3 四分位数
  snapshots:     [Snapshot1, ...]       // 种群快照（每10代）
}
```

种群多样性计算公式：

```
diversity = (1/N) Σ_i ||X_i - X_centroid|| / ||UB_vec - LB_vec||
```

---

## 3. 教育场景定制适应度函数：五因子学习效果模型

### 3.1 适应度总公式

`FitnessCalculator`（`backend/app/services/aoo/fitness_calculator.py`）实现了教育场景的完整适应度计算：

```
fitness = α × learning_effect - β × cognitive_load_score

learning_effect = 0.3 × coverage + 0.7 × avg_final_mastery
cognitive_load_score = avg_daily_load / threshold + 0.3 × difficulty_density
```

其中 **α=0.6**（学习效果权重）、**β=0.4**（认知负荷权重），体现"学习效果优先，认知负荷为约束"的设计原则。

### 3.2 五因子学习增益模型

单个知识点的学习增益由五个因子综合决定：

```
gain(kp) = base_gain × position_factor × prereq_bonus × difficulty_adjust × learning_speed × focus_bonus
```

| 因子 | 公式 | 创新点 |
|------|------|--------|
| **基础增益** | `base_gain = 0.15` | 每个知识点的基础掌握度提升量 |
| **位置因子** | `max(regency, primacy×0.8)` | 结合**近因效应**（刚学完保留好）与**首因效应**（早学有更多巩固时间），使用 `forgetting_factor^rank` 建模 |
| **前置依赖奖励** | `learned_prereqs / total_prereqs` | 前置知识点掌握的越多，增益越大 |
| **难度调整** | `1 - 0.15 × (difficulty/5)` | 高难度知识点增益略低，需更长时间消化 |
| **学习速度** | `student.learning_speed` | 个性化学习速度系数 |
| **重点加成** | `1.5 (if in focus_areas)` | 教师/系统标注的重点知识点获得额外增益 |

### 3.3 遗忘曲线建模

创新性地在适应度函数中集成了**艾宾浩斯遗忘曲线**：

```
recency_factor = forgetting_factor ^ normalized_rank    # 近因：越靠后越新鲜
primacy_factor = forgetting_factor ^ (1 - normalized_rank)  # 首因：越靠前巩固越多
position_factor = max(recency_factor, primacy_factor × 0.8)
```

- `forgetting_factor = 0.85`：越大遗忘越慢
- 使用 U 形曲线同时建模首因和近因效应
- 靠前的知识点有更多回顾巩固时间，靠后的知识点刚学过印象更深

### 3.4 认知负荷惩罚

认知负荷评估包含两个维度：

1. **单日学习量惩罚**：`avg_daily_load / threshold（默认 3h）`— 超出阈值则惩罚
2. **难度密集度惩罚**：连续高难度（≥4 级）知识点超过 2 个时，按 `consecutive^1.5 × 0.5` 指数惩罚
3. **全局难度均匀性**：使用变异系数（CV）惩罚每天难度分布不均

### 3.5 硬约束：前置依赖检查

```
若前置依赖未满足 → strict模式: fitness = -1e9
若前置依赖未满足 → 梯度模式: fitness = base - violations × 100
```

双模式设计：优化迭代使用梯度惩罚（引导搜索向可行区域），Pareto 前沿提取使用硬约束（只保留合法解）。

---

## 4. Pareto 多目标前沿：三类差异化路径生成机制

### 4.1 双目标优化问题

AOO 算法同时优化两个相互制衡的目标：

```
目标1 (最大化): learning_effect  — 追求最优学习效果
目标2 (最小化): cognitive_load_score — 控制认知负荷
```

传统的单目标优化（如加权求和）只能输出一条路径，无法满足不同学习风格学生的需求。

### 4.2 非支配排序算法

`FitnessCalculator._non_dominated_sort()` 实现了 Pareto 最优性判断：

```
A 支配 B 当且仅当:
  learning_effect(A) >= learning_effect(B)
  AND (-cognitive_load_score(A)) >= (-cognitive_load_score(B))
  AND (至少一个严格大于)
```

从种群中筛选出所有非支配解，构成 Pareto 前沿。

### 4.3 三类路径自动分类

从 Pareto 前沿中自动提取三条代表性路径：

| 路径类型 | 选择策略 | 适用场景 |
|----------|---------|---------|
| **效率型 (efficiency)** | `learning_effect` 最高 | 追求最短时间掌握最多知识，适合突击复习 |
| **稳健型 (robust)** | `cognitive_load_score` 最低 | 控制学习压力，适合基础薄弱或时间充裕的学生 |
| **平衡型 (balanced)** | 距理想点最近（归一化欧氏距离） | 学习效果与认知负荷的最佳权衡，默认推荐 |

分类算法使用**归一化欧氏距离**计算每个非支配解到理想点 `(max_learning, min_cognitive)` 的距离，选取最近者作为平衡型路径。

### 4.4 前端三路径对比

前端的 `PathView.vue` 以 Tab 切换方式展示三条路径，用户可以直观对比：

- 效率型：任务密集，日均学习量大，进阶知识点多
- 平衡型：任务分布均匀，难易交替，节奏舒适
- 稳健型：基础夯实优先，每天任务量少，有充足复习时间

每条路径配有独立的甘特图、统计面板和适应度详情。

---

## 5. 异步优化流水线：Celery + Redis 的实时进度反馈

### 5.1 异步解耦架构

AOO 优化是 CPU 密集型计算（500 代 × 50 个体 × 适应度评估），耗时 10-60 秒。直接阻塞 HTTP 请求会导致超时。项目采用 Celery + Redis 异步流水线：

```
┌─────────┐    POST /aoo/optimize     ┌──────────┐   submit_task   ┌──────────┐
│  Vue 3  │ ─────────────────────────→ │ FastAPI  │ ──────────────→ │  Redis   │
│  前端    │ ←── { task_id: "abc123" } │  路由层   │                  │  Queue   │
└────┬────┘                           └──────────┘                  └────┬─────┘
     │                                                                    │
     │  GET /aoo/status/abc123 (轮询 1-2s)                               │
     │  { status: "processing", progress: 45%, ... }                     │
     │                                                                    ▼
     │                                                           ┌──────────────┐
     │                                                           │ Celery Worker│
     │                                                           │ (AOO 优化)   │
     │                                                           │ 500代×50个体 │
     └──────────────────────────────────────────────────────────→│ 进度上报Redis│
                                                                 └──────────────┘
```

### 5.2 Redis 进度追踪设计

任务状态通过多个 Redis Key 实现细粒度追踪：

| Key | 类型 | 内容 |
|-----|------|------|
| `aoo:task:{task_id}:status` | String | `pending/processing/completed/failed` |
| `aoo:task:{task_id}:progress` | String | 进度百分比 (0-100) |
| `aoo:task:{task_id}:result` | JSON | 最优路径 + 适应度详情 + Pareto 前沿 |
| `aoo:task:{task_id}:convergence` | JSON | 收敛曲线（迭代数、最优/平均适应度、多样性） |
| `aoo:task:{task_id}:error` | String | 错误信息（failed 状态） |

### 5.3 每代回调机制

`AOOEngine.optimize()` 支持 `on_iteration` 回调参数，每代迭代后调用：

```python
on_iteration(iteration, best_fitness, avg_fitness, diversity)
```

Celery Task 将此回调数据实时写入 Redis，前端每 1-2 秒轮询 `GET /aoo/status/{task_id}`，获取最新收敛数据并驱动 ECharts 动画更新。

### 5.4 结果持久化兜底

为防止 Redis 数据丢失（如进程重启），`OptimizationService._persist_results()` 将完整结果写入 PostgreSQL 的三张表：

- `learning_paths`：路径主体（最优路径 + 备选路径 + 收敛数据）
- `path_tasks`：每日任务明细（知识点、类型、预估时间、完成状态）
- `aoo_optimization_logs`：每代寻优日志（迭代数、适应度、多样性）

---

## 6. 讯飞星火大模型集成：SparkClient 高可用客户端

### 6.1 客户端架构设计

`SparkClient`（`backend/app/services/llm/spark_client.py`）封装了讯飞星火大模型的完整 HTTP 接入，核心组件包括：

| 组件 | 职责 |
|------|------|
| **ChatResponse / StreamChunk** | 统一响应数据模型 |
| **TokenCounter** | 中英文字符级 Token 估算器（无需 tiktoken） |
| **CircuitBreaker** | 熔断器，防止级联故障 |
| **请求构建器** | OpenAI 兼容的 payload 组装 |
| **重试引擎** | 指数退避重试（最多 3 次） |
| **SSE 解析器** | 流式 `data:` 行解析 |

### 6.2 Token 上下文管理

`TokenCounter` 使用差异化字符估算：

- **中文字符**：1.5 tokens/char（UTF-8 3 字节，语义密度高）
- **英文/数字**：0.25 tokens/char（约 4 字符 = 1 token）

上下文窗口管理策略：

```
1. 优先保留 system 消息（始终不裁剪）
2. 从最早的 user/assistant 对话轮次开始裁剪
3. 为响应预留 safety_margin = 512 tokens
4. 80% 窗口阈值预警，100% 自动裁剪
```

### 6.3 指数退避重试

```
delay = min(1.0 × 2^attempt, 30.0)
attempt 1: 1s → attempt 2: 2s → attempt 3: 4s → 总尝试: 4次（含初始）
```

可重试状态码：`{429, 500, 502, 503, 504}`，认证失败（401/403）不重试直接抛异常。

### 6.4 双模式对话

| 模式 | 方法 | 返回类型 | 适用场景 |
|------|------|---------|---------|
| 非流式 | `chat()` | `ChatResponse` | 诊断摘要、简短问答 |
| 流式 SSE | `chat_stream()` | `AsyncGenerator[StreamChunk]` | 聊天界面、实时内容生成 |

### 6.5 Function Calling 支持

请求支持传入 `tools` 参数（OpenAI 兼容的工具定义格式），响应自动解析 `tool_calls`，为 Agent 服务层提供 Function Calling 能力。

---

## 7. RAG 检索增强生成：六阶段知识库管线

### 7.1 完整管线架构

`KnowledgeBase`（`backend/app/services/rag/knowledge_base.py`）实现了完整的 RAG 六阶段管线：

```
阶段1: 文档加载   →  阶段2: 智能分块   →  阶段3: 向量化
DocumentLoader        DocumentChunker       FallingBackEmbedder
(PDF/TXT/MD)          (800+150 滑动窗口)     (Spark API → BGE → 哈希降级)

阶段4: 向量存储   →  阶段5: 语义检索   →  阶段6: RAG 问答生成
VectorStore.add()     VectorStore.search()   SparkClient.chat()
(NumPy + JSON 持久化) (Top-K=5, 阈值=0.5)    (增强 Prompt + 溯源标注)
(L2 归一化→点积=余弦)
```

### 7.2 智能文档分块器

`DocumentChunker` 实现**递归字符分割 + 滑动窗口重叠**：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `chunk_size` | 800 字符 | 目标块大小 |
| `chunk_overlap` | 150 字符 | 块间重叠大小 |
| `min_chunk_size` | 100 字符 | 短块自动合并 |

分隔符优先级：`\n\n` → `\n` → `。` → `！` → `？` → `；` → `，` → ` ` → 字符级

`MarkdownChunker` 扩展了基础分块器，按 `#`～`###` 标题层级优先分割，保留章节结构信息。

### 7.3 增强 Prompt 模板

`RAGPromptBuilder` 构建包含来源标注的结构化 Prompt：

```
System: "你是燕麦智导知识助手..."
User:   "请根据以下参考文档回答：
         [来源1] ... (chunk content)
         [来源2] ...
         用户问题：{question}
         要求：基于文档回答，标注来源，区分'文档记载'和'知识补充'"
```

每个检索到的 chunk 最多取 1500 字符，总上下文限制 4000 字符，超出则截断。

### 7.4 多维置信度计算

`_calculate_confidence()` 综合四个因素评估答案置信度：

```
confidence = max_score × 0.4 + avg_score × 0.3 + length_score × 0.15 + count_score × 0.15
```

- **max_score (40%)**：最高检索相似度
- **avg_score (30%)**：平均检索相似度
- **length_score (15%)**：答案长度合理性（50~3000 字符为佳）
- **count_score (15%)**：检索结果数量（2-5 个最佳）

---

## 8. 讯飞星辰 Agent：具备工具调用能力的对话助手

### 8.1 Agent 能力模型

`XingchenAgentClient`（`backend/app/services/agent/xingchen_client.py`）接入讯飞星辰 Agent 平台，提供**工具调用型**对话能力：

```
POST /v1/flow/run
{
  "session_id": "sess_abc",
  "flow_id": "learning_assistant",
  "stream": true,
  "inputs": {
    "message": "帮我生成一条学习路径",
    "user_id": "student_001"
  }
}
```

### 8.2 系统提示词设计

Agent 的 `DEFAULT_SYSTEM_PROMPT` 定义了三个核心能力域：

1. **学习路径规划**：调用 AOO 路径规划工具，根据诊断结果生成最优路径
2. **学科知识问答**：调用 RAG 知识库问答工具，基于 NumPy 向量存储检索增强
3. **学习陪伴**：基于诊断数据生成个性化建议、错题归因、复习提醒

### 8.3 多格式响应解析

Agent 客户端兼容两种响应格式：

**OpenAI 兼容**：`{choices: [{message: {content, tool_calls}}]}`

**星辰原生**：`{code, data: {answer, tool_calls}}`

工具调用统一标准化为：

```python
{
  "tool_name": "path_planning",
  "tool_call_id": "call_xxx",
  "arguments": {"kp_ids": [...], "preferences": {...}},
  "result": {...},
  "status": "completed",  # completed / failed / pending
  "error": None
}
```

### 8.4 与 SparkClient 的互补关系

| 维度 | SparkClient | XingchenAgentClient |
|------|-----------|-------------------|
| API 类型 | 纯 LLM（chat/completions） | Agent 平台（flow/run） |
| 认证方式 | `Bearer API_KEY:API_SECRET` | `Bearer API_KEY` + `X-API-Key` |
| 工具调用 | 原生 Function Calling | 平台内置工具编排 |
| 适用场景 | 自由对话、RAG 生成 | 任务型对话（路径规划/诊断分析） |
| TTL 管理 | 无状态（由上层管理） | Redis SessionManager 管理 |

---

## 9. Agent 对话编排：SessionManager + SSE 流式架构

### 9.1 三层编排架构

`AgentService`（`backend/app/services/agent/__init__.py`）作为对话业务编排层，协调客户端与会话管理器：

```
┌─────────────┐
│  FastAPI     │  /api/v1/agent/chat/stream
│  Route       │
└──────┬──────┘
       │
       ▼
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ AgentService│────→│SessionManager    │────→│ Redis           │
│ (编排层)     │     │ (Redis 会话管理) │     │ agent:session:* │
└──────┬──────┘     └──────────────────┘     └─────────────────┘
       │
       ▼
┌──────────────────┐
│XingchenAgentClient│
│ (Agent API 调用)   │
└──────────────────┘
```

### 9.2 Redis 会话三键设计

`SessionManager` 使用三组 Redis Key 管理会话生命周期：

| Key Pattern | 类型 | 内容 | TTL |
|-------------|------|------|-----|
| `agent:session:{id}:meta` | Hash | user_id, created_at, updated_at, msg_count, model | 1h |
| `agent:session:{id}:messages` | List | 对话消息 JSON 序列化，最多 50 条 | 1h |
| `agent:user:{uid}:sessions` | Set | 用户的所有 session_id | 2h |

消息追加使用 Redis Pipeline 批量操作，包含自动裁剪（LTRIM）和 TTL 续期。

### 9.3 SSE 流式事件协议

`AgentService.chat_stream()` 返回结构化的 SSE 事件流：

```
data: {"type":"start", "session_id":"sess_abc", "timestamp":...}

data: {"type":"content", "content":"正在分析"}

data: {"type":"tool_call", "tool_call":{...}}    // 可选

data: {"type":"content", "content":"您的诊断结果..."}

data: {"type":"done", "session_id":"sess_abc", "finish_reason":"stop",
       "content_length":512, "tool_calls_count":2, "usage":{...}}
```

异常情况（熔断、超时、内部错误）通过 `{"type":"error", ...}` 事件通知前端。

### 9.4 对话历史格式化

`get_messages_for_agent()` 从 Redis 拉取最近 20 条消息，自动注入 system prompt：

```python
messages = session_mgr.get_messages_for_agent(
    session_id="sess_abc",
    system_prompt="你是燕麦智导学习助手...",
    limit=20
)
# → [{"role":"system","content":"..."},
#    {"role":"user","content":"..."},
#    {"role":"assistant","content":"...", "tool_calls":[...]},
#    ...]
```

---

## 10. 认知诊断双模型融合：IRT 2-PL + DINA

### 10.1 IRT 2-PL 掌握度估计

`DiagnosisService`（`backend/app/services/diagnosis/__init__.py`）使用**IRT（Item Response Theory）2-PL 模型**进行掌握度估计：

```
P(答对 | θ, b, a, c) = c + (1-c) / (1 + exp(-D × a × (θ - b)))
```

其中：
- **θ**：学生能力（待估计的参数，最终映射到掌握度 [0, 1]）
- **b**：题目难度（从 1-5 映射到 [-1.6, 1.6]）
- **a**：区分度（默认 1.0）
- **c**：猜测参数（默认 0.1）
- **D**：缩放常数（1.7）

使用**极大似然估计（MLE）** 通过 Newton-Raphson 迭代优化 θ：

```
梯度: ∂logL/∂θ = Σ (r - P) × D×a × (P-c)/(1-c) / (P×(1-P))
Fisher Info: I(θ) = Σ P'² / (P×(1-P))
更新: θ_new = θ + gradient / fisher_info
```

最多 50 次迭代，收敛阈值 1e-4。最终通过 logistic 变换映射到 [0, 1]：

```
mastery = 1 / (1 + exp(-θ))
```

### 10.2 DINA 辅助模型

DINA（Deterministic Inputs, Noisy "And" gate）模型用于估计**粗心率（slip）**和**猜测率（guess）**：

```
slip = P(答错 | 掌握了所有属性)  → 从高掌握度(>0.7)的答错率估计
guess = P(答对 | 未掌握所有属性) → 从低掌握度(<0.3)的答对率估计
```

### 10.3 掌握度分级

掌握度值映射到四级标准：

| 范围 | 等级 | 含义 |
|------|------|------|
| [0.85, 1.0] | excellent | 优秀 — 知识结构扎实 |
| [0.70, 0.85) | proficient | 熟练 — 大部分掌握良好 |
| [0.50, 0.70) | developing | 发展中 — 需针对性提升 |
| [0.00, 0.50) | weak | 薄弱 — 需系统重新学习 |

### 10.4 经验置信度估计

基于答题数量与准确率一致性的经验置信度估计（非 Wilson score interval）：

```
confidence = min(1.0, n_questions/10.0) × (1 - |accuracy - 0.5| × 0.3)
```

题目越多置信度越高，极端准确率（0 或 1）因样本可能不充分而降低置信度。

---

## 11. 认知负荷三维度计算：记忆/注意/加工的量化建模

### 11.1 三维度模型

`compute_cognitive_load()` 从答题行为中量化三个维度的认知负荷：

#### 维度 1: 记忆负荷（Memory Load）— 权重 30%

```
time_ratio = time_spent / expected_time
memory_load = sigmoid(avg_time_ratio, center=1.2, steepness=2.5)
```

- 答题时间超出预期越多 → 记忆检索负担越重
- 使用 logistic 函数平滑映射到 [0, 1]

#### 维度 2: 注意力负荷（Attention Load）— 权重 40%

```
attention_load = error_rate × 0.6 + easy_error_rate × 0.4
```

- **error_rate**：总错误率
- **easy_error_rate**：简单题（difficulty ≤ 2）的错误率，权重更高（因为简单题犯错更说明注意力分散）

#### 维度 3: 加工负荷（Processing Load）— 权重 30%

```
processing_load = time_variance_score × 0.5 + consecutive_error_score × 0.5
```

- **time_variance_score**：答题时间标准差 / 1.5（时间波动大 → 认知加工不稳定）
- **consecutive_error_score**：max_consecutive_errors / 5（连续错误 → 思维疲劳或挫败）

### 11.2 综合负荷

```
overall = memory × 0.3 + attention × 0.4 + processing × 0.3
```

负荷等级划分：

| 范围 | 等级 | 建议 |
|------|------|------|
| > 0.6 | 高负荷 | 适当放慢学习节奏 |
| 0.35-0.6 | 适中 | 保持当前状态 |
| < 0.35 | 低负荷 | 可增加挑战难度 |

### 11.3 认知负荷的记录与追踪

`CognitiveLoadRecord` 表每次诊断后写入一条记录，前端 Dashboard 展示历次诊断的负荷趋势折线图，帮助师生发现学习状态变化规律。

---

## 12. 前端 AOO 寻优可视化：ECharts 帧播放与种群动态

### 12.1 帧播放动画机制

`AOOAnimation.vue` 组件将收敛数据逐帧渲染为 ECharts 图表：

```
数据加载 → 计算总帧数 → 创建定时器 → 逐帧更新图表
                                              │
                          ┌────────────────────┘
                          ▼
           每帧更新: 收敛曲线 × 种群散点 × 统计面板
```

### 12.2 收敛曲线图（双Y轴）

| Y轴 | 内容 | 配色 |
|-----|------|------|
| 左Y轴 | 适应度值 [0, 1] | 红/蓝/灰色 |
| 右Y轴 | 种群多样性 [0%, 100%] | 橙色 |

四条曲线：
- **最优适应度**（红色实线 + 渐变面积填充）
- **平均适应度**（蓝色虚线）
- **中位数适应度**（灰色点线，默认隐藏）
- **种群多样性**（橙色实线 + 渐变面积填充）

曲线数据仅展示到当前播放帧，随动画推进逐步绘制。

### 12.3 种群散点分布图

当前帧个体以彩色散点展示：
- **红色**（12px + 白色描边 + 发光阴影）：精英个体（当前最优）
- **蓝色**：普通个体
- **绿色**：探索中个体（刚完成弹射或跳跃）

历史帧个体以半透明灰色小点（4px）"幽灵化"呈现，形成粒子轨迹效果。

### 12.4 实时统计面板

| 指标 | 展示方式 |
|------|---------|
| 当前迭代/总迭代 | 大号数字（JetBrains Mono 等宽字体） |
| 最优适应度 | 红色数字 |
| 平均适应度 | 蓝色数字 |
| 种群多样性 | 橙色数字 + 迷你进度条 |
| 种群规模 | 灰色数字 |

### 12.5 动画控制

- **播放/暂停**：控制帧自动推进
- **速度调节**：1x / 2x / 4x / 8x
- **进度条**：可拖拽跳转到任意帧
- **历史日志**：从 `AOOOptimizationLog` 表中加载历史寻优记录进行回放

---

## 13. 熔断器与多层容错机制：高可用保障设计

### 13.1 双层熔断器

项目在两个 LLM 客户端中分别实现了独立的熔断器：

```
SparkClient.circuit_breaker      ← 保护星火 LLM 调用
XingchenAgentClient._circuit_breaker ← 保护星辰 Agent 调用
```

### 13.2 熔断器状态机

```
             失败次数 < 5                   连续失败 ≥ 5
    ┌──── CLOSED ─────────────────────────────────→ OPEN ────┐
    │ (正常通行)                                        (拒绝请求) │
    │         ←────────────────────────────────                │
    │              成功（重置计数）                      30s 后   │
    │                                                       │
    │                  试探成功             试探失败          │
    └──→ HALF_OPEN ←──────── CLOSED    OPEN ←── HALF_OPEN ←─┘
              (有限放行1次)
```

### 13.3 SparkClient 四层容错

| 层级 | 机制 | 参数 |
|------|------|------|
| 1. 熔断 | CircuitBreaker | 5 次连续失败 → 熔断，30s 恢复 |
| 2. 重试 | 指数退避 | 最多 3 次，初始 1s，max 30s |
| 3. 上下文裁剪 | Token 窗口管理 | 8192 limit，自动裁剪旧消息 |
| 4. 降级 | fallback_response | API 未配置时返回 Mock 响应 |

### 13.4 XingchenAgentClient 三层容错

| 层级 | 机制 | 参数 |
|------|------|------|
| 1. 熔断 | _CircuitBreaker | 5 次连续失败 → 熔断，30s 恢复 |
| 2. 重试 | 指数退避 | 最多 3 次，401/403 不重试 |
| 3. 降级 | _fallback_response | API 未配置时返回 Mock 响应 |

### 13.5 全局异常处理

FastAPI 应用层三层异常处理器：

```
1. RequestValidationError (422) → 返回结构化验证错误
2. HTTPException               → 透传状态码 + detail
3. Exception (500)             → 兜底通用错误 + 日志记录
```

---

## 14. 学习路径闭环数据流：从诊断到优化的完整链路

### 14.1 数据闭环全景

```
   ┌────────────────────────────────────────────────────────────────┐
   │                     学习路径闭环                                │
   │                                                                │
   │  ① 认知诊断         ② AOO 路径优化        ③ 路径交付          │
   │  ┌──────────┐      ┌──────────────┐      ┌──────────┐         │
   │  │ 10-15题  │ ───→ │ IRT 掌握度    │ ───→ │ 甘特图   │         │
   │  │ 作答     │      │ 认知负荷计算   │      │ 时间轴   │         │
   │  │          │      │ ↓             │      │ 变体选择 │         │
   │  │          │      │ 500代 AOO     │      │          │         │
   │  │          │      │ Pareto 三路径 │      │          │         │
   │  └──────────┘      └──────────────┘      └──────────┘         │
   │       ↑                                        │               │
   │       │              ④ 学习反馈               │               │
   │       └──────────── 重新诊断 ─────────────────┘               │
   │                                                                │
   │  ⑤ 并行分析线                                                  │
   │  ┌──────────────────────────────────────────────────────┐      │
   │  │ 教师仪表盘: 全班掌握度趋势 / 共性薄弱点 / 预警名单     │      │
   │  │ 学生看板:   雷达图 / 负荷趋势 / 学习日历 / AI建议      │      │
   │  └──────────────────────────────────────────────────────┘      │
   └────────────────────────────────────────────────────────────────┘
```

### 14.2 关键数据流细节

| 步骤 | 输入 | 处理 | 输出 | 存储 |
|------|------|------|------|------|
| 诊断 | 学生答题数据 | IRT 2-PL 掌握度估计 + 三维认知负荷 | mastery_levels, cognitive_load, weak_points | `diagnosis_records`, `student_knowledge`, `cognitive_load_records` |
| 优化 | 诊断结果 + 知识点图谱 | 500 代 AOO + Pareto 前沿 | 最优路径 + 备选路径 + 收敛数据 | `learning_paths`, `path_tasks`, `aoo_optimization_logs` |
| 问答 | 用户问题 | RAG 检索 + LLM 生成 | 答案 + 溯源 + 置信度 | `chat_history` |
| 反馈 | 新诊断结果 | 加权平均更新（新占 70%） | 更新的 mastery_levels | `student_knowledge`（UPDATE） |

### 14.3 掌握度加权更新

学生知识点掌握度采用**递增加权平均**更新策略：

```python
new_mastery = old_mastery × 0.3 + new_estimate × 0.7
```

新诊断结果占 70% 权重，既保留历史信息又对新数据快速响应。

---

## 15. 技术栈创新总结与对比分析

### 15.1 技术创新矩阵

| 创新维度 | 传统方案 | 燕麦智导方案 | 创新价值 |
|----------|---------|-------------|---------|
| **路径规划算法** | 静态规则（按难度排序、教师编排） | AOO 元启发式算法（500 代进化 + Pareto 多目标） | 自动生成三条差异化路径，适应不同学习风格 |
| **适应度函数** | 单一指标（完成率/正确率） | 五因子学习增益 + 三维认知负荷 + 遗忘曲线 | 平衡学习效果与认知负担，更符合教育规律 |
| **智能交互** | 规则问答 / 预设话术 | 讯飞星火 LLM + RAG 检索增强 + 星辰 Agent | 自然语言理解 + 文档溯源的精准问答 |
| **诊断模型** | 简单正确率 = 掌握度 | IRT 2-PL + DINA 双模型 + 经验置信度估计 | 考虑难度/区分度/猜测/粗心的精确掌握度估计 |
| **认知负荷** | 无量化或单一主观评价 | 三维度客观量化（记忆/注意/加工） | 数据驱动的学习状态监测 |
| **系统架构** | 同步单体 | Celery 异步解耦 + Redis 实时进度 + DB 持久化兜底 | 不阻塞用户体验，10-60s 优化透明化 |
| **可视化** | 静态甘特图 | ECharts 帧播放 + 种群动态 + Pareto 前沿展示 | 算法过程透明可解释，提升 AI 信任度 |
| **高可用** | 基础 try-catch | 双层熔断器 + 指数退避 + Token 裁剪 + 降级 | 确保 LLM 不可用时系统不崩溃 |

### 15.2 工程特色

| 特色 | 实现细节 |
|------|---------|
| **零额外依赖的 Lévy 飞行** | 使用 `math.gamma` 替代 scipy，纯 numpy 实现标准 Lévy 分布 |
| **约 30 个环境变量可调超参数** | `AOOConfig` 支持全部参数环境变量覆盖（`AOO_POPULATION_SIZE` 等） |
| **中英文混合 Token 估算** | 无需 tiktoken 依赖，中文字符 1.5 token，英文 0.25 token |
| **双模式适应度评估** | strict 模式（硬约束，-1e9）用于 Pareto 提取，gradient 模式（梯度惩罚）用于优化搜索 |
| **首因+近因双遗忘曲线** | 同时建模先学后巩固（首因）和后学更清晰（近因）的双效应 |
| **AOO 引擎 pytest 测试** | `test_aoo_engine.py` 覆盖引擎初始化、适应度计算、Lévy 飞行、非支配排序、早停逻辑等算法组件（其余服务/路由模块待补充测试） |

### 15.3 系统能力象限

```
          高
          ↑
  个性化  │                         ★ 燕麦智导
  程度    │              (AOO Pareto + LLM Agent)
          │
          │  传统 LMS
          │  (固定路径)
          │                             自适应学习
          │                             (简单规则)
          │
          └──────────────────────────────────→ 高
                    智能交互深度
```

燕麦智导在"个性化程度"和"智能交互深度"两个维度上均处于行业领先位置：通过 AOO 算法实现多目标优化的个性化路径推荐，通过讯飞星火 LLM + RAG 实现具备溯源能力的自然语言智能交互。

---

> **文档版本**：v1.0 | **生成日期**：2026-07-30 | **基于代码版本**：`main` 分支当前最新
