# 燕麦智导（AOO Guide Path Planning）后端技术文档

> 本文档基于 `backend/` 目录下的实际代码，系统性地总结后端技术架构、核心服务、数据模型、API 接口、算法实现和部署方案，共 15 个章节。

---

## 目录

1. [系统后端架构概述](#1-系统后端架构概述)
2. [数据库设计与 ORM 模型](#2-数据库设计与-orm-模型)
3. [用户认证与权限控制](#3-用户认证与权限控制)
4. [认知诊断引擎](#4-认知诊断引擎)
5. [AOO 优化算法核心实现](#5-aoo-优化算法核心实现)
6. [AOO 路径生成的异步任务流水线](#6-aoo-路径生成的异步任务流水线)
7. [RAG 知识库与检索增强生成](#7-rag-知识库与检索增强生成)
8. [LLM 集成（讯飞星火与星辰 Agent）](#8-llm-集成讯飞星火与星辰-agent)
9. [智能问答与 Agent 对话服务](#9-智能问答与-agent-对话服务)
10. [学情看板与教师仪表盘数据聚合](#10-学情看板与教师仪表盘数据聚合)
11. [API 接口设计与路由体系](#11-api-接口设计与路由体系)
12. [异步任务与消息队列](#12-异步任务与消息队列)
13. [中间件与全局异常处理](#13-中间件与全局异常处理)
14. [日志、配置与安全](#14-日志配置与安全)
15. [测试、部署与运维](#15-测试部署与运维)

---

## 1. 系统后端架构概述

系统后端采用 **FastAPI + Celery + PostgreSQL + Redis + NumPy 向量存储** 的技术栈，整体遵循分层架构（API 路由层 → 服务层 → 数据访问层），以异步 I/O 为核心设计理念，兼顾高并发 API 响应与 CPU 密集型 AOO 优化的异步解耦。

**核心组件及其职责：**

| 组件 | 技术选型 | 职责 |
|------|---------|------|
| Web 框架 | FastAPI 0.115+ | 提供 RESTful API，自动生成 OpenAPI 文档（`/docs`） |
| 异步数据库 | SQLAlchemy 2.0 + asyncpg | 异步 ORM，支持连接池管理与声明式模型 |
| 数据库 | PostgreSQL | 存储用户、诊断记录、学习路径、知识点等核心业务数据 |
| 缓存/消息队列 | Redis 5.0+ | 双重角色：Celery 消息代理 + 结果后端；AOO 任务进度实时缓存 |
| 异步任务 | Celery 5.4+ | 解耦 CPU 密集型 AOO 优化（500 代进化计算），避免阻塞 HTTP 响应 |
| 向量存储 | 自研 NumPy 向量库 | RAG 知识库的文档嵌入存储与语义检索（进程内，JSON 持久化） |
| LLM | 讯飞星火 Spark API | 提供 AI 诊断摘要生成与知识问答的底层语言模型 |
| Agent 平台 | 讯飞星辰 Agent | 提供具备工具调用能力的对话式学习助手 |

**请求处理流程：**
用户请求经由 Nginx 反向代理到达 FastAPI（端口 8000），API 路由层进行参数校验（通过 Pydantic Schema）和身份认证（JWT Token 验证），业务逻辑在服务层处理。对于认知诊断这类轻量级操作，直接在请求生命周期内同步完成并返回；对于 AOO 路径优化这类耗时操作（10~60 秒），通过 Celery 异步提交到后台 Worker 执行，前端通过轮询 `/status/{task_id}` 获取实时进度和收敛曲线数据。RAG 问答则在独立的 `services/rag/` 模块中，由自研的 NumPy 向量存储完成相似度检索后，调用讯飞星火 LLM 生成带溯源的答案。

**应用生命周期：**
FastAPI 通过 `lifespan` 上下文管理器管理启动和关闭逻辑。启动时自动配置日志系统、检查数据库连接、确保 Demo 用户（`student_demo` / `teacher_demo`）存在；关闭时进行资源清理和日志记录。

---

## 2. 数据库设计与 ORM 模型

系统共设计 **11 张核心数据表**，使用 SQLAlchemy 2.0 声明式映射（`Mapped` + `mapped_column`），所有关联列均声明了 `ForeignKey` 约束，确保数据完整性。主键统一使用 PostgreSQL 的 `UUID` 类型，JSON 类型数据（如掌握度详情、认知负荷画像）使用 `JSONB` 列存储。

### 2.1 ER 模型总览

```
users (用户表)
  ├── 1:N → diagnosis_records (诊断记录)
  ├── 1:N → learning_paths (学习路径)
  ├── 1:N → cognitive_load_records (认知负荷记录)
  ├── 1:N → chat_history (问答历史)
  ├── 1:N → aoo_optimization_logs (AOO 寻优日志)
  └── 1:N → student_knowledge (学生知识点掌握度)

knowledge_points (知识点表)
  ├── 自引用 → parent_id (层级结构: 基础层/核心层/进阶层)
  ├── 1:N → knowledge_graph (前置依赖边，双向)
  ├── 1:N → student_knowledge (学生掌握度关联)
  └── 1:N → path_tasks (路径中的每日任务)

learning_paths (学习路径表)
  └── 1:N → path_tasks (每日任务明细)
```

### 2.2 各表核心字段

**users（用户表）：** 存储用户名（唯一索引）、昵称、邮箱（唯一索引）、bcrypt 哈希密码、角色（`student`/`teacher`）、激活状态、超级管理员标记及时间戳。通过 `relationship` 级联关联 6 张子表（`cascade="all, delete-orphan"`）。

**knowledge_points（知识点表）：** 支持层级结构（通过 `parent_id` 自引用），每条知识点包含名称、描述、学科、难度（1-5）、层级标签（`basic`/`core`/`advanced`）、JSONB 标签数组和扩展元数据。通过 `KnowledgeGraphEdge` 建立前置依赖关系（双向，`outgoing_edges` / `incoming_edges`）。

**knowledge_graph（知识图谱边表）：** 存储知识点间的 `prerequisite`（前置依赖）关系，由 `(source_kp_id, target_kp_id)` 唯一约束防止重复。

**diagnosis_records（诊断记录表）：** 每次诊断测验生成一条记录，包含完整答题明细（JSONB：题目 ID、所选选项、耗时、是否正确、关联知识点 ID）、各知识点掌握度（JSONB：掌握度值、等级、置信度）、认知负荷画像（JSONB：记忆负荷、注意力负荷、加工负荷、综合指数）、薄弱点列表（JSONB：知识点名、原因、严重程度、建议补救措施）、雷达图数据、AI 诊断摘要、综合评分、学习风格标签，以及答题统计数据（总题数、正确数、平均用时、预期用时、最大连续错误数）。

**student_knowledge（学生知识点掌握度表）：** 记录每个学生对每个知识点的当前掌握度（0.0-1.0 float）及最近评估时间。由 `(student_id, kp_id)` 唯一约束保证去重。

**learning_paths（学习路径表）：** 存储 AOO 算法生成的完整学习路径方案，核心数据为 `path_data`（JSONB：包含最佳路径每日任务、备选路径、收敛数据、适应度详情等），同时冗余存储预估总分钟数、完成天数、适应度得分（索引）。

**path_tasks（路径任务表）：** 将学习路径展开为每日学习任务列表，每条记录包含所属路径、对应知识点、第几天、当天顺序、任务类型（`video`/`quiz`/`reading`/`project`）、预估分钟数和完成状态。

**cognitive_load_records（认知负荷记录表）：** 记录每次学习活动后的认知负荷评分（0.0-1.0），标注上下文（`diagnostic`/`study`），支持按时间序列分析负荷变化趋势。

**chat_history（问答历史表）：** 存储用户与 AI 的对话记录，包含问题、回答和引用来源列表（JSONB：知识点 ID、内容片段、相似度评分）。

**aoo_optimization_logs（AOO 寻优日志表）：** 记录每轮 AOO 优化的迭代信息，包括迭代轮次、最佳适应度、平均适应度、种群多样性和收敛详细数据（JSONB），支持历史寻优过程回放。

**questions（题库表）：** 存储诊断题目，包含编号（唯一索引）、关联知识点 ID 列表（JSONB）、学科、难度、题型（`single`/`multiple`）、题目文本、选项列表（JSONB：ID、文本、权重）、正确答案 ID、预期答题时间、答案解析和启用状态。

---

## 3. 用户认证与权限控制

系统采用 **JWT 双 Token 机制** 实现无状态认证，基于 `python-jose` 和 `passlib[bcrypt]` 实现。

### 3.1 JWT Token 设计

- **Access Token**：有效期 30 分钟（`ACCESS_TOKEN_EXPIRE_MINUTES`），`type=access`，包含 `sub`（用户 ID）、`iat`（签发时间）、`exp`（过期时间）。
- **Refresh Token**：有效期 7 天（`REFRESH_TOKEN_EXPIRE_DAYS`），`type=refresh`，仅用于换取新的 Access Token，不用于业务接口认证。
- **签名算法**：HS256，密钥由 `SECRET_KEY` 环境变量配置。

### 3.2 密码安全

- 密码使用 **bcrypt** 哈希算法存储，通过 `passlib.context.CryptContext` 管理。
- 注册和登录时，明文密码经过哈希后存入 `hashed_password` 字段，原始密码不落盘。
- `verify_password()` 用于登录时的密码比对。

### 3.3 认证流程

1. **POST /auth/login**：验证用户名和密码，成功后签发 Access Token + Refresh Token，并返回用户信息（id、username、nickname、email、role、status、createTime）。
2. **POST /auth/register**：创建新用户（检查用户名和邮箱唯一性），自动签发 Token 并返回用户信息。
3. **POST /auth/refresh**：使用 Refresh Token 换发新的 Token 对。
4. **GET /auth/me**：获取当前登录用户的详细信息。

### 3.4 依赖注入与权限控制

**`get_current_user` 依赖函数**（`app/api/deps.py`）：
- 通过 `OAuth2PasswordBearer` 从请求头 `Authorization: Bearer <token>` 中提取 Token。
- 解码验证 Token（检查有效性、类型为 `access`）。
- 从数据库加载用户对象，检查账户是否激活。
- 未认证返回 401，用户被禁用返回 403。

**`get_current_superuser` 依赖函数**：
- 基于 `get_current_user`，进一步检查 `is_superuser` 标志。
- 非管理员返回 403。

**角色级权限控制**：
- 诊断 API：`student_id` 必须与当前登录用户 ID 一致，防止代答。
- 路径 API：只能查看和操作自己的学习路径。
- 教师 API：通过 `_ensure_teacher()` 辅助函数验证 `role == "teacher"` 或 `is_superuser`。
- 知识点/题库管理 API：仅教师或管理员可进行 CRUD 操作。
- 用户管理 API：仅超级管理员可查看用户列表、更新和删除用户。

---

## 4. 认知诊断引擎

认知诊断引擎位于 `app/services/diagnosis/`，负责从答卷数据中评估学生的知识点掌握度和认知负荷状态。

### 4.1 题目获取

诊断 API（`GET /diagnosis/questions`）支持按数量和学科获取题目，优先从数据库 `questions` 表加载，若数据库无数据则降级到内置的 Mock 题库。返回的题目包含完整的选项列表（含权重，支持多选题）和预期答题时间。

### 4.2 诊断分析算法

`diagnosis_service.diagnose()` 是核心分析函数，其输入为学生的答题记录（每题包含 `question_id`、`selected_option`、`time_spent`），输出包括：

**知识点掌握度计算：**
- 根据每题关联的知识点 ID（`kp_ids`），汇总该知识点下所有题目的正确率和答题时间。
- 结合选项权重（多选部分正确给予部分分值），计算加权掌握度（0.0-1.0）。
- 输出掌握度等级标签：`weak`（< 0.4）、`developing`（0.4-0.6）、`proficient`（> 0.6）。

**认知负荷评估：**
- 从三个维度评估：**记忆负荷**（基于答题正确率）、**注意力负荷**（基于答题时间偏差和连续错误数）、**加工负荷**（基于高难度题目的完成情况）。
- 综合认知负荷指数为三维度的加权平均值，归一化到 0.0-1.0。

**薄弱点识别：**
- 筛选掌握度低于 0.6 的知识点，标记为薄弱点。
- 根据错误模式生成严重程度（`mild`/`moderate`/`severe`）和建议补救措施。

**学习风格推断与 AI 摘要：**
- 基于答题模式（错误集中/分散、耗时分布、难度偏好）推断学习风格标签。
- 可选通过 LLM 生成 AI 诊断摘要文本。

### 4.3 结果持久化与响应

诊断结果通过 `persist_results()` 方法结构化存储到 `diagnosis_records` 表（JSONB 列存储完整详情），同时更新 `student_knowledge` 表中各知识点的掌握度和最近评估时间。API 响应中包含简化版数据（`mastery_levels`、`cognitive_load`、`weak_points`、`radar_data`）和完整版 `DiagnosisResultResponse` 对象。

诊断提交成功后，自动触发异步 AOO 路径规划任务（通过 Celery `trigger_aoo_path_planning.delay()`），实现诊断 → 路径生成的无缝衔接。

---

## 5. AOO 优化算法核心实现

AOO（Animated Oat Optimization，燕麦动画优化）算法是系统的核心智能引擎，位于 `app/services/aoo/` 目录，由 6 个模块组成。

### 5.1 模块架构

| 模块 | 文件 | 职责 |
|------|------|------|
| 配置管理 | `aoo_config.py` | 约 30 个超参数定义，支持环境变量覆盖 |
| 适应度计算 | `fitness_calculator.py` | 路径方案质量评估，多目标分解 |
| 核心引擎 | `aoo_engine.py` | 种群初始化、探索、开发、精英保留 |
| 服务编排 | `__init__.py`（AOOService） | 引擎+适应度+配置的统一入口 |
| 持久化服务 | `optimization_service.py` | DB 数据加载、结果持久化 |
| 兼容层 | `fitness.py` | 旧接口兼容重导出 |

### 5.2 算法原理

AOO 算法灵感来源于燕麦种子的传播策略，模拟以下自然阶段完成全局优化：

1. **初始化（公式 1-2）：** 随机生成 N=50 个体的初始种群，每个个体是一个 Dim 维位置向量（维度 = 知识点数量），值域 [0, 1]。
2. **参数计算（公式 3）：** 每代动态计算探索系数 `m`、Lévy 步长 `L`、能量参数 `e` 和收敛因子 `c = 1 - (t/T)³`。
3. **探索阶段 — 种子传播（公式 4-5）：** 三组策略模拟风传播（全局随机）、水传播（向最优个体漂移）和动物传播（向随机个体跳跃），探索率随迭代下降。
4. **开发阶段 — 湿敏滚动（公式 6-10）：** 模拟燕麦种子遇湿后的定向滚动，使用 **Lévy 飞行**（β=1.5）实现局部精细搜索，滚动方向由当前个体与最优个体的距离引导。
5. **开发阶段 — 遇障碍弹射（公式 11-14）：** 当个体陷入局部最优时，触发抛体运动模型跳出，仍组合 Lévy 飞行维持探索深度。
6. **边界约束与精英保留：** 每代完成后裁剪越界位置到 [LB, UB]，并将历史最优个体（精英）强制保留到下一代。

### 5.3 教育场景定制的适应度函数

`FitnessCalculator` 将个体位置向量解码为实际学习路径方案，计算多维适应度：

```
原始位置向量 (sorted indices) → 知识点学习顺序
→ 模拟每日学习进程（考虑艾宾浩斯遗忘曲线，forgetting_factor=0.85）
→ 计算两个目标的加权得分：
   目标1 (最大化): learning_effect = coverage × 0.3 + avg_final_mastery × 0.7
   目标2 (最小化): cognitive_load_score = mean(daily_load) / threshold + difficulty_density × 0.3
   总适应度: fitness = 0.6 × learning_effect - 0.4 × cognitive_load_score
→ 硬约束检查: 前置依赖违反 → fitness = -1e9 (直接淘汰)
```

教育场景的定制参数包括：
- **学习效果模型**：基础学习增益 0.15，掌握度上限 1.0，考虑艾宾浩斯遗忘。
- **认知负荷评估**：单日学习量阈值 3 小时，高难度判定阈值 4.0，连续高难度惩罚 0.5。
- **Pareto 多目标**：从 Pareto 前沿中按权重 (0.7, 0.5, 0.3) 提取三条差异化路径。

### 5.4 收敛控制与早停

- **最大迭代次数**：500 代。
- **早停机制**：连续 50 代最优适应度改进 < 1e-6 时自动终止。
- **自适应参数**：`use_adaptive_params=True` 时，探索率随迭代递减，Lévy 步长自适应缩放。
- **种群快照**：每 10 代记录一次种群快照（最多 50 个），用于前端动画回放。

### 5.5 三条差异化路径

AOOService 在优化完成后自动生成三条路径：
- **效率型（efficiency）：** 学习效果权重 0.7，适合追求快速提升的学生。
- **平衡型（balanced）：** 学习效果权重 0.5，综合考虑效果与负荷。
- **稳健型（robust）：** 学习效果权重 0.3，最大限度降低认知负荷。

每条路径均包含完整的每日任务序列（day → tasks），每项任务标注知识点名称、时长、类型和难度。

### 5.6 配置灵活度

所有约 30 个超参数均支持通过大写环境变量 `AOO_<FIELD>` 覆盖，例如：
- `AOO_POPULATION_SIZE=100` 可增大种群规模。
- `AOO_MAX_ITERATIONS=1000` 可增加迭代次数。
- `AOO_ALPHA=0.8` 可调高学习效果权重。

---

## 6. AOO 路径生成的异步任务流水线

AOO 优化是 CPU 密集型运算（500 代进化 + 50 个个体的适应度评估），单次运行耗时 10-60 秒，因此系统采用 **异步任务 + 轮询** 模式解耦。

### 6.1 任务触发

诊断提交接口（`POST /diagnosis/submit`）在完成诊断分析后，自动调用：
```python
trigger_aoo_path_planning.delay(diagnosis_id=diagnosis_id)
```
将路径规划任务提交到 Celery 消息队列。手动触发则通过 `POST /api/v1/aoo/optimize` 接口（需提交 `student_id`、`diagnosis_id`、`mastery_levels`、`cognitive_load`、可选 `config` 超参）。

### 6.2 Celery 任务实现

核心任务函数为 `run_aoo_optimization`（`app/tasks/aoo_optimization.py`），执行流程：

1. **接收参数**：诊断数据 + 超参配置。
2. **初始化进度追踪**：在 Redis 中创建进度键（`AOO_TASK_PROGRESS_KEY`、`AOO_TASK_STATUS_KEY`、`AOO_TASK_CONVERGENCE_KEY` 等），设置初始状态为 `"processing"`。
3. **创建回调函数**：
   - `progress_callback(progress_pct, current_iter, max_iter, best_f)` → 写入 Redis 进度。
   - `iteration_callback(iter, best_f, avg_f, diversity)` → 累积收敛数据到 Redis 列表。
4. **调用 OptimizationService.run()**：执行完整的 AOO 优化工作流（加载知识点 → 构建适应度计算器 → 运行引擎 → 持久化结果）。
5. **写入完成结果**：将 `AOOOptimizeResult`（best_path、fitness_detail、alternative_paths、convergence_data）序列化到 Redis，设置 1 小时 TTL。
6. **失败处理**：捕获异常后写入错误信息到 Redis，标记任务状态为 `"failed"`。支持最多 3 次重试（指数退避）。

### 6.3 前端轮询接口

`GET /api/v1/aoo/status/{task_id}` 是前端轮询的统一入口（建议 1-2 秒间隔），内部实现：

- **优先从 Redis 读取实时状态**（进度百分比、当前迭代、最佳适应度）。
- **聚合收敛数据**：从 Redis 列表中读取累积的 `ConvergenceSnapshot`（iteration, best_fitness, avg_fitness），构建 `ConvergencePoint` 返回。
- **状态解析**：综合 Redis 缓存 + Celery 原生状态，统一映射为 `pending` / `processing` / `completed` / `failed`。
- **超时检测**：处理中任务超过 10 分钟无更新，自动标记为 `failed`（防止僵尸任务）。
- **完成时加载完整结果**：优先从 Redis 读取（快速），若 Redis 数据过期则以数据库 `learning_paths` 表作为兜底（支持按 `task_id` 精确匹配 `path_data` JSONB 字段）。

### 6.4 Celery 工作器配置

- **消息代理**：Redis（`redis://localhost:6379/0`），结果后端：Redis（`redis://localhost:6379/1`）。
- **任务序列化**：JSON。
- **时区**：Asia/Shanghai。
- **时间限制**：硬限制 30 分钟，软限制 25 分钟。
- **Worker 配置**：每个 Worker 最多处理 200 个任务后重启（防止内存泄漏），预取数 = 1（公平调度）。

---

## 7. RAG 知识库与检索增强生成

RAG（Retrieval-Augmented Generation）模块位于 `app/services/rag/`，基于**自研的 NumPy 轻量向量存储**实现，支持文档索引、语义检索和知识增强问答。

> **设计取舍说明：** 早期方案曾计划引入 ChromaDB，最终改为自研实现。原因是：本项目的知识库规模为千级文档块，远未达到需要专用向量数据库的量级；而 ChromaDB 会连带引入 `sqlite`/`onnxruntime` 等重量级依赖，显著增加镜像体积与部署复杂度。改用 NumPy 矩阵 + JSON 持久化后，检索性能在该数据规模下完全够用，且**不新增任何外部服务**。

### 7.1 模块架构

- **`vector_store.py`**：`VectorStore` 核心类。向量以 `np.ndarray` 矩阵常驻内存；写入时同步持久化到单个 JSON 文件，采用「写临时文件后 rename」的原子写入避免损坏。存储阶段对向量做 L2 归一化，使检索时的**点积直接等价于余弦相似度**，省去逐次计算模长的开销。
- **`knowledge_base.py`**：`KnowledgeBase` 核心类，编排加载 → 切分 → 向量化 → 存储的完整链路，并对外提供检索接口。
- **`document_loader.py`**：文档加载器，支持 PDF、TXT、Markdown 格式文件的读取和文本提取。
- **`chunker.py`**：文本分割器，按语义边界将长文档切割为指定大小的文本块。
- **`embedder.py`**：向量化服务，**优先调用讯飞星火 Embedding API**（`text-embedding`，1536 维），失败时回退到 BGE 本地模型，具备重试与超时保护。

### 7.2 文档索引流程

1. **文档加载**：遍历指定目录，使用对应解析器提取文本内容。
2. **文本分割**：按 `chunk_size=800` 字符、`chunk_overlap=150` 字符的滑动窗口将文档切分为文本块，保留文档元数据（文件名、页码、章节）。
3. **向量化**：调用讯飞星火 Embedding API（失败回退 BGE 本地模型）将文本块转换为 1536 维向量。
4. **存储**：向量经 L2 归一化后追加到内存矩阵，并连同元数据原子写入 JSON 持久化文件。

### 7.3 语义检索与增强生成

**检索流程（`kb.query()`）：**
1. 用户问题 → 嵌入模型编码 → 向量相似度检索。
2. 与内存中的归一化向量矩阵做点积（等价余弦相似度），返回 Top-K（默认 5）个最相似的文档块。
3. 按 `similarity_threshold=0.5` 过滤低质量结果。
4. 按上下文长度限制（`max_context_chars=4000`）截断检索结果。

**增强生成：**
- 将检索到的文档上下文 + 用户问题组装为增强 Prompt。
- 调用讯飞星火 LLM 生成带溯源的答案。
- 答案附带完整的引用来源列表（文档名、页码、章节、内容片段、相似度评分、引用编号）。

### 7.4 API 接口

- **POST /rag/query**：知识问答（输入问题，返回答案 + 来源列表 + 置信度 + Token 用量）。
- **POST /rag/index**：索引指定目录中的文档（支持递归、清空重建）。
- **GET /rag/stats**：获取知识库统计信息（文档块数量、集合大小等）。
- **POST /rag/reset**：重置知识库（清空数据并重建）。

RAG 模块的向量存储与检索**仅依赖 NumPy**（核心依赖中已包含），因此开箱即用、无需额外安装。仅当需要启用 BGE 本地嵌入回退时，才需安装 `requirements-ai.txt` 中的 sentence-transformers、torch 等大体积可选包；默认走讯飞 Embedding API 的链路不需要它们。

---

## 8. LLM 集成（讯飞星火与星辰 Agent）

系统集成了两套讯飞 AI 能力，位于 `app/services/llm/` 和 `app/services/agent/` 目录。

### 8.1 讯飞星火 Spark API

`app/services/llm/xunfei.py` 封装了讯飞星火大模型的 WebSocket 调用：

- **模型版本**：`spark-x`（通过 `XF_MODEL` 配置）。
- **API 地址**：`wss://spark-api.xf-yun.com/v3.5/chat`。
- **认证方式**：基于 `APP_ID` + `API_KEY` + `API_SECRET` 的签名鉴权（HMAC-SHA256）。
- **功能**：支持多轮对话上下文管理，可配置温度、最大 Token 数、Top-K 等生成参数。
- **应用场景**：认知诊断的 AI 摘要生成、RAG 知识问答的答案生成。

### 8.2 讯飞星辰 Agent 平台

`app/services/agent/xingchen_client.py` 封装了讯飞星辰 Agent 平台的 HTTP API：

- **协议**：HTTP POST，支持 JSON 一次性返回和 SSE 流式返回两种模式。
- **认证**：通过 `XINGCHEN_AGENT_API_KEY` 请求头认证。
- **会话管理**：基于 `flow_id`（Agent 流程 ID）和 `session_id` 管理多轮对话上下文。
- **工具调用**：Agent 支持调用预定义的工具（如知识点查询、学习路径检索），返回结果中包含 `tool_calls` 结构化数据。
- **会话 TTL**：`XINGCHEN_SESSION_TTL=3600` 秒，Redis 管理的会话在超时后自动失效。
- **配置检查**：`GET /agent/health` 返回 Agent 是否已配置（`configured` 字段），便于前端判断是否展示 Agent 对话入口。

### 8.3 双通道设计

系统为 AI 对话提供了双通道：
- **RAG 问答通道**（`/rag/query`）：适用于教材知识检索场景，返回带文档溯源的答案。
- **Agent 对话通道**（`/agent/chat` 和 `/chat/agent`）：适用于开放式学习辅导场景，支持工具调用和多轮上下文。

两个通道共享统一的消息格式和响应结构，前端可通过切换 `stream=True/False` 选择流式或一次性返回。

---

## 9. 智能问答与 Agent 对话服务

### 9.1 AgentService 核心服务

`AgentService`（`app/services/agent/__init__.py`）是对话服务的统一编排层，整合了 `XingchenAgentClient`（API 客户端）和 `SessionManager`（Redis 会话管理）：

- **`chat(session_id, message, user_id)`**：非流式对话，发送消息后等待完整响应，自动存储用户和助手消息到会话历史。
- **`chat_stream(session_id, message, user_id)`**：SSE 流式对话，生成器函数逐块 yield `data: {...}\n\n` 格式的 SSE 事件，支持熔断器保护（连续错误自动降级）。
- **`get_history(session_id, user_id, limit)`**：获取会话历史，解析工具调用结果。
- **`list_user_sessions(user_id)`**：列出用户的所有会话。
- **`delete_session(session_id, user_id)`**：删除会话（含所有权校验）。

系统预设了 `DEFAULT_SYSTEM_PROMPT`，定义 AI 助手为"燕麦智导"学习助手，专注于知识点解析、学习建议和路径规划辅导。

### 9.2 SessionManager 会话管理

基于 Redis 实现的无状态会话管理：

- **Redis 键设计**：
  - `agent:session:{session_id}:meta` → 会话元数据（用户 ID、创建时间、消息数、模型名）。
  - `agent:session:{session_id}:messages` → 消息列表（JSON 序列化）。
  - `agent:user:{user_id}:sessions` → 用户会话索引（Set 类型）。
- **消息管理**：`append_message()` 自动裁剪超出上限的消息（FIFO），注入时间戳。
- **Agent 消息构建**：`get_messages_for_agent()` 自动插入系统提示词，构建完整的对话上下文。
- **生命周期**：支持 `renew_session()` 续期、`delete_session()` 删除、`clear_all_user_sessions()` 清空。

### 9.3 流式输出与错误处理

- **流式格式**：SSE（Server-Sent Events），Content-Type 为 `text/event-stream`，包含 `Cache-Control: no-cache` 和 `X-Accel-Buffering: no` 头以禁用 Nginx 缓冲。
- **熔断器**：连续 3 次 Agent API 调用失败后自动熔断，返回降级提示。
- **错误分类**：网络超时 → 提示"服务繁忙"；Agent 返回错误 → 透传错误详情；未知异常 → 安全兜底消息。

### 9.4 对话历史持久化

所有问答记录自动存储到 PostgreSQL 的 `chat_history` 表，包含问题、答案、引用来源（JSONB），支持历史查询和学习行为分析。

---

## 10. 学情看板与教师仪表盘数据聚合

### 10.1 学生端看板

`/api/v1/dashboard` 前缀下提供 4 个端点：

- **GET /dashboard/overview**：聚合概览数据（总学习分钟数、已完成/总任务数、已掌握/总知识点数、连续学习天数、最近学习日期）。
- **GET /dashboard/cognitive-load-trend**：获取最近 N 次诊断的认知负荷变化趋势（三维度 + 综合指数 + 相应评分）。
- **GET /dashboard/calendar-activity**：获取指定月份的学习日历活动（JSONB `dailyTasks` 解码为日期 → 学习分钟数 → 任务数 → 涉及知识点）。
- **GET /dashboard/suggestions**：基于最新诊断结果生成 AI 学习建议（薄弱点专项练习建议、认知负荷预警、交替学习法、艾宾浩斯复习策略）。

### 10.2 教师端仪表盘

`/api/v1/teacher` 前缀下提供 7 个端点，所有端点均通过 `_ensure_teacher()` 校验教师权限：

- **GET /teacher/class-overview**：班级总览（学生总数、平均掌握度、平均认知负荷、平均路径完成率、高负荷人数、低掌握度人数）。
- **GET /teacher/students**：学生列表（含学情摘要），支持按字段排序（`sortBy`：avgMastery / cognitiveLoad / pathCompletion / weakPointCount）。
- **GET /teacher/weak-knowledge-points**：全班共性薄弱知识点 Top-N，按受影响人数降序聚合（从所有诊断记录的 `weak_points` JSONB 中提取并去重计数）。
- **GET /teacher/mastery-trend**：全班每日平均掌握度变化趋势（按日期聚合所有学生的诊断评分）。
- **GET /teacher/alerts**：预警学生列表（高认知负荷 > 0.7 或低掌握度 < 0.4），标注严重程度（`danger`/`warning`）和原因类型（`highLoad`/`lowMastery`/`both`）。
- **GET /teacher/students/{student_id}**：单个学生学情详情下钻（掌握度详情列表、认知负荷三维度、薄弱点详情含补救建议）。
- **GET /teacher/dashboard**：仪表盘聚合接口（一次性返回 overview + students + weakKps + masteryTrend + alerts，减少前端请求次数）。

### 10.3 数据聚合技术特点

- **JSONB 灵活查询**：掌握度、认知负荷、薄弱点等非结构化数据存储在 PostgreSQL 的 JSONB 列中，通过 Python 字典操作灵活提取和聚合。
- **内存聚合**：薄弱知识点和趋势分析通过 Python 字典在内存中聚合（无需 GROUP BY JSONB 列），降低查询复杂度。
- **批量查询优化**：学生列表接口先批量查询所有学生，再逐个查询最新诊断和路径（通过 LIMIT 1 + ORDER BY 降序），避免 N+1 问题。

---

## 11. API 接口设计与路由体系

### 11.1 路由结构

系统 API 统一挂载在 `/api/v1` 前缀下，通过 `router.py` 聚合 13 个子路由模块：

| 前缀 | 模块 | 端点数量 | 描述 |
|------|------|---------|------|
| `/api/v1` | `health` | 1 | 健康检查 |
| `/api/v1/auth` | `auth` | 4 | 登录、注册、Token 刷新、用户信息 |
| `/api/v1/users` | `users` | 4 | 用户 CRUD（管理员专用） |
| `/api/v1/diagnosis` | `diagnosis` | 5 | 获取题目、提交答案、查看结果、历史 |
| `/api/v1/knowledge-points` | `knowledge` | 6 | 知识点 CRUD + 知识图谱 |
| `/api/v1/questions` | `questions` | 6 | 题库 CRUD + 批量导入 |
| `/api/v1/aoo` | `aoo` | 2 | 触发 AOO 优化 + 轮询状态 |
| `/api/v1/rag` | `rag` | 4 | RAG 问答、索引、统计、重置 |
| `/api/v1/agent` | `agent` | 5 | Agent 对话、历史、会话管理、健康检查 |
| `/api/v1/chat` | `chat` | 1 | 统一对话入口（兼容层） |
| `/api/v1/teacher` | `teacher` | 7 | 教师仪表盘全套端点 |
| `/api/v1/learning-paths` | `learning_paths` | 5 | 学习路径获取、切换、删除 |
| `/api/v1/dashboard` | `dashboard` | 4 | 学生学情看板 |

### 11.2 统一响应格式

所有 API 返回采用统一的 `ResponseBase[T]` 泛型结构：

```json
{
  "code": 200,
  "message": "操作成功",
  "data": { ... }
}
```

分页接口使用 `PaginatedResponse[T]`，额外包含 `total`、`page`、`page_size`、`pages` 字段。

### 11.3 核心 API 端点速查

**认证模块：**
- `POST /auth/login` — 请求：`{username, password}` → 返回：`{token, userInfo}`
- `POST /auth/register` — 请求：`{username, password, nickname?, email?, role?}` → 返回：`{token, userInfo}`
- `POST /auth/refresh` — 请求：`refresh_token` (query) → 返回：`{access_token, refresh_token}`
- `GET /auth/me` — 返回当前用户详情

**诊断模块：**
- `GET /diagnosis/questions?count=15&subject=人工智能导论` — 获取诊断题目列表
- `POST /diagnosis/submit` — 请求：`{answers, subject, grade, student_id}` → 返回：`{mastery_levels, cognitive_load, weak_points, diagnosis_id, radar_data, result}`
- `GET /diagnosis/latest` — 获取最新诊断结果
- `GET /diagnosis/{diagnosis_id}` — 获取指定诊断详情
- `GET /diagnosis?page=1&page_size=10` — 诊断历史列表
- `GET /diagnosis/history?page=1&page_size=10` — 诊断历史列表（兼容路径）

**AOO 优化模块：**
- `POST /aoo/optimize` — 请求：`{student_id, diagnosis_id, mastery_levels, cognitive_load, config?}` → 返回：`{task_id, status: "queued", progress: 0}`
- `GET /aoo/status/{task_id}` — 返回：`{status, progress, current_iteration, max_iterations, best_fitness, convergence_data, result?, error?}`

**RAG 知识库：**
- `POST /rag/query` — 请求：`{question, top_k?, temperature?, max_tokens?}` → 返回：`{answer, sources, confidence, retrieval_count, model, token_usage}`
- `POST /rag/index` — 请求：`{directory, recursive?, clear_existing?}` → 返回：`{message, chunks_indexed}`
- `GET /rag/stats` — 知识库统计
- `POST /rag/reset` — 重置知识库

**Agent 对话：**
- `POST /agent/chat` — 请求：`{session_id, message, user_id, stream?}` → 流式/非流式返回
- `POST /chat/agent` — 统一聊天入口（兼容层）
- `GET /agent/history/{session_id}?user_id=xxx` — 会话历史
- `GET /agent/sessions?user_id=xxx` — 用户会话列表
- `DELETE /agent/sessions/{session_id}?user_id=xxx` — 删除会话
- `GET /agent/health` — Agent 配置检查

**教师仪表盘：**
- `GET /teacher/class-overview` — 班级总览
- `GET /teacher/students?sortBy=avgMastery&order=desc` — 学生列表
- `GET /teacher/weak-knowledge-points?topN=5` — 共性薄弱点
- `GET /teacher/mastery-trend?days=30` — 掌握度趋势
- `GET /teacher/alerts` — 预警学生
- `GET /teacher/students/{student_id}` — 学生详情下钻
- `GET /teacher/dashboard` — 仪表盘聚合数据

**学习路径：**
- `GET /learning-paths/current` — 当前活跃路径
- `GET /learning-paths/history?page=1&page_size=10` — 历史路径
- `POST /learning-paths/select` — 切换备选方案
- `GET /learning-paths/{path_id}` — 路径详情
- `DELETE /learning-paths/{path_id}` — 删除路径

---

## 12. 异步任务与消息队列

### 12.1 Celery 架构

系统使用 Celery 5.4+ 作为分布式任务队列，Redis 同时作为消息代理（broker）和结果后端（result backend）：

```
FastAPI HTTP Worker                 Celery Worker
      │                                  │
      │ POST /aoo/optimize               │
      ├─ delay(task) ──→ Redis Queue ──→ ├─ run_aoo_optimization()
      │                    (broker)      │    ├─ load diagnosis data
      │                                  │    ├─ run AOO engine (10-60s)
      │  GET /aoo/status/{id}            │    ├─ persist results to DB
      ├─ redis.get(progress) ←─ Redis ── ├─ redis.set(result, TTL=1h)
      │  (轮询 1-2s 间隔)     (cache)    │
      ▼                                  ▼
   返回进度/收敛数据                  返回完整结果
```

### 12.2 任务定义

目前系统定义了三类 Celery 任务：

1. **`run_aoo_optimization`（aoo_optimization.py）**：核心 AOO 优化任务，包含完整的进度报告、收敛数据累积和结果持久化逻辑。
2. **`trigger_aoo_path_planning`（diagnosis.py）**：诊断完成后的自动触发任务（占位），支持最多 3 次重试和指数退避。
3. **`example_long_task`（example.py）**：示例长时任务，用于验证 Celery 配置。

### 12.3 任务生命周期

```
PENDING → STARTED (processing) → SUCCESS (completed)
                               → FAILURE (failed, 含重试)
                               → REVOKED (手动取消)
```

- **进度追踪**：通过 `self.update_state(state="PROGRESS", meta={...})` 在任务内部更新状态。
- **收敛数据流**：每代迭代完成后通过 `iteration_callback` 将 `ConvergenceSnapshot` 追加到 Redis 列表。
- **结果 TTL**：完成结果在 Redis 中存储 1 小时后自动过期，数据库 `learning_paths` 表作为永久存储兜底。
- **超时处理**：硬限制 30 分钟（`task_time_limit`），软限制 25 分钟（`task_soft_time_limit`），状态轮询接口额外施加 10 分钟死线检测。

### 12.4 Worker 启动

```bash
celery -A app.tasks.celery_app worker --loglevel=info --concurrency=2
```

生产环境建议使用 `--concurrency` 控制并发数（CPU 密集型任务不宜过大），配合 `--max-tasks-per-child=200` 防止内存泄漏。

---

## 13. 中间件与全局异常处理

### 13.1 CORS 中间件

系统在 `main.py` 中注册了 `CORSMiddleware`，关键配置：

- **允许来源**：从 `CORS_ORIGINS` 环境变量（JSON 数组）解析，默认为 `["http://localhost:5173", "http://localhost:3000"]`。
- **允许凭证**：`allow_credentials=True`（支持跨域携带 Cookie/Authorization 头）。
- **允许方法**：`["*"]`（全部 HTTP 方法）。
- **允许头部**：`["*"]`（全部请求头）。
- **暴露头部**：`X-Total-Count`（分页总数）、`Content-Disposition`（文件下载）。

### 13.2 全局异常处理器

`register_exception_handlers()` 注册了三层异常处理（从具体到通用）：

1. **`RequestValidationError`（422）**：Pydantic 参数校验失败时触发，返回结构化错误详情（`errors` 包含字段级错误信息）。
2. **`HTTPException`**：业务逻辑主动抛出的 HTTP 异常，统一包装为 `{code, message, data}` 格式。
3. **`Exception`（500）**：兜底处理器，捕获所有未预期的异常，记录完整 Traceback 日志，返回安全的 "内部服务异常" 消息（不泄露内部错误细节）。

### 13.3 数据库会话管理

`get_db()` 依赖注入函数实现请求级的数据库会话管理：
- 请求进入时创建 `AsyncSession`。
- `yield session` 后将控制权交给路由处理。
- 处理完成后自动 `commit()`。
- 异常时自动 `rollback()`。
- `finally` 块中确保 `close()`，防止连接泄漏。

---

## 14. 日志、配置与安全

### 14.1 配置管理

系统使用 `pydantic-settings` 的 `BaseSettings` 实现类型安全的配置管理：

- **加载来源**：自动从 `backend/.env` 文件读取（`env_file`），同时支持环境变量覆盖。
- **单例模式**：使用 `@lru_cache()` 装饰 `get_settings()` 确保全局只有一个配置实例。
- **计算属性**：`sync_database_url`（将 `+asyncpg` 替换为纯 PostgreSQL URL供 Alembic 使用）、`redis_url`（自动拼接密码）、`cors_origins_list`（JSON 解析 CORS 白名单）。

### 14.2 配置项分类

| 类别 | 环境变量 | 说明 |
|------|---------|------|
| 应用 | `PROJECT_NAME`、`VERSION`、`APP_HOST`、`APP_PORT`、`DEBUG` | 基本元数据与运行模式 |
| JWT | `SECRET_KEY`、`ALGORITHM`、`ACCESS_TOKEN_EXPIRE_MINUTES`、`REFRESH_TOKEN_EXPIRE_DAYS` | 认证密钥与过期策略 |
| PostgreSQL | `POSTGRES_HOST`、`POSTGRES_PORT`、`POSTGRES_USER`、`POSTGRES_PASSWORD`、`POSTGRES_DB`、`DATABASE_URL` | 数据库连接 |
| Redis | `REDIS_HOST`、`REDIS_PORT`、`REDIS_DB`、`REDIS_PASSWORD`、`REDIS_URL` | 缓存与消息队列 |
| Celery | `CELERY_BROKER_URL`、`CELERY_RESULT_BACKEND` | 任务队列连接 |
| 讯飞星火 | `XF_APP_ID`、`XF_API_KEY`、`XF_API_SECRET`、`XF_API_URL`、`XF_MODEL` | LLM API 配置 |
| 讯飞星辰 | `XINGCHEN_AGENT_API_URL`、`XINGCHEN_AGENT_API_KEY`、`XINGCHEN_AGENT_FLOW_ID`、`XINGCHEN_SESSION_TTL` | Agent 平台配置 |
| RAG | `RAG_PERSIST_DIR`、`RAG_CHUNK_SIZE`、`RAG_CHUNK_OVERLAP`、`RAG_SIMILARITY_THRESHOLD`、`RAG_TOP_K`、`RAG_MAX_CONTEXT_CHARS` | 知识库参数 |
| 日志 | `LOG_LEVEL`、`LOG_FORMAT`（`console`/`json`）、`LOG_FILE_PATH` | 日志行为 |
| CORS | `CORS_ORIGINS`（JSON 数组字符串） | 跨域白名单 |

### 14.3 日志系统

`setup_logging()`（`app/core/logging.py`）提供双模式日志：

- **Console 格式（开发）**：`[2026-07-30 14:30:00] INFO     app.module | message`，清晰可读。
- **JSON 格式（生产）**：`{"time": "...", "level": "INFO", "module": "...", "message": "..."}`，易于接入 ELK/Loki 等日志采集系统。
- **双输出**：同时写入控制台（stdout）和日志文件（`./logs/app.log`），日志目录自动创建。
- **噪声抑制**：降低 `uvicorn.access`、`sqlalchemy.engine`、`httpx` 的日志级别到 WARNING，避免刷屏。

### 14.4 安全措施

- **密码哈希**：bcrypt 单向哈希，不可逆。
- **JWT 签名**：HS256 算法，密钥不低于 32 字符。
- **Token 类型区分**：`access` 和 `refresh` 类型分离，refresh token 仅用于换发，不用于业务接口。
- **CORS 白名单**：仅允许配置的来源域名，防止跨站请求伪造。
- **Docker 安全**：Nginx 反向代理配置安全头（`X-Content-Type-Options`、`X-Frame-Options`、`X-XSS-Protection`）。
- **错误信息安全**：500 异常返回通用消息，不暴露内部堆栈。

---

## 15. 测试、部署与运维

### 15.1 测试

测试文件位于 `backend/tests/`，使用 pytest 框架。AOO 算法有 60+ 个测试用例，覆盖算法核心组件（初始化、探索、开发、收敛、适应度计算、Pareto 提取、早停逻辑）。LLM 服务、RAG 管线、Agent 服务、认知诊断引擎及 API 路由模块目前暂无自动化测试覆盖。

运行测试：
```bash
cd backend
pytest tests/ -v
```

### 15.2 开发环境部署

```bash
# 1. 创建虚拟环境
cd backend
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/macOS

# 2. 安装依赖
pip install -r requirements.txt
# 如需 RAG 功能：
pip install -r requirements-ai.txt

# 3. 配置环境变量
cp .env.example .env  # 编辑数据库连接等配置

# 4. 启动 PostgreSQL + Redis（Docker 或本地服务）

# 5. 运行数据库迁移
alembic upgrade head

# 6. 启动 FastAPI（热重载模式）
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 7. 启动 Celery Worker（另一个终端）
celery -A app.tasks.celery_app worker --loglevel=info --concurrency=2
```

### 15.3 Docker 生产部署

**后端 Dockerfile**（`backend/Dockerfile`）采用多阶段构建：
- 基础镜像：`python:3.11-slim`。
- 依赖安装：使用阿里云 PyPI 镜像加速（`-i https://mirrors.aliyun.com/pypi/simple/`）。
- 启动脚本：`entrypoint.sh` 自动化以下流程：
  1. 等待 PostgreSQL 就绪（最多 30 次重试，每次 2 秒，通过 `asyncpg` 连接测试）。
  2. 等待 Redis 就绪（失败不阻塞，警告后继续）。
  3. 运行 Alembic 数据库迁移（`alembic upgrade head`），失败时降级为 `_create_tables.py` 直接建表。
  4. 启动 uvicorn 服务（`0.0.0.0:8000`）。

**Docker Compose 完整栈**（根目录 `docker-compose.yml` / `docker-compose.prod.yml`）：
- `postgres` 服务：PostgreSQL 16，健康检查 + 数据卷持久化。
- `redis` 服务：Redis 7，健康检查。
- `backend` 服务：FastAPI 应用，依赖 postgres + redis，端口 8000。
- `celery_worker` 服务：Celery Worker，依赖 redis + postgres，执行 AOO 优化等异步任务。
- `nginx` 服务：前端静态文件 + API 反向代理，端口 80/443。

### 15.4 环境变量清单

**Docker 环境**（`backend/.env.docker`）的关键差异：
- `POSTGRES_HOST=postgres`（Docker 服务名）。
- `REDIS_HOST=redis`（Docker 服务名）。
- `DATABASE_URL=postgresql+asyncpg://aoo_user:...@postgres:5432/aoo_guide_path`。

### 15.5 数据库迁移

使用 Alembic 管理数据库版本：
```bash
# 生成迁移脚本
alembic revision --autogenerate -m "描述"

# 升级到最新
alembic upgrade head

# 回滚一步
alembic downgrade -1

# 查看当前版本
alembic current
```

### 15.6 其他辅助脚本

- **`create_demo_users.py`**：手动创建 Demo 用户（如今已集成到应用 `lifespan` 事件中自动执行）。
- **`setup_local.py`**：本地环境一键设置脚本。
- **`env_bootstrap.py`**：环境变量自检与诊断工具。
- **`test_api_flow.py`**：端到端 API 工作流验证脚本（诊断→路径生成→看板查询）。
- **`e2e_test.py`**：完整端到端测试脚本。

### 15.7 性能与扩展

- **数据库连接池**：`pool_size=20` + `max_overflow=10`，`pool_pre_ping=True` 自动检测断连，`pool_recycle=3600` 定期回收。
- **Celery 独立引擎**：`OptimizationService` 使用独立的 `create_async_engine`（`pool_size=5`，`pool_recycle=1800`），避免与 FastAPI 请求池竞争。
- **Redis TTL 策略**：AOO 结果 1 小时过期（热点数据），数据库永久存储（冷数据），兼顾查询速度和存储效率。
- **日志轮转**：建议配合 Linux `logrotate` 管理 `./logs/app.log`，防止日志文件无限增长。

---

> **文档版本**：v1.0 · **生成日期**：2026-07-30 · **基于代码分支**：main
