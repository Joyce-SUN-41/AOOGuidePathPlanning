# 动麦智导（AOO Guide）后端技术文档

## 1. 技术栈与项目结构

### 1.1 核心技术栈

| 类别 | 技术选型 | 说明 |
|------|---------|------|
| Web 框架 | FastAPI 0.104+ | 异步高性能，OpenAPI 自动文档 |
| ORM | SQLAlchemy 2.0 | 2.0 风格 Typed API，类型安全 |
| 数据库 | PostgreSQL 15+ | 生产级关系型数据库 |
| 异步任务 | Celery 5.3+ | AOO 路径优化异步执行 |
| 缓存/队列 | Redis 7+ | Celery broker + 会话存储 + 进度缓存 |
| 向量计算 | NumPy 2.0+ | 向量相似度检索（替代 ChromaDB，零运维依赖） |
| 大模型 | 讯飞星火 (SparkClient, WebSocket 优先) | 智能对话与 RAG 生成 |
| Agent | 讯飞星辰 Agent 平台 | 工具调用型任务对话 |
| 认证 | JWT (python-jose) | 双 Token（access + refresh） |
| 配置 | pydantic-settings | .env 自动注入 |
| 服务容器 | Docker + Docker Compose | 一键部署 |
| 网关 | Nginx | 反向代理 + WebSocket 升级 + gzip |

### 1.2 目录结构

```
backend/
├── app/
│   ├── main.py                    # FastAPI 应用入口 + 中间件 + 生命周期
│   ├── core/
│   │   ├── config.py              # pydantic-settings 配置
│   │   ├── database.py            # SQLAlchemy 引擎/会话
│   │   └── security.py            # JWT 双 Token 认证
│   ├── models/                    # SQLAlchemy 2.0 模型（11 张表）
│   │   ├── user.py, knowledge.py, cehui.py
│   │   ├── learning_path.py, chat.py, agent.py, cognitive_load.py
│   ├── schemas/                   # Pydantic 请求/响应模型
│   ├── api/v1/                    # 13 个路由模块
│   │   ├── auth.py, users.py, cehui.py, knowledge.py
│   │   ├── aoo.py, chat.py, dashboard.py, teacher.py
│   │   ├── agent.py, health.py, records.py, admin.py, feedback.py
│   ├── services/
│   │   ├── aoo/                   # AOO 算法引擎
│   │   ├── llm/                   # SparkClient + 重试引擎
│   │   ├── rag/                   # 知识库 RAG 管线
│   │   ├── agent/                 # 会话管理 + Xingchen 客户端
│   │   ├── cehui/             # IRT 测绘模型
│   │   └── optimization/          # AOO 优化服务（Celery Task）
│   ├── tasks/                     # Celery 定义
│   └── db/                        # 迁移脚本
├── data/                          # 种子数据（knowledge_points.json 等）
├── tests/                         # pytest 测试套件
├── Dockerfile
└── requirements.txt
```

### 1.3 应用入口（main.py）

`main.py` 负责应用生命周期与中间件装配：

- `@asynccontextmanager` 生命周期：
  - **启动**：初始化数据库（建表/迁移）、按需创建 Demo 用户（`ENABLE_DEMO_USERS` 默认关闭）、初始化 Celery 连接、预热 RAG 知识库
  - **关闭**：关闭 Redis 连接、释放资源
- 中间件链：`CORSMiddleware`（生产环境限制域名）→ `GZipMiddleware`（min_size=512, compresslevel=6，压缩 JSON 响应节流外部带宽）→ 请求 ID 追踪
- 路由装配：挂载 13 个 v1 路由模块到 `/api/v1`
- 健康检查：`/health` 与 `/api/v1/health`（含 DB/Redis/Celery 依赖探测）

---

## 2. 数据模型设计（11 张表）

所有模型基于 SQLAlchemy 2.0 `Mapped` 类型标注，具备完整外键约束。

