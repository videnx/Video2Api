import pytest
from fastapi.testclient import TestClient

from app.core.auth import get_current_active_user
from app.main import app
from app.services.sora_nurture_service import SoraNurtureServiceError, sora_nurture_service

pytestmark = pytest.mark.unit


def _mock_batch(batch_id: int, status: str = "queued", failed_count: int = 0) -> dict:
    return {
        "batch_id": int(batch_id),
        "name": f"batch-{batch_id}",
        "group_title": "Sora",
        "profile_ids": [1, 2],
        "total_jobs": 2,
        "scroll_count": 10,
        "like_probability": 0.25,
        "follow_probability": 0.15,
        "max_follows_per_profile": 100,
        "max_likes_per_profile": 100,
        "status": status,
        "success_count": 1,
        "failed_count": int(failed_count),
        "canceled_count": 0,
        "like_total": 2,
        "follow_total": 1,
        "error": None,
        "operator_username": "Admin",
        "started_at": "2026-02-09 12:00:00",
        "finished_at": None,
        "created_at": "2026-02-09 12:00:00",
        "updated_at": "2026-02-09 12:00:00",
    }


@pytest.fixture()
def client():
    app.dependency_overrides[get_current_active_user] = lambda: {"id": 1, "username": "Admin"}
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.clear()


def test_retry_nurture_batch_success(monkeypatch, client):
    async def _fake_retry(batch_id: int):
        return _mock_batch(batch_id=batch_id, status="queued", failed_count=0)

    monkeypatch.setattr(sora_nurture_service, "retry_batch_failed_jobs", _fake_retry)
    resp = client.post("/api/v1/nurture/batches/7/retry")
    assert resp.status_code == 200
    data = resp.json()
    assert int(data["batch_id"]) == 7
    assert data["status"] == "queued"


def test_retry_nurture_batch_running_returns_400(monkeypatch, client):
    async def _fake_retry(_batch_id: int):
        raise SoraNurtureServiceError("任务组正在执行，无法重试")

    monkeypatch.setattr(sora_nurture_service, "retry_batch_failed_jobs", _fake_retry)
    resp = client.post("/api/v1/nurture/batches/9/retry")
    assert resp.status_code == 400
    data = resp.json()
    assert data["error"]["type"] == "nurture_service_error"
    assert "无法重试" in data["detail"]
