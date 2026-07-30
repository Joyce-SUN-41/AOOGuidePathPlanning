<<<<<<< HEAD
# 🏗️ 燕麦智导 — AI 智能学习路径规划平台

基于 **AOO（Animated Oat Optimization）算法**的智能学习路径规划系统，结合认知诊断、大语言模型与 RAG 知识库，为教师和学生提供个性化学习路径推荐。

## ✨ 功能特性

| 功能 | 描述 |
|------|------|
| 🧠 **认知诊断** | 通过题目作答评估学生知识点掌握程度、认知负荷与薄弱环节 |
| 🗺️ **学习路径规划** | 基于 AOO 优化算法自动生成个性化学习路径，平衡学习效果与认知负荷 |
| 💬 **智能问答** | 集成讯飞星火大模型 + RAG 知识库，提供学习辅导与知识检索 |
| 📊 **学情看板** | 可视化展示学习进度、知识点雷达图、认知负荷变化曲线 |
| 👩‍🏫 **教师仪表盘** | 查看全班学情、知识点掌握分布、个体与群体分析 |

## 🛠️ 技术栈

### 前端
- **Vue 3** + **TypeScript** — 渐进式框架
- **Vite** — 极速构建工具
- **Ant Design Vue 4** — UI 组件库
- **ECharts 5** + **ECharts GL** — 数据可视化
- **Pinia** — 状态管理

### 后端
- **FastAPI** — 高性能异步 Web 框架
- **SQLAlchemy 2.0** + **asyncpg** — 异步 ORM + PostgreSQL
- **Celery** + **Redis** — 异步任务队列
- **NumPy** — AOO 算法数值计算
- **ChromaDB** — 向量数据库（RAG 支持）

### 基础设施
- **PostgreSQL 16** — 主数据库
- **Redis 7** — 缓存 / 消息队列
- **Docker** + **Docker Compose** — 一键部署
- **Nginx** — 生产环境反向代理

## 🚀 快速启动

### 前置要求

- [Docker](https://www.docker.com/) 20.10+
- [Docker Compose](https://docs.docker.com/compose/) 2.0+

### 1. 克隆项目

```bash
git clone https://github.com/<your-username>/AOOGuidePathPlanning.git
cd AOOGuidePathPlanning
```

### 2. 一键启动（开发模式）

```bash
docker compose up -d
```

首次启动会自动：
- 拉取 PostgreSQL / Redis / Node / Python 镜像
- 安装前后端依赖
- 创建数据库表并执行迁移
- 自动创建 Demo 账号

### 3. 访问

| 服务 | 地址 |
|------|------|
| 前端页面 | http://localhost:5173 |
| 后端 API 文档 | http://localhost:8000/docs |
| 后端健康检查 | http://localhost:8000/api/v1/health |

### 4. Demo 账号

| 角色 | 用户名 | 密码 |
|------|--------|------|
| 学生 | `student_demo` | `123456` |
| 教师 | `teacher_demo` | `123456` |

## 📦 生产部署

```bash
docker compose -f docker-compose.prod.yml up -d
```

生产模式特点：
- 前端通过 Nginx 提供静态服务（端口 80）
- API 通过 Nginx 反向代理到后端
- Redis 启用内存限制（256MB LRU）
- 关闭热重载和源码挂载

访问：http://localhost

## 📁 项目结构

```
AOOGuidePathPlanning/
├── src/                        # 前端源码
│   ├── api/                    # Axios API 封装
│   ├── components/             # 公共组件
│   ├── layouts/                # 布局组件
│   ├── router/                 # Vue Router 路由
│   ├── stores/                 # Pinia 状态管理
│   ├── types/                  # TypeScript 类型定义
│   ├── views/                  # 页面组件
│   └── styles/                 # 全局样式 (Less)
├── backend/                    # 后端源码
│   ├── app/
│   │   ├── api/v1/             # REST API 路由
│   │   ├── core/               # 配置 / 安全 / 数据库
│   │   ├── models/             # SQLAlchemy ORM 模型
│   │   ├── schemas/            # Pydantic 数据模型
│   │   ├── services/           # 业务逻辑层
│   │   │   └── aoo/            # AOO 优化算法核心
│   │   ├── tasks/              # Celery 异步任务
│   │   └── scripts/            # 数据种子 / 工具脚本
│   ├── alembic/                # 数据库迁移
│   ├── requirements.txt        # Python 依赖
│   └── Dockerfile
├── docker-compose.yml          # 开发环境编排
├── docker-compose.prod.yml     # 生产环境编排
├── nginx.conf                  # Nginx 配置
├── Dockerfile                  # 前端生产镜像
└── README.md
```

## ⚙️ 配置说明

所有配置通过环境变量管理，默认值已适配 Docker 环境。

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `SECRET_KEY` | JWT 签名密钥 | `change-me`（生产务必更换） |
| `POSTGRES_HOST` | 数据库主机 | `postgres`（Docker 服务名） |
| `REDIS_URL` | Redis 连接 | `redis://redis:6379/0` |
| `CELERY_BROKER_URL` | Celery 消息代理 | `redis://redis:6379/0` |
| `XF_API_KEY` | 讯飞星火 API 密钥 | 空（不填则禁用 AI 对话） |

完整变量见 `backend/.env.docker` 和 `backend/.env.example`。

### 非 Docker 本地开发

如需在宿主机直接运行（不使用 Docker）：

```bash
# 后端
cd backend
pip install -r requirements.txt
cp .env.example .env        # 编辑数据库地址为 localhost
uvicorn app.main:app --reload --port 8000

# 前端
npm install
npm run dev
```

## 🔬 AOO 算法

本系统实现了论文 *The Animated Oat Optimization Algorithm* 的核心逻辑，包括：

- **探索阶段**：模拟燕麦种子通过风、水、动物三种途径传播
- **开发阶段**：滚动传播（Lévy 飞行 + 滚动向量）和弹射传播（抛体运动 + Lévy 飞行）
- **适应度函数**：`α × 学习效果 − β × 认知负荷 − 前置依赖惩罚`

> 算法纯 NumPy 实现，零额外科学计算依赖。

## 📄 License

MIT

---

**燕麦智导** — 让每一条学习路径都如燕麦生长般自然高效 🌾
=======
# AOOGuidePathPlanning
针对应用型高校人工智能通识课“统一教学”与“个体差异”的矛盾，本课题依托认知负荷理论，以团队前期ESI高被引的AOO算法为工具，构建多目标学习路径推荐模型。通过认知诊断识别学生认知负荷与知识掌握水平，以学习效果最大化和认知负荷最小化为目标，通过AOO算法求解最优学习路径。准实验验证该路径对学习效果的提升及负荷的降低效果，为人工智能通识课从经验驱动向算法驱动的精准教学转型提供依据。
>>>>>>> ad070cfe3ed37e9ce80699bc99be39c355d18785
