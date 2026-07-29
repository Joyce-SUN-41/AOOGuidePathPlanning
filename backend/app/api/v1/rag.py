"""RAG 知识库 API 端点"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.schemas.rag import (
    RAGIndexRequest,
    RAGIndexResponse,
    RAGQueryRequest,
    RAGQueryResponse,
    RAGSource,
    RAGStatsResponse,
    RAGTokenUsage,
)
from app.services.rag.knowledge_base import get_knowledge_base

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rag", tags=["RAG Knowledge Base"])


# ---- 问答接口 ----


@router.post("/query", response_model=RAGQueryResponse, summary="RAG 知识问答")
async def rag_query(req: RAGQueryRequest):
    """基于知识库的增强问答

    流程: 用户问题 → 语义检索 → 构建增强 Prompt → LLM 生成 → 返回答案+来源
    """
    try:
        kb = await get_knowledge_base()

        # 如果有学科过滤，传递到检索
        # (当前 ChromaDB 过滤通过 metadata where 实现)
        result = await kb.query(
            question=req.question,
            top_k=req.top_k,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
        )

        sources = [
            RAGSource(
                document=s.get("document", "未知文档"),
                page=str(s.get("page", "")),
                section=str(s.get("section", "")),
                content=s.get("content", ""),
                score=s.get("score", 0.0),
                ref=s.get("ref", 0),
            )
            for s in result.sources
        ]

        token_usage = None
        if result.token_usage:
            token_usage = RAGTokenUsage(**result.token_usage)

        return RAGQueryResponse(
            answer=result.answer,
            sources=sources,
            confidence=result.confidence,
            retrieval_count=result.retrieval_count,
            model=result.model,
            token_usage=token_usage,
            query_id=result.query_id,
        )

    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=f"知识库未就绪: {e}")
    except Exception as e:
        logger.exception("RAG query failed")
        raise HTTPException(status_code=500, detail=f"问答服务错误: {e}")


# ---- 索引接口 ----


@router.post("/index", response_model=RAGIndexResponse, summary="索引文档目录")
async def rag_index(req: RAGIndexRequest):
    """索引指定目录中的文档到知识库

    支持 PDF、TXT、Markdown 格式。
    """
    try:
        kb = await get_knowledge_base()

        count = await kb.index_directory(
            directory=req.directory,
            recursive=req.recursive,
            clear_existing=req.clear_existing,
        )

        return RAGIndexResponse(
            message=f"索引完成，共 {count} 个文档块",
            chunks_indexed=count,
            directory=req.directory,
        )

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except NotADirectoryError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=f"知识库未就绪: {e}")
    except Exception as e:
        logger.exception("RAG indexing failed")
        raise HTTPException(status_code=500, detail=f"索引失败: {e}")


# ---- 管理接口 ----


@router.get("/stats", response_model=RAGStatsResponse, summary="知识库统计")
async def rag_stats():
    """获取知识库统计信息"""
    try:
        kb = await get_knowledge_base()
        stats = kb.get_stats()
        return RAGStatsResponse(**stats)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=f"知识库未就绪: {e}")


@router.post("/reset", summary="重置知识库")
async def rag_reset():
    """重置知识库（清空数据并重建）"""
    from app.services.rag import reset_knowledge_base

    try:
        await reset_knowledge_base()
        return {"message": "知识库已重置"}
    except Exception as e:
        logger.exception("RAG reset failed")
        raise HTTPException(status_code=500, detail=f"重置失败: {e}")