| 表名 | 职责 | 关键字段 |
|------|------|---------|
| `users` | 用户（学生/教师/管理员） | id, username, email, role, learning_speed, hashed_password |
| `knowledge_points` | 知识点（含图谱关系） | id, subject, title, difficulty, prerequisites, importance |
| `questions` | 题库 | id, kp_id, content, difficulty, type |
| `cehui_records` | 测绘会话 | id, user_id, cehui_type, total_questions, accuracy |
| `student_knowledge` | 学生-知识点掌握度 | user_id, kp_id, mastery, confidence, last_cehuid_at |
| `cognitive_load_records` | 认知负荷记录 | id, user_id, record_id, memory_load, attention_load, processing_load, overall_load |
| `learning_paths` | 学习路径主体 | id, user_id, optimal_path(JSON), convergence_data(JSON), pareto_front(JSON) |
| `path_tasks` | 每日任务明细 | id, path_id, day, kp_id, task_type, est_minutes, completed |
| `chat_history` | 对话历史 | id, user_id, role, content, session_id, sources |
| `agent_sessions` | Agent 会话持久化 | id, session_id, user_id, messages(JSON), updated_at |
| `aoo_optimization_logs` | 寻优日志 | id, user_id, task_id, iteration, best_fitness, diversity |

---

## 3. API 架构（13 个路由模块）

统一响应格式：`ResponseBase[T]`（`code` + `message` + `data`）。

### 3.1 路由清单

| 模块 | 前缀 | 核心端点 |
|------|------|---------|
| `auth.py` | `/auth` | POST `/register`, POST `/login`, POST `/refresh`, POST `/logout` |
| `users.py` | `/users` | GET `/me`, GET `/{id}`, PUT `/me`, GET `/students`(教师) |
| `cehui.py` | `/cehui` | GET `/question-bank`, POST `/submit`, GET `/records/{id}` |
| `knowledge.py` | `/knowledge` | GET `/points`, GET `/{id}`, GET `/graph`(前置依赖图) |
| `aoo.py` | `/aoo` | POST `/optimize`(Celery), GET `/status/{task_id}`, GET `/results/{id}` |
| `chat.py` | `/chat` | POST `/message`, POST `/rag`(RAG 问答), GET `/history` |
| `dashboard.py` | `/dashboard` | GET `/stats`(学生), GET `/teacher`(全班), GET `/platform-stats`(公开) |
| `teacher.py` | `/teacher` | GET `/students`, GET `/weak-points`, GET `/progress/{id}` |
| `agent.py` | `/agent` | POST `/chat`, POST `/chat/stream`(SSE), GET `/sessions` |
| `health.py` | `/health` | GET `/`(存活), GET `/ready`(依赖就绪) |
| `records.py` | `/records` | GET `/cehuis`, GET `/paths`, GET `/cognitive-load` |
| `admin.py` | `/admin` | POST `/seed`(重灌种子), GET `/metrics` |
| `feedback.py` | `/feedback` | POST `/path`(路径反馈), GET `/analytics` |

### 3.2 认证机制（security.py）

双 Token 设计：

| Token | 有效期 | 用途 |
|-------|--------|------|
| Access Token | 30 分钟 | 业务 API 鉴权（`Depends(get_current_user)`） |
| Refresh Token | 7 天 | 无感刷新 Access Token |

- 密码哈希：`passlib[bcrypt]`
- 算法：`python-jose` HS256
- 路由守卫：所有业务端点显式 `Depends(get_current_user)`；公开端点（如 `/dashboard/platform-stats`）不挂载依赖即可匿名访问
- 演示账号：`ENABLE_DEMO_USERS` 默认 **False**（生产环境不自动创建后门账号），仅在开发/演示环境显式置 true 时由生命周期创建 `student_demo` / `teacher_demo`

---

## 4. AOO 算法服务

### 4.1 服务分层

