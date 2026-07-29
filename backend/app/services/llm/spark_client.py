"""讯飞星火大模型 API 接入服务 — HTTP 方式调用

支持：
- 多轮对话（携带历史上下文）
- 流式输出（SSE）
- 工具调用（Function Calling）
- 错误重试与熔断降级
- Token 计数与上下文长度控制
- 请求日志记录

配置参数（环境变量）：
    XF_API_KEY      — API Key
    XF_API_SECRET   — API Secret
    XF_APP_ID       — 应用 ID
    XF_MODEL        — 模型名称（默认 spark-x）

用法示例:
    client = SparkClient(api_key, api_secret, app_id)
    resp = await client.chat([{"role": "user", "content": "你好"}])
    async for chunk in client.chat_stream(messages):
        print(chunk.content)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx

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
    """单次对话响应"""

    content: str = ""
    role: str = "assistant"
    usage: Optional[TokenUsage] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    finish_reason: Optional[str] = None

    @classmethod
    def from_api_response(cls, choice: dict, usage: Optional[dict] = None) -> "ChatResponse":
        """从 API 原始响应解析"""
        message = choice.get("message", {})
        resp = cls(
            content=message.get("content", "") or "",
            role=message.get("role", "assistant"),
            tool_calls=message.get("tool_calls"),
            finish_reason=choice.get("finish_reason"),
        )
        if usage:
            resp.usage = TokenUsage(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
            )
        return resp


@dataclass
class StreamChunk:
    """流式输出片段"""

    content: str = ""
    reasoning_content: Optional[str] = None  # 深度思考内容（如 deepseek-r1 风格）
    tool_calls: Optional[List[Dict[str, Any]]] = None
    finish_reason: Optional[str] = None
    usage: Optional[TokenUsage] = None


# ============================================================================
# 熔断器
# ============================================================================


class CircuitState(Enum):
    """熔断器状态"""

    CLOSED = "closed"  # 正常通行
    OPEN = "open"  # 熔断断开，拒绝请求
    HALF_OPEN = "half_open"  # 半开，试探性放行


class CircuitBreaker:
    """简单熔断器，防止级联失败。

    规则：
    - 在时间窗口内连续失败达到阈值 → 熔断打开（直接拒绝）
    - 经过恢复超时后 → 半开状态（允许一次试探）
    - 试探成功 → 闭合恢复；失败 → 重新打开
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_requests: int = 1,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_requests = half_open_max_requests

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: float = 0.0
        self.half_open_successes = 0

    @property
    def is_open(self) -> bool:
        """当前是否拒绝请求"""
        if self.state == CircuitState.CLOSED:
            return False

        if self.state == CircuitState.OPEN:
            elapsed = time.monotonic() - self.last_failure_time
            if elapsed >= self.recovery_timeout:
                logger.info("Circuit breaker: OPEN → HALF_OPEN (recovery timeout reached)")
                self.state = CircuitState.HALF_OPEN
                self.half_open_successes = 0
                return False
            return True

        # HALF_OPEN: 允许 limited 请求通过
        if self.state == CircuitState.HALF_OPEN:
            if self.half_open_successes >= self.half_open_max_requests:
                # 还在等待探测结果，暂时拒绝
                return True
            return False

        return False

    def record_success(self) -> None:
        """记录一次成功"""
        if self.state == CircuitState.HALF_OPEN:
            self.half_open_successes += 1
            if self.half_open_successes >= self.half_open_max_requests:
                logger.info("Circuit breaker: HALF_OPEN → CLOSED (probe succeeded)")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
        else:
            # CLOSED: reset failure count on success
            self.failure_count = max(0, self.failure_count - 1)

    def record_failure(self) -> None:
        """记录一次失败"""
        self.failure_count += 1
        self.last_failure_time = time.monotonic()

        if self.state == CircuitState.HALF_OPEN:
            logger.warning("Circuit breaker: HALF_OPEN → OPEN (probe failed)")
            self.state = CircuitState.OPEN
        elif self.failure_count >= self.failure_threshold:
            logger.warning(
                "Circuit breaker: CLOSED → OPEN (%d consecutive failures)", self.failure_count
            )
            self.state = CircuitState.OPEN

    def reset(self) -> None:
        """手动重置熔断器"""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.half_open_successes = 0
        logger.info("Circuit breaker manually reset to CLOSED")


