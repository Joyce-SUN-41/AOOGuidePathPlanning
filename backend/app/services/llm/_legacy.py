"""旧版讯飞星火客户端 — 向后兼容

原有的 XunfeiSparkClient 实现保持不变，避免破坏已有引用。
新代码请使用 spark_client.SparkClient。
"""

import base64
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class XunfeiSparkClient:
    """讯飞星火大模型 HTTP/WebSocket 客户端（旧版）"""

    BASE_URL = "https://spark-api-open.xf-yun.com/v1"

    def __init__(self):
        self.app_id = settings.XF_APP_ID
        self.api_key = settings.XF_API_KEY
        self.api_secret = settings.XF_API_SECRET

    def _get_auth_url(self) -> str:
        """生成带鉴权签名的 WebSocket URL"""
        host = "spark-api.xf-yun.com"
        path = "/v3.5/chat"
        now = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")

        signature_origin = f"host: {host}\ndate: {now}\nGET {path} HTTP/1.1"
        signature_sha = hmac.new(
            self.api_secret.encode(),
            signature_origin.encode(),
            digestmod=hashlib.sha256,
        ).digest()
        signature = base64.b64encode(signature_sha).decode()

        authorization_origin = (
            f'api_key="{self.api_key}", algorithm="hmac-sha256", '
            f'headers="host date request-line", signature="{signature}"'
        )
        authorization = base64.b64encode(authorization_origin.encode()).decode()

        return (
            f"{settings.XF_API_URL}?"
            f"authorization={authorization}&"
            f"date={now}&"
            f"host={host}"
        )

    async def chat_completion(self, messages: list[dict], **kwargs) -> dict:
        """调用讯飞星火 Chat API (HTTP 方式)"""
        if not self.app_id or not self.api_key:
            logger.warning("讯飞 API 密钥未配置，返回模拟响应")
            return self._mock_response(messages)

        headers = {
            "Authorization": f"Bearer {self.api_key}:{self.api_secret}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": kwargs.get("model", settings.XF_MODEL),
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 2048),
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(
                    f"{self.BASE_URL}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as e:
                logger.error("讯飞 API 调用失败: %s", e)
                raise

    @staticmethod
    def _mock_response(messages: list[dict]) -> dict:
        """开发环境模拟响应"""
        return {
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": f"[模拟讯飞响应] 收到 {len(messages)} 条消息",
                    },
                }
            ],
            "usage": {"total_tokens": len(str(messages))},
        }


# 全局单例
xunfei_client = XunfeiSparkClient()
