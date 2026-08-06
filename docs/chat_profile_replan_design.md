# 问答画像回流驱动路径更新（建议 10）— Reflect-to-Replan 闭环

> 状态：机制设计稿（待与老师对齐后再编码）
> 适用范围：Chat 会话结束 → 提取结构化画像 → 增量修正掌握度 → 触发 AOO 重规划（生成新版本路径）
> 设计基线：对齐既有架构（StudentCognitiveProfile 问答增量 / ChatMasteryProfile 绝对视图 / CognitiveProfileEvent 可观测 / _persist_results 版本机制 / trigger_aoo_path_planning(mastery_levels=)）

---

## 一、目标与原则

把"导学终端"从孤立对话升级为**路径的活水源**：学生在对话中暴露的掌握度变化，经结构化提取后增量修正画像，并在变化显著时驱动 AOO 重规划，生成待采纳的新版本路径。三原则（来自数据真实性底线）：

1. **绝不覆盖测绘主掌握度**：回流只写增量（`StudentCognitiveProfile.mastery_deltas`）或对话绝对视图（`ChatMasteryProfile`），不回写 `StudentKnowledge`。
2. **仅增量修正**：画像信号以 delta 形式沉淀，融合在内存（adapter）完成，落库不互相覆盖。
3. **授权才触发**：仅当学生明确授权"本次对话计入学习画像"时，才执行提取与重规划；未授权则对话纯咨询，零副作用。

---

## 二、现状盘点（已具备的半套闭环）

- `optimization_service._persist_results`：已有 `path_regenerate` 事件 + 版本管理（找 `is_active` 路径作父，`version = parent+1`，`auto_adopt` 控制是否直接生效）。**这正是重规划落点，直接复用，不新建版本表。**
- `optimization_service.run(... mastery_levels: Dict[str,float] ...)`：`trigger_aoo_path_planning` 已支持 `mastery_levels` 入参。回流只需拼出"修正后掌握度向量"传入。
- `CognitiveProfileEvent`：`event_type` 已含 `chat_signal/fusion/aoo_trigger/path_regenerate/baseline_fallback`，新增 `chat_reflection` 类型完全一致。
- `knowledge_base.py`：已有 LLM 提取 `mastery_estimates` 的提示词先例，可复用其抽取范式。
- `StudentCognitiveProfile.mastery_deltas`：设计初衷即"问答增量（相对）"，本回流的 delta 天然落此处。
- `ChatMasteryProfile.mastery`：对话梳理出的绝对掌握度视图，可用于"对话画像"展示与融合。
- `PathView.vue`：已有"待采纳重规划版本"横幅（`v{{pendingPath.version}}` + `explanation` 字段），chat 触发的重规划可直接落此横幅，无需新 UI。

**缺口**：① 会话结束缺"提取结构化画像"的动作；② 缺"delta → 修正向量 → 触发重规划"的编排；③ 缺"授权开关"。

---

## 三、闭环数据流

```
Chat 会话（授权计入画像）
   │  会话结束 / 手动"结束并提炼画像"
   ▼
POST /chat/summarize-profile
   │  Agent 从对话抽取 {kp_id: delta_mastery, new_weak_points[], confidence}
   ▼
写入 StudentCognitiveProfile.mastery_deltas（增量）+ CognitiveProfileEvent(type=chat_reflection)
   │  同时可选更新 ChatMasteryProfile.mastery（绝对视图，供"对话画像"展示）
   ▼
判定显著度：|sum(delta_mastery)| > 0.3 ?
   ├─ 否 → 仅落画像事件，不重规划（轻量回流）
   └─ 是 → 调用 trigger_replan 工具
              │  融合 = 测绘基线 StudentKnowledge + mastery_deltas → 修正向量
              ▼
       trigger_aoo_path_planning(mastery_levels=修正向量, parent_path_id=当前生效路径)
              │  复用 _persist_results：生成 v(parent+1)，is_active=False（待采纳）
              ▼
       CognitiveProfileEvent(type=path_regenerate, reasoning=...)
   ▼
PathView 横幅："检测到新版本路径 vN（待采纳）" + explanation（来自 reasoning）
```

---

## 四、后端设计

### 4.1 POST /chat/summarize-profile（新增）
- 入参（新增 schema `ChatSummarizeRequest`）：`session_id: str`、`authorized: bool = True`、`user_id: str`。
- 逻辑：
  1. 拉取该 `session_id` 的对话历史（复用 agent history 仓储）。
  2. 调 `service.chat(...)` 以抽取指令："从本段师生对话中，识别学生哪些知识点掌握度发生了变化。输出 JSON：{deltas:[{kp_id, delta_mastery(-0.2~+0.2)}], new_weak_points:[kp_id], confidence(0~1)}。仅基于对话中**明确暴露**的信号，勿编造；无法判断则返回空列表。"
  3. 解析 JSON（容错：解析失败 → 返回空画像 + `event_type=chat_reflection` 留痕"提取失败"，不阻断）。
  4. 写 `StudentCognitiveProfile.mastery_deltas`（按 kp_id 累加 delta，更新 confidence/n/last_at）——**仅增量，不碰 StudentKnowledge**。
  5. 写 `CognitiveProfileEvent(event_type="chat_reflection", payload={deltas, new_weak_points, confidence}, reasoning="会话提炼：识别出 N 个知识点掌握度变化")`。
  6. 返回 `{deltas, new_weak_points, confidence, significant: bool}`。
- 鉴权：`Depends(get_current_user)`。

