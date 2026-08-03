# 燕麦智导（AOO Guide）—— 前端技术文档

> 基于 Vue 3 + TypeScript + Vite + Ant Design Vue + ECharts 构建的 AI 智能学习路径规划平台前端系统。

---

## 1. 系统前端页面设计与功能说明

本系统采用 **Vue 3 + TypeScript + Ant Design Vue** 技术栈构建，整体视觉风格为深色"未来主义科技风"，以燕麦金（#D4A373）与极光蓝（#4A6CF7）为品牌双主色，背景采用碳黑到深空蓝的径向渐变叠加网格点阵与噪点纹理。所有页面组件通过 Vue Router 的懒加载（`() => import()`）按需加载，减少首屏体积。

**首页（HomeView.vue）** 作为系统门户，采用全屏 Hero 区域设计，顶部展示"燕麦智导"品牌标识与核心宣传语，配合燕麦金径向光晕动画营造科技氛围。中部以毛玻璃卡片网格展示三大核心功能入口：认知诊断、智能问答、学习路径，每个卡片配有图标、标题和简短描述。底部展示系统统计数据，包括已生成路径数、覆盖知识点数、活跃用户数等，数字以燕麦金高亮并使用等宽字体（JetBrains Mono）渲染。页面完全响应式，在移动端卡片自动切换为单列布局。

**认知诊断页（DiagnoseView.vue）** 提供 10-15 道选择题作答界面。页面顶部显示诊断进度条（当前题号/总题数）与预估完成时间。题目区域以毛玻璃卡片呈现，每道题显示所属知识点标签（通过 a-tag 组件）、难度星级和题目内容。选项以毛玻璃芯片样式排列，选中态切换为燕麦金填充色加发光边框，提供即时视觉反馈。系统自动记录每道题的答题时间（通过 `timeSpent` 字段精确到秒），在提交时将完整答题数据（questionId、selectedOptionId、timeSpent）打包发送至后端。提交后进入结果展示页，以 ECharts 雷达图展示各知识点掌握度分布，并用环形进度条展示综合评分和认知负荷指数。结果页同时列出薄弱知识点列表（按严重程度排序：严重/中等/轻微），每个薄弱点附带原因分析和改进建议。

**我的路径页（PathView.vue）** 集成 LearningPathView 和 AOOAnimation 两大核心组件。页面采用 Tab 切换结构：主 Tab 展示当前学习路径，包含统计面板（总天数、总时长、覆盖知识点数、日均学习量、认知负荷指数五项指标卡片）、路径变体选择器（三条差异化方案横向排列）、以及甘特图/时间轴双视图切换。甘特图使用 ECharts custom series 渲染，横轴为学习天数、纵轴为任务列表，每个任务以彩色矩形条展示，左侧带有任务类型对应的颜色指示条（视频=蓝色、测验=橙色、阅读=绿色、项目=紫色、练习=青色）。时间轴视图以垂直时间线方式按天分组展示任务卡片，鼠标悬停时弹出详细 tooltip 显示知识点、难度星级、学习资源和预估时间。AOO 动画 Tab 展示寻优过程可视化（详见第 2 点）。

**智能问答页（ChatView.vue）** 以"AI 智能工作台"为设计理念。页面背景使用 Canvas 绘制的动态粒子连线系统（50 个粒子 + 鼠标斥力交互），营造智能生命体交流的氛围。页面顶部为学科选择器（下拉菜单，预置人工智能导论、机器学习、深度学习、数据结构与算法等 6 个学科），中部为对话消息列表（自定义 ChatMessage 组件渲染），底部为输入区域（支持 Enter 发送、Shift+Enter 换行）并附带快捷提问按钮。对话区域上方提供快捷问题卡片（如"什么是深度学习？""解释反向传播算法的原理"等），点击即可发送。每条消息显示角色头像、内容、时间戳，助手消息额外显示溯源标注按钮、置信度指示和 Token 用量信息。消息列表自动滚动到底部。

**学生学情看板（DashboardView.vue）** 通过 ECharts 提供四类可视化图表：知识掌握雷达图（展示各知识点当前掌握度与初始掌握度的双区域对比）、认知负荷趋势折线图（展示历次诊断的记忆负荷/注意力负荷/加工负荷/综合负荷四条折线，含警戒线标注）、学习日历热力图（GitHub 贡献图风格，展示每日学习活动分布）、以及薄弱知识点列表（表格形式，按严重度排序，支持查看详情和建议）。页面头部以四张统计卡片展示综合评分仪表盘、完成任务进度、已掌握知识点数和总学习时长聚合数据。所有图表使用 ResizeObserver 实现容器尺寸自适应。

**教师仪表盘（TeacherDashboardView.vue）** 展示全班学情总览。页面按六大功能区组织：班级概览卡片（总学生数、平均掌握度、平均认知负荷、路径完成率）、学生列表表格（支持按掌握度/认知负荷/路径完成度等字段排序，含分页）、认知负荷分布柱状图（按区间统计学生人数分布）、共性薄弱知识点 Top 5 列表（含薄弱学生数和平均掌握度）、全班掌握度变化趋势折线图（按天聚合）、以及预警学生列表（高亮显示认知负荷过高或持续退步的学生，分 warning 和 danger 两个严重级别）。单击学生行可打开右侧 Drawer 抽屉，展示该学生的知识点掌握度雷达图、认知负荷维度和薄弱点详情（下钻功能）。路由守卫限制仅教师角色可访问。

**登录/注册页（LoginView.vue / RegisterView.vue）** 采用左右分栏布局。左侧为品牌展示区，深空背景叠加燕麦金径向光晕和粒子动画，展示"燕麦智导"品牌名称和宣传语。右侧为表单区，登录表单包含用户名、密码输入框和"记住我"复选框；注册表单额外包含昵称、邮箱和角色选择（学生/教师）。表单验证在前端完成（必填项、密码强度、两次密码一致性等）。登录成功后自动跳转到首页或 redirect 参数指向的原始页面。已登录用户访问登录/注册页会自动重定向到首页。

---

## 2. AOO 寻优过程的可视化实现方案

AOO 寻优过程使用 **ECharts 5.x** 实现完整的可视化方案，核心组件为 `AOOAnimation.vue`。该组件采用**帧播放动画**机制：将后端返回的 `AOOConvergenceData` 数据（包含每一代迭代的种群快照）逐帧渲染为 ECharts 图表，通过 JavaScript 定时器驱动帧切换。

**可视化元素包括：**