```
┌─────────────────────────────────────────────┐
│ api/v1/aoo.py  (HTTP 边界: 接收请求/轮询状态) │
└───────────────┬─────────────────────────────┘
                ▼
┌─────────────────────────────────────────────┐
│ services/optimization/optimization_service.py │
│  - 准备优化上下文 (知识点/测绘/图谱)            │
│  - 调用 AOOEngine.optimize()                  │
│  - 解析 Pareto 前沿 → 三类路径                 │
│  - 持久化到 learning_paths / path_tasks        │
└───────────────┬─────────────────────────────┘
                ▼
┌─────────────────────────────────────────────┐
│ services/aoo/                                 │
│  aoo_engine.py      (六阶段进化主循环)         │
│  fitness_calculator.py (五因子适应度)          │
│  aoo_config.py      (约30个超参数)             │
│  pareto_front.py    (非支配排序)               │
└─────────────────────────────────────────────┘
                ▼
┌─────────────────────────────────────────────┐
│ tasks/celery_app.py → AOO 优化 Task (异步)    │
│  - Redis 进度上报 (每 10 代快照)              │
│  - 早停 (50代无改进)                          │
└─────────────────────────────────────────────┘
```

### 4.2 OptimizationService 关键方法

- `_prepare_context()`：聚合学生测绘结果、知识点图谱、前置依赖，构造 `OptimizationContext`
- `_run_optimization()`：实例化 `AOOEngine`，传入 `on_iteration` 回调写入 Redis 进度
- `_persist_results()`：将最优路径、Pareto 前沿、收敛数据写入 `learning_paths`，每日任务写入 `path_tasks`，每代日志写入 `aoo_optimization_logs`
- `_build_path_tasks()`：将知识点排列解码为带预估时长的每日任务列表（基于 `est_minutes` 与日学习预算汇总）

---

## 5. LLM 服务：SparkClient

`services/llm/spark_client.py` 封装讯飞星火接入，以**助手 WebSocket 接口**为首选通道、REST 为降级通道：

```
ws(s)://spark-openapi.cn-huabei-1.xf-yun.com/v1/assistants/{assistant_id}
```

- **鉴权**：HMAC-SHA256 签名（host + date + HTTP 请求行），拼接后 Base64 编码
- **连接复用**：进程级共享 httpx 异步客户端单例（连接池复用），高并发下显著降低建连延迟
- **降级链**：WebSocket 不可用时，按 `spark-x` 为首的 REST 候选模型链降级
- **TokenCounter**：中文字符 1.5 token / 英文数字 0.25 token，无需 tiktoken 依赖
- **重试引擎**：指数退避（最多 3 次，初始 1s，上限 30s），可重试状态码 {429, 500, 502, 503, 504}
- **熔断器**：连续 5 次失败触发熔断，30s 后半开试探
- **双模式**：`chat()` 非流式 / `chat_stream()` 异步生成器（SSE 解析 `data:` 行）
- **Function Calling**：支持传 `tools`，自动解析 `tool_calls`

---

## 6. RAG 知识库服务

`services/rag/knowledge_base.py` 实现六阶段管线，向量存储采用 **NumPy + JSON 持久化**（L2 归一化后点积等价于余弦相似度）：

| 阶段 | 实现 | 说明 |
|------|------|------|
| 加载 | `DocumentLoader` | PDF/TXT/MD |
| 分块 | `DocumentChunker` | 800+150 滑动窗口，Markdown 按标题优先 |
| 向量化 | `FallingBackEmbedder` | Spark API → BGE → 哈希降级 |
| 存储 | `VectorStore` | NumPy 数组 + JSON |
| 检索 | `search()` | Top-K=5, 相似度阈值 0.5 |
| 生成 | `SparkClient.chat()` | 增强 Prompt + 来源标注 + 置信度 |

置信度由 `max_score×0.4 + avg_score×0.3 + length_score×0.15 + count_score×0.15` 综合，使系统在不确定时诚实拒答。

---

