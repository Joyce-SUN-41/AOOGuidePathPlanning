# 动麦智导 (AOO Guide Path Planning) — 开发者指南

## 项目概述

动麦智导是一个基于 **AOO（Animated Oat Optimization）算法** 和 **讯飞星火大模型** 的 AI 智能学习路径规划平台。面向人工智能通识课学生，提供学情测绘 → 路径优化 → 导学终端 → 学情分析的闭环学习支持。

### 核心技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3 + TypeScript + Vite + Ant Design Vue + ECharts |
| 后端 | FastAPI (Python 3.11) + SQLAlchemy 2.0 + Celery |
| 数据库 | PostgreSQL 16 + Redis 7 |
| AI/算法 | AOO 优化引擎 + 讯飞星火大模型 + IRT/DINA 学情测绘 + NumPy 向量存储 RAG |
| 部署 | Docker Compose + Nginx + GitHub Actions |

---

## 快速开始

### 前置要求

- **Node.js** >= 20
- **Python** >= 3.11
- **PostgreSQL** >= 15
- **Redis** >= 7
- **Docker** (可选，推荐用于生产环境)

### 1. 克隆仓库

```bash
git clone https://github.com/Joyce-SUN-41/AOOGuidePathPlanning.git
cd AOOGuidePathPlanning
```

### 2. 后端启动

```bash
cd backend

# 创建虚拟环境
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate  # macOS/Linux

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入数据库、Redis、星火 API 凭证

# 运行数据库迁移
alembic upgrade head

# 启动开发服务器
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 3. 前端启动

```bash
cd ..  # 回到项目根目录

# 安装依赖
npm install

# 启动开发服务器
npm run dev
# 访问 http://localhost:5173
```

### 4. Docker 一键启动（完整环境）

```bash
docker compose up -d
# 前端: http://localhost:80
# 后端 API 文档: http://localhost:8000/docs
```

---

## 项目结构

```
AOOGuidePathPlanning/
├── backend/                     # FastAPI 后端
│   ├── app/
│   │   ├── api/v1/              # API 路由（13 个模块）
│   │   ├── core/                # 配置/数据库/安全/日志/中间件
│   │   ├── models/              # SQLAlchemy ORM 模型（11 张表）
│   │   ├── schemas/             # Pydantic 请求/响应模型
│   │   ├── services/            # 业务逻辑层
│   │   │   ├── aoo/             # AOO 优化引擎
│   │   │   ├── cehui/       # 学情测绘（IRT 2-PL + DINA）
│   │   │   ├── llm/             # LLM 集成（星火 + 星辰）
│   │   │   ├── rag/             # RAG 检索增强生成
│   │   │   └── agent/           # Agent 对话编排
│   │   └── tasks/               # Celery 异步任务
│   ├── scripts/                 # 工具脚本
│   ├── tests/                   # 测试（pytest）
│   ├── alembic/                 # 数据库迁移
│   ├── Dockerfile
│   ├── requirements.txt
│   └── entrypoint.sh
│
├── src/                         # Vue 3 前端
│   ├── api/                     # API 模块（8 个业务模块）
│   ├── components/              # 可复用组件
│   │   ├── shared/              # 通用组件（ErrorState 等）
│   │   └── chat/                # 聊天组件
│   ├── views/                   # 页面组件（7 个页面）
│   ├── stores/                  # Pinia 状态管理
│   ├── types/                   # TypeScript 类型定义
│   ├── router/                  # Vue Router 路由配置
│   └── styles/                  # 全局样式（Less）
│
├── .github/workflows/           # GitHub Actions CI/CD
├── docker-compose.yml           # 开发环境
├── docker-compose.prod.yml      # 生产环境
├── Dockerfile                   # 前端多阶段构建
├── nginx.conf                   # Nginx 反向代理配置
└── docs/                        # 项目文档
```

---

## 开发约定

### 代码风格

- **Python**: 遵循 PEP 8, 使用 `flake8` 检查
- **TypeScript/Vue**: 遵循 ESLint + Prettier 配置
- **提交信息**: `type(scope): description`（如 `feat(aoo): add convergence tracking`）
- **分支策略**: `main`（稳定） ← `develop`（开发） ← `feature/*`（功能分支）

### 命名规范

| 上下文 | 规范 | 示例 |
|--------|------|------|
| Python 文件/函数/变量 | `snake_case` | `estimate_mastery_irt()` |
| Python 类 | `PascalCase` | `CehuiService` |
| Vue 组件文件 | `PascalCase.vue` | `LearningPathView.vue` |
| TypeScript 类型/接口 | `PascalCase` | `AOOConvergenceData` |
| TypeScript 变量/函数 | `camelCase` | `fetchCurrentPath()` |
| CSS 类 | BEM + kebab-case | `.convergence-tab--active` |
| 数据库表名 | `snake_case` | `knowledge_points` |
| API 端点 | `kebab-case` | `/api/v1/learning-paths` |

### API 约定

- 响应统一格式: `{ code: number, message: string, data: T }`
- 错误码: 0 成功, 401 未授权, 403 无权限, 404 不存在, 500 服务器错误
- 分页参数: `page` (1-based) + `pageSize`
- Token: Bearer 方式, 请求头 `Authorization: Bearer <token>`

---

## 运行测试

### 后端测试

```bash
cd backend
pytest app/ -v --tb=short
# 带覆盖率
pytest app/ -v --cov=app --cov-report=term-missing
```

### 前端测试

```bash
npm run test          # 运行所有测试
npm run test:watch    # 监听模式
npm run test:coverage # 覆盖率报告
```

---

## 数据库迁移

```bash
cd backend

# 创建新迁移
alembic revision --autogenerate -m "description"

# 升级到最新
alembic upgrade head

# 回滚一个版本
alembic downgrade -1
```

---

## 环境变量参考

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `POSTGRES_HOST` | PostgreSQL 主机 | `localhost` |
| `POSTGRES_PORT` | PostgreSQL 端口 | `5432` |
| `POSTGRES_USER` | 数据库用户 | `aoo_user` |
| `POSTGRES_PASSWORD` | 数据库密码 | — |
| `POSTGRES_DB` | 数据库名 | `aoo_guide_path` |
| `REDIS_URL` | Redis 连接 | `redis://localhost:6379/0` |
| `SECRET_KEY` | JWT 签名密钥 | **生产必须更换** |
| `XF_APP_ID` | 星火应用 ID | — |
| `XF_API_KEY` | 星火 API Key | — |
| `XF_API_SECRET` | 星火 API Secret | — |
| `XF_MODEL` | 星火模型 | `spark-x` |

---

## 常见问题

### Q: 数据库连接失败？

确保 PostgreSQL 已启动，且 `.env` 中的 `DATABASE_URL` 格式正确：
```
postgresql+asyncpg://user:password@host:5432/database
```

### Q: 星火 API 调用失败？

1. 确认 `.env` 中 `XF_APP_ID`、`XF_API_KEY`、`XF_API_SECRET` 已配置
2. 未配置时系统会使用本地降级响应，不会崩溃
3. 检查网络是否能访问 `https://spark-api-open.xf-yun.com`

### Q: 如何种子化 AI 通识课知识点？

```bash
cd backend
python scripts/seed_ai_knowledge.py
```

---

## 相关资源

- [FastAPI 文档](https://fastapi.tiangolo.com/)
- [Vue 3 文档](https://vuejs.org/)
- [Ant Design Vue](https://antdv.com/)
- [讯飞开放平台](https://console.xfyun.cn/)