- **收敛曲线图（双 Y 轴）**：左 Y 轴为适应度值（范围 0-1），右 Y 轴为种群多样性（0%-100%）。图中叠加四条曲线：最优适应度（红色实线，带渐变面积填充）、平均适应度（蓝色虚线）、中位数适应度（灰色点线，默认隐藏以减少视觉噪音）、种群多样性（橙色实线，带渐变面积填充）。曲线数据仅展示到当前播放帧，随动画推进逐步绘制，模拟实时收敛过程。

- **种群散点分布图**：在收敛曲线的同一坐标空间中，叠加种群个体的散点分布。当前帧的个体以彩色散点展示，颜色编码个体角色：红色=精英个体（当前最优）、蓝色=普通个体、绿色=探索中个体（刚刚完成弹射或跳跃）。精英个体使用更大的符号尺寸（12px）+ 白色描边 + 发光阴影突出显示。历史帧的个体以半透明灰色小点（4px）"幽灵化"呈现，展示种群在解空间中的移动轨迹，形成"粒子轨迹"动画效果。

- **当前迭代标记线**：在当前帧的 X 轴位置绘制一条虚线标记，标注"第 N 代"。

- **实时统计面板**：图表上方显示五个关键指标：当前迭代数/总迭代数（大号数字）、最优适应度（红色）、平均适应度（蓝色）、种群多样性（橙色 + 迷你进度条）、种群规模。所有数字使用 JetBrains Mono 等宽字体。

**可视化数据接口格式：**

前端通过 `pathStore` 轮询 `GET /api/v1/aoo/status/{task_id}` 接口获取每轮迭代的中间结果。当任务状态为 `completed` 时，响应的 `result` 字段包含 `AOOLearningPathResult` 对象：

```typescript
interface AOOLearningPathResult {
  bestPath: BestPath          // 最优学习路径
  convergence: AOOConvergenceData  // 收敛曲线数据
}

interface AOOConvergenceData {
  iterations: number[]        // 迭代轮次序列 [1, 2, 3, ...]
  bestFitness: number[]       // 每代最佳适应度
  avgFitness: number[]        // 每代平均适应度
  diversity: number[]         // 每代种群多样性 [0, 1]
  medianFitness: number[]     // 每代中位数适应度
  q1Fitness: number[]         // 每代 Q1 四分位数
  q3Fitness: number[]         // 每代 Q3 四分位数
  populationSnapshots?: PopulationSnapshot[]  // 种群快照
  metadata: ConvergenceMetadata  // 元信息
}

interface PopulationSnapshot {
  fitnessValues: number[]     // 个体适应度值列表
  positionsX: number[]        // 降维后的 X 坐标
  positionsY: number[]        // 降维后的 Y 坐标
  colors: string[]            // 'elite' | 'normal' | 'exploring'
  bestIndex: number           // 最佳个体索引
}
```

前端 TypeScript 类型（`src/types/aoo.ts`）与后端 Pydantic Schema（`backend/app/schemas/aoo.py`）通过 `CamelModel` 基类自动完成 snake_case → camelCase 转换，严格同步。

---

## 3. 路径推荐的甘特图与任务列表渲染

学习路径的甘特图展示由 `LearningPathView.vue` 组件实现，数据来源于 `pathStore.ganttData` 计算属性。`pathStore` 从 `currentPath.dailyTasks`（二维数组，外层按天索引，内层为当天任务列表）派生出 `ganttData` 数组，每个任务从每天的 8:00 开始顺序排列，任务间自动间隔 15 分钟休息时间，最少展示宽度为 15 分钟。

**甘特图实现方案：** 使用 ECharts 的 `custom` series 类型，通过 `renderItem` 函数逐任务绘制矩形 + 左侧颜色指示条 + 文字标签。X 轴为学习天数（值域 0.5 到 maxDay+0.5，间隔 1 天，标签格式为"第N天"），Y 轴为任务名称（按天逆序排列，当天第一个任务在上方）。每个任务矩形宽度根据 `estimatedMinutes / 60` 计算，最小宽度 12px。矩形配色按任务类型区分（video=蓝色 #1890FF、quiz=橙色 #FA8C16、reading=绿色 #52C41A、project=紫色 #722ED1、exercise=青色 #13C2C2）。当任务数超过 12 项时，自动启用 ECharts dataZoom 纵向滑块进行滚动浏览。

**时间轴视图：** 作为甘特图的替代展示模式，以垂直时间线按天分组。每天用彩色圆点标记（颜色编码当天平均难度：绿=简单、橙=中等、红=困难），下方以卡片列表展示当天任务。每个任务卡片左侧带有类型色条，卡片主体显示任务类型标签（a-tag）、预估时间、任务标题，鼠标悬停时弹出 detailed tooltip（知识点名称、难度星级、学习资源列表）。两种视图通过工具栏按钮一键切换。

**三条差异化路径的切换展示：** 路径变体选择器位于甘特图/时间轴上方，以三列网格布局展示三条路径方案：速成冲刺型（橙色主题，高学习效果/高负荷推进，适合有基础的学习者）、稳扎稳打型（蓝色主题，平衡学习效果与认知负荷，默认选中）、查漏补缺型（绿色主题，低负荷/重点攻克薄弱点）。每张变体卡片显示图标、名称、强度标签（a-tag）、方案描述、关键统计（天数/任务数/总时长）和方案亮点标签。当前激活方案标注"✓ 当前方案"角标。点击卡片触发 `pathStore.selectAlternativePath()` 方法，从后端切换路径方案，甘特图/时间轴数据联动更新。备选路径数据通过 `GET /api/v1/aoo/status/{taskId}` 的 `alternativePaths` 字段获取。

---

## 4. 智能问答模块的 WEB 交互与溯源展示

智能问答模块（ChatView.vue + ChatInput.vue + ChatMessage.vue + QuickQuestions.vue）实现了自然语言提问、流式输出和溯源标注的完整体验。

**输入与发送交互：** 用户在底部输入框（`a-textarea`，autoSize 自适应高度）中输入问题，支持 Enter 键直接发送（通过 `@pressEnter` 事件处理，排除中文输入法组合状态）和 Shift+Enter 换行。输入框右侧有发送按钮（SendOutlined 图标），流式输出期间切换为停止按钮以支持取消。输入框上方提供 5 个快捷提问按钮（QuickQuestions 组件），点击自动填入并发送。学科选择器位于页面顶部，切换学科后对话历史保持不变（需手动清空）。

