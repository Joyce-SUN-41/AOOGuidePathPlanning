"""认证相关 Pydantic 模式"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class Token(BaseModel):
    """Token 响应"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    """解码后的 Token payload"""
    sub: str
    exp: datetime
    type: str = "access"


class LoginRequest(BaseModel):
    """登录请求"""
    username: str
    password: str


class UserInfoResponse(BaseModel):
    """用户信息（供认证响应用，字段对齐前端 UserInfo 类型）"""
    id: str
    username: str
    nickname: Optional[str] = ""
    avatar: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    role: str = "student"
    status: int = 1       # 0=禁用, 1=激活
    createTime: str = ""  # ISO 格式字符串


class AuthResponse(BaseModel):
    """认证成功响应（登录/注册），前端期望 {token, userInfo} 格式"""
    token: str
    refreshToken: Optional[str] = None
    userInfo: UserInfoResponse
