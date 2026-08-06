# 学情测绘后规划命名为"起点规划"（建议 11）— Baseline Plan Naming

> 状态：机制设计稿（待与老师对齐后再编码）
> 适用范围：测绘首轮产出 = "起点规划"（baseline）；问答回流重规划 = "动态更新 vN"（update_vN）
> 设计基线：对齐既有架构（LearningPath 模型无 plan_type / path_data JSONB 可扩展 / _persist_results 单写入点 / 建议 10 版本管理）

---

## 一、目标

给"学情测绘后生成的那条路径"一个明确的语义名称——**起点规划（baseline）**，与后续由问答画像回流触发的"动态更新 vN（update_vN）"区分开。价值：学生一眼看懂"这是我的起点"还是"这是根据我近期问答演化出的新版本"，让路径的"能动"特性（建议 10）在 UI 上显性化。

约束（来自提示词）：向后兼容——旧路径 `plan_type` 为空时按 `baseline` 显示。

---

## 二、现状盘点

- `LearningPath` 模型（`backend/app/models/learning_path.py`）当前字段：`student_id, diagnosis_id, name, path_data(JSONB), version, parent_path_id, is_active, created_at` 等。**无 `plan_type` 字段**。
- 生成路径的唯一写入点是 `optimization_service._persist_results`（约 line 485）：无论首轮还是 `path_regenerate`，都在此构造 `LearningPath(..., parent_path_id=parent_id, version=new_version, path_data=...)`。`auto_adopt` 区分是否直接生效，但写入逻辑同一处。
- 前端：路径为**测绘完成后自动生成**（RecordsView 提示"完成测绘后将自动生成"），并非手动点按钮触发。因此"CTA 文案"实际落点有两处：测绘完成结果页（若有跳转 CTA）、HomeView 学习路径卡片（"查看路径"）。PathView 标题目前写死"我的学习路径"。

---

## 三、字段方案（二选一，推荐 A）

### 方案 A：新增顶层列 `plan_type`（推荐）
- `LearningPath` 加 `plan_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, default="baseline")`。
- 优点：可索引、可查询（教师端按类型统计、前端按类型渲染文案）、与 `version` 同层一致。
- 代价：需新增 alembic 迁移（如 `012_plan_type.py`，`down_revision=011`）。
- 取值枚举：`"baseline"`（起点规划）、`"update_v2" / "update_v3" / ...`（动态更新第 N 版，N = parent.version+1）。

### 方案 B：写入 `path_data` JSONB
- 在 `path_data` 中加 `"plan_type": "baseline"` 键，零迁移、零风险。
- 缺点：不可直接 SQL 查询，前端需读 `path_data.plan_type`；与现有顶层 `version` 字段语义割裂。
- 适用：若老师希望"零数据库变更、最快上线"，选 B。

**默认推荐 A**（可查询、与版本管理语义统一）；若顾虑迁移成本则 B。两者不影响写入逻辑。

---

## 四、写入逻辑（单点改造 `_persist_results`）

在 `optimization_service._persist_results` 构造 `LearningPath` 处（line 485 附近）新增赋值：

```
plan_type = "baseline" if parent_id is None else f"update_v{new_version}"
```

- 首轮：`parent_id is None` → `"baseline"`（起点规划 v1，其中 v1 由 `version` 字段体现）。
- 回流重规划：`parent_id` 存在 → `"update_v{parent.version+1}"`，与建议 10 的 `_persist_results` 版本机制天然契合，无需额外传参。
- `version` 字段仍保留为纯数字（1,2,3...），`plan_type` 仅作语义标签，二者解耦互不冲突。

若选方案 B，则在 `path_data` dict 构造时注入 `plan_type` 键，逻辑相同。

---

## 五、前端文案与展示

