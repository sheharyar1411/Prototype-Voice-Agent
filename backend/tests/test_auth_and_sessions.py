"""
Tests for Authentication and Voice Call Sessions API endpoints.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_auth_login_success(client: AsyncClient):
    """POST /api/auth/login with valid admin credentials returns session token."""
    response = await client.post(
        "/api/auth/login",
        json={"username": "admin@gerta.ai", "password": "admin123gertai"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["error"] is None
    assert "token" in data["data"]
    assert data["data"]["user"]["email"] == "admin@gerta.ai"
    assert data["data"]["user"]["role"] == "Super Admin"


@pytest.mark.asyncio
async def test_auth_login_invalid_credentials(client: AsyncClient):
    """POST /api/auth/login with invalid password returns 401 envelope."""
    response = await client.post(
        "/api/auth/login",
        json={"username": "admin@gerta.ai", "password": "wrongpassword"},
    )
    assert response.status_code == 401
    data = response.json()
    assert data["data"] is None
    assert data["error"]["code"] == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_auth_me_authenticated(client: AsyncClient):
    """GET /api/auth/me with Bearer token returns admin profile."""
    # First login to obtain token
    login_res = await client.post(
        "/api/auth/login",
        json={"username": "admin@gerta.ai", "password": "admin123gertai"},
    )
    token = login_res.json()["data"]["token"]

    response = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["email"] == "admin@gerta.ai"


@pytest.mark.asyncio
async def test_auth_me_unauthorized(client: AsyncClient):
    """GET /api/auth/me without token returns 401."""
    response = await client.get("/api/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_auth_logout(client: AsyncClient):
    """POST /api/auth/logout returns success message."""
    response = await client.post("/api/auth/logout")
    assert response.status_code == 200
    assert response.json()["error"] is None


@pytest.mark.asyncio
async def test_list_call_sessions_empty(client: AsyncClient):
    """GET /api/voice/sessions returns empty list if no sessions recorded."""
    response = await client.get("/api/voice/sessions")
    assert response.status_code == 200
    data = response.json()
    assert data["error"] is None
    assert isinstance(data["data"], list)


@pytest.mark.asyncio
async def test_list_call_sessions_alias(client: AsyncClient):
    """GET /sessions top-level alias returns identical envelope."""
    response = await client.get("/sessions")
    assert response.status_code == 200
    assert response.json()["error"] is None
    assert isinstance(response.json()["data"], list)


@pytest.mark.asyncio
async def test_call_session_lifecycle_and_retrieval(client: AsyncClient):
    """Simulate call completion and verify retrieval via /api/voice/sessions."""
    # Send end-of-call report to trigger CallSession creation
    end_call_payload = {
        "message": {
            "type": "end-of-call-report",
            "call": {
                "id": "vapi-call-test-99",
                "customer": {"number": "5125559988"},
            },
            "transcript": "Sarah: Hello, how can I help?\nCaller: I need to register.",
        }
    }
    webhook_res = await client.post("/api/voice/webhook", json=end_call_payload)
    assert webhook_res.status_code == 200

    # Query sessions
    sessions_res = await client.get("/api/voice/sessions")
    assert sessions_res.status_code == 200
    sessions = sessions_res.json()["data"]
    assert len(sessions) >= 1

    session = next((s for s in sessions if s.get("vapi_call_id") == "vapi-call-test-99"), None)
    assert session is not None
    assert session["caller_phone"] == "5125559988"
    assert "Sarah: Hello" in session["transcript"]
    assert session["status"] == "completed"

    # Query specific session by id
    detail_res = await client.get(f"/api/voice/sessions/{session['id']}")
    assert detail_res.status_code == 200
    assert detail_res.json()["data"]["id"] == session["id"]
