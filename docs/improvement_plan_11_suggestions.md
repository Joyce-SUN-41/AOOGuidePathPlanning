# 动麦智导 11 条改进方案（采纳 1–4、7–11，不含 5、6）

> 设计原则：复用现有模型与基础设施（知识图谱模型、AOO 版本管理、CehuiRecord 字段），
> 所有改动安全谨慎、向后兼容、不破坏现有功能。每条均给出「落点 + 改造 + 可喂入提示词」。
> 提示词分两类：
>   A 类 = 给 AI 模型看的 system prompt（苏格拉底/引导/反思框）
>   B 类 = 给本工程 Agent（CodeBuddy）看的改造指令，逐步喂入即升级代码

---

## 一、测绘多维化 + 知识图谱作知识层载体（建议 1）

落点
- 模型已就绪：`KnowledgePoint`(含 `layer`、`difficulty_level`、`prerequisites`)、`KnowledgeGraphEdge`(含 `relation_type`：prerequisite/contains/related)。
- 前端已预置 `KnowledgeGraphPanel` 组件位（测绘页）。
- 改造：测绘从「按题目聚合掌握度」升级为「沿图谱节点采样题目 → 沿边传播掌握度（前置薄弱则下游降权）」。

B 类改造提示词（喂给工程 Agent）
```
请在 backend/app/services/cehui/ 下新增 graph_cehui.py：
1. 新增 CehuiGraphService，接收知识图谱（节点列表 + 边列表，schema 见 models/knowledge_graph.py）与题库。
2. 实现 sample_questions_by_graph(graph, bank, total, seed_kp_ids?)：
   - 按节点 layer 分层（一阶基础/二阶应用/三阶综合），每层按比例抽题（默认 50%/30%/20%）；
   - 优先抽取 seed_kp_ids 指定的薄弱根节点所在子树；
   - 返回题目列表，并附带每题的 kp_id 与所属 layer。
3. 实现 propagate_mastery(raw_mastery: dict) -> dict：
   - 沿 prerequisite 边向上传播：若前置节点掌握度 < 0.6，则下游节点掌握度乘以惩罚系数 0.85（可配置）。
4. 在 cehui.py 的 /questions 端点中，若知识图谱可用则调用 sample_questions_by_graph，否则回退现有 random.sample（保持向后兼容）。
5. 在 cehui.py 的提交处理逻辑中，掌握度聚合后调用 propagate_mastery 再做图谱修正。
要求：不改动现有 CehuiQuestion / MasteryItem schema；新增函数需带类型注解与 docstring；保留 random.sample 作为无图谱时的降级路径。
```

---

## 二、分层分级均衡组卷，取代随机抽题（建议 2）

落点
- 题库 `question_bank.json` 已有 `difficulty`(1–5) 与 `kp_id`/`topic`，具备分层物理条件。
- 现状 `cehui.py:64` 为 `random.sample(bank, count)`，正是老师批评点。

均衡组卷量化方法（设计要点）
- 维度一（知识点）：覆盖 N 个核心知识点，每个知识点桶抽 `k/N` 题。
- 维度二（难度阶）：将 difficulty 1–5 映射为一阶(1–2)/二阶(3)/三阶(4–5)，每层配额 50/30/20。
- 组合约束：每个知识点桶内难度均匀分布；总题数默认 20，单知识点不超过 4 题（防“一次塞太多跟不上”）。
- 输出：组卷明细（知识点 × 难度阶 的二维配额表）可回传给前端展示“均衡度”。