### 5.1 测绘完成页 CTA（建议落点）
测绘完成后若有"查看路径"引导（CehuiView 结果区 / RecordsView 空态"完成测绘后将自动生成"），文案改为：
- 主 CTA：**"生成我的起点规划"**（按钮，跳 PathView）
- 若路径已自动生成，结果区提示：**"你的起点规划已生成"**
- HomeView 学习路径卡片链接文案可由"查看路径"微调为"查看我的起点规划"（禁 emoji，复用 Ant Design 图标 `NodeIndexOutlined`/`ArrowRightOutlined`）。
- 注意：因路径自动生成，CTA 本质是"查看"而非"生成"；文案建议用"查看我的起点规划"避免误导，具体措辞待老师审稿。

### 5.2 PathView 标题动态化
当前 `page-title` 写死"我的学习路径"。改为 computed：
- `plan_type === "baseline"` → **"起点规划 v1"**（v1 来自 `currentPath.version`）
- `plan_type` 以 `"update_v"` 开头 → **"动态更新 vN"**（N = version）
- 向后兼容：`plan_type` 为 null/空 → 按 `"baseline"` 显示 **"起点规划 v1"**（满足旧路径兼容约束）。
- 复用现有 `NodeIndexOutlined` 图标，禁 emoji。

### 5.3 与建议 10 待采纳横幅联动
`PathView` 已有"待采纳重规划版本"横幅（`v{{pendingPath.version}}` + `explanation`）。可在横幅中把"更新至 vN"与 `plan_type` 对齐：pending 版本其 `plan_type` 已是 `update_vN`，横幅标题可显式写"动态更新 vN（待采纳）"，使起点规划 / 动态更新 的语义贯穿到底。

---

## 六、向后兼容与迁移

- 旧路径 `plan_type` 为空 → 前端一律按 `baseline`（起点规划 v1）显示；后端查询若不依赖 `plan_type` 则无影响。
- 若选方案 A：alembic `012_plan_type.py` 用 `ALTER TABLE learning_paths ADD COLUMN plan_type VARCHAR(32)`，`server_default` 不设（避免覆盖既有语义），由应用层兼容 null → baseline。
- 不设 `NOT NULL`，保证存量数据零阻断。

---

## 七、边界与风控（待老师确认）

1. **字段方案 A vs B**：是否接受一次 alembic 迁移（推荐 A），还是零变更选 B？
2. **"生成"措辞**：路径实际自动生成，CTA 用"生成我的起点规划"还是"查看我的起点规划"？建议后者更诚实，待老师定。
3. **vN 展示口径**：标题用 `plan_type` 的 `update_vN` 还是直接读 `version` 数字？两者等价（N=version），建议统一读 `version` 以减少字段耦合，仅用 `plan_type` 区分 baseline/update 语义。
4. **教师端**：是否需要在教师看板按 `plan_type` 统计"起点规划数 / 动态更新数"？若需要，方案 A 的查询优势更明显。

---

## 八、落地清单（对齐后执行）

后端：
- `models/learning_path.py`：加 `plan_type` 列（方案 A）或确认写入 `path_data`（方案 B）
- `alembic/versions/012_plan_type.py`（方案 A）：新增列
- `services/aoo/optimization_service.py`：`_persist_results` 写入 `plan_type`（baseline / update_vN）

前端：
- `PathView.vue`：`page-title` 改为 computed（起点规划 v1 / 动态更新 vN，null→baseline）
- `CehuiView.vue` 结果区 / `RecordsView.vue` 空态 / `HomeView.vue` 卡片：CTA 文案调整（待老师审稿）
- `types` / store：路径对象类型补 `plan_type?` 字段（若方案 A）

测试：
- 后端单测：首轮写入 plan_type="baseline"、regenerate 写入 "update_v{parent+1}"、null 兼容
- 前端：旧路径（plan_type=null）显示"起点规划 v1"；新路径标题随类型切换

---

## 九、与既有设计的兼容

- 完全复用 `_persist_results` 现有 version/parent 逻辑，仅追加一个字段赋值，不破坏重规划链路（建议 10）。
- `version` 数字字段不变，前端展示可在 `plan_type` + `version` 上组合，互不冲突。
- 与建议 10 的待采纳横幅天然对齐：pending 版本 plan_type 已是 update_vN。
- 禁 emoji、复用 Ant Design 图标，符合设计系统红线。
