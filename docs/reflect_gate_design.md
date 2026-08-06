# 反思框机制设计（建议 9）— ReflectGate

> 状态：机制设计稿（待与老师对齐后再编码）
> 适用范围：ChatView 助手消息含"可复制使用的素材"时的反思闭环
> 设计基线：对齐现有架构（FastAPI + /chat/agent + SSE 流式 + Pinia chat store + ChatMessage.vue 复制按钮）

---

## 一、目标与原则

反思框（ReflectGate）是一个**拦截-反思-放行**机制，目的是把"学生直接复制 AI 成品"转化为"学生先证明自己读懂了"。它只拦截**可复制使用的素材**（代码块、完整提纲、公式推导），普通对话不弹。机制三原则：

1. 仅拦截可复用素材，绝不打扰正常问答。
2. 反思是"证明读懂"，不是"再考一次"——模型给对错反馈与一句追问，绝不直接改答案。
3. 三步闭环可循环：追问 → 判对错 → 给新思路重生成，直到学生真正理解。

---

## 二、触发条件（"可复制使用的素材"如何判定）

判定在助手消息**流式结束后**（`finishAssistant` 之后）对 `message.content` 做一次扫描，命中即弹框。判定优先级：

1. 代码块：正则 `/```[\s\S]*?```|~~~[\s\S]*?~~~/` 命中（Markdown  fences，覆盖 ``` 与 ~~~）。
2. 显式标记：内容含 `[可复用素材]` 或 `[可复制]` 文本标记（模型在输出完整提纲/公式推导时主动打标，作为代码块之外的兜底）。
3. 结构性提纲：命中"至少 3 个有序/无序列表项 + 含 '步骤/提纲/方案' 关键词"的弱信号（可选，默认关闭，避免误伤）。

建议默认启用 1+2，3 暂作可配置开关。判定结果写入 `ChatMessage` 新字段 `hasReusableMaterial: boolean`，由 store 维护，供 `ChatMessage.vue` 控制复制按钮锁定态。

注意：代码块判定是**前端正则**，与模型是否打标解耦——即使模型忘记打 `[可复用素材]`，含代码块仍会触发，保证机制不被模型"绕过"。

---

## 三、状态机

每条被拦截的助手消息携带一个独立的 ReflectGate 状态，初始为 `LOCKED`（复制/使用锁定）。状态迁移：

```
LOCKED ──(勾选"我已读懂" + 提交一个问题)──> REFLECTING
REFLECTING ──(后端返回 understood=false)──> LOCKED（保留已填问题，提示重答）
REFLECTING ──(后端返回 understood=true)──> UNLOCKED（解除复制/使用锁定）
UNLOCKED ──(学生点"用我的新思路重生成")──> 进入下一轮 /chat/agent（新思路作为用户消息）
```

补充说明：

- `understood=true` 且勾选"我已读懂"是**解除锁定的充要条件**，二者缺一不可（防止学生只勾选不提问，或只提问没勾选）。
- 一次消息可多次反思：若 `understood=false`，学生修改问题再次提交，状态回到 `REFLECTING`，不新建消息。
- 锁定仅针对该条消息的"复制/使用"动作；学生仍可与 AI 继续正常对话（发新消息不受限）。

---

## 四、前端组件设计（ReflectGate.vue）

新建 `src/components/chat/ReflectGate.vue`，Ant Design Vue，禁 emoji，图标统一用 `@ant-design/icons-vue`。

### 4.1 入参与出参
- Props：`messageId: string`、`locked: boolean`、`understood: boolean`、`feedback: string`、`followUp: string`、`reflecting: boolean`。
- Emits：`submit-reflect`(question: string)、`request-regenerate`(newIdea: string)、`acknowledge`(checked: boolean)。

### 4.2 界面元素
- (a) "我已读懂"勾选框（`a-checkbox`），绑定本地 `acknowledged` 状态，向上 emit `acknowledge`。
- (b) "向老师提一个问题"必填文本框（`a-textarea`），占位文案如"用自己的话，向老师提一个关于这段素材的问题"。
- (c) "提交反思"按钮（`a-button`），禁用条件：`!acknowledged || question.trim()==='' || reflecting`。
- (d) 反思反馈区：模型返回后展示 `feedback`（对错说明）+ `followUp`（一句追问），用 `a-alert`（info/warning 按 understood 着色）。
- (e) "用我的新思路重生成"入口（`a-button`，仅 `understood=true` 后出现）：弹一个小输入框收"新思路"，emit `request-regenerate`。

### 4.3 与 ChatView / ChatMessage 的衔接
- `ChatView.vue` 在 `finishAssistant` 后调用判定函数；命中则在对应助手气泡下方渲染 `<ReflectGate>`。
- `ChatMessage.vue` 的复制按钮受 `hasReusableMaterial && !unlocked` 控制：未解锁时按钮置灰（`disabled`）并提示"完成反思后可复制"，解锁后恢复。
- "使用"广义包含：复制、以及未来可能的"插入到笔记/导出单条"。本机制先锁"复制"，导出单条在 UNLOCKED 后才允许。

---

## 五、后端接口设计（POST /chat/reflect）

新增 `backend/app/api/v1/chat.py` 路由 `/reflect`，复用现有 `get_agent_service()`。

### 5.1 请求契约（新增 schema，写 `schemas/agent.py`）
```
class ReflectRequest(CamelModel):
    session_id: str          # 复用 /chat/agent 的会话 id，维持上下文
    question: str            # 学生向老师提的问题（必填，前端已校验非空）
    material: str            # 被拦截的素材原文（代码块/提纲），供模型判断依据