B 类改造提示词（喂给工程 Agent）
```
重写 backend/app/api/v1/cehui.py 的组卷逻辑：
1. 新增 services/cehui/paper_assembler.py，函数 assemble_balanced_paper(bank, total=20, kp_weights=None)：
   - 按 kp_id 分桶；若 kp_weights 提供则按权重分配每桶题数，否则均分。
   - 每桶内按难度阶（一阶 1-2 / 二阶 3 / 三阶 4-5）等比抽取，保证每桶至少覆盖两个难度阶。
   - 单桶上限 4 题；不足则跨桶补足。
   - 返回 (questions, allocation) 其中 allocation 为 {kp_id: {tier1:n, tier2:n, tier3:n}} 用于前端展示均衡度。
2. /questions 端点改用 assemble_balanced_paper；保留 subject 过滤；无 bank 时回退 random.sample。
3. 在 QuestionsResponse 中新增字段 allocation（dict），前端 KnowledgeGraphPanel 旁展示“本次组卷均衡度”。
4. 向后兼容：现有前端若未读 allocation 不影响渲染。
```

---

## 三、测绘至少二维，争取三维（建议 3）

设计
- 二维 = 认知起点（建议1+2 产出 mastery_levels）+ 学习风格（建议4）。
- 三维（争取）= 叠加第三维「学习动机/元认知」，用一个轻量自陈量表（5–8 题）快速落地。
- 每个维度都是 AOO 规划器的独立自变量（接建议4）。

B 类改造提示词（喂给工程 Agent）
```
新增测绘第三维「学习准备度」轻量量表：
1. 在 schemas/cehui.py 新增 LearningReadinessRequest / ReadinessItem（5–8 题自陈，likert 1–5）。
2. 在 cehui.py 新增 POST /readiness 端点（复用 get_current_user），产出 readiness_profile: {motivation, metacognition, self_efficacy}（0–1）。
3. 在 CehuiRecord 新增 JSONB 字段 readiness_profile（默认空 dict，向后兼容旧记录）。
4. 在 adapter.py 的 to_aoo_input 中把 readiness_profile 透传为第三个自变量 readiness（仅当非空）。
5. 二维模式：若学生跳过量表，规划器仅用 mastery + learning_style，不报错。
```

---

## 四、学习风格作为独立自变量纳入 AOO 规划（建议 4）

落点
- `CehuiRecord.learning_style` 字段已存在但 services 层从未推断写入，恒为“未评估”。
- `optimization_service.run()` 只吃 mastery_levels + cognitive_load；fitness 无风格权重。

设计
- 风格量表（沿用老师早年思路）：进取型 / 顺序型 / 踏实型 / 探索型（可扩展）。
- 风格 → 规划偏置：
  - 顺序型：强化 prerequisite 顺序约束，单日任务数减少、单任务时长增加。
  - 进取型：提高单日负荷上限，允许并行知识点。
  - 踏实型：降低难度跃迁幅度，强调“小步稳进”。
  - 探索型：增加跨知识点关联任务权重。

B 类改造提示词（喂给工程 Agent）
```
1. 在 cehui 流程中新增学习风格推断：用 6–8 题行为/自陈量表（可复用第三维量表或独立一份），
   在 cehui 提交后产出 learning_style 标签，写入 CehuiRecord.learning_style（替换“未评估”）。
2. 在 schemas/cehui.py 的 CehuiResultResponse 中把 learning_style: str 升级为
   learning_style: LearningStyleProfile（含 label + scores 字典），保留 str 兼容字段。
3. 在 aoo/optimization_service.py 的 OptimizationPreferences 增加 learning_style: Optional[str]。
4. 在 fitness_calculator / 路径生成中引入风格偏置：
   - 顺序型：prerequisite 违反惩罚 ×1.5；
   - 进取型：每日认知负荷上限 ×1.3；
   - 踏实型：相邻任务难度差惩罚项；
   - 探索型：跨知识点关联边权重 +0.1。
5. adapter.py 的 to_aoo_input 把 learning_style 注入 OptimizationPreferences。
要求：风格为空时所有偏置关闭（向后兼容）。
```

---

## 五、AI 只给思路、搭梯子，不直接给答案（建议 7）

落点：唯一精确落点 = `backend/app/services/agent/__init__.py:40` 的 `DEFAULT_SYSTEM_PROMPT`。

