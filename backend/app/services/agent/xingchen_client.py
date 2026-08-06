"""讯飞星辰 Agent 平台 HTTP 客户端

封装星辰 Agent API 调用，支持：
- Bearer Token 认证
- 非流式对话（JSON 响应）
- SSE 流式输出
- 工具调用结果解析
- 指数退避重试 + 熔断降级
- 请求日志追踪

API 规范参考：
    讯飞星辰 Agent 平台 API 接入文档
    POST {XINGCHEN_AGENT_API_URL}/v1/flow/run

配置参数（环境变量）：
    XINGCHEN_AGENT_API_URL   — Agent 平台 API 地址
    XINGCHEN_AGENT_API_KEY   — API 认证密钥
    XINGCHEN_AGENT_FLOW_ID   — 工作流 ID

用法示例:
    client = XingchenAgentClient(base_url, api_key, flow_id)
    resp = await client.chat(session_id="sess_1", message="你好")
    async for chunk in client.chat_stream(session_id="sess_1", message="你好"):
        print(chunk)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


# ============================================================================
# 数据模型
# ============================================================================


@dataclass
class AgentResponse:
    """单次非流式对话响应"""

    session_id: str = ""
    content: str = ""
    finish_reason: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    usage: Optional[Dict[str, int]] = None
    raw_response: Optional[Dict[str, Any]] = None


@dataclass
class AgentStreamChunk:
    """SSE 流式输出片段"""

    content: str = ""
    finish_reason: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    usage: Optional[Dict[str, int]] = None
    error: Optional[str] = None


# ============================================================================
# 自定义异常
# ============================================================================


class AgentClientError(Exception):
    """Agent 客户端通用异常"""
    pass


class AgentAPIError(AgentClientError):
    """API 返回错误"""

    def __init__(self, status_code: int, message: str, response_body: Optional[str] = None):
        self.status_code = status_code
        self.message = message
        self.response_body = response_body
        super().__init__(f"[{status_code}] {message}")


class AgentAuthError(AgentAPIError):
    """认证失败"""
    pass


class AgentTimeoutError(AgentClientError):
    """请求超时"""
    pass


class AgentCircuitOpenError(AgentClientError):
    """熔断器开启"""
    pass


# ============================================================================
# 熔断器（与 SparkClient 共享逻辑，此处做轻量独立实现）
# ============================================================================


class _CircuitBreaker:
    """简单熔断器"""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = self.CLOSED
        self.failure_count = 0
        self.last_failure_time: float = 0.0

    @property
    def is_open(self) -> bool:
        if self.state == self.CLOSED:
            return False
        if self.state == self.OPEN:
            if time.monotonic() - self.last_failure_time >= self.recovery_timeout:
                logger.info("Agent circuit breaker: OPEN → HALF_OPEN")
                self.state = self.HALF_OPEN
                return False
            return True
        # HALF_OPEN: allow one probe
        return False

    def record_success(self) -> None:
        if self.state == self.HALF_OPEN:
            logger.info("Agent circuit breaker: HALF_OPEN → CLOSED")
            self.state = self.CLOSED
            self.failure_count = 0
        else:
            self.failure_count = max(0, self.failure_count - 1)

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = time.monotonic()
        if self.state == self.HALF_OPEN:
            logger.warning("Agent circuit breaker: HALF_OPEN → OPEN (probe failed)")
            self.state = self.OPEN
        elif self.failure_count >= self.failure_threshold:
            logger.warning("Agent circuit breaker: CLOSED → OPEN (%d failures)", self.failure_count)
            self.state = self.OPEN

    def reset(self) -> None:
        self.state = self.CLOSED
        self.failure_count = 0
        logger.info("Agent circuit breaker reset to CLOSED")


# ============================================================================
# 核心客户端
# ============================================================================


class XingchenAgentClient:
    """讯飞星辰 Agent 平台 HTTP 客户端。

    特性：
    - Bearer Token 认证
    - 非流式 + SSE 流式两种模式
    - 指数退避重试（最多 3 次）
    - 熔断降级
    - 自动提取工具调用结果
    """

    # 重试配置
    MAX_RETRIES: int = 3
    RETRY_BASE_DELAY: float = 1.0
    RETRY_MAX_DELAY: float = 30.0
    RETRYABLE_STATUSES: set = {429, 500, 502, 503, 504}

    # 超时
    REQUEST_TIMEOUT: float = 120.0
    STREAM_TIMEOUT: float = 300.0

    def __init__(
        self,
        base_url: str,
        api_key: str,
        flow_id: str = "",
    ):
        """
        Args:
            base_url: Agent 平台 API 地址 (如 https://api-agent.xf-yun.com)
            api_key: API 认证密钥
            flow_id: 工作流 ID（发布时获取）
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.flow_id = flow_id

        self._circuit_breaker = _CircuitBreaker()
        self._client: Optional[httpx.AsyncClient] = None
        self._client_lock = asyncio.Lock()

        logger.info(
            "XingchenAgentClient initialized | base_url=%s | flow_id=%s",
            self.base_url,
            self.flow_id,
        )

    # ---- 属性 ----

    @property
    def is_configured(self) -> bool:
        """是否已配置完整凭证"""
        return bool(self.base_url and self.api_key)

    @property
    def chat_endpoint(self) -> str:
        # 兼容两种配置：
        # 1) 配置为完整 endpoint: https://xxx/v1/flow/run
        # 2) 配置为 base URL: https://xxx
        if self.base_url.endswith("/v1/flow/run"):
            return self.base_url
        return f"{self.base_url}/v1/flow/run"

    # ---- HTTP 客户端管理 ----

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            async with self._client_lock:
                if self._client is None:
                    self._client = httpx.AsyncClient(
                        timeout=httpx.Timeout(self.REQUEST_TIMEOUT),
                        limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
                    )
                    logger.debug("Agent httpx.AsyncClient created")
        return self._client

    async def close(self) -> None:
        """释放 HTTP 客户端资源"""
        if self._client is not None:
            async with self._client_lock:
                if self._client is not None:
                    await self._client.aclose()
                    self._client = None
                    logger.debug("Agent httpx.AsyncClient closed")

    # ---- 请求构建 ----

    def _build_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _build_payload(
        self,
        session_id: str,
        message: str,
        user_id: str = "",
        stream: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """构建请求体

        遵循星辰 Agent 平台 API 规范，字段可能因版本而异。
        核心字段: session_id, inputs(含 message), flow_id
        """
        payload: Dict[str, Any] = {
            "session_id": session_id,
            "stream": stream,
            "inputs": {
                "message": message,
                "user_id": user_id or session_id,
            },
        }
        flow_id = kwargs.get("flow_id", self.flow_id)
        if flow_id:
            payload["flow_id"] = flow_id
        # 透传额外参数
        for key in ("temperature", "max_tokens", "top_p"):
            if key in kwargs:
                payload[key] = kwargs[key]
        # 系统提示词（建议 7：引导式 system prompt）透传到 inputs.system；
        # 星辰平台若支持 system 指令即生效，不支持时作为普通字段静默忽略，不破坏调用。
        system_prompt = kwargs.get("system")
        if system_prompt:
            payload["inputs"]["system"] = system_prompt
        return payload

    # ---- 非流式对话 ----

    async def chat(
        self,
        session_id: str,
        message: str,
        user_id: str = "",
        **kwargs: Any,
    ) -> AgentResponse:
        """发送非流式对话请求。

        Args:
            session_id: 会话 ID
            message: 用户消息
            user_id: 用户 ID

        Returns:
            AgentResponse 包含回复内容和工具调用结果

        Raises:
            AgentCircuitOpenError: 熔断器开启
            AgentAPIError: API 错误
            AgentAuthError: 认证失败
            AgentTimeoutError: 请求超时
        """
        if not self.is_configured:
            logger.warning("Agent API not configured, returning fallback response")
            return self._fallback_response(session_id, message)

        if self._circuit_breaker.is_open:
            raise AgentCircuitOpenError("Circuit breaker is OPEN")

        payload = self._build_payload(session_id, message, user_id, stream=False, **kwargs)
        headers = self._build_headers()
        headers["Accept"] = "application/json"

        log_id = _short_id()
        logger.info("[%s] AGENT REQUEST | session=%s | msg_len=%d", log_id, session_id, len(message))

        try:
            response_data = await self._request_with_retry(payload, headers, log_id)
        except AgentClientError:
            raise
        except Exception as e:
            self._circuit_breaker.record_failure()
            raise AgentClientError(f"Unexpected error: {e}") from e

        return self._parse_response(response_data, session_id)

    def _parse_response(self, data: Dict[str, Any], session_id: str) -> AgentResponse:
        """解析 API 响应为 AgentResponse

        适配多种可能的响应格式：
        - 星辰标准格式: {code, message, data: {answer, tool_calls, ...}}
        - OpenAI 兼容格式: {choices: [{message: {content, tool_calls}}]}
        """
        # 检查错误码
        code = data.get("code", 0)
        if code != 0 and code != 200:
            err_msg = data.get("message", "Unknown error")
            raise AgentAPIError(code, err_msg, json.dumps(data, ensure_ascii=False))

        # 提取 data 层
        inner = data.get("data", data)

        # 解析回复内容
        content = ""
        finish_reason = "stop"
        tool_calls: List[Dict[str, Any]] = []

        # 格式1: OpenAI 兼容 {choices: [{message: {content, tool_calls}}]}
        if "choices" in inner:
            choices = inner["choices"]
            if choices:
                msg = choices[0].get("message", choices[0].get("delta", {}))
                content = msg.get("content", "") or ""
                finish_reason = choices[0].get("finish_reason", "stop")
                raw_tool_calls = msg.get("tool_calls")
                if raw_tool_calls:
                    tool_calls = self._normalize_tool_calls(raw_tool_calls)
        else:
            # 格式2: 星辰原生格式 {answer, tool_calls}
            content = inner.get("answer", "") or inner.get("content", "") or inner.get("text", "") or ""
            finish_reason = inner.get("finish_reason", "stop")
            raw_tool_calls = inner.get("tool_calls") or inner.get("tools")
            if raw_tool_calls:
                tool_calls = self._normalize_tool_calls(raw_tool_calls)

        # 提取 usage
        usage = inner.get("usage") or data.get("usage")

        return AgentResponse(
            session_id=session_id,
            content=content,
            finish_reason=finish_reason,
            tool_calls=tool_calls,
            usage=usage,
            raw_response=data,
        )

    def _normalize_tool_calls(self, raw: Any) -> List[Dict[str, Any]]:
        """统一工具调用格式"""
        if not raw:
            return []
        if isinstance(raw, list):
            result = []
            for tc in raw:
                if isinstance(tc, dict):
                    normalized = {
                        "tool_name": tc.get("name") or tc.get("function", {}).get("name", "unknown"),
                        "tool_call_id": tc.get("id") or tc.get("tool_call_id", ""),
                        "arguments": tc.get("arguments") or tc.get("function", {}).get("arguments", {}),
                        "result": tc.get("result") or tc.get("output"),
                        "status": tc.get("status", "completed"),
                        "error": tc.get("error"),
                    }
                    # 尝试解析 arguments 字符串
                    if isinstance(normalized["arguments"], str):
                        try:
                            normalized["arguments"] = json.loads(normalized["arguments"])
                        except (json.JSONDecodeError, TypeError):
                            pass
                    result.append(normalized)
            return result
        return []

    # ---- 流式对话 ----

    async def chat_stream(
        self,
        session_id: str,
        message: str,
        user_id: str = "",
        **kwargs: Any,
    ) -> AsyncGenerator[AgentStreamChunk, None]:
        """SSE 流式对话，返回异步生成器。

        用法:
            async for chunk in client.chat_stream("sess_1", "你好"):
                print(chunk.content, end="", flush=True)

        Yields:
            AgentStreamChunk 包含增量内容和元信息
        """
        if not self.is_configured:
            logger.warning("Agent API not configured, returning mock stream")
            yield AgentStreamChunk(content="[模拟响应] 星辰 Agent API 未配置。请在 .env 中设置 XINGCHEN_AGENT_API_URL 和 XINGCHEN_AGENT_API_KEY。")
            yield AgentStreamChunk(content="", finish_reason="stop")
            return

        if self._circuit_breaker.is_open:
            raise AgentCircuitOpenError("Circuit breaker is OPEN")

        payload = self._build_payload(session_id, message, user_id, stream=True, **kwargs)
        headers = self._build_headers()
        headers["Accept"] = "text/event-stream"

        log_id = _short_id()
        logger.info("[%s] AGENT STREAM | session=%s | msg_len=%d", log_id, session_id, len(message))

        client = await self._get_client()
        chunk_count = 0

        try:
            async with client.stream(
                "POST",
                self.chat_endpoint,
                headers=headers,
                json=payload,
                timeout=httpx.Timeout(self.STREAM_TIMEOUT),
            ) as response:
                if response.status_code >= 400:
                    body = await response.aread()
                    raise AgentAPIError(
                        response.status_code,
                        "Stream request failed",
                        body.decode("utf-8", errors="replace")[:1000],
                    )

                async for line in response.aiter_lines():
                    if not line:
                        continue
                    # SSE 格式: "data: {...}" 或 "data: [DONE]"
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            logger.info("[%s] AGENT STREAM DONE | chunks=%d", log_id, chunk_count)
                            break

                        try:
                            data = json.loads(data_str)
                        except json.JSONDecodeError:
                            logger.warning("[%s] Invalid SSE JSON: %s", log_id, data_str[:200])
                            continue

                        chunk = self._parse_stream_chunk(data)
                        chunk_count += 1
                        yield chunk

                        if chunk.finish_reason == "stop":
                            break

            self._circuit_breaker.record_success()

        except AgentClientError:
            self._circuit_breaker.record_failure()
            raise
        except httpx.TimeoutException:
            self._circuit_breaker.record_failure()
            raise AgentTimeoutError(f"Stream request timed out after {self.STREAM_TIMEOUT}s")
        except httpx.HTTPError as e:
            self._circuit_breaker.record_failure()
            raise AgentClientError(f"HTTP stream error: {e}") from e
        except Exception as e:
            self._circuit_breaker.record_failure()
            raise AgentClientError(f"Unexpected stream error: {e}") from e

        logger.info("[%s] AGENT STREAM END | total_chunks=%d", log_id, chunk_count)

    def _parse_stream_chunk(self, data: Dict[str, Any]) -> AgentStreamChunk:
        """解析 SSE 数据片段"""
        # 检查顶层错误
        code = data.get("code", 0)
        if code != 0 and code != 200:
            return AgentStreamChunk(
                error=data.get("message", "Stream error"),
                finish_reason="error",
            )

        inner = data.get("data", data)

        content = ""
        finish_reason = None
        tool_calls = None
        usage = None

        # OpenAI 兼容格式: choices[0].delta.content
        if "choices" in inner:
            choices = inner["choices"]
            if choices:
                delta = choices[0].get("delta", {})
                content = delta.get("content", "") or ""
                finish_reason = choices[0].get("finish_reason")
                usage = inner.get("usage")
                if delta.get("tool_calls"):
                    tool_calls = self._normalize_tool_calls(delta["tool_calls"])
        else:
            # 星辰原生 SSE 格式
            content = inner.get("answer", "") or inner.get("content", "") or inner.get("delta", "") or ""
            finish_reason = inner.get("finish_reason") or inner.get("status")
            usage = inner.get("usage") or data.get("usage")
            raw_tool_calls = inner.get("tool_calls") or inner.get("tools")
            if raw_tool_calls:
                tool_calls = self._normalize_tool_calls(raw_tool_calls)

        return AgentStreamChunk(
            content=content,
            finish_reason=finish_reason,
            tool_calls=tool_calls,
            usage=usage,
        )

    # ---- 重试逻辑 ----

    async def _request_with_retry(
        self,
        payload: Dict[str, Any],
        headers: Dict[str, str],
        log_id: str,
    ) -> Dict[str, Any]:
        client = await self._get_client()
        last_exception: Optional[Exception] = None

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                response = await client.post(
                    self.chat_endpoint,
                    headers=headers,
                    json=payload,
                    timeout=httpx.Timeout(self.REQUEST_TIMEOUT),
                )

                if response.is_success:
                    self._circuit_breaker.record_success()
                    return response.json()

                body = response.text[:1000]
                status = response.status_code

                # 认证失败 → 直接抛出，不重试
                if status in (401, 403):
                    raise AgentAuthError(status, "Authentication failed", body)

                # 可重试的状态码
                if status in self.RETRYABLE_STATUSES and attempt < self.MAX_RETRIES:
                    delay = min(self.RETRY_BASE_DELAY * (2 ** attempt), self.RETRY_MAX_DELAY)
                    logger.warning(
                        "[%s] Agent retry %d | status=%d | delay=%.1fs",
                        log_id, attempt + 1, status, delay,
                    )
                    await asyncio.sleep(delay)
                    last_exception = AgentAPIError(status, "Retryable error", body)
                    continue

                raise AgentAPIError(status, f"API error (status={status})", body)

            except httpx.TimeoutException:
                if attempt < self.MAX_RETRIES:
                    delay = min(self.RETRY_BASE_DELAY * (2 ** attempt), self.RETRY_MAX_DELAY)
                    logger.warning("[%s] Agent timeout retry %d | delay=%.1fs", log_id, attempt + 1, delay)
                    await asyncio.sleep(delay)
                    last_exception = AgentTimeoutError(f"Timeout (attempt {attempt + 1})")
                    continue
                raise AgentTimeoutError(f"Timeout after {self.MAX_RETRIES + 1} attempts")

            except (AgentAPIError, AgentAuthError):
                raise
            except httpx.HTTPError as e:
                if attempt < self.MAX_RETRIES:
                    delay = min(self.RETRY_BASE_DELAY * (2 ** attempt), self.RETRY_MAX_DELAY)
                    logger.warning("[%s] Agent HTTP retry %d | error=%s", log_id, attempt + 1, e)
                    await asyncio.sleep(delay)
                    last_exception = e
                    continue
                raise AgentClientError(f"HTTP error: {e}") from e
            except Exception as e:
                raise AgentClientError(f"Unexpected error: {e}") from e

        self._circuit_breaker.record_failure()
        if last_exception:
            raise last_exception  # type: ignore
        raise AgentClientError("Max retries exhausted")

    # ---- 降级响应 ----

    def _fallback_response(self, session_id: str, message: str) -> AgentResponse:
        """API 未配置时的降级响应"""
        return AgentResponse(
            session_id=session_id,
            content=(
                f"[本地模拟响应] 讯飞星辰 Agent API 未配置。\n"
                f"请在 .env 中设置 XINGCHEN_AGENT_API_URL 和 XINGCHEN_AGENT_API_KEY。\n"
                f"收到消息: \"{message[:200]}\""
            ),
            finish_reason="stop",
        )


# ============================================================================
# 全局单例工厂
# ============================================================================

_agent_client_instance: Optional[XingchenAgentClient] = None


def get_agent_client(
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    flow_id: Optional[str] = None,
) -> XingchenAgentClient:
    """获取 XingchenAgentClient 全局单例。

    首次调用时从 Settings 读取配置，后续复用。
    也支持显式传入参数覆盖默认配置。
    """
    global _agent_client_instance

    if _agent_client_instance is None:
        from app.core.config import settings

        _agent_client_instance = XingchenAgentClient(
            base_url=base_url or settings.XINGCHEN_AGENT_API_URL,
            api_key=api_key or settings.XINGCHEN_AGENT_API_KEY,
            flow_id=flow_id or settings.XINGCHEN_AGENT_FLOW_ID,
        )
        logger.info("XingchenAgentClient global singleton created")

    return _agent_client_instance


async def reset_agent_client() -> None:
    """重置全局客户端（配置变更后调用）"""
    global _agent_client_instance
    if _agent_client_instance is not None:
        await _agent_client_instance.close()
        _agent_client_instance = None
        logger.info("XingchenAgentClient global singleton reset")


# ============================================================================
# 工具函数
# ============================================================================


def _short_id() -> str:
    return hex(int(time.monotonic() * 1_000_000) % 0xFFFFFF)[2:].zfill(6)
