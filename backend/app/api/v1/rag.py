"""RAG 知识库 API — 检索增强生成问答

端点:
- POST /api/v1/rag/query   RAG 问答（支持 skip_retrieval 直连 LLM）
- POST /api/v1/rag/index   索引文档目录
- GET  /api/v1/rag/stats   获取知识库统计
- POST /api/v1/rag/reset   重置知识库
"""

import asyncio
import json
import logging
import uuid
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.common import ResponseBase
from app.schemas.rag import (
    RAGIndexRequest,
    RAGIndexResponse,
    RAGQueryRequest,
    RAGQueryResponse,
    RAGStatsResponse,
)
from app.services.rag import get_knowledge_base, reset_knowledge_base
from app.services.rag.knowledge_base import KnowledgeBase

router = APIRouter(prefix="/rag", tags=["RAG Knowledge Base"])

logger = logging.getLogger(__name__)


def _to_query_response(result) -> RAGQueryResponse:
    """将 KnowledgeBase 的 RAGQueryResult 转为对外 Schema"""
    token_usage = None
    if getattr(result, "token_usage", None):
        token_usage = result.token_usage
    return RAGQueryResponse(
        answer=result.answer,
        sources=result.sources,
        confidence=result.confidence,
        retrieval_count=result.retrieval_count,
        model=result.model,
        token_usage=token_usage,
        query_id=result.query_id,
    )


async def _get_kb() -> KnowledgeBase:
    """获取已初始化的知识库单例"""
    return await get_knowledge_base()


# ---------------------------------------------------------------------------
# SSE 流式支持
# ---------------------------------------------------------------------------

# KnowledgeBase.query_stream 用于分隔来源信息的哨兵标记
_SOURCES_SENTINEL = "<<SOURCES>>"


def _sse(payload: dict) -> str:
    """将字典序列化为一条 SSE data 帧"""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _rag_sse_generator(
    kb: KnowledgeBase,
    payload: RAGQueryRequest,
) -> AsyncGenerator[str, None]:
    """产出 SSE 事件流

    帧格式（与前端 ragQueryStream 约定一致）:
    - {"content": "增量文本"}      增量内容
    - {"sources": [...]}            检索来源（结束前发送一次）
    - {"error": "错误信息"}         错误
    - [DONE]                        终止标记
    """
    query_id = str(uuid.uuid4())[:8]
    try:
        # 先下发 query_id，便于前端埋点/关联
        yield _sse({"query_id": query_id})

        if payload.skip_retrieval:
            # 跳过检索：直接流式调用大模型
            stream = kb.direct_chat_stream(
                question=payload.question,
                temperature=payload.temperature,
                max_tokens=payload.max_tokens,
            )
        else:
            stream = kb.query_stream(
                question=payload.question,
                top_k=payload.top_k,
                temperature=payload.temperature,
                max_tokens=payload.max_tokens,
            )

        async for chunk in stream:
            if not chunk:
                continue
            if chunk.startswith(_SOURCES_SENTINEL):
                raw = chunk[len(_SOURCES_SENTINEL):]
                try:
                    sources = json.loads(raw) if raw else []
                except (ValueError, TypeError):
                    sources = []
                yield _sse({"sources": sources})
                continue
            yield _sse({"content": chunk})
            # 让出事件循环，确保分块及时刷出而非被缓冲成整包
            await asyncio.sleep(0)

    except asyncio.CancelledError:
        # 客户端主动断开，静默结束，不记为错误
        raise
    except Exception as e:  # noqa: BLE001
        logger.exception("[/rag/query][stream] 流式问答失败")
        yield _sse({"error": f"AI 服务暂时不可用：{e}"})
    finally:
        yield "data: [DONE]\n\n"


@router.post("/query", response_model=ResponseBase[RAGQueryResponse])
async def rag_query(
    payload: RAGQueryRequest,
    current_user: User = Depends(get_current_user),
    kb: KnowledgeBase = Depends(_get_kb),
):
    """RAG 问答

    - skip_retrieval=False: 先检索知识库再增强生成
    - skip_retrieval=True:  跳过检索，直接调用大模型回答
    - stream=True:          以 SSE (text/event-stream) 逐块返回
    """
    # ---- 流式分支（stream=True 时返回 SSE，其余逻辑保持不变）----
    if payload.stream:
        return StreamingResponse(
            _rag_sse_generator(kb, payload),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                # 关闭 Nginx 缓冲，否则 SSE 会被攒包后一次性下发
                "X-Accel-Buffering": "no",
            },
        )

    try:
        if payload.skip_retrieval:
            result = await kb.direct_chat(
                question=payload.question,
                temperature=payload.temperature,
                max_tokens=payload.max_tokens,
            )
        else:
            result = await kb.query(
                question=payload.question,
                top_k=payload.top_k,
                temperature=payload.temperature,
                max_tokens=payload.max_tokens,
            )
    except Exception as e:  # noqa: BLE001
        logger.exception("[/rag/query] 问答处理失败")
        # 不返回生硬的 500，向前端返回可读的错误提示（HTTP 200）
        return ResponseBase[RAGQueryResponse](
            code=500,
            message=f"AI 服务暂时不可用：{e}",
            data=RAGQueryResponse(
                answer=f"AI 服务暂时不可用：{e}",
                sources=[],
                confidence=0.0,
                retrieval_count=0,
                model="",
                token_usage=None,
                query_id=str(uuid.uuid4())[:8],
            ),
        )
    return ResponseBase[RAGQueryResponse](data=_to_query_response(result))


@router.post("/index", response_model=ResponseBase[RAGIndexResponse])
async def rag_index(
    payload: RAGIndexRequest,
    current_user: User = Depends(get_current_user),
    kb: KnowledgeBase = Depends(_get_kb),
):
    """索引指定目录下的文档到知识库"""
    try:
        chunks_indexed = await kb.index_directory(
            payload.directory,
            recursive=payload.recursive,
            clear_existing=payload.clear_existing,
        )
    except Exception as e:  # noqa: BLE001
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"索引失败: {e}",
        )
    return ResponseBase[RAGIndexResponse](
        data=RAGIndexResponse(
            message=f"已完成索引，共 {chunks_indexed} 个文档块",
            chunks_indexed=chunks_indexed,
            directory=payload.directory,
        )
    )


@router.get("/stats", response_model=ResponseBase[RAGStatsResponse])
async def rag_stats(
    current_user: User = Depends(get_current_user),
):
    """获取知识库统计信息"""
    try:
        kb = await get_knowledge_base()
        raw = kb.get_stats()
    except Exception:  # noqa: BLE001
        raw = {"status": "not_initialized", "documents": 0}
    return ResponseBase[RAGStatsResponse](data=RAGStatsResponse(**raw))


@router.post("/reset", response_model=ResponseBase[dict])
async def rag_reset(
    current_user: User = Depends(get_current_user),
):
    """重置知识库（清空索引并释放资源）"""
    await reset_knowledge_base()
    return ResponseBase[dict](data={"message": "知识库已重置"})