**流式输出逻辑：** 前端通过 `ragQueryStream()` 函数发起流式请求。该函数使用原生 `fetch` API 发起 POST 请求到 `/api/v1/rag/query`，请求头设置 `Accept: text/event-stream`，请求体包含 `{...data, stream: true}`。响应体通过 `ReadableStream` 的 `getReader()` 逐块读取，解析 SSE 格式（`data: ` 前缀行），按事件类型分发处理：`type: "chunk"` 事件将 `content` 追加到当前助手消息；`type: "done"` 事件将最终答案、引用来源、置信度、Token 用量等写入消息对象并结束流式状态。非流式响应（后端未开启 stream）时，一次性获取完整 JSON 并通过前端模拟打字机效果逐字展示。`ChatStore` 管理对话状态，包括 `addAssistantPlaceholder()`（创建空白占位消息）、`appendToAssistant()`（流式追加文本）、`finishAssistant()`（完成并附加元数据，含 sources、confidence、tokenUsage）、`cancelStream()`（通过 AbortController 取消请求）等操作。

**溯源标注展示：** 每条助手消息的 `sources` 字段包含引用来源列表（`RAGSource[]`），每个来源对象包含：`document`（文档名称）、`page`（页码）、`section`（章节）、`content`（引用内容摘要）、`score`（相似度得分）、`ref`（引用编号）。前端在答案文本末尾渲染"参考来源"折叠面板，展开后以列表形式展示每条来源：文档名 + 页码（如"《人工智能导论》第 45 页"）作为标题，点击可展开查看引用内容。同时，在答案正文中通过正则替换 `[1]`、`[2]` 等引用标记为可点击的悬浮标注标签，鼠标悬停时弹出 Popover 显示该引用的文档名、页码和内容摘要。置信度以小型环形进度条 + 百分比数字展示在消息角落。

**拒答提示：** 当 RAG 检索无充分证据时（后端返回 `confidence` 低于阈值或 `sources` 为空数组），前端展示特定的拒答界面：答案区显示灰色文字"抱歉，当前知识库中暂无足够的信息来回答这个问题。"，下方附带"建议您：尝试换一种表述方式提问，或联系教师补充相关学习资料。"。消息不展示溯源标注区域，置信度显示为红色低分。前端同时提供"反馈"按钮，允许用户标记该回答不够准确。

---

## 5. 学情看板的数据可视化图表

学生端和教师端的学情看板均使用 ECharts 5.x 实现全部图表，通过 ResizeObserver 实现响应式尺寸自适应。

**学生端图表（DashboardView.vue）：**

- **知识掌握度雷达图**：使用 `echarts` 的 `radar` 类型。数据来源于 `diagnosisStore.masteryRadarData`（{name: 知识点名, value: 掌握度 0-100}[]）。雷达图配置双数据系列：当前掌握度（燕麦金填充区域）和初始掌握度（半透明蓝色区域），两区域的重叠部分以更深的颜色突出提升幅度。雷达图上方叠加提升百分比标注（如"+23%"）。指示器标签使用知识点名称，最大值为 100。

- **认知负荷指数变化折线图**：使用 `line` 类型。横轴为诊断日期，纵轴为负荷值（0-1）。四根折线分别展示记忆负荷（蓝色）、注意力负荷（橙色）、加工负荷（绿色）、综合负荷（红色粗线）。综合负荷在 0.7 以上区域用红色半透明带标注"高负荷警戒区"。图表支持 dataZoom 横向滑动缩放，默认展示最近 10 次诊断数据。

- **学习进度条**：不是 ECharts 图表，而是通过自定义 CSS 进度条 + Ant Design Vue 的 `a-progress` 组件实现。展示已完成任务数 / 总任务数，进度条颜色根据完成率动态变化（<30%=红色、30%-70%=橙色、>70%=绿色）。下方用数字展示具体完成比例。

- **薄弱知识点列表**：使用 Ant Design Vue 的 `a-table` 组件。列包括知识点名称、严重程度（mild/moderate/severe，以不同颜色 Tag 展示）、薄弱原因、改进建议。支持按严重程度排序和按知识点名称筛选。每行有"查看详情"操作按钮，点击展开该知识点的学习资源推荐。

- **学习日历热力图**：使用 ECharts 的 `calendar` + `heatmap` 类型。数据来源于 `dashboardApi.getCalendarActivity()`，以 GitHub 贡献图风格展示每日学习时长分布。单元格颜色从浅灰到深绿渐变（学习时间越长越深），支持月份切换（左右箭头切换 calendarYear/calendarMonth）。

**教师端图表（TeacherDashboardView.vue）：**

- **班级认知负荷分布柱状图/箱线图**：使用 `bar` 类型。横轴为认知负荷区间（0-0.2 / 0.2-0.4 / 0.4-0.6 / 0.6-0.8 / 0.8-1.0），纵轴为学生人数。高于 0.7 的柱子使用红色，0.4-0.7 使用黄色，低于 0.4 使用绿色。图表上叠加一条班级平均认知负荷的红色虚线标记（markLine）。

- **共性薄弱知识点热力图/词云**：薄弱知识点列表以 `a-table` 表格展示 Top 5，包含知识点名称、薄弱学生数（可排序）、全班平均掌握度。同时利用 ECharts 的 `bar` 类型绘制水平条形图，Y 轴为知识点名称（按薄弱学生数降序），X 轴为薄弱学生数，柱子颜色按平均掌握度梯度着色（深红→浅红→橙色→黄色→绿色）。

- **预警学生列表**：使用 `a-table` 组件，高亮显示预警学生行。预警行根据严重程度使用不同的行背景色：`severity === 'danger'` 的使用红色半透明背景 + 左侧红色边框，`severity === 'warning'` 的使用橙色半透明背景 + 左侧橙色边框。表格列包括学生姓名、平均掌握度（低值红色）、认知负荷（高值红色）、预警原因（highLoad/lowMastery/both）、严重程度标签。预警学生默认排在表格顶部（通过前端排序）。

- **下钻功能**：点击任意学生行，触发 `showStudentDetail()` 方法，调用 `teacherApi.getStudentDetail(studentId)` 获取该学生的详细学情数据（知识点掌握度列表、认知负荷多维度、薄弱点、综合评分），在右侧 `a-drawer` 抽屉中渲染该学生的个人学情详情页（包含迷你雷达图和认知负荷指标卡片）。

---

## 6. 系统整体技术架构中的 WEB 层描述

本系统的前端采用 **Vue 3（Composition API）+ TypeScript + Vite** 作为核心框架，配合 **Ant Design Vue 4.x** 作为 UI 组件库，**ECharts 5.x** 作为数据可视化引擎。状态管理使用 **Pinia** 配合 **pinia-plugin-persistedstate** 插件实现关键状态的 localStorage 持久化。

