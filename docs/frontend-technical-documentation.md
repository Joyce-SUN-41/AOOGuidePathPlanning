# 燕麦智导（AOO Guide）前端技术文档

## 1. 技术栈与项目结构

### 1.1 核心技术栈

| 类别 | 技术选型 | 说明 |
|------|---------|------|
| 框架 | Vue 3.4+ | Composition API + `<script setup>` |
| 语言 | TypeScript 5.x | 严格模式类型安全 |
| 构建 | Vite 5 | 极速 HMR + 生产打包 |
| UI 组件 | Ant Design Vue 4 | 企业级组件库 |
| 图表 | ECharts 5 | 收敛曲线 / 雷达图 / 甘特图 / 负荷趋势 |
| 状态管理 | Pinia 2 | 全局 stores |
| 路由 | Vue Router 4 | 路由守卫 + 角色检查 |
| HTTP | Axios | 统一拦截器 + JWT 注入 |
| 样式 | Less + CSS 变量 | 冷酷科技风设计令牌 |

### 1.2 目录结构

```
src/
├── api/
│   ├── index.ts                 # Axios 实例 + getToken() + 拦截器
│   └── modules/                 # 按业务域拆分 API 模块
│       ├── auth.ts, diagnose.ts, knowledge.ts
│       ├── aoo.ts, chat.ts, dashboard.ts
│       ├── teacher.ts, agent.ts, records.ts
├── views/                       # 8+ 页面
│   ├── LoginView.vue, RegisterView.vue, HomeView.vue
│   ├── DiagnoseView.vue, PathView.vue, LearningPathView.vue
│   ├── ChatView.vue, DashboardView.vue, TeacherView.vue, RecordsView.vue
├── components/                  # 可复用组件
│   ├── AOOAnimation.vue         # AOO 寻优帧播放
│   ├── OatDispersalBackground.vue  # 冷燕麦粒子场背景
│   ├── charts/                  # ECharts 封装组件
│   └── layout/                  # 侧栏 / 顶栏 / 页脚
├── composables/
│   ├── useIsMobile.ts           # matchMedia 断点 768 统一移动端判定
│   └── useAooProgress.ts        # 优化进度轮询
├── stores/                      # Pinia stores
│   ├── user.ts, path.ts, agent.ts, diagnosis.ts
├── router/                      # 路由定义 + 守卫
├── styles/                      # 设计令牌 + 主题
│   ├── tokens.less              # 冷酷科技风变量
│   └── global.less
└── utils/                       # 工具函数
```

### 1.3 设计哲学（OAT-OPS 指挥终端）

前端采用"冷酷科技风 / OAT-OPS 指挥终端"视觉基调，与通用 AI 模板明确区隔：

- **近纯黑暗场** `#06080D` + 硬栅格线矩阵（64px 1px `rgba(148,163,184,0.05)`）+ 极淡噪点
- **单一高光色** = 燕麦金 `#D4A373`；辅助冷色 = 青蓝 `#00D4FF`；轴/文 = `#94A3B8` / `#CBD5E1` / `#F8FAFC`
- **等宽字体当主角**（JetBrains Mono）做刊头 / 状态行 / 数字
- **直角 / 方点 / 硬描边**（radius 0~2px）
- 路由转场 `page-wipe` = clip-path 硬切扫光（去模糊）；侧栏激活 = 左侧 2px 燕麦金硬条
- 品牌独有符号：`OatDispersalBackground`（冷燕麦粒子场）作 Hero 背景
- **审美红线**：禁止柔和玻璃辉光、渐变描边字、圆角胶囊、彩色模糊光斑、呼吸脉冲光等通用 AI 模板感

图表遵循一致深色基线：ECharts 轴名 `#CBD5E1`、轴标签 `#94A3B8`、网格线 `rgba(255,255,255,0.08~0.12)`、tooltip 底 `rgba(20,27,43,0.95)`、数据点描边 `#141B2B`。

---

## 2. API 调用层

### 2.1 统一 Axios 实例（api/index.ts）

- Base URL 指向 `/api/v1`（Nginx 反向代理到后端）
- 请求拦截器：从 `getToken()` 注入 `Authorization: Bearer {access}`
- 响应拦截器：解包 `ResponseBase.data`，401 → 尝试 refresh 或跳登录
- 错误统一提示（Ant Design Message）

### 2.2 模块化 API（api/modules/）

所有业务接口统一放入 `src/api/modules/`，按域拆分，token 一律经 `getToken()` 获取，杜绝硬编码密钥：

| 模块 | 覆盖端点 |
|------|---------|
| `auth.ts` | 登录 / 注册 / 刷新 / 登出 |
| `diagnose.ts` | 题库拉取 / 提交诊断 |
| `knowledge.ts` | 知识点 / 图谱 |
| `aoo.ts` | 提交优化 / 轮询状态 / 获取结果 |
| `chat.ts` | 对话 / RAG 问答 |
| `dashboard.ts` | 学生 / 教师 / 平台统计 |
| `teacher.ts` | 班级学情 / 薄弱点 |
| `agent.ts` | Agent 流式对话 |
| `records.ts` | 诊断 / 路径 / 负荷记录 |

---

## 3. 路由与鉴权

### 3.1 路由表（8+ 页面）

