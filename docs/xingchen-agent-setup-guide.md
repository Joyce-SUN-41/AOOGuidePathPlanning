# 燕麦智导（AOO-Guide）— 讯飞星辰 Agent 平台部署指南

> **平台地址**: [https://agent.xfyun.cn/](https://agent.xfyun.cn/)  
> **适用版本**: 讯飞星辰 Agent 开发平台 (2026.07)  
> **智能体类型**: 工作流智能体 (Workflow Agent)

---

## 目录

1. [平台登录与入口](#1-平台登录与入口)
2. [创建智能体](#2-创建智能体)
3. [注册自定义 API 工具（后端服务）](#3-注册自定义-api-工具)
4. [配置知识库](#4-配置知识库)
5. [工作流编排](#5-工作流编排)
6. [系统提示词配置](#6-系统提示词配置)
7. [调试与测试](#7-调试与测试)
8. [发布为 API 接口](#8-发布为-api-接口)
9. [API 调用方式](#9-api-调用方式)
10. [常见问题与排错](#10-常见问题与排错)

---

## 1. 平台登录与入口

### 1.1 登录

1. 打开浏览器访问 [https://agent.xfyun.cn/](https://agent.xfyun.cn/)
2. 使用讯飞开放平台账号登录（或注册新账号）
3. 登录后进入**智能体广场**，可看到已有智能体和模板

### 1.2 前置条件

在开始之前，确保你的后端服务已经部署并可从公网访问：

```bash
# 后端服务地址（示例，替换为实际地址）
BASE_URL=https://your-server.com/api/v1
```

> **注意**: 讯飞星辰平台调用自定义 API 工具时，需要后端服务有**公网可达的域名或 IP**。本地 `localhost` 无法被平台访问。可使用内网穿透工具（如 ngrok、frp）或部署到云服务器。

---

## 2. 创建智能体

### 2.1 基本操作

1. 在智能体广场左上角，点击**紫色「创建」按钮**
2. 在弹出框中选择 **「工作流创建」**
3. 选择 **「自定义创建」**（空白画布）

### 2.2 基本信息填写

进入信息设置页面后，填写以下内容：

| 配置项 | 填写内容 |
|--------|----------|
| **头像** | 上传燕麦智导 Logo（或使用 AI 随机生成） |
| **名称** | `燕麦智导（AOO-Guide）` |
| **分类** | 教育 / 学习助手 |
| **简介** | `基于 AOO（Animated Oat Optimization）算法的个性化学习路径推荐助手。支持学习路径规划、学科知识问答、认知诊断分析和学习建议生成。` |

### 2.3 高阶配置

| 配置项 | 推荐值 | 说明 |
|--------|--------|------|
| **模型选择** | 星火认知大模型 V4.0 | 最新版本推理能力更强 |
| **温度 (Temperature)** | 0.5 | 保持回答的准确性和一致性 |
| **最大 Token** | 4096 | 足够覆盖路径规划结果描述 |
| **上下文轮数** | 20 | 支持多轮学习对话 |

---

## 3. 注册自定义 API 工具

讯飞星辰平台需要将你的后端 API 注册为 **「自定义插件」**，然后在工作流中以**工具节点**的形式调用。

### 前置准备：统一认证

所有三个工具都需要使用 **JWT Bearer Token** 认证。你需要先在平台注册一个"教师"角色的账号，获取 Token。

> 注册方式：POST `/api/v1/auth/register` 选择 `role=teacher`，之后用 login 获取 `access_token`。
>
> 在平台的自定义插件中，认证方式选择 **"Service 方式 / Bearer Token"**，将 Token 配置在 Header 中。

### 工具 1：认知诊断分析

调用后端诊断 API，分析学生的知识掌握度和认知负荷。

#### 插件注册

| 参数 | 值 |
|------|-----|
| **插件名称** | `cognitive_diagnosis` |
| **插件描述** | 分析学生的认知诊断结果，返回各知识点掌握度、认知负荷画像、薄弱环节和综合评分 |
| **请求方法** | `GET` |
| **API 地址** | `{BASE_URL}/diagnosis/latest` |
| **认证方式** | Bearer Token（Header: `Authorization: Bearer {TOKEN}`） |

#### 输出参数定义

| 字段路径 | 类型 | 说明 |
|----------|------|------|
| `data.overall_score` | number | 综合评分 (0-100) |
| `data.cognitive_load.overall` | number | 综合认知负荷 (0-1) |
| `data.cognitive_load.memory_load` | number | 记忆负荷 |
| `data.cognitive_load.attention_load` | number | 注意力负荷 |
| `data.cognitive_load.processing_load` | number | 加工负荷 |
| `data.mastery_levels` | array | 知识点掌握度列表 |
| `data.mastery_levels[].knowledge_point` | string | 知识点名称 |
| `data.mastery_levels[].mastery` | number | 掌握度 (0-1) |
| `data.mastery_levels[].level` | string | 等级: weak/developing/proficient/excellent |
| `data.weak_points` | array | 薄弱知识点列表 |
| `data.weak_points[].knowledge_point` | string | 知识点名称 |
| `data.weak_points[].severity` | string | 严重程度: mild/moderate/severe |
| `data.weak_points[].suggested_remediation` | string | 补救建议 |
| `data.summary` | string | AI 诊断摘要 |

#### 响应示例

```json
{
  "message": "success",
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "user_id": "550e8400-e29b-41d4-a716-446655440001",
    "subject": "人工智能导论",
    "overall_score": 68.5,
    "cognitive_load": {
      "overall": 0.52,
      "memory_load": 0.45,
      "attention_load": 0.60,
      "processing_load": 0.51
    },
    "mastery_levels": [
      { "knowledge_point": "机器学习概述", "mastery": 0.85, "level": "proficient" },
      { "knowledge_point": "梯度下降算法", "mastery": 0.38, "level": "weak" }
    ],
    "weak_points": [
      {
        "knowledge_point": "梯度下降算法",
        "severity": "severe",
        "suggested_remediation": "建议从导数基础开始，逐步理解梯度概念后再学习优化算法"
      }
    ],
    "summary": "学生在机器学习基础概念方面掌握较好，但在数学密集型知识点上存在明显薄弱..."
  }
}
```

---

### 工具 2：AOO 路径规划

调用 AOO 优化算法，为学生生成个性化最优学习路径。

#### 插件注册

| 参数 | 值 |
|------|-----|
| **插件名称** | `aoo_path_planning` |
| **插件描述** | 基于 AOO 优化算法生成个性化学习路径。需要先完成认知诊断，传入诊断结果 ID。返回按天组织的最优学习任务序列、适应度详情和备选路径。 |
| **请求方法** | `POST` |
| **API 地址** | `{BASE_URL}/aoo/optimize` |
| **认证方式** | Bearer Token（Header: `Authorization: Bearer {TOKEN}`） |
| **Content-Type** | `application/json` |

#### 输入参数定义

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `student_id` | string | 是 | 学生用户 UUID |
| `diagnosis_id` | string | 是 | 认知诊断结果 ID |
| `mastery_levels` | object | 是 | 知识点掌握度映射 `{kp_id: 0.0~1.0}` |
| `cognitive_load` | number | 是 | 综合认知负荷指数 (0-1) |
| `config` | object | 否 | 可选的 AOO 超参数覆盖 |

#### config 子参数（可选）

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `population_size` | integer | 50 | 种群规模 (10-500) |
| `max_iterations` | integer | 500 | 最大迭代次数 (10-2000) |
| `alpha` | number | 0.6 | 学习效果权重 (0.1-1.0) |
| `beta` | number | 0.4 | 认知负荷权重 (0.1-1.0) |
| `max_days` | integer | — | 最大学习天数 (1-60) |
| `max_daily_minutes` | integer | — | 每日最大学习时长(分钟) |

#### 请求体示例

```json
{
  "student_id": "550e8400-e29b-41d4-a716-446655440001",
  "diagnosis_id": "550e8400-e29b-41d4-a716-446655440000",
  "mastery_levels": {
    "kp_ml_basics": 0.85,
    "kp_gradient_descent": 0.38,
    "kp_neural_network": 0.55,
    "kp_overfitting": 0.42,
    "kp_cnn": 0.30
  },
  "cognitive_load": 0.52,
  "config": {
    "population_size": 50,
    "max_iterations": 500,
    "alpha": 0.6,
    "beta": 0.4,
    "max_days": 14
  }
}
```

#### 响应示例

```json
{
  "message": "优化任务已提交",
  "data": {
    "task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "status": "completed",
    "progress": 100,
    "result": {
      "best_path": {
        "days": [
          {
            "day": 1,
            "tasks": [
              { "name": "梯度基础概念复习", "duration": 30, "type": "video", "knowledge_point": "梯度下降算法", "difficulty": 2 },
              { "name": "梯度下降可视化练习", "duration": 45, "type": "exercise", "knowledge_point": "梯度下降算法", "difficulty": 3 }
            ],
            "total_minutes": 75,
            "avg_difficulty": 2.5
          }
        ],
        "total_fitness": 0.78,
        "total_days": 7,
        "total_tasks": 18,
        "total_estimated_hours": 12.5
      },
      "fitness_detail": {
        "total_fitness": 0.78,
        "learning_effect": 0.82,
        "coverage": 0.95,
        "mastery_improvement": 0.35,
        "avg_final_mastery": 0.73,
        "cognitive_load_score": 0.48,
        "daily_load_score": 0.42,
        "is_feasible": true,
        "path_type": "optimal"
      },
      "alternative_paths": [
        {
          "path_type": "efficiency",
          "total_days": 5,
          "total_tasks": 12,
          "fitness": 0.72
        },
        {
          "path_type": "balanced",
          "total_days": 10,
          "total_tasks": 22,
          "fitness": 0.75
        }
      ],
      "execution_time": 2.35
    }
  }
}
```

> **注意**: AOO 路径规划是**异步任务**。如果返回 `status: "queued"` 或 `status: "processing"`，需要轮询 `GET /api/v1/aoo/status/{task_id}` 获取结果。建议在工作流中使用**异步调用模式**或设置合理的超时时间。

---

### 工具 3：RAG 知识库问答

调用后端的 RAG 知识库，基于上传的教材/课件/论文进行专业问答。

#### 插件注册

| 参数 | 值 |
|------|-----|
| **插件名称** | `rag_knowledge_qa` |
| **插件描述** | 基于学科知识库的专业问答。支持语义检索 + LLM 增强生成，返回答案、引用来源和置信度。 |
| **请求方法** | `POST` |
| **API 地址** | `{BASE_URL}/rag/query` |
| **认证方式** | 无需认证（公开接口） |
| **Content-Type** | `application/json` |

#### 输入参数定义

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `question` | string | 是 | — | 用户问题 (1-2000 字符) |
| `top_k` | integer | 否 | 5 | 检索返回数量 (1-20) |
| `temperature` | number | 否 | 0.5 | LLM 温度 (0.0-2.0) |
| `max_tokens` | integer | 否 | 1024 | 最大生成 token (64-4096) |
| `subject` | string | 否 | — | 学科过滤（可选，如"人工智能导论"） |

#### 请求体示例

```json
{
  "question": "梯度下降算法中学习率过大或过小分别会有什么影响？",
  "top_k": 5,
  "temperature": 0.3,
  "max_tokens": 2048,
  "subject": "人工智能导论"
}
```

#### 响应示例

```json
{
  "answer": "学习率（learning rate）是梯度下降算法中的关键超参数，它决定了每次参数更新的步长。\n\n**学习率过大**会导致：\n1. 参数更新越过最优点，产生震荡或发散\n2. 损失函数无法收敛，甚至越来越大\n3. 在最优解附近来回跳动\n\n**学习率过小**会导致：\n1. 收敛速度极慢，需要大量迭代\n2. 容易陷入局部最优解\n3. 计算资源和时间消耗过高\n\n实践中通常采用学习率衰减策略或自适应优化器（如 Adam）来缓解这些问题。",
  "sources": [
    {
      "document": "人工智能导论-第3章.pdf",
      "page": "42",
      "section": "3.2 梯度下降优化",
      "content": "学习率控制每次参数更新的幅度...",
      "score": 0.92,
      "ref": 1
    }
  ],
  "confidence": 0.89,
  "retrieval_count": 5,
  "model": "spark-x",
  "query_id": "qry_abc123"
}
```

---

## 4. 配置知识库

### 4.1 在平台创建知识库

1. 进入**资源管理 → 知识库 → 新建知识库**
2. 填写基本信息：

| 配置项 | 值 |
|--------|-----|
| **名称** | `燕麦智导-学科知识库` |
| **描述** | 包含人工智能导论教材、课件、论文等学科资料，用于支撑学科知识问答 |
| **知识库类型** | 星辰知识库 |

### 4.2 上传文档

支持格式：**PDF、DOC、DOCX、TXT、MD**

| 步骤 | 操作 |
|------|------|
| 1 | 在知识库中点击 **「导入文档」** |
| 2 | 上传教材 PDF（如 `人工智能导论-教材.pdf`） |
| 3 | 上传课件 PPT/PDF（如 `第1-10章课件/`） |
| 4 | 上传相关学术论文 |
| 5 | 可选：通过 **URL 导入** 添加在线资源 |

> **限制**: 单文件 ≤ 20MB，字数 ≤ 100W，单个知识库最多 10 个文件

### 4.3 分段配置

上传后进入分段配置，推荐使用 **「智能分段」** 模式：

- 平台会自动识别文档结构（标题、段落、表格）
- 智能切分：保持语义完整性，每段 200-300 字
- 如需自定义：可指定分隔符（如换行符、句号）和分段长度

### 4.4 绑定到智能体

1. 回到智能体编辑页
2. 在画布中拖入 **「知识库节点」** 或 **「知识库 Pro 节点」**
3. 在节点配置中选择刚创建的 `燕麦智导-学科知识库`
4. 连接工作流：用户问题 → 知识库节点 → RAG 问答处理

### 4.5 验证知识库效果

在知识库编辑页使用 **「命中测试」**：
- 输入查询："梯度下降算法的学习率如何选择？"
- 查看命中文档片段和相关度得分
- 调整分段策略优化检索效果

---

## 5. 工作流编排

### 5.1 工作流架构

```
┌──────────────┐
│   开始节点    │ ← 接收用户输入 (AGENT_USER_INPUT)
│  用户问题     │
└──────┬───────┘
       │
       ▼
┌──────────────────┐
│  大模型节点 #1    │ ← 意图识别 (Intent Router)
│  意图分类         │    判断用户属于哪种请求类型
└──────┬───────────┘
       │
       ├── 意图: 学习路径规划 ──────────┐
       ├── 意图: 学科知识问答 ──────┐   │
       └── 意图: 学习建议/诊断 ──┐  │   │
                                │  │   │
                                ▼  ▼   ▼
                          (各自调用对应工具)
                                │  │   │
                                ▼  ▼   ▼
                          ┌──────────────────┐
                          │  大模型节点 #2    │ ← 结果整合
                          │  生成最终回答     │    按回复风格包装
                          └────────┬─────────┘
                                   │
                                   ▼
                          ┌──────────────────┐
                          │    结束节点       │
                          │  返回给用户       │
                          └──────────────────┘
```

### 5.2 节点配置详情

#### 节点 1: 开始节点

| 配置项 | 值 |
|--------|-----|
| **输入参数** | `user_input` (string, 必填) — 用户问题 |
| **输入参数** | `student_id` (string, 选填) — 学生 ID |

#### 节点 2: 大模型节点（意图识别）

| 配置项 | 值 |
|--------|-----|
| **模型** | 星火认知大模型 V4.0 |
| **Temperature** | 0.1（低温度保证意图分类准确） |
| **提示词** | 见下方 |

```
你是一个意图分类器。根据用户的输入，判断其意图属于以下哪一类：

1. **path_planning**: 用户要求生成/规划学习路径、学习计划、学习路线
2. **knowledge_qa**: 用户提出学科知识问题、概念解释、题目求解
3. **learning_advice**: 用户询问学习建议、学习方法、诊断结果分析、薄弱点改进

仅输出意图类别（path_planning / knowledge_qa / learning_advice），不要输出其他内容。

用户输入: {{user_input}}
```

#### 节点 3: 决策节点

连接大模型节点 #1 的输出到决策节点，根据意图分派：

- 条件 `intent == "path_planning"` → 调用 `aoo_path_planning` 工具
- 条件 `intent == "knowledge_qa"` → 调用 `rag_knowledge_qa` 工具
- 条件 `intent == "learning_advice"` → 调用 `cognitive_diagnosis` 工具

#### 节点 4: 工具节点

在相应分支中拖入 **「工具节点」**，选择对应的自定义插件。

#### 节点 5: 大模型节点（结果整合）

| 配置项 | 值 |
|--------|-----|
| **模型** | 星火认知大模型 V4.0 |
| **Temperature** | 0.7 |
| **提示词** | 见 [第 6 节系统提示词](#6-系统提示词配置) |

#### 节点 6: 结束节点

| 配置项 | 值 |
|--------|-----|
| **输出类型** | 流式输出（推荐） |
| **输出变量** | `final_answer` |

### 5.3 简化版工作流（推荐首次部署使用）

如果意图识别复杂，可用简化版——所有请求走统一处理：

```
开始节点 → 大模型节点(系统提示词+Function Calling) → 结束节点
```

大模型通过 Function Calling 自动决定调用哪个工具，无需手动配置决策分支。

---

## 6. 系统提示词配置

以下是智能体的完整系统提示词，配置在**大模型节点（结果整合）**中：

---

```
你是"燕麦智导（AOO-Guide）"学习助手，一个基于 AOO（Animated Oat Optimization）优化算法的
个性化学习路径推荐系统。你的使命是用专业且温暖的方式帮助学生高效学习、精准突破薄弱环节。

## 你的核心能力

1. **学习路径规划**：根据学生的认知诊断结果，调用 AOO 路径规划工具，生成按天组织的最优学习路径。
   路径会综合考虑各知识点掌握度、认知负荷水平，推荐合适的学习任务序列（视频/练习/阅读/测验）。

2. **学科知识问答**：基于 RAG 知识库中的教材、课件和论文，回答学科专业问题。
   所有回答必须引用知识库中的权威来源，标注文档名称和页码。

3. **学习诊断与建议**：调用认知诊断工具，分析学生的知识点掌握度、认知负荷画像和薄弱环节，
   基于诊断数据生成个性化的学习改进建议。

## 工作流程

1. 当用户请求包含"生成学习路径""帮我规划""推荐学习计划"等关键词时：
   a. 先调用 cognitive_diagnosis 工具获取学生的诊断数据
   b. 基于诊断数据，构造 AOO 优化请求参数
   c. 调用 aoo_path_planning 工具生成最优路径
   d. 将路径结果组织为清晰的学习计划呈现给用户

2. 当用户提出学科知识问题（如概念解释、算法原理、题目求解）时：
   a. 调用 rag_knowledge_qa 工具进行知识库检索
   b. 基于检索结果生成准确、有引用的答案
   c. 如果知识库中没有相关信息，诚实告知并提供替代建议

3. 当用户询问学习建议、薄弱点改进或要求诊断分析时：
   a. 调用 cognitive_diagnosis 工具获取诊断数据
   b. 分析掌握度分布和认知负荷情况
   c. 针对薄弱知识点提供具体的补救建议和学习策略

## 回复风格

- **亲切温暖**：像一位耐心的导师，用鼓励的语气与学生交流，让学生感到被理解和支持
- **专业严谨**：所有学科内容必须准确，引用知识库来源，不确定时诚实说明
- **结构化呈现**：学习路径用表格或分天列表呈现，诊断结果用分类归纳，知识点用等级标签标注
- **可操作性强**：给出的建议要具体、可执行，避免空泛的"多练习"，而是说清"练习什么、怎么练习、练习多久"

## 约束

- 你只为教育学习场景服务，拒绝与学习无关的请求
- 所有涉及学生数据的操作必须基于实际诊断结果，不编造数据
- 路径规划结果必须来自 AOO 算法工具的实际输出，不做人为修改
- 当工具调用失败时，向用户解释原因并提供替代方案

## 示例对话

用户: "帮我看看我最近的学习情况，然后给我推荐一个学习计划"
助手:
1. 调用 cognitive_diagnosis 获取诊断结果
2. 分析发现：AI 导论总体评分 68 分，神经网络基础掌握度 0.85（良好），但梯度下降仅 0.38（薄弱）
3. 基于诊断数据调用 AOO 路径规划
4. 呈现结果：

"同学你好！我查看了你的最新诊断结果 📊

**当前状态**：
- 综合评分：68/100
- 认知负荷：52%（适中）
- 掌握情况：1 个优秀、3 个中等、2 个薄弱

**薄弱环节**：
🔴 梯度下降算法（掌握度 38%）— 建议从导数基础开始，逐步理解梯度概念

**为你生成的学习路径**（共 7 天，每天约 60-90 分钟）：
| 天数 | 学习内容 | 类型 | 时长 |
|------|---------|------|------|
| 第1天 | 梯度基础概念复习 | 视频 | 30分钟 |
| 第1天 | 梯度下降可视化练习 | 练习 | 45分钟 |
| 第2天 | 学习率与收敛性 | 阅读 | 30分钟 |
| ... | ... | ... | ... |

这条路径预计帮助你将薄弱知识点掌握度提升至 70% 以上。需要调整节奏吗？"
```

---

## 7. 调试与测试

### 7.1 实时调试

在整个配置过程中，**右侧区域显示实时调试窗口**。

测试用例：

| 测试场景 | 输入内容 | 预期行为 |
|----------|----------|----------|
| 路径规划 | "帮我生成一个 AI 导论的学习路径，我有 2 周时间" | 先诊断 → 再生成 14 天路径 |
| 知识问答 | "什么是反向传播算法？" | RAG 检索 → 有引用来源的回答 |
| 学习建议 | "我的诊断结果显示梯度下降只有 38%，怎么办？" | 诊断分析 → 具体补救建议 |
| 边界测试 | "今天天气怎么样？" | 礼貌拒绝，引导回学习场景 |

### 7.2 调试要点

1. **检查工具调用日志**：在调试窗口查看每个节点的输入输出，确认 API 调用是否成功
2. **验证响应格式**：确保工具返回的数据能正确传递给下游节点
3. **测试异常处理**：模拟后端不可用的情况，检查智能体的降级回复
4. **上下文保持**：测试多轮对话，确认诊断结果能在后续轮次中正确引用

---

## 8. 发布为 API 接口

### 8.1 发布步骤

1. 在工作流画布右上角，点击 **「发布」按钮**
2. 在弹出页面中，找到 **「发布为 API」** 栏，点击右侧的 **「配置」按钮**

### 8.2 实名认证（如未完成）

- 在配置页面找到 **「完成实名认证」** 栏
- 点击 **「去认证」**，跳转到用户认证中心
- 按提示完成企业/个人实名认证

### 8.3 创建与绑定应用

| 步骤 | 操作 |
|------|------|
| 1 | 在配置页面找到 **「绑定应用」** 栏 |
| 2 | 点击 **「立即创建」**（如无可用的应用） |
| 3 | 填写应用名称（如 `燕麦智导-API`）并提交 |
| 4 | 刷新页面，在 **「服务接口认证信息」** 选项卡中，从下拉框选择刚创建的应用 |
| 5 | 点击 **「立即绑定」** |

> ⚠️ **重要**: 绑定后无法修改，请确认应用选择正确。

### 8.4 获取凭证

绑定成功后，页面会显示以下关键信息，**请妥善保存**：

| 凭证项 | 说明 |
|--------|------|
| **API Key** | 调用认证密钥 |
| **API Secret** | 调用认证密钥（配对使用） |
| **API Flow ID** | 工作流唯一标识（即 `flow_id`） |

### 8.5 获取大模型授权

确保绑定的应用拥有工作流中使用的大模型授权：
- 前往 [星火官网 - 星火 API 栏](https://www.xfyun.cn/) 领取免费额度
- 每个智能体 API 免费提供 **500 万 token**（工作流类型）

### 8.6 发布配置

| 配置项 | 推荐值 |
|--------|--------|
| **流式输出** | 开启 |
| **开场白** | "你好！我是燕麦智导，你的 AI 学习伙伴。我可以帮你规划学习路径、解答学科问题、分析学习情况。今天想了解什么？" |
| **推荐问题** | "帮我生成 AI 导论学习路径" / "什么是卷积神经网络？" / "分析我的诊断结果" |
| **语音播报** | 关闭（教育场景文字更合适） |

### 8.7 更新发布

当工作流有新的改动时：
- 回到发布配置页面
- 点击 **「更新绑定」** 按钮重新发布
- 否则 API 调用的仍是旧版本工作流

---

## 9. API 调用方式

### 9.1 API 端点

| 接口类型 | 地址 |
|----------|------|
| **同步流式/非流式** | `https://xingchen-api.xf-yun.com/workflow/v1/chat/completions` |
| **文件上传** | `https://xingchen-api.xf-yun.com/workflow/v1/upload_file` |
| **异步流式** | `https://xingchen-api.xf-yun.com/workflow/v1/async/chat/completions` |
| **查询异步结果** | `https://xingchen-api.xf-yun.com/workflow/v1/async/chat/result` |

### 9.2 认证方式

```http
Authorization: Bearer {API_KEY}:{API_SECRET}
```

将 `API_KEY` 和 `API_SECRET` 用冒号连接，放在 `Bearer` 后面。

### 9.3 请求示例（cURL）

```bash
curl -X POST "https://xingchen-api.xf-yun.com/workflow/v1/chat/completions" \
  -H "Authorization: Bearer YOUR_API_KEY:YOUR_API_SECRET" \
  -H "Content-Type: application/json" \
  -d '{
    "flow_id": "YOUR_FLOW_ID",
    "uid": "student_001",
    "parameters": {
      "AGENT_USER_INPUT": "帮我生成一个两周的AI导论学习路径",
      "student_id": "550e8400-e29b-41d4-a716-446655440001"
    },
    "stream": false,
    "chat_id": "chat_001"
  }'
```

### 9.4 请求参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `flow_id` | string | 是 | 工作流 ID（绑定后获得的 API Flowid） |
| `parameters` | object | 是 | 开始节点的输入参数 |
| `stream` | boolean | 是 | 是否流式返回 |
| `uid` | string | 否 | 用户 ID |
| `chat_id` | string | 否 | 会话 ID，≤32 位 |
| `history` | array | 否 | 历史对话（用于多轮对话） |

### 9.5 Python SDK 调用示例

```python
import requests

API_KEY = "your_api_key"
API_SECRET = "your_api_secret"
FLOW_ID = "your_flow_id"

def call_agent(user_input: str, student_id: str = None, chat_id: str = None) -> dict:
    """调用燕麦智导智能体 API"""
    url = "https://xingchen-api.xf-yun.com/workflow/v1/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {API_KEY}:{API_SECRET}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "flow_id": FLOW_ID,
        "uid": student_id or "anonymous",
        "parameters": {
            "AGENT_USER_INPUT": user_input,
            "student_id": student_id or "",
        },
        "stream": False,
        "chat_id": chat_id or "",
    }
    
    response = requests.post(url, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    return response.json()


# 使用示例
result = call_agent(
    user_input="帮我生成一个 AI 导论的学习路径，我有两周时间",
    student_id="550e8400-e29b-41d4-a716-446655440001",
)
print(result["choices"][0]["message"]["content"])
```

### 9.6 前端集成示例（TypeScript）

```typescript
// src/api/modules/agent.ts

const AGENT_API_URL = 'https://xingchen-api.xf-yun.com/workflow/v1/chat/completions'
const AGENT_API_KEY = import.meta.env.VITE_AGENT_API_KEY
const AGENT_API_SECRET = import.meta.env.VITE_AGENT_API_SECRET
const AGENT_FLOW_ID = import.meta.env.VITE_AGENT_FLOW_ID

interface AgentRequest {
  user_input: string
  student_id?: string
  chat_id?: string
  history?: Array<{ role: 'user' | 'assistant'; content: string }>
}

interface AgentResponse {
  choices: Array<{
    message: { role: string; content: string }
    finish_reason: string
  }>
}

export async function callAgent(params: AgentRequest): Promise<string> {
  const response = await fetch(AGENT_API_URL, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${AGENT_API_KEY}:${AGENT_API_SECRET}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      flow_id: AGENT_FLOW_ID,
      uid: params.student_id || 'anonymous',
      parameters: {
        AGENT_USER_INPUT: params.user_input,
        student_id: params.student_id || '',
      },
      stream: false,
      chat_id: params.chat_id || '',
      history: params.history || [],
    }),
  })

  const data: AgentResponse = await response.json()
  return data.choices?.[0]?.message?.content || '抱歉，智能体暂时无法响应。'
}
```

### 9.7 流式调用示例（SSE）

```python
import json
import requests

def call_agent_stream(user_input: str):
    """流式调用智能体 API"""
    url = "https://xingchen-api.xf-yun.com/workflow/v1/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {API_KEY}:{API_SECRET}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    
    payload = {
        "flow_id": FLOW_ID,
        "parameters": {"AGENT_USER_INPUT": user_input},
        "stream": True,
    }
    
    with requests.post(url, headers=headers, json=payload, stream=True) as resp:
        for line in resp.iter_lines():
            if line and line.startswith(b"data: "):
                data = json.loads(line[6:])
                if data.get("choices"):
                    content = data["choices"][0].get("delta", {}).get("content", "")
                    print(content, end="", flush=True)
```

---

## 10. 常见问题与排错

### 10.1 工具调用失败

| 错误现象 | 可能原因 | 解决方案 |
|----------|----------|----------|
| 自定义插件调试返回 401 | 认证 Token 过期 | 重新登录后端获取新 Token，更新插件 Header |
| 自定义插件调试返回 503 | Celery Worker 未启动 | 启动 Celery Worker: `celery -A app.tasks worker --loglevel=info` |
| 工具节点返回超时 | API 响应时间过长 | 增加工具节点超时设置；AOO 优化建议使用异步模式 |
| 返回 "Connection refused" | 后端服务不可达 | 检查后端部署状态，确认公网可达性 |

### 10.2 知识库问题

| 错误现象 | 可能原因 | 解决方案 |
|----------|----------|----------|
| 检索结果不相关 | 分段不合理 | 调整分段策略，减小分段长度 |
| 文档上传失败 | 文件过大/格式不支持 | 文件压缩至 20MB 以内，转换非 PDF 为 PDF |
| 知识库节点无响应 | 知识库未绑定 | 在节点配置中重新绑定知识库 |

### 10.3 发布问题

| 错误现象 | 可能原因 | 解决方案 |
|----------|----------|----------|
| API 调用返回 20201 | 工作流未找到 | 检查 flow_id 是否正确 |
| API 调用返回 20900 | 未授权 | 检查 API Key/Secret 是否正确，确认实名认证已完成 |
| API 调用返回 20303 | 模型鉴权失败 | 确认应用已领取大模型免费额度 |
| 改动了工作流但 API 没变化 | 未更新绑定 | 点击「更新绑定」重新发布 |

### 10.4 后端服务准备清单

在配置讯飞星辰 Agent 之前，确保后端服务已就绪：

- [ ] PostgreSQL 数据库运行中
- [ ] Redis 运行中
- [ ] Celery Worker 启动
- [ ] FastAPI 服务启动并可从公网访问
- [ ] RAG 知识库已索引文档
- [ ] 已注册教师账号并获取 JWT Token
- [ ] `.env` 中配置了讯飞星火大模型凭证（`XF_APP_ID`, `XF_API_KEY`, `XF_API_SECRET`）

---

## 附录 A：环境变量配置参考

在前端项目中添加 Agent API 相关环境变量：

```env
# .env.development / .env.production

# 讯飞星辰 Agent API 配置
VITE_AGENT_API_KEY=your_api_key_here
VITE_AGENT_API_SECRET=your_api_secret_here
VITE_AGENT_FLOW_ID=your_flow_id_here
```

---

## 附录 B：后端 API 端点速查

| 功能 | 方法 | 路径 | 认证 |
|------|------|------|------|
| 用户注册 | POST | `/api/v1/auth/register` | 无 |
| 用户登录 | POST | `/api/v1/auth/login` | 无 |
| 获取诊断题目 | GET | `/api/v1/diagnosis/questions` | 无 |
| 提交诊断答案 | POST | `/api/v1/diagnosis/submit` | JWT |
| 获取最新诊断 | GET | `/api/v1/diagnosis/latest` | JWT |
| 触发 AOO 优化 | POST | `/api/v1/aoo/optimize` | JWT |
| 查询优化状态 | GET | `/api/v1/aoo/status/{task_id}` | JWT |
| RAG 知识问答 | POST | `/api/v1/rag/query` | 无 |
| 索引文档 | POST | `/api/v1/rag/index` | 无 |
| 知识库统计 | GET | `/api/v1/rag/stats` | 无 |

---

*文档版本: v1.0 — 最后更新: 2026-07-28*