# ============================================================================
# Token 计数器
# ============================================================================


class TokenCounter:
    """简单 Token 估算器（无需 tiktoken 依赖）。

    估算规则：
    - 中文字符：~1.5 tokens/char
    - 英文/数字/标点：~0.25 tokens/char（约 4 字符 = 1 token）
    - 总开销约 ±20%，保守偏高估算。

    生产环境建议替换为 tiktoken 精确计数。
    """

    _CHINESE_START = ord("\u4e00")
    _CHINESE_END = ord("\u9fff")
    _CHINESE_RATIO: float = 1.5
    _OTHER_RATIO: float = 0.25

    @staticmethod
    def estimate(text: str) -> int:
        """估算单段文本的 token 数"""
        if not text:
            return 0
        chinese = sum(1 for c in text if TokenCounter._CHINESE_START <= ord(c) <= TokenCounter._CHINESE_END)
        other = len(text) - chinese
        return int(chinese * TokenCounter._CHINESE_RATIO + other * TokenCounter._OTHER_RATIO)

    @staticmethod
    def estimate_messages(messages: List[Dict[str, Any]]) -> int:
        """估算消息列表的 token 总量"""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += TokenCounter.estimate(content)
            elif isinstance(content, list):
                # 多模态消息格式: [{"type": "text", "text": "..."}, {"type": "image_url", ...}]
                for part in content:
                    if isinstance(part, dict):
                        total += TokenCounter.estimate(part.get("text", ""))
            # 工具调用内容
            if msg.get("tool_calls"):
                total += TokenCounter.estimate(json.dumps(msg["tool_calls"], ensure_ascii=False))
            if msg.get("tool_call_id"):
                total += TokenCounter.estimate(str(msg.get("tool_call_id", "")))
            if msg.get("name"):
                total += TokenCounter.estimate(str(msg["name"]))
            # role 标记开销
            total += 4
        # 每条消息额外 3 token 的格式化开销
        total += len(messages) * 3
        return total


# ============================================================================
# SparkClient 核心客户端
# ============================================================================


class SparkClientError(Exception):
    """Spark 客户端通用异常"""

    pass


class SparkAPIError(SparkClientError):
    """API 返回错误"""

    def __init__(self, status_code: int, message: str, response_body: Optional[str] = None):
        self.status_code = status_code
        self.message = message
        self.response_body = response_body
        super().__init__(f"[{status_code}] {message}")


class SparkCircuitOpenError(SparkClientError):
    """熔断器开启，请求被拒绝"""

    pass


class SparkTimeoutError(SparkClientError):
    """请求超时"""

    pass


class SparkTokenLimitError(SparkClientError):
    """Token 超出限制"""

    pass


