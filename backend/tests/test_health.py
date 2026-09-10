from httpx import AsyncClient

from app.api.routes import health as health_module


async def _ok() -> bool:
    return True


async def test_health_all_up(client: AsyncClient, monkeypatch) -> None:
    monkeypatch.setattr(health_module, "check_mysql", _ok)
    monkeypatch.setattr(health_module, "check_redis", _ok)
    monkeypatch.setattr(health_module, "check_milvus", lambda: True)
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json() == {
        "status": "ok",
        "checks": {"mysql": "ok", "redis": "ok", "milvus": "ok"},
    }


async def test_health_degraded_when_one_down(client: AsyncClient, monkeypatch) -> None:
    async def _fail() -> bool:
        return False

    monkeypatch.setattr(health_module, "check_mysql", _ok)
    monkeypatch.setattr(health_module, "check_redis", _fail)
    monkeypatch.setattr(health_module, "check_milvus", lambda: True)
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "degraded"
    assert resp.json()["checks"]["redis"] == "unreachable"
