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
    AutoOptimizeRequest,
    AutoOptimizeResponse,
    RAGIndexRequest,
    RAGIndexResponse,
    RAGQueryRequest,
    RAGQueryResponse,
    RAGStatsResponse,
)
from app.services.cehui.adapter import CehuiAdapter
from app.services.cehui.throttle import (
    acquire_optimize_slot,
    release_optimize_slot,
)
from app.services.agent.session_manager import get_session_manager
from app.services.rag import get_knowledge_base, reset_knowledge_base
from app.services.rag.knowledge_base import KnowledgeBase

router = APIRouter(prefix="/rag", tags=["RAG Knowledge Base"])

logger = logging.getLogger(__name__)


def _to_query_response(result) -> RAGQueryResponse:
    """将 KnowledgeBase 的 RAGQueryResult 转为对外 Schema"""
    token_usage = None
    if getattr(result, "token_usage", None):
        token_usage = result.token_usage
    cehui = getattr(result, "_cehui", None)
    return RAGQueryResponse(
        answer=result.answer,
        sources=result.sources,
        confidence=result.confidence,
        retrieval_count=result.retrieval_count,
        model=result.model,
        token_usage=token_usage,
        query_id=result.query_id,
        cehui=cehui,
    )


async def _get_kb() -> KnowledgeBase:
    """获取已初始化的知识库单例"""
    return await get_knowledge_base()


# ---------------------------------------------------------------------------
# SSE 流式支持
# ---------------------------------------------------------------------------

