"""工具函数模块"""

import uuid


def generate_id() -> str:
    """生成唯一 ID (UUID4)"""
    return str(uuid.uuid4())