class SparkClient:
    """讯飞星火大模型 HTTP 客户端。

    特性：
    - HTTP 方式调用星火 API（兼容 OpenAI 接口规范）
    - 多轮对话（自动携带历史上下文）
    - 流式输出（SSE 解析）
    - Function Calling 工具调用
    - 指数退避重试（最多 3 次）
    - 熔断降级
    - Token 上下文窗口管理
    """

    # 默认 API 地址
    DEFAULT_BASE_URL = "https://spark-api-open.xf-yun.com"
    DEFAULT_CHAT_ENDPOINT = "/x2/chat/completions"

    # 重试配置
    MAX_RETRIES: int = 3
    RETRY_BASE_DELAY: float = 1.0  # 初始退避秒数
    RETRY_MAX_DELAY: float = 30.0  # 最大退避秒数
    RETRYABLE_STATUSES: set = {429, 500, 502, 503, 504}

    # 上下文窗口默认值
    DEFAULT_MAX_CONTEXT_TOKENS: int = 8192  # spark-x 上下文窗口
    CONTEXT_SAFETY_MARGIN: int = 512  # 预留 margin 给 response

    # 请求超时
    REQUEST_TIMEOUT: float = 60.0
    STREAM_TIMEOUT: float = 120.0

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        app_id: str,
        model: str = "spark-x",
        base_url: Optional[str] = None,
        max_context_tokens: Optional[int] = None,
    ):
        """
        Args:
            api_key: 讯飞 API Key
            api_secret: 讯飞 API Secret
            app_id: 讯飞应用 ID
            model: 模型名称 (spark-x / spark-pro / spark-lite 等)
            base_url: API 基础地址，默认正式环境
            max_context_tokens: 上下文窗口大小，默认 8192
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.app_id = app_id
        self.model = model
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self.max_context_tokens = max_context_tokens or self.DEFAULT_MAX_CONTEXT_TOKENS

        self.circuit_breaker = CircuitBreaker()
        self._client: Optional[httpx.AsyncClient] = None
        self._client_lock = asyncio.Lock()

        logger.info(
            "SparkClient initialized | model=%s | base_url=%s | max_ctx=%d",
            self.model,
            self.base_url,
            self.max_context_tokens,
        )

    # ---- 属性 ----

    @property
    def is_configured(self) -> bool:
        """是否配置了完整凭证"""
        return bool(self.api_key and self.api_secret and self.app_id)

    @property
    def chat_endpoint(self) -> str:
        return f"{self.base_url}{self.DEFAULT_CHAT_ENDPOINT}"

    # ---- HTTP 客户端管理 ----

    async def _get_client(self) -> httpx.AsyncClient:
        """获取或创建 HTTP 客户端（线程安全）"""
        if self._client is None:
            async with self._client_lock:
                if self._client is None:
                    self._client = httpx.AsyncClient(
                        timeout=httpx.Timeout(self.REQUEST_TIMEOUT),
                        limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
                    )
                    logger.debug("httpx.AsyncClient created")
        return self._client

    async def close(self) -> None:
        """关闭 HTTP 客户端，释放资源"""
        if self._client is not None:
            async with self._client_lock:
                if self._client is not None:
                    await self._client.aclose()
                    self._client = None
                    logger.debug("httpx.AsyncClient closed")

    # ---- 请求构建 ----

    def _build_headers(self) -> Dict[str, str]:
        """构建请求头"""
        return {
            "Authorization": f"Bearer {self.api_key}:{self.api_secret}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _build_payload(
        self,
        messages: List[Dict[str, Any]],
        *,
        stream: bool = False,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """构建请求体"""
        payload: Dict[str, Any] = {
            "model": kwargs.get("model", self.model),
            "messages": messages,
            "stream": stream,
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 2048),
            "top_p": kwargs.get("top_p", 0.9),
        }
        if "top_k" in kwargs:
            payload["top_k"] = kwargs["top_k"]
        if "frequency_penalty" in kwargs:
            payload["frequency_penalty"] = kwargs["frequency_penalty"]
        if "presence_penalty" in kwargs:
            payload["presence_penalty"] = kwargs["presence_penalty"]
        if "stop" in kwargs:
            payload["stop"] = kwargs["stop"]
        if tools:
            payload["tools"] = tools
        if tool_choice:
            payload["tool_choice"] = tool_choice

        return payload

    # ---- 上下文管理 ----

    def _trim_messages(
        self,
        messages: List[Dict[str, Any]],
        reserved_tokens: int = 0,
    ) -> List[Dict[str, Any]]:
        """裁剪消息列表以适应上下文窗口。

        策略：
        1. 始终保留 system 消息
        2. 从最早的 user/assistant 对话开始删除
        3. 保留足够的 token 空间给 response（reserved_tokens）

        Args:
            messages: 消息列表
            reserved_tokens: 为响应预留的 token 数

        Returns:
            裁剪后的消息列表
        """
        max_input_tokens = self.max_context_tokens - reserved_tokens - self.CONTEXT_SAFETY_MARGIN
        estimated = TokenCounter.estimate_messages(messages)

        if estimated <= max_input_tokens:
            return messages

        logger.warning(
            "Messages exceed context window, trimming | estimated=%d > max=%d",
            estimated,
            max_input_tokens,
        )

        system_msgs = [m for m in messages if m["role"] == "system"]
        conversation = [m for m in messages if m["role"] != "system"]

        # 从最早的对话轮次开始裁剪
        while len(conversation) > 1:
            current = system_msgs + conversation
            if TokenCounter.estimate_messages(current) <= max_input_tokens:
                logger.info("Trimmed messages from %d to %d", len(messages), len(current))
                return current
            conversation.pop(0)

        # 极端情况：只剩 system + 1 条消息
        result = system_msgs + conversation
        logger.warning(
            "Messages trimmed to minimum | final_count=%d | tokens=%d",
            len(result),
            TokenCounter.estimate_messages(result),
        )
        return result

    def check_token_limit(self, messages: List[Dict[str, Any]]) -> Optional[str]:
        """检查消息是否超出 token 限制，返回警告信息或 None"""
        total = TokenCounter.estimate_messages(messages)
        if total > self.max_context_tokens:
            return (
                f"Input tokens ({total}) exceed context window ({self.max_context_tokens}). "
                f"Messages will be trimmed automatically."
            )
        if total > self.max_context_tokens * 0.8:
            return (
                f"Input tokens ({total}) approaching context window ({self.max_context_tokens}). "
                f"Consider reducing history length."
            )
        return None

    # ---- 非流式对话 ----

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        *,
        stream: bool = False,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> ChatResponse:
        """发送对话请求（非流式）。

        Args:
            messages: 对话消息列表 [{"role": "user", "content": "..."}]
            stream: 是否流式（False 时一次性返回）
            tools: 工具定义列表（Function Calling）
            tool_choice: 工具选择策略 ("auto" / "none" / {"type": "function", "function": {"name": "..."}})
            max_tokens: 最大生成 token 数
            temperature: 采样温度

        Returns:
            ChatResponse 对象

        Raises:
            SparkCircuitOpenError: 熔断器开启
            SparkAPIError: API 返回错误
            SparkTimeoutError: 请求超时
        """
        if not self.is_configured:
            logger.warning("XF credentials not configured, returning mock response")
            return self._fallback_response(messages)

        # 熔断检查
        if self.circuit_breaker.is_open:
            raise SparkCircuitOpenError("Circuit breaker is OPEN, request rejected")

        # Token 检查 + 裁剪
        warning = self.check_token_limit(messages)
        if warning:
            logger.warning(warning)
        trimmed = self._trim_messages(messages, reserved_tokens=max_tokens)

        payload = self._build_payload(
            trimmed,
            stream=False,
            tools=tools,
            tool_choice=tool_choice,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs,
        )
        headers = self._build_headers()

        log_id = _short_id()
        logger.info(
            "[%s] REQUEST | model=%s | msgs=%d | tokens_est=%d | max_tokens=%d | tools=%s",
            log_id,
            self.model,
            len(trimmed),
            TokenCounter.estimate_messages(trimmed),
            max_tokens,
            bool(tools),
        )

        try:
            response_data = await self._request_with_retry(payload, headers, log_id)
        except SparkClientError:
            raise
        except Exception as e:
            self.circuit_breaker.record_failure()
            raise SparkClientError(f"Unexpected error: {e}") from e

        # 解析响应
        choices = response_data.get("choices", [])
        if not choices:
            raise SparkAPIError(200, "Empty response: no choices returned", json.dumps(response_data))

        usage_data = response_data.get("usage")
        response = ChatResponse.from_api_response(choices[0], usage_data)

        logger.info(
            "[%s] RESPONSE | content_len=%d | tokens(p=%d c=%d t=%d) | finish=%s",
            log_id,
            len(response.content),
            response.usage.prompt_tokens if response.usage else 0,
            response.usage.completion_tokens if response.usage else 0,
            response.usage.total_tokens if response.usage else 0,
            response.finish_reason,
        )

        return response

    # ---- 流式对话 ----

    async def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        *,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> AsyncGenerator[StreamChunk, None]:
        """流式对话，返回异步生成器。

        用法:
            async for chunk in client.chat_stream(messages):
                print(chunk.content, end="", flush=True)

        Args:
            messages: 对话消息列表
            tools: 工具定义列表
            tool_choice: 工具选择策略
            max_tokens: 最大生成 token 数
            temperature: 采样温度

        Yields:
            StreamChunk 对象，包含增量内容和元信息
        """
        if not self.is_configured:
            logger.warning("XF credentials not configured, returning mock stream")
            yield StreamChunk(content="[模拟讯飞星火流式响应] API 凭证未配置，请在 .env 中设置 XF_API_KEY 等参数。")
            yield StreamChunk(content="", finish_reason="stop")
            return

        # 熔断检查
        if self.circuit_breaker.is_open:
            raise SparkCircuitOpenError("Circuit breaker is OPEN, request rejected")

        # Token 检查 + 裁剪
        warning = self.check_token_limit(messages)
        if warning:
            logger.warning(warning)
        trimmed = self._trim_messages(messages, reserved_tokens=max_tokens)

        payload = self._build_payload(
            trimmed,
            stream=True,
            tools=tools,
            tool_choice=tool_choice,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs,
        )
        headers = self._build_headers()

        log_id = _short_id()
        logger.info(
            "[%s] STREAM_REQ | model=%s | msgs=%d | tokens_est=%d | max_tokens=%d | tools=%s",
            log_id,
            self.model,
            len(trimmed),
            TokenCounter.estimate_messages(trimmed),
            max_tokens,
            bool(tools),
        )

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
                    raise SparkAPIError(
                        response.status_code,
                        f"Stream request failed",
                        body.decode("utf-8", errors="replace"),
                    )

                async for line in response.aiter_lines():
                    if not line:
                        continue
                    # SSE 格式: "data: {...}"
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            logger.info("[%s] STREAM DONE | chunks=%d", log_id, chunk_count)
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

            # 流成功 → 记录到熔断器
            self.circuit_breaker.record_success()

        except SparkClientError:
            self.circuit_breaker.record_failure()
            raise
        except httpx.TimeoutException:
            self.circuit_breaker.record_failure()
            raise SparkTimeoutError(f"Stream request timed out after {self.STREAM_TIMEOUT}s")
        except httpx.HTTPError as e:
            self.circuit_breaker.record_failure()
            raise SparkClientError(f"HTTP stream error: {e}") from e
        except Exception as e:
            self.circuit_breaker.record_failure()
            raise SparkClientError(f"Unexpected stream error: {e}") from e

        logger.info("[%s] STREAM END | total_chunks=%d", log_id, chunk_count)

    def _parse_stream_chunk(self, data: dict) -> StreamChunk:
        """解析单条 SSE 数据为 StreamChunk"""
        choices = data.get("choices", [])
        if not choices:
            return StreamChunk()

        choice = choices[0]
        delta = choice.get("delta", {})
        finish_reason = choice.get("finish_reason")

        chunk = StreamChunk(
            content=delta.get("content", "") or "",
            reasoning_content=delta.get("reasoning_content"),
            tool_calls=delta.get("tool_calls"),
            finish_reason=finish_reason,
        )

        # 最后一个 chunk 通常携带 usage
        usage_data = data.get("usage")
        if usage_data:
            chunk.usage = TokenUsage(
                prompt_tokens=usage_data.get("prompt_tokens", 0),
                completion_tokens=usage_data.get("completion_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0),
            )

        return chunk

    # ---- 重试逻辑 ----

    async def _request_with_retry(
        self,
        payload: Dict[str, Any],
        headers: Dict[str, str],
        log_id: str,
    ) -> Dict[str, Any]:
        """发送请求，失败时指数退避重试。

        Args:
            payload: 请求体
            headers: 请求头
            log_id: 日志追踪 ID

        Returns:
            解析后的 JSON 响应

        Raises:
            SparkAPIError: API 返回非 2xx 且不可重试
            SparkTimeoutError: 请求超时且重试耗尽
        """
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

                # 2xx: 成功
                if response.is_success:
                    self.circuit_breaker.record_success()
                    return response.json()

                # 非 2xx
                body = response.text[:1000]
                status = response.status_code

                if status in self.RETRYABLE_STATUSES and attempt < self.MAX_RETRIES:
                    delay = min(self.RETRY_BASE_DELAY * (2**attempt), self.RETRY_MAX_DELAY)
                    logger.warning(
                        "[%s] Retryable error %d | attempt=%d/%d | retry_in=%.1fs",
                        log_id,
                        status,
                        attempt + 1,
                        self.MAX_RETRIES,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    last_exception = SparkAPIError(status, "Retryable server error", body)
                    continue

                raise SparkAPIError(status, "API error", body)

            except httpx.TimeoutException:
                if attempt < self.MAX_RETRIES:
                    delay = min(self.RETRY_BASE_DELAY * (2**attempt), self.RETRY_MAX_DELAY)
                    logger.warning(
                        "[%s] Timeout retry | attempt=%d/%d | retry_in=%.1fs",
                        log_id,
                        attempt + 1,
                        self.MAX_RETRIES,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    last_exception = SparkTimeoutError(f"Request timed out (attempt {attempt + 1})")
                    continue
                raise SparkTimeoutError(
                    f"Request timed out after {self.MAX_RETRIES + 1} attempts"
                )

            except httpx.HTTPError as e:
                if attempt < self.MAX_RETRIES:
                    delay = min(self.RETRY_BASE_DELAY * (2**attempt), self.RETRY_MAX_DELAY)
                    logger.warning(
                        "[%s] HTTP error retry | attempt=%d/%d | error=%s",
                        log_id,
                        attempt + 1,
                        self.MAX_RETRIES,
                        e,
                    )
                    await asyncio.sleep(delay)
                    last_exception = e
                    continue
                raise SparkClientError(f"HTTP error after {self.MAX_RETRIES + 1} attempts: {e}") from e

            except SparkAPIError:
                raise
            except Exception as e:
                raise SparkClientError(f"Unexpected error: {e}") from e

        # 所有重试耗尽
        self.circuit_breaker.record_failure()
        if last_exception:
            raise last_exception  # type: ignore
        raise SparkClientError("Max retries exhausted with unknown error")

    # ---- 降级 ----

    def _fallback_response(self, messages: List[Dict[str, Any]]) -> ChatResponse:
        """凭证未配置时的降级响应（开发/测试环境）"""
        last_user_msg = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user_msg = str(m.get("content", ""))[:200]
                break

        return ChatResponse(
            content=(
                f"[本地模拟响应] 讯飞星火 API 未配置。\n"
                f"请在 .env 中设置 XF_API_KEY、XF_API_SECRET、XF_APP_ID。\n"
                f"收到 {len(messages)} 条消息，最后一条用户消息: \"{last_user_msg}\""
            ),
            usage=TokenUsage(
                prompt_tokens=TokenCounter.estimate_messages(messages),
                completion_tokens=50,
                total_tokens=TokenCounter.estimate_messages(messages) + 50,
            ),
            finish_reason="stop",
        )


# ============================================================================
# 全局单例工厂
# ============================================================================

_spark_client_instance: Optional[SparkClient] = None


def get_spark_client(
    api_key: Optional[str] = None,
    api_secret: Optional[str] = None,
    app_id: Optional[str] = None,
    model: Optional[str] = None,
) -> SparkClient:
    """获取 SparkClient 全局单例。

    首次调用时从 Settings 读取配置，后续调用复用实例。
    也支持显式传入参数覆盖默认配置。

    Returns:
        全局 SparkClient 实例
    """
    global _spark_client_instance

    if _spark_client_instance is None:
        from app.core.config import settings

        _spark_client_instance = SparkClient(
            api_key=api_key or settings.XF_API_KEY,
            api_secret=api_secret or settings.XF_API_SECRET,
            app_id=app_id or settings.XF_APP_ID,
            model=model or settings.XF_MODEL,
        )
        logger.info("SparkClient global singleton created")

    return _spark_client_instance


async def reset_spark_client() -> None:
    """重置全局客户端（如配置变更后）"""
    global _spark_client_instance
    if _spark_client_instance is not None:
        await _spark_client_instance.close()
        _spark_client_instance = None
        logger.info("SparkClient global singleton reset")


# ============================================================================
# 工具函数
# ============================================================================


def _short_id() -> str:
    """生成短追踪 ID（6 位十六进制）"""
    return hex(int(time.monotonic() * 1_000_000) % 0xFFFFFF)[2:].zfill(6)