## 7. Agent 服务（会话 + 星辰）

### 7.1 SessionManager（Redis）

| Key Pattern | 类型 | TTL |
|-------------|------|-----|
| `agent:session:{id}:meta` | Hash | 1h |
| `agent:session:{id}:messages` | List（≤50 条） | 1h |
| `agent:user:{uid}:sessions` | Set | 2h |

消息追加使用 Pipeline 批量操作 + LTRIM 裁剪 + TTL 续期。

### 7.2 XingchenAgentClient

接入讯飞星辰 Agent 平台 `POST /v1/flow/run`，兼容 OpenAI 兼容格式与星辰原生格式，工具调用统一标准化。与 SparkClient 形成互补：Spark 负责自由对话与 RAG 生成，星辰负责任务型对话（路径规划/测绘分析）。

### 7.3 AgentService + SSE

`chat_stream()` 返回结构化 SSE 事件：`start` → `content`/`tool_call` → `done`/`error`，保证流式链路在任何异常下优雅收尾。

---

## 8. 测绘服务（IRT + DINA）

`services/cehui/__init__.py` 使用 IRT 2-PL 模型，通过 Newton-Raphson（最多 50 次迭代，收敛阈值 1e-4）估计学生能力 θ，经 logistic 映射到 [0,1] 掌握度；DINA 模型估计粗心率与猜测率；掌握度分四级（excellent/proficient/developing/weak）。置信度基于答题数量与准确率一致性估计。

---

## 9. 认知负荷服务

`compute_cognitive_load()` 量化三维度：记忆负荷（30%，基于答题时间比）、注意力负荷（40%，基于错误率与简单题错误率）、加工负荷（30%，基于时间波动与连续错误）。综合负荷 >0.6 高负荷、0.35-0.6 适中、<0.35 低负荷，作为 AOO 适应度负荷约束的数据来源。

---

## 10. 异步任务（Celery）

`tasks/celery_app.py` 定义 AOO 优化 Task：从 Redis 接收优化上下文 → 运行 `OptimizationService` → 每 10 代写入 Redis 进度 → 完成后落盘 PostgreSQL。Celery Worker 通过配置环境变量 `UVICORN_WORKERS` 协同调节并发；Nginx 侧 `upstream backend keepalive 32` 提升连接复用。

---

## 11. 配置（config.py）

`Settings`（pydantic-settings）支持全量环境变量注入：

- `VERSION` = "0.1.0"
- `ENABLE_DEMO_USERS` 默认 False
- `DATABASE_URL` 经 `effective_database_url` 动态拼接（支持 SQLite 回退）
- LLM：`XF_APP_ID` / `XF_API_KEY` / `XF_API_SECRET` / `XF_ASSISTANT_ID` / `XF_MODEL`（spark-x）
- Redis：`REDIS_URL`（默认 `redis://localhost:6379/0`）
- Celery：`CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND`

---

## 12. 安全加固要点

- 密码 bcrypt 哈希，JWT HS256 双 Token
- 所有业务端点显式 `Depends(get_current_user)`，无全局中间件泄露风险
- 输入校验：pydantic schema + `RequestValidationError`(422) 结构化返回
- 容错：SparkClient / XingchenClient 双层熔断器 + 指数退避 + 降级响应
- Docker 非 root 运行，Nginx 超时 120s，`Connection $connection_upgrade` 按 upgrade 头动态映射

---

## 13. 部署与运维

- `docker-compose.yml`：Nginx + frontend + backend + PostgreSQL + Redis + Celery Worker 一体化编排
- 后端 `Dockerfile`：`uvicorn --workers ${UVICORN_WORKERS:-2}`，内存受限环境默认 2 worker 即可稳定支撑
- 知识库预热：生命周期阶段加载种子知识点与文档，首次请求零冷启动延迟
- 可观测性：`/health` 与 `/api/v1/health` 提供存活与依赖就绪探针，便于容器编排探活