**前端框架层：** 使用 Vite 作为构建工具，配置了 `unplugin-vue-components` 实现 Ant Design Vue 组件的按需自动导入（无需手动 import），路径别名 `@` 映射到 `src/` 目录。TypeScript 严格模式开启，所有接口类型定义集中在 `src/types/` 目录。路由系统使用 Vue Router 4 的 `createWebHistory` 模式，所有页面组件采用动态 `import()` 懒加载。

**后端 API 网关：** 使用 FastAPI 框架构建 RESTful API 服务，全局路由前缀为 `/api/v1`。通过 `APIRouter` 模块化组织认证、诊断、AOO 优化、RAG 问答、教师仪表盘等 14 个路由模块。集成 Celery 异步任务队列（Redis 作为 Broker）处理 AOO 路径优化等计算密集型任务。RAG 知识库的文档嵌入由**自研的 NumPy 轻量向量存储**（`app/services/rag/vector_store.py`）管理：向量以 `np.ndarray` 矩阵常驻内存，写入时同步以 JSON 文件原子持久化；存储阶段做 L2 归一化，使检索时的点积直接等价于余弦相似度。该方案不引入任何额外的数据库服务或重量级依赖。

**WebSocket 与实时推送：** 本系统未使用 WebSocket，而是通过 **SSE（Server-Sent Events）** 实现智能问答的流式输出。`/api/v1/rag/query` 接口在 `stream: true` 模式下以 `text/event-stream` 格式逐块返回 AI 生成内容。Nginx 配置中针对 SSE 路径设置了 `proxy_buffering off`、`proxy_cache off`、`chunked_transfer_encoding on` 等参数确保流式传输不被缓冲。AOO 寻优进度的实时更新通过 HTTP 轮询实现（前端每 2 秒轮询 `GET /api/v1/aoo/status/{task_id}`，最多轮询 150 次即 5 分钟超时保护）。

**静态资源部署：** 生产环境下，前端 `vite build` 构建产物（`dist/` 目录）由 Nginx 1.25 Alpine 静态服务。Nginx 配置了 API 反向代理（`/api/` → `backend:8000`）、SPA fallback（所有非文件请求指向 `index.html`）、Gzip 压缩（gzip_types 覆盖 js/css/json/svg/xml/wasm）、静态资源缓存（带 hash 的 assets 文件设置 1 年 max-age）、安全头（X-Frame-Options、X-Content-Type-Options、X-XSS-Protection）。开发环境下，Vite dev server 通过 `proxy` 配置将 `/api` 请求代理到后端（默认 `http://localhost:8000`，支持 `VITE_PROXY_TARGET` 环境变量覆盖）。

**系统技术架构图（调用关系）：**

```
┌──────────────────────────────────────────────────────────────────────┐
│                         用户浏览器 (Browser)                          │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │             Vue 3 SPA (Vite + TypeScript)                     │   │
│  │  ┌─────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │   │
│  │  │  Views  │ │  Stores  │ │ ECharts  │ │ Ant Design Vue   │ │   │
│  │  │ (14页)  │ │ (Pinia)  │ │ (图表)   │ │ (UI Components)  │ │   │
│  │  └─────────┘ └──────────┘ └──────────┘ └──────────────────┘ │   │
│  └──────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
                │  HTTP/HTTPS  │  SSE (text/event-stream)
                ▼              ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     Nginx 1.25 (反向代理)                             │
│   静态文件服务 (/ → dist/)   │   API 代理 (/api/ → backend:8000)       │
│   Gzip · SPA fallback · 安全头 · SSE 无缓冲                           │
└──────────────────────────────────────────────────────────────────────┘
                │
                ▼
┌──────────────────────────────────────────────────────────────────────┐
│                   FastAPI 后端服务 (Python 3.11)                       │
│  ┌──────────┐ ┌───────────┐ ┌──────────┐ ┌────────────────────────┐ │
│  │Auth 模块 │ │Diagnosis  │ │ AOO 优化  │ │ RAG 问答 (NumPy 向量) │ │
│  │JWT Token │ │认知诊断   │ │Celery异步 │ │  向量检索 + LLM生成    │ │
│  └──────────┘ └───────────┘ └──────────┘ └────────────────────────┘ │
│  ┌──────────┐ ┌───────────┐ ┌──────────┐ ┌────────────────────────┐ │
│  │Teacher   │ │Dashboard  │ │Learning  │ │  Agent (讯飞星辰API)   │ │
│  │教师仪表盘│ │学情看板   │ │Path 路径 │ │  SSE 流式对话          │ │
│  └──────────┘ └───────────┘ └──────────┘ └────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
        │                   │                     │
        ▼                   ▼                     ▼
┌──────────────┐  ┌──────────────────┐  ┌─────────────────────────────┐
│ PostgreSQL   │  │ Redis 7          │  │ NumPy 向量存储 (进程内)      │
│ 用户/诊断/   │  │ Celery Broker +  │  │ 文档嵌入 + 余弦检索          │
│ 路径/知识点  │  │ 缓存             │  │ JSON 文件持久化，非独立服务  │
└──────────────┘  └──────────────────┘  └─────────────────────────────┘
                                          │
                                          ▼
                              ┌─────────────────────────────┐
                              │  讯飞星火大模型 API          │
                              │  (LLM 生成 + Embedding)     │
                              └─────────────────────────────┘
```

---

## 7. 前端与后端的数据接口定义

前端通过 Axios 实例（`src/api/index.ts`）与后端 RESTful API 通信，baseURL 由环境变量 `VITE_API_BASE_URL` 配置（开发环境 `http://localhost:8000/api/v1`，生产环境 `/api/v1`）。请求拦截器自动注入 Bearer Token，响应拦截器统一处理 code=0/200 成功逻辑和各类错误码。以下为核心接口清单：

**认知诊断提交接口：**
- **POST** `/api/v1/diagnosis/submit`
- **请求参数**：`{ answers: [{ questionId: string, selectedOption: string, timeSpent: number }], subject: string, grade: string }` — answers 为答题列表，每项包含题目 ID、用户选项 ID、答题耗时（秒），subject 为学科名称，grade 为年级。
- **返回字段**：`{ id, userId, createdAt, subject, grade, masteryLevels: [{ knowledgePoint, mastery, level, confidence }], cognitiveLoad: { memoryLoad, attentionLoad, processingLoad, overall }, learningStyle, weakPoints: [{ knowledgePoint, reason, severity, suggestedRemediation }], overallScore, summary, radarData }` — masteryLevels 为各知识点掌握度 0-1（level 分为 weak/developing/proficient/excellent），cognitiveLoad 为四维认知负荷，overallScore 为综合评分 0-100。
- **错误码**：400（参数校验失败）、401（未登录）、403（非学生角色）、500（诊断计算异常）。

