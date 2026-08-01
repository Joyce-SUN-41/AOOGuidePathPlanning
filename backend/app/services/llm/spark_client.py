"""讯飞星火助手 WebSocket API 客户端

使用星火助手 WebSocket 接口，通过 HMAC-SHA256 签名鉴权。

接口文档:
    ws(s)://spark-openapi.cn-huabei-1.xf-yun.com/v1/assistants/{assistant_id}

认证方式: HMAC-SHA256 签名
- 签名串: host: {host}\ndate: {date}\nGET {path} HTTP/1.1
- 密钥: API Secret
- 结果: Base64(HMAC-SHA256)
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional
from urllib.parse import quote, urlparse

import httpx
import websockets

from app.core.config import settings

logger = logging.getLogger(__name__)


# ============================================================================
# 数据模型
# ============================================================================


@dataclass
class TokenUsage:
    """Token 用量统计"""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class ChatResponse:
    """非流式对话完整响应"""
    content: str = ""
    usage: Optional[TokenUsage] = None
    model: str = ""
    sid: str = ""
    finish_reason: str = "stop"


@dataclass
class StreamChunk:
    """流式对话增量片段"""
    content: str = ""
    finish_reason: Optional[str] = None
    usage: Optional[TokenUsage] = None
    error: Optional[str] = None
    sid: str = ""


# ============================================================================
# 星火助手 WebSocket 客户端
# ============================================================================


class SparkClient:
    """讯飞星火助手 WebSocket 客户端

    使用星火助手 API 进行对话，支持普通和流式两种模式。

    用法:
        client = SparkClient()
        resp = await client.chat([{"role": "user", "content": "你好"}])
        print(resp.content)

        async for chunk in client.chat_stream([{"role": "user", "content": "你好"}]):
            if chunk.content:
                print(chunk.content, end="")
    """

    def __init__(
        self,
        app_id: str = "",
        api_key: str = "",
        api_secret: str = "",
        api_url: str = "",
        assistant_id: str = "",
        model: str = "generalv3",
        api_password: str = "",
    ):
        self.app_id = app_id or settings.XF_APP_ID
        self.api_key = api_key or settings.XF_API_KEY
        self.api_secret = api_secret or settings.XF_API_SECRET
        self.assistant_id = assistant_id or getattr(settings, "XF_ASSISTANT_ID", "")
        self.model = model or settings.XF_MODEL
        # REST API 的 APIPassword (与 WS 的 api_key/api_secret 不同)
        self.api_password = api_password or getattr(settings, "XF_API_PASSWORD", "")

        # WebSocket URL — 优先使用传入值，其次环境变量
        api_url = api_url or settings.XF_API_URL or ""
        if api_url:
            self._ws_url = api_url
        elif self.assistant_id:
            self._ws_url = (
                f"wss://spark-openapi.cn-huabei-1.xf-yun.com"
                f"/v1/assistants/{self.assistant_id}"
            )
        else:
            self._ws_url = ""

    # ---- 公共属性 ----

    @property
    def is_configured(self) -> bool:
        """检查是否已配置完整

        REST 模式 (http/https): 需要 api_password 或 (api_key + api_secret)
        WebSocket 模式 (ws/wss): 需要 app_id + api_key + api_secret
        """
        if not self._ws_url:
            return False
        # REST API 模式
        if self._ws_url.startswith(("http://", "https://")):
            return bool(self.api_password or (self.api_key and self.api_secret))
        # WebSocket 模式
        return bool(self.app_id and self.api_key and self.api_secret)

    # ---- 公共方法 ----

    async def close(self) -> None:
        """释放资源（WebSocket 客户端无需显式关闭）"""
        pass

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.5,
        max_tokens: int = 2048,
        top_k: int = 4,
        uid: str = "",
    ) -> ChatResponse:
        """非流式对话：收集所有流式块后返回完整结果

        Returns:
            ChatResponse 包含完整答案和 token 用量
        """
        full_answer_parts: List[str] = []
        token_usage: Optional[TokenUsage] = None
        sid = ""

        async for chunk_data in self._chat_raw(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            top_k=top_k,
            uid=uid,
        ):
            tp = chunk_data.get("type", "")
            if tp == "content":
                full_answer_parts.append(chunk_data.get("content", ""))
            elif tp == "usage":
                token_usage = TokenUsage(
                    prompt_tokens=chunk_data.get("prompt_tokens", 0),
                    completion_tokens=chunk_data.get("completion_tokens", 0),
                    total_tokens=chunk_data.get("total_tokens", 0),
                )
            elif tp == "error":
                raise RuntimeError(
                    f"星火助手错误 (code={chunk_data.get('code')}): "
                    f"{chunk_data.get('message', '未知错误')}"
                )
            sid = chunk_data.get("sid", sid)

        return ChatResponse(
            content="".join(full_answer_parts),
            usage=token_usage,
            model=self.model,
            sid=sid,
            finish_reason="stop",
        )

    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.5,
        max_tokens: int = 2048,
        top_k: int = 4,
        uid: str = "",
    ) -> AsyncGenerator[StreamChunk, None]:
        """流式对话：逐块返回生成内容

        Yields:
            StreamChunk 包含增量内容和元信息
        """
        async for chunk_data in self._chat_raw(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            top_k=top_k,
            uid=uid,
        ):
            tp = chunk_data.get("type", "")
            if tp == "content":
                yield StreamChunk(
                    content=chunk_data.get("content", ""),
                    sid=chunk_data.get("sid", ""),
                )
            elif tp == "usage":
                yield StreamChunk(
                    usage=TokenUsage(
                        prompt_tokens=chunk_data.get("prompt_tokens", 0),
                        completion_tokens=chunk_data.get("completion_tokens", 0),
                        total_tokens=chunk_data.get("total_tokens", 0),
                    ),
                    finish_reason="stop",
                    sid=chunk_data.get("sid", ""),
                )
            elif tp == "error":
                yield StreamChunk(
                    error=chunk_data.get("message", "未知错误"),
                    finish_reason="error",
                    sid=chunk_data.get("sid", ""),
                )
                return

    # ---- 内部：原始 WebSocket 通信 ----

    async def _chat_raw(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.5,
        max_tokens: int = 2048,
        top_k: int = 4,
        uid: str = "",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """原始 WebSocket 通信，返回结构化字典流

        Yield 格式:
            {"type": "content", "content": str, "sid": str}
            {"type": "usage", "prompt_tokens": int, "completion_tokens": int,
             "total_tokens": int, "sid": str}
            {"type": "error", "code": int, "message": str, "sid": str}
        """
        if not self.is_configured:
            yield {
                "type": "error",
                "code": -1,
                "message": (
                    "星火助手未配置，请在 .env 中设置 "
                    "XF_APP_ID, XF_API_KEY, XF_API_SECRET, XF_ASSISTANT_ID"
                ),
                "sid": "",
            }
            return

        # HTTP(S) URL → REST API 模式（OpenAI 兼容接口）
        if self._ws_url.startswith(("http://", "https://")):
            logger.debug(
                "Spark REST mode | url=%s | model=%s | msgs=%d",
                self._ws_url, self.model, len(messages),
            )
            async for item in self._chat_rest(
                messages, temperature, max_tokens, top_k, uid
            ):
                yield item
            return

        # 1. 构建鉴权 URL
        ws_url = self._build_auth_url()

        # 2. 构建请求体
        request_payload = self._build_request(
            messages, temperature, max_tokens, top_k, uid
        )

        logger.debug(
            "Spark WS connecting | app_id=%s | model=%s | msgs=%d | temp=%.2f",
            self.app_id, self.model, len(messages), temperature,
        )

        try:
            async with websockets.connect(
                ws_url,
                ping_interval=30,
                ping_timeout=10,
                close_timeout=5,
                max_size=2 ** 23,  # 8 MB
            ) as ws:
                await ws.send(json.dumps(request_payload, ensure_ascii=False))
                logger.debug("Spark WS request sent, waiting for response...")

                async for raw in ws:
                    try:
                        response = json.loads(raw)
                    except json.JSONDecodeError:
                        logger.warning("Spark WS: unparseable frame: %.200s", raw)
                        continue

                    # 检查 header 错误
                    header = response.get("header", {})
                    code = header.get("code", 0)
                    sid = header.get("sid", "")
                    status = header.get("status", -1)

                    if code != 0:
                        error_msg = header.get("message", "未知错误")
                        logger.error(
                            "Spark WS error [%d]: %s (sid=%s)", code, error_msg, sid
                        )
                        yield {
                            "type": "error",
                            "code": code,
                            "message": f"星火助手错误 [{code}]: {error_msg}",
                            "sid": sid,
                        }
                        return

                    # 解析 payload
                    payload = response.get("payload", {})
                    choices = payload.get("choices", {})
                    text_list = choices.get("text", [])

                    for item in text_list:
                        content = item.get("content", "")
                        if content:
                            yield {
                                "type": "content",
                                "content": content,
                                "sid": sid,
                            }

                    # 最后一条：Token 用量
                    if status == 2:
                        usage = payload.get("usage", {})
                        usage_text = usage.get("text", {})
                        yield {
                            "type": "usage",
                            "prompt_tokens": usage_text.get("prompt_tokens", 0),
                            "completion_tokens": usage_text.get("completion_tokens", 0),
                            "total_tokens": usage_text.get("total_tokens", 0),
                            "sid": sid,
                        }
                        break

        except websockets.exceptions.ConnectionClosed as e:
            logger.error("Spark WS connection closed: code=%s reason=%s", e.code, e.reason)
            yield {
                "type": "error",
                "code": e.code or -1,
                "message": f"WebSocket 连接关闭: {e.reason or '未知原因'}",
                "sid": "",
            }
        except asyncio.TimeoutError:
            logger.error("Spark WS connection timeout")
            yield {
                "type": "error",
                "code": -1,
                "message": "星火助手连接超时，请稍后重试",
                "sid": "",
            }
        except OSError as e:
            logger.error("Spark WS network error: %s", e)
            yield {
                "type": "error",
                "code": -1,
                "message": f"网络连接失败: {e}",
                "sid": "",
            }
        except Exception:
            logger.exception("Spark WS unexpected error")
            yield {
                "type": "error",
                "code": -1,
                "message": "星火助手服务内部错误，请查看后端日志",
                "sid": "",
            }

    # ---- 私有方法 ----

    def _build_auth_url(self) -> str:
        """构建带 HMAC-SHA256 签名的 WebSocket URL

        讯飞 WebSocket 鉴权规范:
        1. 解析 host / path
        2. 生成 RFC 1123 时间
        3. 签名串: host: {host}\ndate: {date}\nGET {path} HTTP/1.1
        4. HMAC-SHA256(api_secret, 签名串) → Base64
        5. 拼接 authorization 查询参数
        """
        parsed = urlparse(self._ws_url)
        host = parsed.hostname or ""
        path = parsed.path or "/"

        now = datetime.now(timezone.utc)
        date_str = now.strftime("%a, %d %b %Y %H:%M:%S GMT")

        signature_string = f"host: {host}\ndate: {date_str}\nGET {path} HTTP/1.1"

        signature = base64.b64encode(
            hmac.new(
                self.api_secret.encode("utf-8"),
                signature_string.encode("utf-8"),
                digestmod=hashlib.sha256,
            ).digest()
        ).decode("utf-8")

        authorization = (
            f'api_key="{self.api_key}", '
            f'algorithm="hmac-sha256", '
            f'headers="host date request-line", '
            f'signature="{signature}"'
        )

        auth_encoded = quote(authorization)
        return (
            f"{self._ws_url}"
            f"?authorization={auth_encoded}"
            f"&date={quote(date_str)}"
            f"&host={quote(host)}"
        )

    def _build_request(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        top_k: int,
        uid: str,
    ) -> Dict[str, Any]:
        """构建星火助手 WebSocket 请求体"""
        return {
            "header": {
                "app_id": self.app_id,
                "uid": uid or f"aoo_{uuid.uuid4().hex[:12]}",
            },
            "parameter": {
                "chat": {
                    "domain": self.model,
                    "temperature": temperature,
                    "top_k": top_k,
                    "max_tokens": max_tokens,
                }
            },
            "payload": {
                "message": {
                    "text": messages,
                }
            },
        }

    # ---- REST API 模式 ----

    async def _chat_rest(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.5,
        max_tokens: int = 2048,
        top_k: int = 4,  # noqa: ARG002 (REST API 不使用 top_k)
        uid: str = "",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """REST API 模式（讯飞 OpenAI 兼容接口）

        当 XF_API_URL 设置为 http(s):// 地址时使用此路径。
        认证方式: Authorization: Bearer {APIPassword}
        APIPassword 从控制台对应模型版本页面获取，与 WS 的 api_key/api_secret 不同。
        """
        # 优先使用 XF_API_PASSWORD；若未配置则回退到 {api_key}:{api_secret} 格式
        if self.api_password:
            auth_token = self.api_password
        else:
            auth_token = f"{self.api_key}:{self.api_secret}"
            logger.warning(
                "XF_API_PASSWORD 未设置，使用 api_key:api_secret 格式认证 "
                "（可能与讯飞 HTTP API 不兼容，建议在 .env 中设置 XF_API_PASSWORD）"
            )

        headers = {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json",
        }

        candidate_models: List[str] = []
        if self.model:
            candidate_models.append(self.model)
            # MaaS/旧版星火：若首选模型不可用，追加候选列表用于降级。
            # Spark X2 的 model 固定为 spark-x，候选列表不含它，故 candidate=[spark-x] 不会降级换模型。
            candidate_models += [
                m
                for m in ("4.0Ultra", "generalv3.5", "generalv3", "generalv2", "general", "pro-128k")
                if m not in candidate_models
            ]

        last_error_msg = ""
        # 限流/流控类错误（应就地退避重试而非换模型）：
        # 11202 秒级并发超限 / 11201 日流控 / 11203 并发超限 / 10007 用户流量受限(需等上条回复完)
        # AppIdQpsOverFlowError / rate limit / 并发 / 限流 / too many requests 等文本也覆盖
        qps_error_signs = (
            "11202",
            "11201",
            "11203",
            "10007",
            "qps",
            "qpsoverflow",
            "appidqpsoverflowerror",
            "rate",
            "too many requests",
            "concurrency",
            "并发",
            "限流",
            "流控",
        )
        # 每个候选模型最多尝试 MAX_RETRY 次（含 QPS 限流退避重试）
        MAX_RETRY = 3
        for attempt_model in candidate_models:
            qps_retries = 0
            while qps_retries < MAX_RETRY:
                payload: Dict[str, Any] = {
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                # Spark X2 等端点已在 URL 路径中指定模型，不传 model 字段
                if attempt_model:
                    payload["model"] = attempt_model

                try:
                    async with httpx.AsyncClient(timeout=60.0) as client:
                        response = await client.post(
                            self._ws_url,
                            headers=headers,
                            json=payload,
                        )
                        if response.status_code == 200:
                            data = response.json()
                            # 讯飞 X2 在 HTTP 200 时仍可能在响应体顶层返回业务错误码（code != 0），
                            # 例如 11202 秒级限流、11201 日流控、11203 并发超限、10007 用户流量受限等。
                            biz_code = data.get("code", 0)
                            if biz_code not in (0, None):
                                body = data.get("message", "") or data.get("error", {}).get("message", "")
                                body = f"{body} (code={biz_code})"[:500]
                                body_lower = body.lower()
                                # 业务级限流：退避重试同一模型
                                is_qps_error = any(sign in body_lower for sign in qps_error_signs)
                                if is_qps_error and qps_retries < MAX_RETRY - 1:
                                    qps_retries += 1
                                    backoff = min(2 ** qps_retries, 8)
                                    logger.warning(
                                        "讯飞业务限流 (biz_code=%s)，%ss 后第 %d 次重试模型 %s",
                                        biz_code,
                                        backoff,
                                        qps_retries,
                                        attempt_model,
                                    )
                                    await asyncio.sleep(backoff)
                                    continue
                                last_error_msg = f"星火业务错误 [code={biz_code}]: {body}"
                                logger.error("Spark X2 业务错误: %s", last_error_msg)
                                yield {
                                    "type": "error",
                                    "code": biz_code,
                                    "message": f"星火服务错误 (code={biz_code}): {body}",
                                    "sid": data.get("sid", ""),
                                }
                                return

                            sid = data.get("id", "") or data.get("sid", "")

                            # OpenAI 兼容格式: choices[0].message.content
                            choices = data.get("choices", [])
                            if choices:
                                content = choices[0].get("message", {}).get("content", "")
                                if content:
                                    yield {
                                        "type": "content",
                                        "content": content,
                                        "sid": sid,
                                    }

                            usage = data.get("usage", {})
                            yield {
                                "type": "usage",
                                "prompt_tokens": usage.get("prompt_tokens", 0),
                                "completion_tokens": usage.get("completion_tokens", 0),
                                "total_tokens": usage.get("total_tokens", 0),
                                "sid": sid,
                            }
                            return  # 成功，结束生成器

                        # 非 200：读取响应体判断错误类型
                        body = ""
                        try:
                            body = response.text[:500]
                        except Exception:
                            body = "<无法读取响应体>"
                        body_lower = body.lower()

                        # QPS / 并发限流：退避后重试同一模型（而非换模型）
                        is_qps_error = any(sign in body_lower for sign in qps_error_signs)
                        if is_qps_error and qps_retries < MAX_RETRY - 1:
                            qps_retries += 1
                            backoff = min(2 ** qps_retries, 8)  # 指数退避，上限 8s
                            logger.warning(
                                "讯飞 QPS/并发限流 (code=%s)，%ss 后第 %d 次重试模型 %s",
                                response.status_code,
                                backoff,
                                qps_retries,
                                attempt_model,
                            )
                            await asyncio.sleep(backoff)
                            continue

                        # 模型不存在 / 无权限：换候选模型重试
                        is_model_error = (
                            "10404" in body
                            or "model not found" in body_lower
                            or "model_not_found" in body_lower
                            or "11200" in body
                            or "appidnoautherror" in body_lower
                            or "noauth" in body_lower
                            or "unauthorized" in body_lower
                            or "权限" in body
                        )
                        if is_model_error:
                            last_error_msg = f"星火 REST API 错误 [{response.status_code}]: {body}"
                            logger.warning(
                                "讯飞模型 %s 不可用 (code=%s)，尝试下一个候选模型",
                                attempt_model,
                                "11200" if "11200" in body else "10404",
                            )
                            break  # 跳出 while，换下一个候选模型
                        # 其他 HTTP 错误，按原逻辑抛出
                        response.raise_for_status()

                except httpx.HTTPStatusError as e:
                    resp_body = ""
                    try:
                        resp_body = e.response.text[:500] if e.response else ""
                    except Exception:
                        resp_body = "<无法读取响应体>"
                    logger.error(
                        "Spark REST HTTP %d: body=%s",
                        e.response.status_code if e.response else -1,
                        resp_body,
                    )
                    yield {
                        "type": "error",
                        "code": e.response.status_code if e.response else -1,
                        "message": (
                            f"星火 REST API 错误 [{e.response.status_code if e.response else '?'}]"
                            f"{': ' + resp_body if resp_body else ''}"
                        ),
                        "sid": "",
                    }
                    return
                except (httpx.TimeoutException, httpx.ConnectError) as e:
                    logger.error("Spark REST network error: %s", e)
                    yield {
                        "type": "error",
                        "code": -1,
                        "message": f"星火 REST API 连接失败: {e}",
                        "sid": "",
                    }
                    return
                except Exception:
                    logger.exception("Spark REST unexpected error")
                    yield {
                        "type": "error",
                        "code": -1,
                        "message": "星火 REST API 内部错误，请查看后端日志",
                        "sid": "",
                    }
                    return

        # 所有候选模型都失败（均为 10404 模型不存在）
        yield {
            "type": "error",
            "code": 10404,
            "message": (
                f"讯飞星火所有候选模型均不可用（最后错误：{last_error_msg or '未知'}）。"
                "请在 .env 中将 XF_MODEL 设置为本账号下有效的模型名。"
            ),
            "sid": "",
        }


# ============================================================================
# 全局单例
# ============================================================================

_spark_client: Optional[SparkClient] = None


def get_spark_client() -> SparkClient:
    """获取全局 SparkClient 单例"""
    global _spark_client
    if _spark_client is None:
        _spark_client = SparkClient()
        logger.info("SparkClient global singleton created")
    return _spark_client


def reset_spark_client() -> None:
    """重置全局 SparkClient"""
    global _spark_client
    _spark_client = None
    logger.info("SparkClient global singleton reset")


# 兼容旧版别名
get_chat_client = get_spark_client
