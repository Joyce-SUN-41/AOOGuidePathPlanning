FROM python:3.11-slim

WORKDIR /app

# 先复制依赖文件 (利用 Docker 缓存层)
COPY requirements.txt .

# 安装 Python 依赖（pip 国内镜像加速）
RUN pip install --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com

# 复制项目代码
COPY . .

# 创建数据和日志目录
RUN mkdir -p /app/data /app/logs

# 设置启动脚本权限
RUN chmod +x /app/entrypoint.sh

# 暴露端口
EXPOSE 8000

# 使用 entrypoint 脚本启动（自动运行数据库迁移）
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
