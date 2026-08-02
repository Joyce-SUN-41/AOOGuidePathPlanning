# ============================================================
#  AOO Backend — 多阶段 Docker 构建
# ============================================================

# ---- Stage 1: 依赖安装 ----
FROM python:3.11-slim AS builder

WORKDIR /app

# 安装构建依赖（核心 + 可选 AI 扩展）
COPY requirements.txt requirements-ai.txt* ./
RUN pip install --no-cache-dir -r requirements.txt \
    -i https://mirrors.aliyun.com/pypi/simple/ \
    --trusted-host mirrors.aliyun.com
RUN if [ -f requirements-ai.txt ]; then \
        pip install --no-cache-dir -r requirements-ai.txt \
        -i https://mirrors.aliyun.com/pypi/simple/ \
        --trusted-host mirrors.aliyun.com; \
    fi

# ---- Stage 2: 生产运行 ----
FROM python:3.11-slim

# 创建非 root 用户
RUN groupadd -r aoo && useradd -r -g aoo -d /app -s /sbin/nologin aoo

WORKDIR /app

# 从 builder 阶段复制已安装的包
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# 复制项目代码
COPY . .

# 创建数据和日志目录，设置权限
RUN mkdir -p /app/data /app/logs && \
    chown -R aoo:aoo /app && \
    chmod +x /app/entrypoint.sh

# 切换到非 root 用户
USER aoo

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,os; port=os.environ.get('APP_PORT','8000'); urllib.request.urlopen('http://localhost:'+port+'/api/v1/health/live')" || exit 1

# 使用 entrypoint 脚本启动（自动运行数据库迁移）
ENTRYPOINT ["/app/entrypoint.sh"]
# 端口从 APP_PORT 环境变量读取（默认 8000），与配置保持一致、可被覆盖
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${APP_PORT:-8000}"]
