from __future__ import annotations

from fastapi.testclient import TestClient

from anti_bagu.api.app import create_app
from anti_bagu.config import Settings


def cloud_settings(tmp_path) -> Settings:
    return Settings(
        deepseek_api_key=None,
        dashscope_api_key=None,
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        storage_dir=tmp_path / "storage",
        audit_log_dir=tmp_path / "logs",
        admin_username="admin",
        admin_password="correct-horse-battery",
    )


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_activation_registration_login_and_task_lifecycle(tmp_path) -> None:
    app = create_app(cloud_settings(tmp_path))
    with TestClient(app) as client:
        admin_login = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "correct-horse-battery"},
        )
        assert admin_login.status_code == 200
        admin_token = admin_login.json()["token"]

        created_key = client.post(
            "/api/v1/admin/activation-keys",
            headers=bearer(admin_token),
            json={"valid_days": 7},
        )
        assert created_key.status_code == 200
        activation_key = created_key.json()["display_key"]
        assert activation_key.startswith("AB-")

        registration = client.post(
            "/api/v1/auth/register",
            json={
                "activation_key": activation_key,
                "username": "candidate.one",
                "password": "strong-password",
            },
        )
        assert registration.status_code == 201

        reused = client.post(
            "/api/v1/auth/register",
            json={
                "activation_key": activation_key,
                "username": "candidate.two",
                "password": "strong-password",
            },
        )
        assert reused.status_code == 400

        login = client.post(
            "/api/v1/auth/login",
            json={"username": "candidate.one", "password": "strong-password"},
        )
        assert login.status_code == 200
        token = login.json()["token"]

        created_task = client.post(
            "/api/v1/tasks",
            headers=bearer(token),
            json={
                "name": "后端开发一面",
                "mode": "interview",
                "mobile_required": False,
            },
        )
        assert created_task.status_code == 201
        assert created_task.json()["status"] == "draft"
        task_id = created_task.json()["id"]

        tasks = client.get("/api/v1/tasks", headers=bearer(token))
        assert tasks.status_code == 200
        assert [item["id"] for item in tasks.json()] == [task_id]

        preflight = client.post(
            f"/api/v1/tasks/{task_id}/preflight", headers=bearer(token)
        )
        assert preflight.status_code == 200
        assert preflight.json()["ready"] is False
        assert preflight.json()["checks"][0]["key"] == "agent"
        assert preflight.json()["task"]["status"] == "check_failed"


def test_user_cannot_access_admin_api(tmp_path) -> None:
    app = create_app(cloud_settings(tmp_path))
    with TestClient(app) as client:
        admin = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "correct-horse-battery"},
        ).json()
        key = client.post(
            "/api/v1/admin/activation-keys",
            headers=bearer(admin["token"]),
            json={},
        ).json()["display_key"]
        client.post(
            "/api/v1/auth/register",
            json={
                "activation_key": key,
                "username": "normal.user",
                "password": "strong-password",
            },
        )
        user = client.post(
            "/api/v1/auth/login",
            json={"username": "normal.user", "password": "strong-password"},
        ).json()
        response = client.get(
            "/api/v1/admin/overview", headers=bearer(user["token"])
        )
        assert response.status_code == 403