### 4.2 trigger_replan 工具（agent 工具集新增）
- 触发条件：`|sum(delta_mastery)| > 0.3` 且学生授权。
- 实现（后端函数 `trigger_replan(student_id, deltas, parent_path_id)`）：
  1. 读 `StudentKnowledge`（测绘基线掌握度）+ `StudentCognitiveProfile.mastery_deltas`（问答增量）。
  2. 融合：`corrected[kp_id] = clamp(baseline[kp_id] + delta, 0, 1)`（融合逻辑可复用 `cehui/adapter.py` 的既有融合函数，避免重复实现）。
  3. 调 `trigger_aoo_path_planning(mastery_levels=corrected, parent_path_id=当前生效路径)`，内部 `_persist_results` 生成 `v(parent+1)`，`auto_adopt=False`（待采纳，更安全；可留 `auto_adopt` 可配开关）。
  4. 落 `CognitiveProfileEvent(type=path_regenerate, reasoning=...)`（复用 _persist_results 现有 reasoning 模板，reasoning 中标注"来源：问答画像回流"）。
- 该工具**不在对话里自动调用**，而是由 summarize-profile 的后端编排在显著度达标时显式调用，避免 Agent 自由触发重规划的不确定性。

### 4.3 显著度阈值与防抖
- 默认 `|sum(delta)| > 0.3` 触发重规划；低于阈值仅落画像（轻量回流），不重规划，避免路径频繁抖动。
- 同一会话多次 summarize 幂等：deltas 覆盖写（按 kp_id 取最新），不重复累加，避免重复触发。

---

## 五、前端设计

### 5.1 授权开关（ChatView）
- 会话工具栏新增"计入学习画像"开关（`a-switch`，默认关）。文案："授权后，本次对话将提炼为学习画像并可能更新你的路径"。
- 开关开启时，会话结束（清空/离开/手动"结束并提炼"）调用 `/chat/summarize-profile`；关闭则纯咨询。
- 提炼中显示 loading，完成后 `message.success("已提炼学习画像" + (显著 ? "，路径已更新至新版本" : ""))`。

### 5.2 PathView 提示（复用现有待采纳横幅）
- 无需新组件：`trigger_replan` 生成的路径已是 `is_active=False` 的 pending 版本，`PathView` 现有横幅直接显示 `v{{pendingPath.version}}` + `explanation`（来自 reasoning）。
- 提示语建议（需老师审稿，禁 emoji）："路径已根据近期问答更新至 vN（待采纳）" —— 复用现有 `pending-title` 结构，仅把 `explanation` 填充为回流 reasoning。
- 若老师希望更明确标注来源，可在 `explanation` 前缀"（问答画像回流）"。

### 5.3 "对话画像"抽屉（可选增强）
- 现有 ChatMasteryProfile 已支撑"对话画像"展示；回流写入后可让 PathView/问答页展示"本次对话修正了哪些知识点"，形成闭环可见性。本机制先保证回流正确，展示增强为可选项。

---

## 六、边界与风控（待老师确认）

1. **授权粒度**：开关是"整个会话计不计入"，还是"每条消息实时计入"？建议按会话（简单、可控），待老师确认。
2. **auto_adopt 策略**：默认生成待采纳版本（学生一键采纳），还是直接替换当前路径？建议默认待采纳，避免路径被对话悄悄替换引发困惑。
3. **显著度阈值 0.3**：是否按知识点数量/置信度加权？当前用 `|sum(delta)|`，可改为"任一 kp |delta|>0.15 或 总和>0.3"。阈值待老师/数据验证后调。
4. **融合口径**：修正向量 = 测绘基线 + 问答 delta。若学生未做测绘（无基线），应以 `ChatMasteryProfile` 绝对视图或微弱先验参与（沿用既有 `baseline_fallback` 逻辑），不回写客观数据。
5. **与反思框（建议 9）的关系**：建议 9 的 reflect 记录如需回流，可后续接入本机制（reflect 的 understood/feedback 作为画像信号源之一）。本稿先独立，留扩展位。
6. **成本**：`/chat/summarize-profile` 每会话一次 LLM 调用，成本可控；建议仅授权会话才调用。

---

## 七、落地清单（对齐后执行）

后端：
- `schemas/agent.py`：加 `ChatSummarizeRequest` / `ChatSummarizeResponse`
- `api/v1/chat.py`：加 `POST /chat/summarize-profile`
- 新增 `services/chat/profile_reflector.py`：`summarize_profile(session_id, user_id)`（抽取 + 写 deltas + 写 chat_reflection 事件）+ `trigger_replan(student_id, deltas, parent_path_id)`（融合 + 调 trigger_aoo_path_planning）
- `CognitiveProfileEvent` 的 `event_type` 文档补 `chat_reflection`
- 融合逻辑复用 `cehui/adapter.py` 既有函数，不重写

前端：
- `ChatView.vue`：加"计入学习画像"开关 + 会话结束调用 summarize-profile
- `PathView.vue`：回流 reasoning 填入现有 `explanation`（提示语待老师审稿）
- 可选：问答页"对话画像"抽屉展示本次修正

测试：
- 后端单测：summarize 抽取 JSON 容错、delta 累加幂等、显著度判定、trigger_replan 版本号 + is_active=False
- 联调：授权对话 → 提炼 → 显著 → PathView 出现 vN 待采纳横幅 → 一键采纳

---

## 八、与既有设计的兼容

- 不新建版本表，完全复用 `_persist_results` 的 parent/version/auto_adopt 机制。
- 不碰 `StudentKnowledge`（客观掌握度），仅写 `StudentCognitiveProfile.mastery_deltas` / `ChatMasteryProfile`（与既有数据真实性底线一致）。
- `CognitiveProfileEvent` 仅新增 `chat_reflection` 类型，不破坏既有事件消费（aoo.py 按 `path_regenerate` 查询不受影响）。
- `trigger_aoo_path_planning` 接口签名不变，仅由新编排调用。
- PathView 零新增组件，复用待采纳横幅。
