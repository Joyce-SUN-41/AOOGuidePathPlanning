-- ============================================================================
-- 燕麦智导 (AOO Guide Path Planning) — 完整数据库建表脚本
-- 数据库: PostgreSQL 16
-- 字符集: UTF-8
-- ============================================================================

-- 启用 UUID 扩展 (如果尚未启用)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- 1. 用户表 (users)
--    扩展原有 User 模型，新增 role 字段区分学生/教师
-- ============================================================================
CREATE TABLE IF NOT EXISTS users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username        VARCHAR(50)  NOT NULL,
    email           VARCHAR(255) NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    role            VARCHAR(20)  NOT NULL DEFAULT 'student'
                        CHECK (role IN ('student', 'teacher')),
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
    is_superuser    BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX ix_users_username ON users (username);
CREATE UNIQUE INDEX ix_users_email    ON users (email);
CREATE        INDEX ix_users_role     ON users (role);

COMMENT ON TABLE  users               IS '用户表：学生/教师';
COMMENT ON COLUMN users.id            IS '用户唯一ID (UUID)';
COMMENT ON COLUMN users.username      IS '用户名';
COMMENT ON COLUMN users.email         IS '邮箱';
COMMENT ON COLUMN users.hashed_password IS 'bcrypt 加密密码';
COMMENT ON COLUMN users.role          IS '角色: student | teacher';
COMMENT ON COLUMN users.is_active     IS '是否激活';
COMMENT ON COLUMN users.is_superuser  IS '是否超级管理员';
COMMENT ON COLUMN users.created_at    IS '创建时间';
COMMENT ON COLUMN users.updated_at    IS '更新时间';