# KnowledgeBase.query_stream 用于分隔来源信息的哨兵标记
_SOURCES_SENTINEL = "<<SOURCES>>"
_CEHUI_SENTINEL = "<<CEHUI>>"


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
    - {"cehui": {...}}          测绘数据（测绘模式下发送）
    - {"error": "错误信息"}         错误
    - [DONE]                        终止标记
    """
    query_id = str(uuid.uuid4())[:8]
    full_answer = ""
    try:
        # 先下发 query_id，便于前端埋点/关联
        yield _sse({"query_id": query_id})

        if payload.skip_retrieval:
            # 跳过检索：直接流式调用大模型
            stream = kb.direct_chat_stream(
                question=payload.question,
                temperature=payload.temperature,
                max_tokens=payload.max_tokens,
                fast=payload.fast_mode,
                cehui=payload.cehui_mode,
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
            if chunk.startswith(_CEHUI_SENTINEL):
                raw = chunk[len(_CEHUI_SENTINEL):]
                try:
                    cehui = json.loads(raw) if raw else {}
                except (ValueError, TypeError):
                    cehui = {}
                yield _sse({"cehui": cehui})
                continue
            yield _sse({"content": chunk})
            # 让出事件循环，确保分块及时刷出而非被缓冲成整包
            await asyncio.sleep(0)
            full_answer += chunk

    except asyncio.CancelledError:
        # 客户端主动断开，静默结束，不记为错误
        raise
    except Exception as e:  # noqa: BLE001
        logger.exception("[/rag/query][stream] 流式问答失败")
        yield _sse({"error": f"AI 服务暂时不可用：{e}"})
    finally:
        yield "data: [DONE]\n\n"

    # 流式结束后，把本轮问答存入会话历史（支撑画像提炼 / 建议10）
    # 失败仅记录日志，绝不阻断响应
    if payload.session_id and full_answer:
        try:
            mgr = get_session_manager()
            await mgr.append_message(
                payload.session_id,
                {"role": "user", "content": payload.question},
                user_id=str(current_user.id) if current_user else None,
            )
            await mgr.append_message(
                payload.session_id,
                {"role": "assistant", "content": full_answer},
                user_id=str(current_user.id) if current_user else None,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("[/rag/query] 会话历史保存失败(session=%s): %s", payload.session_id, e)


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
                fast=payload.fast_mode,
                cehui=payload.cehui_mode,
            )
        else:
            result = await kb.query(
                question=payload.question,
                top_k=payload.top_k,
                temperature=payload.temperature,
                max_tokens=payload.max_tokens,
            )
        # 非流式分支：把问答存入会话历史（支撑画像提炼 / 建议10）
        if payload.session_id:
            try:
                mgr = get_session_manager()
                await mgr.append_message(
                    payload.session_id,
                    {"role": "user", "content": payload.question},
                    user_id=str(current_user.id) if current_user else None,
                )
                await mgr.append_message(
                    payload.session_id,
                    {"role": "assistant", "content": result.answer},
                    user_id=str(current_user.id) if current_user else None,
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("[/rag/query] 会话历史保存失败(session=%s): %s", payload.session_id, e)
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


@router.post("/auto-optimize", response_model=ResponseBase[AutoOptimizeResponse])
async def rag_auto_optimize(
    payload: AutoOptimizeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ResponseBase[AutoOptimizeResponse] | dict:
    """对话测绘 → AOO 自动路径优化
    
    当 LLM 在对话中检测到薄弱知识点时，前端调用此端点触发 AOO 优化。
    适配器会将 LLM 推测与历史答题测绘数据置信度加权融合，生成 AOO 标准输入，
    并复用现有 Celery 异步优化流水线。
    
    边界: 严格恪守"LLM 只做认知感知 → AOO 专注数学寻优"的松耦合原则
    """
    adapter = CehuiAdapter(user_id=current_user.id, db=db)

    chat_cehui = {
        "mastery_estimates": payload.mastery_estimates,
        "cognitive_load": payload.cognitive_load,
        "learning_intent": payload.learning_intent,
        "needs_optimization": payload.needs_optimization,
    }

    aoo_params = await adapter.build_aoo_params(chat_cehui)

    # 可观测性: 记录被丢弃的未对齐知识点，便于后续排查 LLM 输出质量
    unresolved = aoo_params.get("unresolved_names") or []
    if unresolved:
        logger.warning(
            "[auto-optimize] %d 个知识点信号未对齐已丢弃 | user=%s | names=%s",
            len(unresolved), current_user.id, unresolved,
        )

    if not aoo_params["can_optimize"]:
        if aoo_params.get("resolved_count", 0) == 0 and unresolved:
            msg = (
                "本轮对话提到的知识点暂未收录到知识图谱中，"
                "无法据此优化学习路径。"
            )
        else:
            msg = (
                f"当前检测到 {aoo_params['weak_count']} 个薄弱知识点，"
                "未达到自动优化阈值。完成测绘答题后可获得更精准的路径推荐。"
            )
        return ResponseBase[AutoOptimizeResponse](
            data=AutoOptimizeResponse(triggered=False, message=msg)
        )

    # 获取测绘记录 ID（优先用历史测绘记录）
    diagnosis_id = aoo_params.get("diagnosis_id")

    if not diagnosis_id:
        # 没有历史测绘记录: 无法直接调用 AOO（AOO 需要 diagnosis_id）
        return ResponseBase[AutoOptimizeResponse](
            data=AutoOptimizeResponse(
                triggered=False,
                message=(
                    "检测到薄弱知识点，但尚未完成正式测绘答题。"
                    "请在学情测绘页面完成答题后，系统将自动生成最优学习路径。"
                ),
            )
        )

    # 节流: 冷却窗口内不重复触发，避免连续追问并发多个 AOO 任务互相覆盖
    acquired, retry_after = await acquire_optimize_slot(str(current_user.id))
    if not acquired:
        logger.info(
            "[auto-optimize] 命中冷却窗口，跳过本次触发 | user=%s | retry_after=%ss",
            current_user.id, retry_after,
        )
        minutes = max(1, round(retry_after / 60))
        return ResponseBase[AutoOptimizeResponse](
            data=AutoOptimizeResponse(
                triggered=False,
                message=(
                    f"学习路径刚刚已根据对话优化过，约 {minutes} 分钟后可再次优化。"
                    "本轮对话的测绘结果已记录。"
                ),
            )
        )

    # P3: CHAT_PROFILE_ENABLED 总开关 — 关闭时即使前端请求也不触发 AOO 重规划，
    # 但 adapter 在 build_aoo_params 中已 best-effort 落库聊天信号（受 λ 控制），
    # 数据真实性不受损，仅停止"自动改路径"这一动作。
    from app.core.config import settings as _settings
    profile_enabled = bool(getattr(_settings, "CHAT_PROFILE_ENABLED", True))
    if not profile_enabled:
        logger.info(
            "[auto-optimize] CHAT_PROFILE_ENABLED=False, 关闭自动重规划总开关 | user=%s",
            current_user.id,
        )
        return ResponseBase[AutoOptimizeResponse](
            data=AutoOptimizeResponse(
                triggered=False,
                message=(
                    "学习路径自动优化功能已全局关闭。"
                    "本轮对话的测绘结果已记录，但不会自动调整路径。"
                ),
            )
        )

    # 触发 AOO 异步优化（复用现有 AOO 接口逻辑）
    try:
        from app.tasks.aoo_optimization import run_aoo_optimization

        # 组装 AOO 参数
        mastery_dict = aoo_params.get("mastery_levels", {})
        load_value = aoo_params.get("cognitive_load", 0.5)

        # 启动 Celery 异步任务
        task = run_aoo_optimization.delay(
            diagnosis_id=str(diagnosis_id),
            student_id=str(current_user.id),
            mastery_levels=mastery_dict,
            cognitive_load=float(load_value),
            auto_adopt=bool(payload.auto_adopt),
        )

        logger.info(
            "[auto-optimize] AOO 优化已入队 | user=%s | cehui=%s | task=%s",
            current_user.id, diagnosis_id, task.id,
        )

        return ResponseBase[AutoOptimizeResponse](
            data=AutoOptimizeResponse(
                triggered=True,
                message="检测到薄弱知识点，已自动生成学习路径优化方案。",
                aoo_task_id=task.id,
            )
        )
    except Exception as e:
        # 投递失败 → 释放冷却名额，避免白白占用窗口
        await release_optimize_slot(str(current_user.id))
        logger.error("[auto-optimize] AOO 优化触发失败: %s", e, exc_info=True)
        return ResponseBase[AutoOptimizeResponse](
            data=AutoOptimizeResponse(
                triggered=False,
                message="学习路径优化暂时无法启动，请稍后重试。",
            )
        )


# ============================================================
# GET /chat-profile — 读取该生「仅来自导学终端」的对话画像
# ============================================================


@router.get(
    "/chat-profile",
    response_model=ResponseBase[dict],
    summary="获取导学终端对话画像",
    description=(
        "返回该生通过导学终端对话梳理出的知识点掌握特点 (绝对掌握度视图)。\n"
        "与「学情测绘」的客观答题掌握度严格分离，仅用于展示与「测绘+对话」重规划融合。"
    ),
)
async def get_chat_profile(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """读取对话画像 — 前端导学终端页「对话画像」抽屉的数据源"""
    try:
        adapter = CehuiAdapter(db=session, user_id=current_user.id)
        profile = await adapter.get_chat_profile()
        return ResponseBase(message="ok", data=profile)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[chat-profile] 读取失败: %s", exc)
        return ResponseBase(
            message="读取对话画像失败",
            data={
                "exists": False,
                "chat_signal_count": 0,
                "last_chat_at": None,
                "updated_at": None,
                "items": [],
            },
        )
