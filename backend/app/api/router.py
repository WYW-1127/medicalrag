from fastapi import APIRouter

api_router = APIRouter()


@api_router.get("/")
async def root() -> dict[str, str]:
    return {"app": "MedicalRAG", "version": "0.1.0"}