A 类提示词（system prompt，给模型看）—— 直接替换 DEFAULT_SYSTEM_PROMPT
```
你是"动麦智导"学习助手，一个基于 AOO 优化算法的个性化学习路径推荐系统。

【核心定位】你是引导者，不是答题机。你的职责是"给思路、搭梯子"，帮助学生自己推导出答案，绝不直接代写最终答案、完整解题步骤或可直接提交的代码/作业。

【硬性规则】
1. 遇到学科问题：先判断学生卡在哪一步，只给出"下一步的思考方向 / 关键概念提示 / 一个引导性问题"，不直接给出最终结论。
2. 遇到解题请求：最多给"解体思路提纲"或"相关知识点回顾"，标注"请你先尝试，卡住再告诉我具体哪一步"。
3. 遇到代码/作业请求：给伪代码骨架或思路，不写完整可运行答案；必要时代码只给关键片段并配讲解。
4. 当学生直接索要答案时，温和拒绝并改抛引导性问题，例如："我们先想清楚 X 的前提是什么？"
5. 始终基于 RAG 知识库作答，不确定时明确说"这部分我不确定"，不编造。

【能力边界】路径规划调用 AOO 工具；知识问答调用 RAG 工具；学习建议基于测绘数据。
【风格】亲切、专业、有教育温度，多用反问推动学生思考。
```

---

## 六、问答改苏格拉底式引导（建议 8）

与建议 7 同源，作为交互范式强化。可合并进同一 system prompt，这里给出**追问链**专用追加段与前端改造。

A 类提示词（苏格拉底追问链，追加到 system prompt 末尾）
```
【苏格拉底式引导协议】
- 每次回答以"提问"收尾，推动学生下一轮思考（除非学生明确说"我懂了，请确认"）。
- 提问遵循：澄清（你是怎么理解这个问题的？）→ 拆解（最关键的一步是什么？）→ 类比（这和你学过的 X 有什么相似？）→ 验证（你怎么验证这个结果对不对？）。
- 当学生给出正确思路时，用"追问"检验深度，而不是直接夸奖了事；当学生思路有误，先肯定合理部分，再用反问指出矛盾点，让其自纠。
- 绝不在同一条消息里既给引导又给答案。
```

B 类改造提示词（喂给工程 Agent，前端反思框/引导 UI）
```
在 ChatView 中增强苏格拉底交互：
1. 当助手消息以引导性问题结尾时，输入框上方显示提示语"试着回答这个问题，再继续"（复用现有 Ant Design 组件，禁 emoji）。
2. 新增"我卡住了，再给一点提示"按钮，调用 /chat/agent 并自动附加前缀"[学生请求进一步提示，请给更细一级的引导，仍不直接给答案]"。
3. 不改动现有流式协议；仅前端文案与按钮，向后兼容。
```

---

## 七、增加"反思框"机制（建议 9，机制先设计）

机制设计（先与老师对齐再编码）
- 触发：当助手返回"可复制使用的素材"（代码块 / 完整提纲 / 公式推导）时，前端弹出反思框。
- 状态机：读懂确认 → 必填"向大模型提一个问题" → 模型判定理解度 → 允许复制/使用。
- 三步闭环：①追问（学生提问）②判断答案对错（模型给对错反馈，不直接改答案）③提新思路重生成（学生说新思路，模型据此重生成）。