**路径生成接口（AOO 优化）：**
- **POST** `/api/v1/aoo/optimize`
- **请求参数**：`{ diagnosis_id: string, preferences?: { maxDays, focusAreas, intensity, maxDailyMinutes, populationSize, maxIterations } }` — diagnosis_id 为诊断结果 ID，preferences 为可选优化偏好（如最大天数、重点领域、学习强度 light/moderate/intensive）。
- **返回字段**：`{ taskId: string, estimatedSeconds: number }` — 异步任务 ID + 预估完成秒数。
- **状态轮询**：`GET /api/v1/aoo/status/{task_id}` → `{ taskId, status: 'pending'|'queued'|'processing'|'completed'|'failed', progress: 0-100, result?: { bestPath: {...}, convergence: {...} }, errorMessage?, estimatedRemainingSeconds? }` — 每 2 秒轮询，完成时 result 含路径 + 收敛数据。
- **错误码**：400（缺少 diagnosis_id）、401、403、404（task 不存在）、500（AOO 引擎异常）。

**智能问答接口：**
- **POST** `/api/v1/rag/query`
- **请求参数**：`{ question: string, top_k?: number(默认5), temperature?: number(默认0.5), max_tokens?: number(默认1024), student_id?: string, subject?: string, stream?: boolean }` — stream=true 时启动 SSE 流式输出。
- **SSE 事件格式**：`data: {"type":"chunk","content":"文本片段"}`（流式增量）→ `data: {"type":"done","answer":"完整答案","sources":[{document,page,section,content,score,ref}],"confidence":0.85,"retrieval_count":5,"model":"spark-lite","token_usage":{...},"query_id":"..."}`（流式结束）。
- **一次性返回**（stream=false）：直接返回完整 `RAGQueryResponse` JSON。
- **错误码**：400（问题为空）、422（参数校验）、500（LLM 调用失败或知识库未初始化）。

**学生学情数据获取接口：**
- `GET /api/v1/dashboard/cognitive-load-trend?limit=10` → `CognitiveLoadTrendPoint[]` — 认知负荷历史趋势。
- `GET /api/v1/dashboard/calendar-activity?year=&month=` → `DailyActivityItem[]` — 学习日历数据。
- `GET /api/v1/dashboard/suggestions` → `LearningSuggestion[]` — AI 学习建议。
- `GET /api/v1/dashboard/overview` → `DashboardOverview` — 看板概览数据（总学习时长、完成任务数、已掌握知识点数、连续学习天数等）。

**教师班级聚合数据接口：**
- `GET /api/v1/teacher/class-overview` → `ClassOverview`（总学生数、平均掌握度、平均认知负荷、高负荷人数、低掌握度人数）。
- `GET /api/v1/teacher/students?sortBy=&order=` → `{ students: StudentSummary[], total }` — 学生学情列表。
- `GET /api/v1/teacher/weak-knowledge-points?topN=5` → `WeakKpStat[]` — 共性薄弱知识点。
- `GET /api/v1/teacher/mastery-trend?days=30` → `MasteryTrendPoint[]` — 全班掌握度趋势。
- `GET /api/v1/teacher/alerts` → `AlertStudent[]` — 预警学生列表。
- `GET /api/v1/teacher/students/{student_id}` → `StudentDetail` — 单个学生详情（下钻）。
- `GET /api/v1/teacher/dashboard` → `TeacherDashboardData` — 聚合数据（一次性获取上述所有数据）。

**登录/注册接口：**
- `POST /api/v1/auth/login` → `{ token, userInfo: { id, username, nickname, role, ... } }` — 请求体 `{ username, password, remember? }`。token 为 JWT 格式。
- `POST /api/v1/auth/register` → `{ token, userInfo }` — 请求体 `{ username, password, confirmPassword, nickname, email?, role }`。
- `POST /api/v1/auth/refresh` → `{ token }` — 刷新 Token。
- `POST /api/v1/auth/logout` → void — 退出登录（服务端可选的 Token 黑名单）。
- `GET /api/v1/auth/me` → `UserInfo` — 获取当前用户信息。

**通用错误响应格式：** 所有接口错误均返回 `{ code: number, message: string, data?: any }`。前端 Axios 拦截器对 HTTP 层面的 401/403/404/500 以及业务层面的非 0/200 code 进行统一处理，显示 Ant Design Vue message 提示。

---

## 8. AOO 寻优动画回放的控制逻辑

AOO 寻优动画回放由 `AOOAnimation.vue` 组件实现，该组件接收父组件传入的 `AOOConvergenceData` 数据，通过内置的帧播放引擎驱动 ECharts 图表的逐帧渲染。

**播放控制栏包括以下控件：**

- **重新播放按钮（ReloadOutlined 图标）**：点击后调用 `replay()` 方法，将 `currentFrameIndex` 重置为 0，`hasCompleted` 重置为 false，然后自动开始播放。

- **后退一帧 / 前进一帧按钮（StepBackwardOutlined / StepForwardOutlined 图标）**：分别调用 `stepBackward()` 和 `stepForward()` 方法，在当前帧基础上减 1 或加 1，通过调用 `seekTo()` 方法实现跳转。到达首帧或末帧时按钮自动 disabled。

- **播放/暂停按钮（CaretRightOutlined / PauseCircleOutlined 图标）**：核心控制按钮，使用 `togglePlayPause()` 切换。播放状态下启动 `setInterval` 定时器，每帧间隔由当前速度档位决定（1x=600ms、2x=300ms、5x=120ms）。定时器回调中递增 `currentFrameIndex` 并调用 `updateChart()` 刷新图表，到达最后一帧时自动暂停并触发 `complete` 事件。暂停状态下调用 `stopAnimationTimer()` 清除定时器。窗口失焦时（`visibilitychange` 事件）自动暂停，避免后台持续消耗性能。

- **进度条（Range Input）**：透明滑块覆盖在可视化进度条之上，用户可拖拽滑块跳转到任意帧。`@input` 事件调用 `seekTo(Number(target.value))`，通过 `clamped` 计算确保索引在有效范围内。进度条下方有填充动画显示当前播放进度百分比。

- **速度调节（1x / 2x / 5x 三档按钮）**：通过 `setSpeed()` 方法切换当前速度档位。切换时如果正在播放，会先停止当前定时器，再以新间隔重启定时器。速度按钮组使用胶囊样式，当前选中档位高亮为蓝色。

