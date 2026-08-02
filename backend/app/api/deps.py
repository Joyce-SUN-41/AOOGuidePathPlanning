"""FastAPI 依赖注入"""

import ipaddress
import time
from collections import defaultdict
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import decode_token
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


# ---------------------------------------------------------------------------
# 登录端点专项限流（比全局 120 req/min 严格得多，防暴力破解）
# ---------------------------------------------------------------------------
_LOGIN_MAX_REQUESTS = 10          # 窗口内最大尝试次数
_LOGIN_WINDOW_SECONDS = 60        # 时间窗口 (秒)
_login_store: "defaultdict[str, list[float]]" = defaultdict(list)


def _login_client_ip(request: Request) -> str:
    """与全局限流一致的真实客户端 IP 解析（受信任代理下才采信 XFF）"""
    direct_ip = request.client.host if request.client else "unknown"
    try:
        addr = ipaddress.ip_address(direct_ip)
    except ValueError:
        return direct_ip
    trusted = any(
        addr in ipaddress.ip_network(c, strict=False)
        for c in settings.trusted_proxies_list
        if _valid_cidr(c)
    )
    if not trusted:
        return direct_ip
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        ips = [ip.strip() for ip in forwarded.split(",") if ip.strip()]
        for ip in reversed(ips):
            try:
                if ipaddress.ip_address(ip) not in _trusted_networks():
                    return ip
            except ValueError:
                return ip
        return ips[0] if ips else direct_ip
    real_ip = request.headers.get("X-Real-IP")
    return real_ip.strip() if real_ip else direct_ip


def _valid_cidr(c: str) -> bool:
    try:
        ipaddress.ip_network(c, strict=False)
        return True
    except ValueError:
        return False


def _trusted_networks():
    nets = []
    for c in settings.trusted_proxies_list:
        if _valid_cidr(c):
            nets.append(ipaddress.ip_network(c, strict=False))
    return nets


async def login_rate_limit(request: Request):
    """登录端点限流依赖：单 IP 每分钟最多 10 次登录尝试"""
    client_ip = _login_client_ip(request)
    now = time.time()
    window_start = now - _LOGIN_WINDOW_SECONDS
    timestamps = _login_store[client_ip]
    timestamps[:] = [t for t in timestamps if t > window_start]
    if len(timestamps) >= _LOGIN_MAX_REQUESTS:
        retry_after = int(timestamps[0] + _LOGIN_WINDOW_SECONDS - now) + 1
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="登录尝试过于频繁，请稍后再试",
            headers={"Retry-After": str(retry_after)},
        )
    timestamps.append(now)
    # 控制内存：条目过多时清理过期项
    if len(_login_store) > 10_000:
        for ip, ts in list(_login_store.items()):
            ts[:] = [t for t in ts if t > window_start]
            if not ts:
                del _login_store[ip]


async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """从 JWT Token 中解析当前登录用户"""
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌类型错误",
        )

    user_id: str = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌负载无效",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户已被禁用",
        )

    return user


async def get_current_user_optional(
    token: Optional[str] = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """可选认证：有有效 Token 则返回用户，否则返回 None（不抛 401）

    用于埋点等允许匿名访问的端点 —— navigator.sendBeacon 无法携带
    Authorization 头，因此这类请求必须能在无身份的情况下被接受。
    """
    if not token:
        return None

    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    try:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
    except Exception:  # noqa: BLE001 — 埋点场景下任何 DB 异常都降级为匿名
        return None

    if user is None or not user.is_active:
        return None
    return user


async def get_current_superuser(
    current_user: User = Depends(get_current_user),
) -> User:
    """获取当前用户并验证是否为超级管理员"""
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足",
        )
    return current_user
