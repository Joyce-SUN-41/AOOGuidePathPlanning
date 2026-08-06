# 学情测绘（测绘）题目数量设计全面分析

## 摘要

当前"学情测绘"模块在后端 API 默认抽取 20 题（前端 `CehuiView.vue` 写死 `count: 20`），题库总量 1000 题、覆盖 11 个知识点、题型全部为单选。整体设计在"覆盖面"上基本合理（11 个知识点用 20 题能全覆盖），但存在三个结构性隐患：一、47.5% 的题库题目 `difficulty` 为 `null`，导致分层分级均衡组卷（50/30/20 难度配额）严重失真；二、20 题 / 11 个知识点 = 每知识点平均仅 1.8 题，低于测绘模型 `calibrate_confidence` 要求的 `total >= 2` 阈值，会削弱掌握度置信估计；三、题型单一（1000 题全是单选）、难度阶梯在进阶层（4-5）题量偏少、且预估耗时模型未真正使用 `expected_time_sec`。下文逐项展开。

## 一、题目数量的现状梳理（数据基线）

题库 `backend/data/question_bank.json` 共 **1000 题**，全部为 `single` 单选，每题仅挂载 1 个知识点（`kp_ids` 长度为 1）。知识点共 **11 个**（`knowledge_points.json`），与"人工智能导论"学科对应。

抽题数量的实际取值有四处来源：
- 前端 `CehuiView.vue`：`getQuestions({count: 20, subject})` 写死 20。
- 后端 API `GET /api/v1/cehui/questions`：`count` 默认 20，上限 200。
- 实际落库的测绘：提交接口 `POST /submit` 按用户作答的 `answers` 计算，题目数即前端抽到的 20。
- 预计耗时：`estimated_duration_min = max(5, count * 20 // 60)`，20 题约等于 7 分钟。

知识点覆盖（每 KP 题数）分布均匀：kp_ai_001 有 65 题、kp_ai_011 有 91 题，区间 65–103，11 个知识点合计 1000 题，无明显"某些知识点无题"的空缺。

## 二、题目数量是否"够用"——从测绘精度的角度

测绘引擎用 DINA 认知测绘模型（`_dina_em` 迭代估计每个知识点的掌握度），并调用 `calibrate_confidence` 做经验置信区间。该函数在第 224 行起对 `kpa.total < 2` 的知识点直接 `continue`（跳过 slip/guess 估计），并在置信区间计算里以 `min(3, n)` 封顶。这意味着：**单个知识点少于 2 道题时，该知识点的测绘置信估计会被降权或落入宽区间**。

按 20 题 / 11 个知识点分配，在理想的"均衡组卷"下每知识点约 1–2 题（`assemble_balanced_paper` 会尽量分散到各 `kp_id` 桶），大量知识点只能分到 1 题。结果：11 个知识点中相当一部分会命中 `total < 2`，导致其掌握度被当作低置信处理，影响后续 AOO 路径规划与薄弱点判定的可靠性。

结论：**20 题对 11 个知识点来说偏紧**。要让每个知识点都达到 `>= 2` 题的最低样本，至少需要 22 题（理想均衡下），实际因组卷约束往往需 25–30 题才稳妥。建议把默认抽题量提到 **30 题左右**。

## 三、分层分级均衡组卷的难度配额失真（核心缺陷）

`assemble_balanced_paper` 把题目按 `kp_id` 分桶、按难度阶 [`1-2 → 50%`、`3 → 30%`、`4-5 → 20%`] 配额分配，意图实现"基础 50% / 核心 30% / 进阶 20%"的层次感。但题库真实难度分布为：

- 难度 `null`：**475 题（47.5%）**
- 难度 1：63、难度 2：141、难度 3：147、难度 4：127、难度 5：47

组卷器对难度为 `null` 的题目用 `max(1, q.get("difficulty") or 1)` 兜底为 1。后果是：那 475 道"无难度"题全部被塞进难度 1 桶，使"基础层"实际占比远超 50%，核心层与进阶层被挤压。从各知识点内部看，几乎每个知识点的题量里都含 10–55 道 `null` 难度题（如 kp_ai_011 的 91 题中有 43 道为 `null`），组卷质量高度依赖这批未标注难度数据，分层均衡名存实亡。

图谱驱动抽题（`graph_cehui.sample_questions_by_graph`）同样用 `_TIER_BY_DIFFICULTY` 把难度 `null` 归到难度 1 → 基础层，进一步放大失衡。

修复建议（二选一或并用）：① 回填题库 `difficulty` 字段，消除 47.5% 的 `null`；② 在组卷器内对 `null` 难度题按知识点或随机均匀分配到各阶，而不是一律当难度 1。

