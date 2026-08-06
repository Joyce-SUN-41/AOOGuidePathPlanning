from fastapi import APIRouter

from app.api.v1 import (
    agent,
    analytics,
    aoo,
    auth,
    chat,
    dashboard,
    cehui,
    health,
    knowledge,
    learning_paths,
    questions,
    rag,
    teacher,
    users,
)

router = APIRouter(prefix="/api/v1")

router.include_router(health.router, tags=["Health"])
router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
router.include_router(users.router, prefix="/users", tags=["Users"])
router.include_router(cehui.router, prefix="/cehui", tags=["Cehui"])
router.include_router(knowledge.router, prefix="/knowledge-points", tags=["Knowledge Points"])
router.include_router(questions.router, prefix="/questions", tags=["Question Bank"])
router.include_router(aoo.router, tags=["AOO Optimization"])
router.include_router(rag.router, tags=["RAG Knowledge Base"])
router.include_router(agent.router, tags=["Agent"])
router.include_router(chat.router, tags=["Chat"])
router.include_router(teacher.router, prefix="/teacher", tags=["Teacher"])
router.include_router(learning_paths.router, prefix="/learning-paths", tags=["Learning Paths"])
router.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
router.include_router(analytics.router, tags=["Analytics"])
