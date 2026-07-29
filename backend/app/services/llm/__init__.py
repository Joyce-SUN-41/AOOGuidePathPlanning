"""大模型服务 — 讯飞星火 Spark API 集成

两个客户端：
- XunfeiSparkClient（旧版，简单包装）
- SparkClient（新版，spark_client.py，完整功能：流式、工具调用、熔断、重试）
"""

from app.services.llm.spark_client import (
    ChatResponse,
    CircuitBreaker,
    CircuitState,
    SparkAPIError,
    SparkCircuitOpenError,
    SparkClient,
    SparkClientError,
    SparkTimeoutError,
    SparkTokenLimitError,
    StreamChunk,
    TokenCounter,
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
    "TokenCounter",
    # 熔断器
    "CircuitBreaker",
    "CircuitState",
    # 异常
    "SparkClientError",
    "SparkAPIError",
    "SparkCircuitOpenError",
    "SparkTimeoutError",
    "SparkTokenLimitError",
    # 旧版兼容
    "XunfeiSparkClient",
    "xunfei_client",
]