```
`material` 由前端把该条助手消息 `content` 传入，避免让模型仅凭一个问题猜上下文。

### 5.2 响应契约
```
class ReflectResponse(CamelModel):
    understood: bool         # 模型判定学生是否真读懂
    feedback: str            # 对错反馈（一句话，不直接改答案）
    follow_up: str           # 一句追问，引导进一步思考
```

### 5.3 实现要点
- 内部调用 `service.chat(session_id=..., message=REFLECT_INSTRUCTION, user_id=...)`，其中 `REFLECT_INSTRUCTION` 为拼接指令：
  "以下是学生刚收到的学习素材：{material}。学生提问：{question}。请判断学生是否真正读懂了这段素材，给出'读懂/未读懂'的结论、一句对错反馈（指出其理解偏差在哪，但**不要直接把答案改好**），以及一句追问引导学生自己补全。严格只输出 JSON：{understood:bool, feedback:str, follow_up:str}。"
- `service.chat` 已消费 `system=self._system_prompt`（苏格拉底/引导式），与反思"不给现成答案"的基调一致，无需额外 system 覆盖。
- 解析：要求模型输出 JSON；后端做 `json.loads` + 容错（解析失败时 `understood=false`，`feedback="没能识别你的理解，请换种方式再问一次"`，不阻断前端流程）。
- 非流式、低耗时，走现有 `service.chat` 同步路径即可，无需 SSE。
- 鉴权：`Depends(get_current_user)`，与 `/chat/agent` 一致。

### 5.4 重生成衔接
"用我的新思路重生成"本质是发起一轮普通 `/chat/agent`：把学生新思路拼成用户消息（如 "基于我刚才的思路：{newIdea}，请重新生成上面的素材"），复用现有流式链路。后端无需新增接口，仅前端组装消息。

---

## 六、三步闭环的落点映射

| 步 | 学生动作 | 系统响应 | 技术落点 |
|----|----------|----------|----------|
| ① 追问 | 在 ReflectGate 提问题并提交 | 模型返回 understood/feedback/follow_up | POST /chat/reflect |
| ② 判对错 | 看 feedback 与 follow_up | 模型只给反馈不改正，前端据 understood 解锁或保持锁定 | ReflectResponse + 状态机 |
| ③ 重生成 | 点"用我的新思路重生成" | 新思路作为下一轮 /chat/agent 用户消息，AI 重生成素材 | 复用 /chat/agent 流式 |

闭环可反复：若 understood=false，学生改问题再提交（回 ①）；若 understood=true，可继续 ③ 或正常对话。

---

## 七、边界与风控（待老师确认）

1. **误触发**：纯文字讲解含代码片段时必弹。建议老师确认是否接受"有代码即弹"，或改为"代码块 + 长度阈值（如 > 5 行）"。
2. **绕过**：学生可无视反思框直接开新对话复制——机制是教学引导而非强管控，是否需要在后端记录"未反思即复制"供教师端看板，待定。
3. **模型判定可靠性**：understood 由 LLM 判定，存在误判。建议 understood=false 时允许学生"申请人工/跳过"（教师端可配），避免卡死。
4. **文案合规**：所有 UI 文案禁 emoji，图标用 Ant Design；反思提示语需老师审稿（如"向老师提一个问题"的措辞）。
5. **数据留存**：是否把 reflect 记录（问题、feedback、understood）写入测绘/学情画像，供建议 10（问答画像回流）消费——本机制先不落库，仅接口返回，留好扩展位。

---

## 八、落地清单（对齐后执行）

前端：
- `src/components/chat/ReflectGate.vue`（新建）
- `src/stores/chat.ts`：消息增 `hasReusableMaterial` / `reflectState` 字段；`finishAssistant` 后触发判定
- `src/views/ChatView.vue`：`finishAssistant` 后渲染 ReflectGate；接收 submit-reflect / request-regenerate
- `src/components/chat/ChatMessage.vue`：复制按钮按锁定态 disabled
- 判定函数（代码块/标记正则）放 `src/utils/reflect.ts`

后端：
- `backend/app/schemas/agent.py`：加 `ReflectRequest` / `ReflectResponse`
- `backend/app/api/v1/chat.py`：加 `POST /chat/reflect`
- 复用 `get_agent_service().chat`，新增 `REFLECT_INSTRUCTION` 模板常量
- 解析容错 + 鉴权保持 `Depends(get_current_user)`

测试：
- 前端单测：判定函数（代码块/标记/普通文本）
- 后端单测：/chat/reflect 的 JSON 解析容错、understood 映射
- 联调：触发→锁定→提交→解锁→重生成的完整闭环

---

## 九、与既有设计的兼容

- 不改 `/chat/agent` 协议，新增独立 `/chat/reflect`，向后兼容。
- session_id 已端到端存在，直接复用，无需前端改造生成逻辑。
- 不触碰苏格拉底 system prompt（建议 7/8），反思指令作为其补充场景，基调一致。
- 现有"复制"按钮仅增加 disabled 态，无功能删除，风险可控。