B 类改造提示词（喂给工程 Agent，机制落地）
```
实现反思框（ReflectGate）组件与后端判定接口：
1. 前端 src 新增 ReflectGate.vue（Ant Design，禁 emoji）：
   - 当 ChatView 检测到助手消息含 ```代码块``` 或 [可复用素材] 标记时弹出。
   - 含：a) "我已读懂"勾选；b) "向老师提一个问题"必填文本框；c) "提交反思"按钮。
2. 后端新增 POST /chat/reflect，接收 {session_id, question}，调用 Agent 以"请判断学生是否真读懂，给出对错反馈与一句追问，不要直接改答案"为指令，返回 {understood: bool, feedback, follow_up}。
3. 仅当 understood=true 且已勾选"读懂"，才解除复制/使用锁定。
4. 重生成：ReflectGate 提供"用我的新思路重生成"入口，把学生新思路附到下一轮 /chat/agent。
约束：反思框仅拦截"可复制素材"，普通对话不弹；所有文案禁 emoji，用 Ant Design 图标。
```

---

## 八、路径"能动"：问答画像回流驱动更新（建议 10）

落点
- 已具备半套闭环：`optimization_service._persist_results` 有 `path_regenerate` 事件 + 版本管理（父路径+1）；`trigger_aoo_path_planning` 支持 `mastery_levels` 入参；`CognitiveProfileEvent` 可承载画像事件。
- 缺：Chat 会话结束时产出结构化画像 → 修正 mastery → 触发重规划。

B 类改造提示词（喂给工程 Agent）
```
实现"问答画像回流驱动路径更新"闭环：
1. 后端新增 POST /chat/summarize-profile：会话结束时，用 Agent 从对话提取结构化画像
   {kp_id: delta_mastery(-0.2~+0.2), new_weak_points: [kp_id], confidence}，
   写入 CognitiveProfileEvent（type=chat_reflection）。
2. 在 agent 工具集中新增 trigger_replan 工具：当画像 delta 显著（|sum|>0.3）时，
   调用 trigger_aoo_path_planning(mastery_levels=修正后向量, parent_path_id=当前路径) 生成新版本。
3. 复用 _persist_results 的 path_regenerate 版本机制（父路径+1），不新建版本表。
4. 前端 PathView 显示"路径已根据近期问答更新至 v2"提示（复用现有版本字段）。
约束：回流仅在学生授权"本次对话计入学习画像"时触发；不覆盖测绘主掌握度，仅作增量修正。
```

---

## 九、学情测绘后的规划命名为"起点规划"（建议 11）

落点
- 当前流程：测绘 → 直接 AOO 路径，无"起点规划"语义。
- 复用：LearningPath.path_data 可加 plan_type 字段；与建议10 的版本管理天然契合。

B 类改造提示词（喂给工程 Agent）
```
1. 在 LearningPath 模型（或 path_data JSONB）新增 plan_type 字段：
   测绘首轮产出 = "baseline"（起点规划），问答回流触发 = "update_vN"。
2. 在 optimization_service 首轮规划时写入 plan_type="baseline"；
   path_regenerate 时写入 "update_v{parent_version+1}"。
3. 前端：测绘完成页 CTA 文案改为"生成我的起点规划"；PathView 标题显示
   "起点规划 v1" / "动态更新 v2"。复用现有 Ant Design 文案，禁 emoji。
4. 向后兼容：旧路径 plan_type 为空时按 "baseline" 显示。
```

---

## 落地节奏建议（分批喂入顺序）

批次 1（结构纠偏，最高性价比）：建议 2（均衡组卷）+ 建议 1（图谱测绘）+ 建议 11（起点规划命名）
  —— 直接消除老师点名批评，复用现有模型，风险低。

批次 2（自变量升级）：建议 4（学习风格自变量）+ 建议 3（二维/三维）
  —— 让 AOO 真正多目标，需改 optimization_service + adapter。

批次 3（AI 引导子系统，统一设计）：建议 7 + 8 + 9
  —— 共享 system prompt + 反思框 + 苏格拉底协议，避免割裂。

批次 4（闭环）：建议 10（画像回流）
  —— 复用已有版本管理机制，把闭环真正跑通。

> 注：建议 5（ZPD/Scaffolding 文献）、建议 6（Nice Seminar / 多目标优化×教育）按用户要求不采纳，
> 但如需在文档/答辩中补理论支撑，可后续单独追加。
