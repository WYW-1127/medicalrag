async def test_trace_id_header_present(client):
    resp = await client.get("/api/v1/")
    assert resp.status_code == 200
    assert "x-trace-id" in resp.headers
    assert len(resp.headers["x-trace-id"]) == 12


async def test_trace_id_unique_per_request(client):
    r1 = await client.get("/api/v1/")
    r2 = await client.get("/api/v1/")
    assert r1.headers["x-trace-id"] != r2.headers["x-trace-id"]
