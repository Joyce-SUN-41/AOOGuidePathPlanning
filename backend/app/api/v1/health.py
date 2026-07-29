"""健康检查接口"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check():
    """服务健康检查"""
    return {"status": "ok", "message": "AOO Guide Path Planning API is running"}