**存储与读取历史寻优日志：** 寻优日志数据存储在 `AOOOptimizationLog` 数据库表中（后端 ORM 模型 `aoo_optimization_log.py`），与诊断记录（`diagnosis_id`）和学习路径（`path_id`）关联。前端通过以下方式获取回放数据：
- 在路径页面（PathView.vue）的 AOO 动画 Tab 中，`convergenceData` 随路径生成结果一起缓存于 `pathStore`（通过 Pinia persist 插件持久化到 localStorage，key 为 `oat_path_store`）。
- 支持按路径 ID 回放：当用户查看历史路径时，调用 `pathStore.fetchPath(id)` 获取路径详情，如果 API 返回了 convergence 数据，则自动绑定到 `AOOAnimation` 组件。
- 支持按诊断 ID 回放：可以通过 `diagnosisStore.fetchById(id)` 获取历史诊断，再从关联的路径中提取收敛数据。

组件通过 `defineExpose` 对外暴露了完整的编程控制接口：`play()`、`pause()`、`togglePlayPause()`、`seekTo(frameIndex)`、`replay()`、`stepForward()`、`stepBackward()`、`setSpeed(speed)`、`setProgress(pct)`，父组件可通过 `ref` 获取组件实例直接控制播放行为。

---

## 9. 响应式与跨设备适配说明

本系统前端采用**桌面优先（Desktop-First）**策略，同时通过 CSS 媒体查询实现了对平板和手机的响应式适配。

**PC 端（>1024px）：** 所有页面使用 AppLayout 侧边栏布局，侧边栏宽度 240px，主内容区域自适应填充。导航栏固定在顶部（高度 56px），底部有燕麦金发光边框。统计卡片使用 5 列网格布局，路径变体选择器使用 3 列网格。

**平板端（768px-1024px）：** 侧边栏在平板端自动折叠为图标模式（宽度 64px），通过 `AppLayout.vue` 的 `collapsed` 状态控制。统计卡片从 5 列调整为 3 列，部分图表重新计算 Grid 边距。甘特图的 X 轴标签和 Tooltip 尺寸适度缩小。

**手机端（<768px）：** 侧边栏完全隐藏，改为顶部汉堡菜单触发 Drawer 抽屉导航。统计卡片切换为 2 列网格。路径变体选择器从 3 列切换为单列纵向排列。甘特图/时间轴控制栏改为纵向折叠布局，移动端隐藏速度选择按钮以节省空间。AOO 动画组件的控制栏在移动端堆叠排列（direction: column），进度条占满宽度，速度选择按钮隐藏（或收入更多菜单）。

**诊断作答的移动端体验：** 移动端下，题目选项从横排改为纵排，每个选项卡片宽度 100%，方便手指点击。选项的选中态反馈增强（加大触摸区域 min-height、增加 tap highlight）。答题进度条固定在屏幕顶部（sticky），方便随时查看进度。

**路径查看的移动端体验：** 甘特图在移动端替换为时间轴视图（因为横轴天数过多时甘特图在窄屏上不易阅读）。时间轴的任务卡片增大内边距，Tooltip 在移动端改为 Bottom Sheet 样式（固定在屏幕底部弹出），避免悬浮定位超出屏幕。

**全局响应式断点：** 在 `variables.less` 中定义了统一的断点变量，各组件的 `<style scoped>` 中通过 `@media (max-width: 768px)` 和 `@media (max-width: 480px)` 覆盖特定样式。ECharts 图表通过 `ResizeObserver` 监听容器尺寸变化自动重绘。

---

## 10. 教师仪表盘的班级筛选与下钻功能

教师仪表盘（TeacherDashboardView.vue）提供了多维度的班级数据筛选和逐级下钻功能。

**筛选交互：**
- **按班级筛选**：页面顶部工具栏提供班级下拉选择器（`a-select`），教师可选择查看所教的不同班级数据。选择后所有图表和数据表格联动更新。
- **按专业筛选**：与班级选择器并列，提供专业筛选下拉菜单（如"计算机科学""人工智能""软件工程"等），支持多选模式。
- **按学习阶段筛选**：提供学习阶段选择器（如"大一""大二""大三""大四"），按学生的年级/阶段过滤数据。
- **学生列表排序**：表格各列支持点击排序（按平均掌握度、认知负荷、路径完成率、最近活跃日期等字段，asc/desc 切换）。排序参数通过 `studentsSortField` 和 `studentsSortOrder` 状态变量传递给后端 API 的 `sortBy` 和 `order` 参数。

**下钻功能：**
- **学生详情抽屉**：点击学生列表中的任意行触发 `showStudentDetail(student)` 方法。该方法调用 `teacherApi.getStudentDetail(studentId)` 获取该学生的完整学情数据，在右侧 `a-drawer` 抽屉中渲染个人学情详情页。抽屉宽度 480px（移动端 100%），内容包含：学生基本信息（姓名、学号、班级）、知识掌握度迷你雷达图（ECharts，高度 260px）、四维认知负荷指标卡片（记忆负荷/注意力负荷/加工负荷/综合负荷，环形进度条展示）、薄弱知识点列表（a-table）、学习建议（a-alert 组件）。抽屉内提供"查看完整报告"按钮（链路到该学生的完整学情看板页面）。
- **层级导航**：页面顶部显示面包屑导航（a-breadcrumb），支持从"仪表盘 → 班级 → 学生详情"的层级返回路径。点击面包屑任意层级可返回对应视图。
- **数据联动**：筛选条件变更时，通过 `watch` 监听筛选状态变化，自动调用对应 API 刷新所有图表和表格数据。每次数据请求前显示 `tableLoading` 加载状态（表格骨架屏）。

---

## 11. 用户状态管理与路由守卫

前端用户状态管理基于 **Pinia Store** 实现，配合 **pinia-plugin-persistedstate** 插件实现关键状态的 localStorage 持久化。

**登录态管理：**
- **Token 存储**：JWT token 存储在 `useUserStore` 的 `token` 响应式变量中，通过 Pinia persist 插件自动同步到 localStorage（key: `oat_user_store`），持久化字段包括 `token`、`userInfo`、`remember`。
- **Token 注入**：Axios 请求拦截器（`src/api/index.ts`）在每次请求前从 `localStorage.getItem('oat_user_store')` 读取持久化的 token，设置 `Authorization: Bearer {token}` 请求头。这种直接读取 localStorage 的方式避免了与 Pinia Store 的循环依赖。
- **登录态恢复**：页面刷新后，Pinia persist 插件自动从 localStorage 恢复 `token` 和 `userInfo`，无需手动调用恢复方法。用户通过 `useUserStore().isAuthenticated`（computed，基于 token 是否有值）判断登录状态。
- **"记住我"功能**：登录时用户勾选"记住我"复选框，`remember` 字段被持久化。当 `remember` 为 false 时，关闭浏览器或会话结束后 token 被清除（依赖 sessionStorage 或短期过期策略）。
- **退出登录**：调用 `logout()` 方法，清除 `token`、`userInfo`，并立即调用 `localStorage.removeItem()` 清除 `oat_token`、`oat_user`、`oat_user_store` 三个持久化 key，防止 persist 插件恢复。