-- ============================================================================
-- 2. 知识点表 (knowledge_points)
--    自关联 parent_id → knowledge_points.id (前置知识点)
-- ============================================================================
CREATE TABLE IF NOT EXISTS knowledge_points (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name             VARCHAR(200) NOT NULL,
    description      TEXT,
    subject          VARCHAR(100) NOT NULL,
    difficulty_level SMALLINT     NOT NULL DEFAULT 1
                         CHECK (difficulty_level BETWEEN 1 AND 5),
    parent_id        UUID REFERENCES knowledge_points(id)
                         ON DELETE SET NULL,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_kp_subject          ON knowledge_points (subject);
CREATE INDEX ix_kp_difficulty_level ON knowledge_points (difficulty_level);
CREATE INDEX ix_kp_parent_id        ON knowledge_points (parent_id);

COMMENT ON TABLE  knowledge_points                 IS '知识点表';
COMMENT ON COLUMN knowledge_points.id              IS '知识点唯一ID';
COMMENT ON COLUMN knowledge_points.name            IS '知识点名称';
COMMENT ON COLUMN knowledge_points.description     IS '知识点描述';
COMMENT ON COLUMN knowledge_points.subject         IS '学科';
COMMENT ON COLUMN knowledge_points.difficulty_level IS '难度: 1-5';
COMMENT ON COLUMN knowledge_points.parent_id       IS '父知识点ID (层级结构)';
COMMENT ON COLUMN knowledge_points.created_at      IS '创建时间';

-- ============================================================================
-- 3. 知识图谱边表 (knowledge_graph)
--    表示知识点间的前置依赖关系 (有向边)
-- ============================================================================
CREATE TABLE IF NOT EXISTS knowledge_graph (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_kp_id  UUID         NOT NULL REFERENCES knowledge_points(id)
                        ON DELETE CASCADE,
    target_kp_id  UUID         NOT NULL REFERENCES knowledge_points(id)
                        ON DELETE CASCADE,
    relation_type VARCHAR(30)  NOT NULL DEFAULT 'prerequisite'
                        CHECK (relation_type IN ('prerequisite')),
    CONSTRAINT uq_knowledge_graph_edge
        UNIQUE (source_kp_id, target_kp_id),
    CONSTRAINT ck_no_self_loop
        CHECK (source_kp_id <> target_kp_id)
);

CREATE INDEX ix_kg_source_kp_id ON knowledge_graph (source_kp_id);
CREATE INDEX ix_kg_target_kp_id ON knowledge_graph (target_kp_id);

COMMENT ON TABLE  knowledge_graph                IS '知识图谱边：前置依赖关系';
COMMENT ON COLUMN knowledge_graph.id             IS '边唯一ID';
COMMENT ON COLUMN knowledge_graph.source_kp_id   IS '前置知识点ID';
COMMENT ON COLUMN knowledge_graph.target_kp_id   IS '后置知识点ID';
COMMENT ON COLUMN knowledge_graph.relation_type  IS '关系类型: prerequisite';

-- ============================================================================
-- 4. 学生知识点掌握度表 (student_knowledge)
--    记录每个学生对每个知识点的掌握程度
-- ============================================================================
CREATE TABLE IF NOT EXISTS student_knowledge (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    student_id       UUID        NOT NULL REFERENCES users(id)
                          ON DELETE CASCADE,
    kp_id            UUID        NOT NULL REFERENCES knowledge_points(id)
                          ON DELETE CASCADE,
    mastery_level    REAL        NOT NULL DEFAULT 0.0
                          CHECK (mastery_level >= 0.0 AND mastery_level <= 1.0),
    last_assessed_at TIMESTAMPTZ,
    CONSTRAINT uq_student_knowledge
        UNIQUE (student_id, kp_id)
);

CREATE INDEX ix_sk_student_id      ON student_knowledge (student_id);
CREATE INDEX ix_sk_kp_id           ON student_knowledge (kp_id);
CREATE INDEX ix_sk_mastery_level   ON student_knowledge (mastery_level);
CREATE INDEX ix_sk_last_assessed   ON student_knowledge (last_assessed_at);

COMMENT ON TABLE  student_knowledge                 IS '学生-知识点掌握度';
COMMENT ON COLUMN student_knowledge.id              IS '记录ID';
COMMENT ON COLUMN student_knowledge.student_id      IS '学生用户ID';
COMMENT ON COLUMN student_knowledge.kp_id           IS '知识点ID';
COMMENT ON COLUMN student_knowledge.mastery_level   IS '掌握度: 0.0-1.0';
COMMENT ON COLUMN student_knowledge.last_assessed_at IS '最近评估时间';

-- ============================================================================
-- 5. 学习路径表 (learning_paths)
--    为每个学生生成的学习路径，path_data 为 JSONB 存储完整路径结构
-- ============================================================================
CREATE TABLE IF NOT EXISTS learning_paths (
    id                       UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    student_id               UUID        NOT NULL REFERENCES users(id)
                                  ON DELETE CASCADE,
    path_data                JSONB       NOT NULL DEFAULT '{}',
    total_duration           INTEGER,          -- 预计总时长 (分钟)
    estimated_completion_days INTEGER,          -- 预计完成天数
    fitness_score            REAL,              -- AOO 算法适应度得分
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_lp_student_id   ON learning_paths (student_id);
CREATE INDEX ix_lp_created_at   ON learning_paths (created_at);
CREATE INDEX ix_lp_fitness_score ON learning_paths (fitness_score);

COMMENT ON TABLE  learning_paths                       IS '学习路径';
COMMENT ON COLUMN learning_paths.id                    IS '路径ID';
COMMENT ON COLUMN learning_paths.student_id            IS '学生用户ID';
COMMENT ON COLUMN learning_paths.path_data             IS '路径结构数据 (JSONB)';
COMMENT ON COLUMN learning_paths.total_duration        IS '预计总时长 (分钟)';
COMMENT ON COLUMN learning_paths.estimated_completion_days IS '预计完成天数';
COMMENT ON COLUMN learning_paths.fitness_score         IS 'AOO 适应度得分';
COMMENT ON COLUMN learning_paths.created_at            IS '创建时间';

-- ============================================================================
-- 6. 路径任务表 (path_tasks)
--    学习路径中的具体任务，按天分组、按顺序排列
-- ============================================================================
CREATE TABLE IF NOT EXISTS path_tasks (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    path_id          UUID        NOT NULL REFERENCES learning_paths(id)
                           ON DELETE CASCADE,
    kp_id            UUID        NOT NULL REFERENCES knowledge_points(id)
                           ON DELETE CASCADE,
    day_index        INTEGER     NOT NULL DEFAULT 1
                           CHECK (day_index >= 1),
    order_index      INTEGER     NOT NULL DEFAULT 0
                           CHECK (order_index >= 0),
    task_type        VARCHAR(20) NOT NULL DEFAULT 'reading'
                           CHECK (task_type IN ('video', 'quiz', 'reading', 'project')),
    estimated_minutes INTEGER    NOT NULL DEFAULT 15
                           CHECK (estimated_minutes > 0),
    completed        BOOLEAN     NOT NULL DEFAULT FALSE
);

CREATE INDEX ix_pt_path_id   ON path_tasks (path_id);
CREATE INDEX ix_pt_kp_id     ON path_tasks (kp_id);
CREATE INDEX ix_pt_day_order ON path_tasks (path_id, day_index, order_index);
CREATE INDEX ix_pt_completed ON path_tasks (completed);

COMMENT ON TABLE  path_tasks                  IS '学习路径任务';
COMMENT ON COLUMN path_tasks.id               IS '任务ID';
COMMENT ON COLUMN path_tasks.path_id          IS '所属路径ID';
COMMENT ON COLUMN path_tasks.kp_id            IS '对应知识点ID';
COMMENT ON COLUMN path_tasks.day_index        IS '第几天 (从1开始)';
COMMENT ON COLUMN path_tasks.order_index      IS '当天任务顺序';
COMMENT ON COLUMN path_tasks.task_type        IS '任务类型: video/quiz/reading/project';
COMMENT ON COLUMN path_tasks.estimated_minutes IS '预估分钟数';
COMMENT ON COLUMN path_tasks.completed        IS '是否完成';

-- ============================================================================
-- 7. 认知负荷记录表 (cognitive_load_records)
--    记录学生在诊断或学习过程中的认知负荷评分
-- ============================================================================
CREATE TABLE IF NOT EXISTS cognitive_load_records (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    student_id  UUID         NOT NULL REFERENCES users(id)
                        ON DELETE CASCADE,
    load_score  REAL         NOT NULL
                        CHECK (load_score >= 0.0 AND load_score <= 1.0),
    recorded_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    context     VARCHAR(30)  NOT NULL DEFAULT 'study'
                        CHECK (context IN ('diagnostic', 'study'))
);

CREATE INDEX ix_clr_student_id   ON cognitive_load_records (student_id);
CREATE INDEX ix_clr_recorded_at  ON cognitive_load_records (recorded_at);
CREATE INDEX ix_clr_student_time ON cognitive_load_records (student_id, recorded_at);

COMMENT ON TABLE  cognitive_load_records             IS '认知负荷记录';
COMMENT ON COLUMN cognitive_load_records.id          IS '记录ID';
COMMENT ON COLUMN cognitive_load_records.student_id  IS '学生用户ID';
COMMENT ON COLUMN cognitive_load_records.load_score  IS '负荷评分: 0.0-1.0';
COMMENT ON COLUMN cognitive_load_records.recorded_at IS '记录时间';
COMMENT ON COLUMN cognitive_load_records.context     IS '上下文: diagnostic | study';

-- ============================================================================
-- 8. 问答历史表 (chat_history)
--    RAG 问答记录，含溯源引用
-- ============================================================================
CREATE TABLE IF NOT EXISTS chat_history (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    student_id  UUID         NOT NULL REFERENCES users(id)
                        ON DELETE CASCADE,
    question    TEXT         NOT NULL,
    answer      TEXT         NOT NULL,
    sources     JSONB        DEFAULT '[]',
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_ch_student_id  ON chat_history (student_id);
CREATE INDEX ix_ch_created_at  ON chat_history (created_at);

COMMENT ON TABLE  chat_history             IS '问答历史';
COMMENT ON COLUMN chat_history.id          IS '问答ID';
COMMENT ON COLUMN chat_history.student_id  IS '学生用户ID';
COMMENT ON COLUMN chat_history.question    IS '用户问题';
COMMENT ON COLUMN chat_history.answer      IS '系统回答';
COMMENT ON COLUMN chat_history.sources     IS '引用溯源 (JSONB): [{kp_id, content, score}]';
COMMENT ON COLUMN chat_history.created_at  IS '创建时间';

-- ============================================================================
-- 9. AOO寻优日志表 (aoo_optimization_logs)
--    记录每轮 AOO 算法迭代的种群状态
-- ============================================================================
CREATE TABLE IF NOT EXISTS aoo_optimization_logs (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    student_id       UUID         NOT NULL REFERENCES users(id)
                              ON DELETE CASCADE,
    iteration        INTEGER      NOT NULL
                              CHECK (iteration >= 0),
    best_fitness     REAL,
    avg_fitness      REAL,
    diversity        REAL,
    convergence_data JSONB        DEFAULT '{}',
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_aol_student_id          ON aoo_optimization_logs (student_id);
CREATE INDEX ix_aol_created_at          ON aoo_optimization_logs (created_at);
CREATE INDEX ix_aol_student_iteration   ON aoo_optimization_logs (student_id, iteration);

COMMENT ON TABLE  aoo_optimization_logs                  IS 'AOO 寻优日志';
COMMENT ON COLUMN aoo_optimization_logs.id               IS '日志ID';
COMMENT ON COLUMN aoo_optimization_logs.student_id       IS '学生用户ID';
COMMENT ON COLUMN aoo_optimization_logs.iteration        IS '迭代轮次';
COMMENT ON COLUMN aoo_optimization_logs.best_fitness     IS '最佳适应度';
COMMENT ON COLUMN aoo_optimization_logs.avg_fitness      IS '平均适应度';
COMMENT ON COLUMN aoo_optimization_logs.diversity         IS '种群多样性';
COMMENT ON COLUMN aoo_optimization_logs.convergence_data IS '收敛详细数据 (JSONB)';
COMMENT ON COLUMN aoo_optimization_logs.created_at       IS '创建时间';

-- ============================================================================
-- 自动更新 updated_at 的触发器函数
-- ============================================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
