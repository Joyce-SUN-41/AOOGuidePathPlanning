"""
简易 IP 级速率限制中间件（内存实现，无外部依赖）

生产环境建议迁移到 Redis 实现以获得跨进程一致性。
"""
import ipaddress
import time
from collections import defaultdict
from typing import Dict, List, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import settings


def _is_trusted_proxy(ip: str) -> bool:
    """判断来源 IP 是否属于受信任代理网段 (CIDR/IP)"""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for cidr in settings.trusted_proxies_list:
        try:
            if addr in ipaddress.ip_network(cidr, strict=False):
                return True
        except ValueError:
            # 非法的 CIDR/IP 字面量，忽略
            continue
    return False


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    基于滑动窗口的 IP 级速率限制。

    配置：
        max_requests: 窗口内最大请求数
        window_seconds: 时间窗口长度（秒）
        exempt_paths: 豁免路径前缀列表（如健康检查、静态文件）
    """

    def __init__(
        self,
        app,
        max_requests: int = 100,
        window_seconds: int = 60,
        exempt_paths: List[str] | None = None,
    ):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.exempt_paths = exempt_paths or [
            "/health",
            "/metrics",
            "/docs",
            "/redoc",
            "/openapi.json",
        ]
        # 内存存储: ip -> [(timestamp, count), ...]
        self._store: Dict[str, List[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        # 豁免路径
        path = request.url.path
        for exempt in self.exempt_paths:
            if path.startswith(exempt):
                return await call_next(request)

        client_ip = self._get_client_ip(request)
        now = time.time()
        window_start = now - self.window_seconds

        # 滑动窗口清理
        timestamps = self._store[client_ip]
        timestamps[:] = [t for t in timestamps if t > window_start]

        if len(timestamps) >= self.max_requests:
            retry_after = int(timestamps[0] + self.window_seconds - now) + 1
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "请求过于频繁，请稍后再试",
                    "retry_after_seconds": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

        timestamps.append(now)

        # 定期清理过期条目
        if len(self._store) > 10_000:
            self._cleanup(now, window_start)

        return await call_next(request)

    def _get_client_ip(self, request: Request) -> str:
        """获取真实客户端 IP（考虑反向代理，但防止伪造绕过）

        安全策略：
        - 仅当直接来源 (request.client) 属于受信任代理网段时，才解析
          X-Forwarded-For / X-Real-IP；否则一律以 request.client 为准。
        - 解析 XFF 时，从右向左跳过受信任代理占用的段，取最接近真实
          客户端的那一段，避免攻击者在前段伪造 IP 被误采信。
        """
        direct_ip = request.client.host if request.client else "unknown"

        # 直接来源不是受信任代理：不采信任何代理头，直接返回来源 IP
        if not _is_trusted_proxy(direct_ip):
            return direct_ip

        # 来自受信任代理：尝试从 XFF 还原真实客户端
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            ips = [ip.strip() for ip in forwarded.split(",") if ip.strip()]
            # 从右向左剥离受信任代理段，最左一个非受信段即为真实客户端
            for ip in reversed(ips):
                if not _is_trusted_proxy(ip):
                    return ip
            # 全部都是受信段（极端情况），回退到最左段
            return ips[0] if ips else direct_ip

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()

        return direct_ip

    def _cleanup(self, now: float, window_start: float):
        """清理过期 IP 条目"""
        expired = [ip for ip, ts in self._store.items() if not any(t > window_start for t in ts)]
        for ip in expired:
            del self._store[ip]