**路由守卫（`src/router/index.ts`）：**
- **全局前置守卫（beforeEach）**：每次路由跳转前执行三步检查。
    1. **白名单放行**：`/login` 和 `/register` 路由直接放行，但如果用户已登录（`isAuthenticated === true`），则重定向到 `/home`。
    2. **认证检查**：非白名单路由检查 `userStore.isAuthenticated`。未登录则跳转到 `/login?redirect={当前路径}`，登录成功后自动跳回原页面。
    3. **角色权限检查**：路由的 `meta.roles` 定义了该路由允许的角色数组。如果用户角色（`userStore.role`）不在允许范围内，重定向到 `/home` 并打印控制台警告。
- **页面标题**：守卫中根据 `to.meta.title` 动态设置 `document.title`，格式为 `{页面标题} - 燕麦智导`。

**角色切换**：系统支持学生和教师两种角色，角色由登录时后端返回的 `userInfo.role` 决定。路由配置中，学生专属页面（diagnose/path/chat/dashboard）设置 `meta.roles: ['student']`，教师专属页面（teacher/*）设置 `meta.roles: ['teacher']`。首页（/home）不设角色限制，所有已登录用户可访问。角色不匹配的访问尝试被静默重定向到首页。

---

## 12. 前端性能优化策略

针对大量 ECharts 图表和 AOO 动画，系统实施了多层级的性能优化措施：

**代码分割（Code Splitting）：** Vite 构建配置中通过 `rollupOptions.output.manualChunks` 将依赖拆分为三个独立 chunk：`ant-design-vue`（UI 组件库，体积最大）、`echarts`（图表库，按需引入）、`vue-vendor`（Vue/Vue Router/Pinia）。同时所有页面组件使用动态 `import()` 懒加载（在路由配置中以 `() => import('@/views/...')` 形式定义），路由切换时按需加载页面代码。

**图表懒加载：** ECharts 图表实例在组件 `onMounted` 生命周期中初始化，仅在图表容器进入视口时才创建实例。图表数据为空时不初始化 ECharts（如无甘特图数据时显示空状态占位符而非空图表）。`AOOAnimation` 组件在未收到有效的 `convergenceData` 时渲染空状态文字，不创建 ECharts 实例。

**数据分页：** 教师端学生列表使用后端分页（`page` / `pageSize` 参数），每次仅请求当前页数据（默认每页 20 条）。诊断历史列表同样使用分页加载。前端 `a-table` 组件配置 `pagination` 属性实现分页控件。

**按需渲染与条件显示：** 甘特图仅在 `flatTasks.length > 0` 时渲染图表，否则显示空状态。路径变体选择器仅在 `variants.length > 1` 时显示。AOO 动画的统计面板和控制栏可通过 props 控制显隐（`showStats` / `showControls`）。

**ResizeObserver 管理：** 每个 ECharts 图表实例绑定独立的 `ResizeObserver`，组件 `onUnmounted` 时同步调用 `disconnect()` 释放观察者，防止内存泄漏。

**请求去重与轮询管理：** 路径生成时，`pathStore.generatePath()` 检查 `isGenerating && optimizationStatus !== 'idle'` 防止重复触发。轮询停止时通过 `stopPolling()` 清除 `setTimeout` 定时器，组件 dispose 时同步清理。

**Canvas 性能优化：** ChatView 的背景粒子系统限定了最多 50 个粒子，每帧仅绘制必要连线（距离 < 180px 的粒子对），使用 `requestAnimationFrame` 驱动渲染循环，组件 `onBeforeUnmount` 时取消动画帧。

**构建优化：** Vite 生产构建关闭 sourcemap，设置 `chunkSizeWarningLimit: 1500`（允许 ECharts 较大的 chunk），启用 CSS code splitting。

---

## 13. WEB 端错误提示与异常处理界面

系统在多个层面实现了用户友好的错误处理和异常提示：

**网络异常：** Axios 响应拦截器捕获 `error.message.includes('timeout')` 时显示"请求超时，请稍后重试"提示（antd message.error）。网络完全不可达时显示"网络异常，请检查网络连接"。两种情况均不中断页面操作，用户可手动重试。

**API 超时：** Axios 实例默认超时时间为 15 秒。路径生成轮询时，若单次轮询失败不会立即中止，而是延长下次轮询间隔至 4 秒（双倍）并继续重试，最多重试 150 次（总计 5 分钟超时保护）。超时后显示"路径生成超时，请稍后重试或联系管理员"提示，轮询自动停止。

**AOO 计算失败：** 当轮询返回 `status: 'failed'` 时，`pathStore` 将错误信息存入 `error` 状态变量，PathView 页面在 AOO 动画 Tab 区域展示错误提示卡片，包含失败原因（如 `errorMessage`）和"重新生成"操作按钮。用户在路径生成过程中不会看到白屏或崩溃，而是始终看到状态流转（pending → queued → processing → completed/failed）。

**RAG 检索无结果：** 当后端返回的 `confidence` 低于阈值或 `sources` 数组为空时，ChatView 在助手消息中渲染专门的拒答界面。消息气泡显示半透明灰色背景，内容为"抱歉，当前知识库中暂无足够的信息来回答这个问题。"，附带建议文字和反馈按钮。消息的置信度指示器显示为红色低分。

**HTTP 错误状态码：**
- 401 未授权：拦截器区分处理。`/auth/login` 请求的 401 视为"用户名或密码错误"，显示后端返回的 `detail` 消息。其他请求的 401 触发 `handleUnauthorized()`，清除 localStorage 并显示"登录已过期，请重新登录"，500ms 后跳转登录页（带 redirect 参数）。
- 403 禁止访问：显示"没有权限访问"。
- 404 资源不存在：显示"请求的资源不存在"。
- 500 服务器错误：显示"服务器错误"。

**全局异常捕获：** `main.ts` 中通过 `app.config.errorHandler` 注册全局 Vue 错误处理器，将未捕获的组件渲染错误输出到控制台日志（`console.error`），防止整个应用崩溃。路由切换使用 `<transition name="page-fade">` 包裹，确保页面切换的视觉连续性。

**空状态设计：** 各数据展示区在无数据时呈现统一的空状态 UI：居中图标（灰色半透明）+ 主文字（如"暂无学习路径数据"）+ 副文字（引导操作提示，如"完成认知诊断后，系统将自动生成个性化学习路径"），而非空白页面。

**加载状态：** 全局加载组件 `GlobalLoading.vue` 使用 AOO 流动光弧 SVG 动画（替代传统 Spin），所有数据请求期间通过 `loading` 状态变量控制骨架屏或 Spin 组件展示。

---

## 14. 前端日志与用户行为埋点（可选）

本系统设计了前端用户行为埋点机制，用于支持用户测试效果验证和后续数据分析。埋点系统采用轻量级设计，不依赖第三方分析服务，数据通过后端 API 落库存储。

**埋点事件类型：**

| 事件类别 | 事件名称 | 触发时机 | 记录字段 |
|---------|---------|---------|---------|
| 页面浏览 | `page_view` | 路由切换时（router.afterEach） | page, timestamp, userId, referrer |
| 认证行为 | `user_login` / `user_register` / `user_logout` | 登录/注册/退出成功时 | userId, role, timestamp |
| 诊断行为 | `diagnosis_start` / `diagnosis_submit` / `diagnosis_view_result` | 开始诊断/提交答案/查看结果 | diagnosisId, subject, answerCount, totalTimeSpent, overallScore |
| 路径行为 | `path_generate_start` / `path_generate_complete` / `path_view` / `path_switch_variant` | 触发AOO/生成完成/查看路径/切换方案 | pathId, diagnosisId, variantIndex, generationTime |
| 问答行为 | `chat_query` / `chat_view_source` / `chat_rate_answer` | 发送问题/查看溯源/评价答案 | queryId, subject, question(截断), confidence, hasSources |
| 看板行为 | `dashboard_view` / `dashboard_export` | 浏览看板/导出数据 | page, chartInteractions |
| 点击行为 | `button_click` | 关键按钮点击 | buttonId, page |

**实现方式（可选启用）：** 在 `src/utils/` 中创建 `tracking.ts` 工具模块，提供 `track(event, data)` 函数。该函数通过 `navigator.sendBeacon()` 或普通 POST 请求将埋点数据异步发送到后端 `/api/v1/analytics/track` 端点（不影响主业务流程）。埋点调用分散在各 Store 的 action 方法和组件的生命周期钩子中。前端通过环境变量 `VITE_ENABLE_TRACKING` 控制是否启用埋点（开发/测试环境可关闭）。用户敏感信息（如问题原文、答案内容）在发送前做截断或脱敏处理。

**本地日志记录：** 开发环境下通过 `console.log` 输出关键状态变更（路由跳转、API 请求、Store 变更），生产环境关闭。API 请求/响应在开发环境通过 Axios 拦截器以 `[Request]` 和 `[Response]` 前缀输出方法、URL 和参数。

---

## 15. 部署与运行说明（WEB 部分）

**前端项目构建：**

```bash
# 1. 安装依赖
npm install

# 2. 开发环境启动（HMR 热重载，端口 5173）
npm run dev

# 3. 生产环境构建（输出到 dist/ 目录）
npm run build:prod
# 注：build:prod 使用 vite build --mode production，跳过 vue-tsc 类型检查
```

**环境变量配置：**

| 环境变量 | 开发环境 (.env.development) | 生产环境 (.env.production) | 说明 |
|---------|--------------------------|--------------------------|------|
| `VITE_API_BASE_URL` | `http://localhost:8000/api/v1` | `/api/v1` | 后端 API 基础路径 |
| `VITE_APP_TITLE` | 燕麦智导 | 燕麦智导 | 应用标题 |
| `VITE_APP_ENV` | development | production | 当前环境标识 |
| `VITE_PROXY_TARGET` | `http://localhost:8000` | — | Vite dev server 代理目标 |
| `VITE_ENABLE_TRACKING` | false | true | 是否启用埋点 |

**开发环境配置：** 运行 `npm run dev` 启动 Vite dev server（监听 0.0.0.0:5173）。Vite 配置了 API 代理：所有 `/api` 前缀的请求被转发到 `VITE_PROXY_TARGET`（默认 `http://localhost:8000`），解决前端独立端口（5173）与后端（8000）的跨域问题。`unplugin-vue-components` 自动按需加载 Ant Design Vue 组件，无需手动 import。支持 HMR 热重载，修改 `.vue`/`.ts`/`.less` 文件即时生效。

**生产环境构建与部署：** 执行 `npm run build:prod` 后，Vite 在 `dist/` 目录生成优化后的静态文件（HTML + JS + CSS + 图片）。构建配置通过 `manualChunks` 将 ant-design-vue、echarts、vue-vendor 拆分为独立文件便于浏览器缓存。所有带 hash 的文件名支持长期缓存策略。

**Docker 部署：** 生产环境使用 `docker-compose.prod.yml` 一键部署。前端通过 Dockerfile 多阶段构建：第一阶段使用 `node:20-alpine` 运行 `npm run build:prod` 生成 `dist/`；第二阶段使用 `nginx:1.25-alpine`，将 `dist/` 复制到 `/usr/share/nginx/html/`，将 `nginx.conf` 复制到 `/etc/nginx/conf.d/default.conf`。Nginx 作为 Web 服务器同时提供静态文件服务和 API 反向代理，暴露 80 端口。

**Nginx 关键配置：**
- 静态资源缓存：带 hash 的 assets 文件设置 `expires 1y` 和 `Cache-Control: public, immutable`。
- API 代理：`location /api/` 代理到 `http://backend:8000`，透传 `Host`、`X-Real-IP`、`X-Forwarded-For`、`X-Forwarded-Proto` 头。
- SSE 支持：API 代理配置 `proxy_buffering off`、`proxy_cache off`、`chunked_transfer_encoding on`，确保流式响应不被缓冲。
- SPA fallback：`location /` 的 `try_files $uri $uri/ /index.html`，确保前端路由刷新后正确返回 index.html。
- Gzip 压缩：对 text/html、application/javascript、text/css、application/json、image/svg+xml 等类型开启 gzip 压缩（gzip_min_length 1000）。
- 安全头：`add_header X-Frame-Options "SAMEORIGIN"`、`add_header X-Content-Type-Options "nosniff"`、`add_header X-XSS-Protection "1; mode=block"`。

**连接后端服务：** 生产环境前端与后端通过 Docker Compose 自定义网络（`aoo_network`）通信。前端 Nginx 容器的 `/api/` 代理指向 `backend:8000`（Docker 服务名）。后端依赖 PostgreSQL 和 Redis 服务（同样通过 Docker 服务名 `postgres:5432` 和 `redis:6379` 通信）。后端容器启动时通过 `entrypoint.sh` 脚本等待数据库和 Redis 就绪，然后自动运行 Alembic 数据库迁移，最后启动 Uvicorn ASGI 服务器（4 个 worker）。
