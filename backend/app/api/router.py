from fastapi import APIRouter

from app.api.routes import admin, auth, chat, conversations, documents, health

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(chat.router)
api_router.include_router(conversations.router)
api_router.include_router(documents.router)
api_router.include_router(admin.router)


@api_router.get("/")
async def root() -> dict[str, str]:
    return {"app": "MedicalRAG", "version": "0.1.0"}
