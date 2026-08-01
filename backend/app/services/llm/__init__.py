"""大模型服务 — 讯飞星火助手 WebSocket API 集成

客户端：
- SparkClient: 星火助手 WebSocket 客户端 (HMAC-SHA256 签名鉴权)
- ChatResponse / StreamChunk / TokenUsage: 数据模型
- XunfeiSparkClient: 旧版兼容
"""

from app.services.llm.spark_client import (
    ChatResponse,
    SparkClient,
    StreamChunk,
    TokenUsage,
    get_spark_client,
    reset_spark_client,
)

# 保留旧版导入兼容
from app.services.llm._legacy import XunfeiSparkClient, xunfei_client

__all__ = [
    # 新版核心
    "SparkClient",
    "get_spark_client",
    "reset_spark_client",
    # 数据模型
    "ChatResponse",
    "StreamChunk",
    "TokenUsage",
    # 旧版兼容
    "XunfeiSparkClient",
    "xunfei_client",
]
