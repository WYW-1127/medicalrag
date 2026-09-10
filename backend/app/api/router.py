from fastapi import APIRouter

from app.api.routes import auth, health

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)


@api_router.get("/")
async def root() -> dict[str, str]:
    return {"app": "MedicalRAG", "version": "0.1.0"}
