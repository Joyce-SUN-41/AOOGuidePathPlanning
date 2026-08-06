# 燕麦智导全链路检修报告

## Executive Summary

本次对「动麦智导 / 燕麦智导」项目做了从前到后的全链路排查：前端 views → stores → `api/modules` → 后端 `v1` 路由 → services → 数据库模型与迁移。结论是项目主链路整体连通、健康，绝大多数此前记录的暗伤（深色主题、移动端适配、AOO 重规划死循环、字体白屏等）已有落地修复。本次仅发现并修复一处真实链接缺陷：后端缺失 `/auth/logout` 端点，导致前端 `userApi.logout()` 长期指向无效路由（404）。其余排查到的"悬空"项（空 `agent.ts` 模块、`pathStore.generatePath` 前端未调用）均为无害冗余或能力缺口，未做破坏性改动，以"安全谨慎、向后兼容"为第一原则。

---

## 排查范围与方法

逐个比对了 8 个前端 API 模块（`auth / user / cehui / path / dashboard / teacher / chat / rag / knowledge / question`）与 13 个后端 `v1` 路由模块，并追踪了 stores 与 views 的真实调用点（用代码搜索确认 `xxxApi` 仅在 stores 与 views 中出现，未发现悬空 import）。

对照结果：每个前端调用都能在后端找到对应端点，逐一验证通过。

---

## 已确认健康的链路（非暗伤，已复核）

- 认证链路：`/auth/login`、`/auth/register`、`/auth/refresh`、`/auth/me`、`/auth/me`(PUT) 与 `authApi`/`userApi` 完全对齐；Token 刷新、路由守卫、`persist` 插件键名 `oat_user_store` 一致。
- 学情测绘：`cehuiApi.getQuestions/submit/getLatest/getById/getHistory/delete` 对应 `cehui.py` 全部端点；第三维「学习准备度」全链路打通——前端 `toReadinessProfile` 返回 `rawItems/selfEfficacy`（camelCase），后端 `CamelModel(populate_by_name=True)` 正确解析为 `raw_items/self_efficacy`，经 `compute_readiness_profile` 落库，非静默退化。
- AOO 路径规划：`pathApi` 封装的 `/aoo/optimize`、`/aoo/status/{id}`、`/aoo/optimize-flexible`、`/aoo/pending-path`、`/aoo/paths/{id}/adopt`、`/aoo/paths/{id}/diff` 与 `aoo.py` 一致；重规划版本管理（pending/adopt/diff）逻辑严密，此前"采纳后刷新恢复旧版本"死循环已修复。
- 学习路径：`/learning-paths/{current,history,select,{id},delete}` 与 `learning_paths.py` 对齐，P2 备选方案与收敛回放数据随路径记录一并下发。
- 学情看板/教师端/导学终端/RAG：对应端点与字段均一致，异常分支有 fallback 降级。
- 基础设施优化（2026-08-03 落地项已确认生效）：`index.html` 字体非阻塞加载、`nginx.conf` 代理头、`GZipMiddleware`、多 worker 均在位。

---

## 本次修复的暗伤

### 1. 后端缺失 `/auth/logout` 端点（真实链接缺陷，已修复）

前端 `src/api/modules/user.ts` 的 `userApi.logout()` 调用 `POST /auth/logout`，但后端 `auth.py` 从未定义该路由。主退出逻辑 `userStore.logout()` 直接清本地 `oat_user_store` 不依赖该端点，因此此前未暴露为可见故障，但 `userApi.logout` 是死代码指向无效路由（调用即 404，被 catch 静默吞掉，产生噪声）。

修复：在 `backend/app/api/v1/auth.py` 补一个幂等 `POST /logout` 端点。无状态 JWT 场景下服务端不维护会话黑名单，端点返回 200 并做 best-effort 审计日志，让前端调用 ↔ 后端端点重新一一对应。已补 `import logging` 与 `logger` 实例，linter 通过（0 错误）。

---

## 登记但未改动的"悬空/冗余"项（安全优先，不盲目补全）

### 2. `src/api/modules/agent.ts` 是空文件，后端 `/agent/*` 能力前端未接入

后端 `agent.py` 具备完整端点：`/agent/chat`、`/agent/sessions`、`/agent/history/{id}`、`/agent/sessions/{id}`(DELETE)、`/agent/health`，但前端该模块为空且全局无任何 import。ChatView 实际走的是 `/rag/query` + `/chat/reflect` + `/chat/summarize-profile`，现有导学终端功能不受影响。补齐整条 Agent 会话管理 UI 属于功能扩展而非维修，成本高、风险大，超出本次"安全维修"范畴，登记为已知缺口，待后续独立规划。

### 3. `pathStore.generatePath`（POST `/aoo/optimize`）前端无调用点

`generatePath` 仅在 `path.ts` 定义与 `PathView.vue` 注释中出现，前端从不调用（注释明确"不能走 generatePath"）。测绘提交后路径生成由后端 `submit_cehui` 自动触发（`trigger_aoo_path_planning.delay`，Celery 优先、同步兜底），`PathView.onMounted` 的 `fetchCurrentPath()` 拉取后端已生成的活跃路径，闭环靠后端兜底维持，工作正常。`generatePath` 属冗余未触发入口，无害，保留。

### 4. `CehuiView` 跳转带 `?diagnosisId=` 而 `PathView.onMounted` 不读取该参数

`CehuiView.goToGeneratePath` 跳 `/path?diagnosisId=...`，但 `PathView.onMounted` 仅处理 `?id=`（历史路径查看），忽略 `diagnosisId`。因后端已在测绘提交时自动生成路径，此参数当前无实际作用，不构成故障；若未来要改为"前端显式触发生成"，需在此处补 `generatePath` 调用（届时注意与后端自动触发去重）。

---

## 结论

项目全链路在本次检修前已处于高完成度，核心业务闭环（测绘 → 路径生成 → 看板/教师端/导学终端）均真实连通。本次唯一真实链接缺陷（`/auth/logout` 缺失）已闭合；其余为无害冗余或扩展缺口，按"安全谨慎、不破坏现有功能"原则予以登记而非改动。建议后续若要做 Agent 会话管理，再独立补 `agent.ts` 前端模块与对应 UI。

## Limitations

- 本次为静态代码链路排查，未运行完整 Docker 集成测试；运行时行为（尤其 Celery Worker 在线状态下的 `/aoo/optimize` 与 `/cehui/submit` 自动触发竞合）建议通过端到端冒烟测试进一步确认。
- 后端"自动触发 AOO + 前端 fetchCurrentPath"双路径的具体时序边界（首次测绘后路径尚未落库时前端是否短暂空态）未在运行时验证。

## References

1. [后端认证路由 auth.py](backend/app/api/v1/auth.py)
2. [前端认证 API 模块](src/api/modules/user.ts)
3. [后端 AOO 路径优化路由](backend/app/api/v1/aoo.py)
4. [前端路径 store](src/stores/path.ts)
5. [后端测绘路由（含 AOO 自动触发）](backend/app/api/v1/cehui.py)
6. [后端 Agent 会话路由（前端未接入）](backend/app/api/v1/agent.py)