## 四、题型单一与难度阶梯断档

1000 题**全部是单选**，没有多选、判断、简答或情境题。对于"人工智能导论"这类偏概念理解的学科，单选能测识记但弱于测"能否应用/辨析"。题型多样性不足会让掌握度估计偏向"识别"而非"理解"，维度的区分度受限。

难度阶梯上，进阶层（4-5）合计 174 题（17.4%），其中难度 5 仅 47 题且集中在 kp_ai_011；而基础层实际因 `null` 污染虚高。若按"真实已知难度"（排除 `null`）重新看：已知难度题 525 道中，1:63 / 2:141 / 3:147 / 4:127 / 5:47，分布基本合理（中难度最多），但最高难度（5）样本最少，对"优秀"档的识别能力最弱。

## 五、预估耗时模型与实际脱节

API 用 `count * 20 // 60` 估算时长（20 题 ≈ 7 分钟）。但题库题目带 `expected_time_sec` 字段，`assemble_balanced_paper` 又按难度阶梯设置 `expected_time`（基础 15s、核心 20-30s、进阶 35-45s）。实际 20 题若按组卷后真实 `expected_time_sec` 求和约 8–9 分钟，与 7 分钟估算偏差不大；但若将来提到 30 题，前端仍按固定系数可能低估。建议直接对抽中题目的 `expected_time_sec` 求和作为预估，而非用固定均值。

## 六、覆盖面与"是否覆盖所有知识点"的检查

`coverage_check` 会比对抽中题目的知识点集合与全量知识点，缺失则 `logger.warning`，但**仅告警、不强制补齐**，且前端对 `allocation`/`uncovered` 无展示。当前 20 题在 11 个知识点上可全覆盖（桶数 11 < 抽题 20），但若未来题目量降至 < 11 或出现知识点冷门，可能漏覆盖。前端 `CehuiView` 也未按 `allocation` 渲染"组卷均衡度"或"覆盖 11/11"提示，用户无感知。

## 七、综合判断与建议

题目数量设计在"总量 1000 + 覆盖 11 知识点"的题库体量上是充足的，但"单次抽取 20 题"偏紧，且被 `null` 难度数据拖累。优先级建议：

1. 把默认抽题量从 20 提升到 **28–30 题**，确保 11 个知识点各 ≥ 2 题，满足 `calibrate_confidence` 的样本门槛，提升掌握度置信。
2. 治理 `difficulty` 的 `null`（475 题）——回填真实难度，或改组卷逻辑对 `null` 均匀分阶，恢复 50/30/20 分层均衡。
3. 引入多选或情境题，提升"理解/应用"维度区分度（至少在高难度档补充）。
4. 前端显式展示"覆盖知识点 11/11"与组卷均衡度（已有 `allocation` 字段未用），让用户感知测绘完整性。
5. 预估耗时改用抽中题 `expected_time_sec` 求和，随题量自适应。

## 限制

本次分析基于静态代码与种子题库 `question_bank.json`、`knowledge_points.json` 的统计，未运行线上数据库（DB 播种后实际题库与 JSON 是否一致未验证）。若生产环境已通过 `seed_data` 将题目写入数据库，实际抽题走 `get_question_bank_from_db` 路径，其难度字段完整性可能不同于 JSON（需另查 DB）。前端固定 `count: 20` 的假设基于对 `CehuiView.vue` 的当前读取，若有其他入口（如教师端自定义题量）未覆盖则不在本次范围内。

## 参考

1. [backend/data/question_bank.json](e:/AOOGuidePathPlanning/backend/data/question_bank.json) — 1000 题种子题库
2. [backend/data/knowledge_points.json](e:/AOOGuidePathPlanning/backend/data/knowledge_points.json) — 11 个知识点
3. [backend/app/services/cehui/paper_assembler.py](e:/AOOGuidePathPlanning/backend/app/services/cehui/paper_assembler.py) — 均衡组卷逻辑
4. [backend/app/api/v1/cehui.py](e:/AOOGuidePathPlanning/backend/app/api/v1/cehui.py) — 抽题/提交接口
5. [src/views/CehuiView.vue](e:/AOOGuidePathPlanning/src/views/CehuiView.vue) — 前端抽题入口（`count: 20`）
6. [backend/app/services/cehui/__init__.py](e:/AOOGuidePathPlanning/backend/app/services/cehui/__init__.py) — DINA 测绘与 `calibrate_confidence`
7. [backend/app/services/cehui/graph_cehui.py](e:/AOOGuidePathPlanning/backend/app/services/cehui/graph_cehui.py) — 图谱驱动抽题
