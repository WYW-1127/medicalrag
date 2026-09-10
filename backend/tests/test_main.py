async def test_root_returns_app_info(client):
    resp = await client.get("/api/v1/")
    assert resp.status_code == 200
    assert resp.json() == {"app": "MedicalRAG", "version": "0.1.0"}


async def test_openapi_docs_available(client):
    resp = await client.get("/docs")
    assert resp.status_code == 200