| 路由 | 组件 | 角色 |
|------|------|------|
| `/login`, `/register` | LoginView / RegisterView | 匿名 |
| `/` (Home) | HomeView | 登录后 |
| `/diagnose` | DiagnoseView | 学生 |
| `/path` | PathView | 学生 |
| `/path/:id` | LearningPathView | 学生 |
| `/chat` | ChatView | 登录后 |
| `/dashboard` | DashboardView | 学生/教师 |
| `/teacher` | TeacherView | 教师 |
| `/records` | RecordsView | 登录后 |

### 3.2 路由守卫

`router/beforeEach`：检查 `getToken()` 与 Pinia user store；未登录访问受保护路由 → 重定向登录页；角色不符 → 提示并退回首页。登录态持久化于 localStorage，刷新后自动恢复。

---

## 4. 核心页面与组件

### 4.1 AOOAnimation.vue（寻优帧播放）

核心可视化组件，将后端收敛数据（每 10 代快照）逐帧渲染：

- **收敛曲线**：双 Y 轴（左=适应度，右=种群多样性），最优/平均/中位数/多样性四条曲线随时间推进绘制
- **种群散点**：当前帧精英（红，发光）/ 普通（蓝）/ 探索（绿），历史帧幽灵化呈粒子轨迹
- **统计面板**：迭代进度 / 最优适应度 / 平均适应度 / 多样性，等宽字体大号数字
- **控制**：播放/暂停、1x~8x 速度、进度条拖拽、历史记录回放
- **关键技术点**：容器高度由 JS 动态设置时，必须在 `init()` 后显式 `resize()`；轴名改 `nameLocation:'middle'` + `nameGap` 避免遮挡；custom series 文字手动按框宽截断 + `clipRect`

### 4.2 PathView.vue（Pareto 三路径）

以 Tab 切换展示效率型 / 平衡型 / 稳健型三条路径，每条配独立甘特图（`LearningPathView`）、统计面板与适应度详情；收敛曲线采用 `yAxis.inverse` 实现自顶向下收敛展示。

### 4.3 DashboardView.vue（学情看板）

- 雷达图：接首次诊断真实基线，禁用随机数造假；提升百分比以 graphic 标注
- 认知负荷趋势图：补 `dataZoom`（默认近 10 次）
- 薄弱点详情：`a-table` 排序 / 筛选 + 详情抽屉
- 首页统计：走 `/dashboard/platform-stats` 公开端点；接口失败则隐藏模块，绝不回退假数据

### 4.4 ChatView.vue（智能对话）

- SSE 流式渲染（逐字输出）
- 窄屏工具栏 `flex-wrap` + 按钮仅图标
- 已接入讯飞星火（SparkClient）与星辰 Agent 双通道

### 4.5 OatDispersalBackground.vue（品牌背景）

冷燕麦粒子场动画，作为 Hero / 登录页背景，构建区别于通用 AI 模板的视觉识别度。

---

## 5. 状态管理（Pinia）

| Store | 职责 |
|-------|------|
| `user.ts` | 当前用户 / 角色 / token |
| `path.ts` | 当前路径 / Pareto 三路径 / 优化进度 |
| `agent.ts` | 会话列表 / 流式消息缓冲 |
| `diagnosis.ts` | 诊断题目 / 提交状态 / 结果 |

---

## 6. 移动端适配

项目以 `composables/useIsMobile.ts`（matchMedia 断点 768）统一移动端判定，覆盖全套页面：

- 所有 `a-table` 加 `:scroll="{x:'max-content'}"` 横向滚动（不强行堆叠）
- modal 窄屏 `:width="isMobile?'90%':N"`、drawer 窄屏 `:width="isMobile?'100%':N"`
- ChatView toolbar 窄屏换行 + 按钮 `.tb-text{display:none}` 仅留图标
- HomeView 补 `≤480px` 断点
- 窄屏下侧栏折叠为抽屉式导航

---

## 7. 性能与加载优化

- **字体非阻塞加载**：`index.html` Google Fonts 由同步 `<link>` 改为非阻塞（`media="print" onload="this.media='all'"` + `<noscript>` 兜底），字体栈末尾保留 system-ui / PingFang / 微软雅黑系统兜底，彻底消除弱网 / 国内访问首屏白屏
- **外部访问链路**：Nginx 修正 `Connection "upgrade"` 全量写死 bug（改用 `map $http_upgrade $connection_upgrade`），`upstream backend keepalive 32` 提升连接复用，`gzip_proxied any` + API 超时 120s；后端加 `GZipMiddleware` 压缩 JSON 响应节流外部带宽
- **图表 resize**：所有 ECharts 容器在容器尺寸变化时监听 `resize`
- **事件总线**：学习统计通过 eventBus 实时刷新，避免重复拉取

---

## 8. 图标规范

- 全站 **禁止 emoji**，UI 图标一律使用 `@ant-design/icons-vue` 的 `<component :is="..." />`
- 例外：ECharts `formatter` 返回的 HTML 字符串与 CSS `content` 不支持组件，只能使用纯文字

---

## 9. 工程质量

- **Vue "能编译通过" ≠ "能渲染"**：无指令的裸 `<template>` 根标签会被编译成真实 DOM `<template>` 元素导致整页静默空白，已通过组件根节点规范化规避
- `<script setup>` 字符串路径 ref 无效，统一改用函数式 ref `:ref="(el) => (x.value = el)"`
- 数据真实性红线：禁止 `Math.random()` 伪造任何面向用户的业务数据；无真实数据时隐藏模块或显式提示"暂无数据"
- 全部页面已通过 `vue-tsc` 类型检查与 ESLint 校验
