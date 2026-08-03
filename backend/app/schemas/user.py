"""用户相关 Pydantic 模式"""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UserBase(BaseModel):
    """用户基础字段

    username 最小长度与前端登录/注册表单规则保持一致 (>=2)，避免前端放行后
    后端校验拒绝导致 422。
    """
    username: str = Field(..., min_length=2, max_length=50, description="用户名")


class UserCreate(UserBase):
    """创建用户（注册）

    password 最小长度与前端 RegisterView 表单规则保持一致 (>=6)，修复 422。
    """
    password: str = Field(
        ...,
        min_length=6,
        max_length=128,
        description="密码 (至少6位)",
        json_schema_extra={"example": "SecurePass123"},
    )
    nickname: Optional[str] = Field(None, max_length=50, description="昵称（显示名称）")
    email: Optional[EmailStr] = Field(None, description="邮箱（选填）")
    role: Optional[str] = Field("student", description="角色: student | teacher")

    @field_validator("email", mode="before")
    @classmethod
    def empty_str_to_none(cls, v: object) -> object:
        """将空字符串 email 转为 None，兼容前端空值提交"""
        if isinstance(v, str) and v.strip() == "":
            return None
        return v


class UserUpdate(BaseModel):
    """更新用户 (全部可选)"""
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    nickname: Optional[str] = Field(None, max_length=50)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=20)
    avatar: Optional[str] = None
    password: Optional[str] = Field(None, min_length=8, max_length=128)
    role: Optional[str] = None
    is_active: Optional[bool] = None


class UserOut(BaseModel):
    """用户响应 (不含密码)"""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    nickname: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    avatar: Optional[str] = None
    role: str = "student"
    is_active: bool
    is_superuser: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
