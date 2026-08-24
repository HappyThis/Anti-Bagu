from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import select

from anti_bagu.api.app import create_app
from anti_bagu.config import Settings
from anti_bagu.credentials.service import ModelCredentials
from anti_bagu.interview.events import RealtimeEvent
from anti_bagu.persistence.models import Task, TaskEvent, User, UserModelCredentials
from anti_bagu.tasks.model_verifier import VerificationResult


def cloud_settings(tmp_path) -> Settings:
    return Settings(
        deepseek_api_key=None,
        dashscope_api_key=None,
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        storage_dir=tmp_path / "storage",
        credential_key_path=tmp_path / "credential-encryption.key",
        audit_log_dir=tmp_path / "logs",
        admin_username="admin",
        admin_password="correct-horse-battery",
    )


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def resolve_agent_user(app, token: str):
    return await app.state.auth_service.resolve(token, kind="agent")


async def encrypted_credentials_payload(app, user_id: str) -> str:
    async with app.state.session_factory() as session:
        record = await session.get(UserModelCredentials, user_id)
        assert record is not None
        return record.encrypted_payload


async def issue_agent_token(app, username: str) -> str:
    async with app.state.session_factory() as session:
        user = await session.scalar(select(User).where(User.username == username))
        assert user is not None
    issued = await app.state.auth_service.issue_for_user(user, kind="agent")
    return issued.token


async def mark_task_running(app, task_id: str) -> None:
    async with app.state.session_factory() as session:
        task = await session.get(Task, task_id)
        assert task is not None
        task.status = "running"
        await session.commit()


async def publish_task_latency(app, task_id: str) -> None:
    runtime = await app.state.runtime_registry.get(task_id)
    for payload in (
        {"asr": 100.0},
        {"asr": 300.0, "model": 400.0, "endToEnd": 900.0},
        {"model": 600.0, "endToEnd": 1_100.0},
    ):
        await runtime.event_hub.publish(
            RealtimeEvent(
                type="latency.updated",
                session_id=task_id,
                conversation_revision=0,
                payload=payload,
            )
        )


async def seed_answer_cards(app, task_id: str, count: int) -> None:
    async with app.state.session_factory() as session:
        for index in range(1, count + 1):
            focus_id = f"focus-{index}"
            session.add(
                TaskEvent(
                    task_id=task_id,
                    event_id=f"focus-event-{index}",
                    event_type="focus.updated",
                    conversation_revision=index,
                    payload={
                        "focus_id": focus_id,
                        "question": f"问题 {index}",
                        "source": "VOICE",
                    },
                )
            )
            session.add(
                TaskEvent(
                    task_id=task_id,
                    event_id=f"answer-event-{index}",
                    event_type="answer.completed",
                    conversation_revision=index,
                    payload={
                        "focus_id": focus_id,
                        "question": f"问题 {index}",
                        "answer": f"回答 {index}",
                        "code": "",
                        "source": "VOICE",
                    },
                )
            )
        await session.commit()


async def seed_runtime_checkpoint(app, task_id: str) -> None:
    async with app.state.session_factory() as session:
        session.add_all(
            [
                TaskEvent(
                    task_id=task_id,
                    event_id="runtime-turn",
                    event_type="transcript.committed",
                    conversation_revision=1,
                    payload={
                        "turn_id": 1,
                        "channel": "interviewer",
                        "text": "Redis 为什么快？",
                        "source_event_id": "source-turn",
                    },
                ),
                TaskEvent(
                    task_id=task_id,
                    event_id="runtime-focus",
                    event_type="focus.updated",
                    conversation_revision=1,
                    payload={
                        "focus_id": "restored-focus",
                        "question": "Redis 为什么快？",
                        "source": "VOICE",
                        "source_start_turn_id": 1,
                        "source_end_turn_id": 1,
                    },
                ),
                TaskEvent(
                    task_id=task_id,
                    event_id="runtime-answer",
                    event_type="answer.completed",
                    conversation_revision=1,
                    payload={
                        "focus_id": "restored-focus",
                        "question": "Redis 为什么快？",
                        "answer": "因为内存和 I/O 多路复用。",
                        "code": "",
                        "source": "VOICE",
                    },
                ),
            ]
        )
        await session.commit()


async def seed_completed_review_metrics(
    app, task_id: str, summarized: bool
) -> None:
    async with app.state.session_factory() as session:
        task = await session.get(Task, task_id)
        assert task is not None
        now = datetime.now(UTC)
        task.status = "completed"
        task.started_at = now - timedelta(minutes=5)
        task.ended_at = now
        session.add(
            TaskEvent(
                task_id=task_id,
                event_id=f"review-focus-{task_id}",
                event_type="focus.updated",
                conversation_revision=1,
                payload={
                    "focus_id": f"focus-{task_id}",
                    "question": "Redis 为什么快？",
                },
            )
        )
        if summarized:
            session.add(
                TaskEvent(
                    task_id=task_id,
                    event_id=f"review-metrics-{task_id}",
                    event_type="task.metrics",
                    conversation_revision=1,
                    payload={
                        "end_to_end_avg_ms": 1_234.5,
                        "end_to_end_sample_count": 4,
                    },
                )
            )
        else:
            session.add_all(
                [
                    TaskEvent(
                        task_id=task_id,
                        event_id=f"legacy-latency-a-{task_id}",
                        event_type="latency.updated",
                        conversation_revision=1,
                        payload={"endToEnd": 1_000},
                    ),
                    TaskEvent(
                        task_id=task_id,
                        event_id=f"legacy-latency-b-{task_id}",
                        event_type="latency.updated",
                        conversation_revision=1,
                        payload={"endToEnd": 2_000},
                    ),
                ]
            )
        await session.commit()


async def runtime_summary(app, task_id: str) -> tuple[int, str, int]:
    runtime = await app.state.runtime_registry.get(task_id)
    return (
        len(runtime.coordinator.store.turns),
        runtime.coordinator.store.current_focus,
        runtime.coordinator.last_analyzed_turn_id,
    )


class SuccessfulModelVerifier:
    async def verify_asr(self, _: str) -> VerificationResult:
        return VerificationResult(True, "语音识别连接正常", 120.0)

    async def verify_llm(self, _: str) -> VerificationResult:
        return VerificationResult(True, "回答服务连接正常", 180.0)


def test_agent_screenshot_is_accepted_and_saved_for_running_task(tmp_path) -> None:
    app = create_app(cloud_settings(tmp_path))
    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "correct-horse-battery"},
        ).json()
        task = client.post(
            "/api/v1/tasks",
            headers=bearer(login["token"]),
            json={"name": "截图测试", "mobile_required": False},
        ).json()
        assert client.portal is not None
        client.portal.call(mark_task_running, app, task["id"])
        agent_token = client.portal.call(issue_agent_token, app, "admin")

        with client.websocket_connect(
            "/ws/agent",
            headers={"Authorization": f"Bearer {agent_token}"},
        ) as socket:
            socket.send_json(
                {
                    "type": "agent.hello",
                    "device": {"device_key": "screenshot-test"},
                }
            )
            assert socket.receive_json()["type"] == "agent.ready"
            socket.send_json(
                {
                    "type": "screenshot.submit",
                    "request_id": "request-1",
                    "task_id": task["id"],
                    "mime_type": "image/jpeg",
                    "image_base64": base64.b64encode(b"fake-jpeg").decode("ascii"),
                }
            )
            response = socket.receive_json()

        assert response["type"] == "screenshot.result"
        assert response["status"] == "accepted"
        screenshots = list(
            (tmp_path / "storage" / "tasks" / task["id"] / "screenshots").glob(
                "*.jpg"
            )
        )
        assert len(screenshots) == 1
        assert screenshots[0].read_bytes() == b"fake-jpeg"


def test_task_ui_websocket_uses_http_only_login_cookie(tmp_path) -> None:
    app = create_app(cloud_settings(tmp_path))
    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "correct-horse-battery"},
        )
        assert login.status_code == 200
        task = client.post(
            "/api/v1/tasks",
            json={"name": "Cookie WebSocket", "mobile_required": False},
        ).json()

        with client.websocket_connect(f"/ws/tasks/{task['id']}/ui") as socket:
            status_event = socket.receive_json()

        assert status_event["type"] == "session.status"
        assert status_event["payload"]["status"] == "draft"


def test_task_ui_snapshot_restores_more_than_fifty_answer_cards(tmp_path) -> None:
    app = create_app(cloud_settings(tmp_path))
    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "correct-horse-battery"},
        ).json()
        task = client.post(
            "/api/v1/tasks",
            headers=bearer(login["token"]),
            json={"name": "Snapshot", "mobile_required": False},
        ).json()
        assert client.portal is not None
        client.portal.call(seed_answer_cards, app, task["id"], 106)

        with client.websocket_connect(f"/ws/tasks/{task['id']}/ui") as socket:
            assert socket.receive_json()["type"] == "session.status"
            snapshot = socket.receive_json()

        assert snapshot["type"] == "answer.snapshot"
        assert snapshot["payload"]["total_count"] == 106
        assert len(snapshot["payload"]["cards"]) == 106
        assert snapshot["payload"]["cards"][0]["question"] == "问题 1"
        assert snapshot["payload"]["cards"][-1]["question"] == "问题 106"


def test_reviews_use_task_metric_summary_with_legacy_latency_fallback(tmp_path) -> None:
    app = create_app(cloud_settings(tmp_path))
    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "correct-horse-battery"},
        ).json()
        summarized_task = client.post(
            "/api/v1/tasks",
            headers=bearer(login["token"]),
            json={"name": "Summary", "mobile_required": False},
        ).json()
        legacy_task = client.post(
            "/api/v1/tasks",
            headers=bearer(login["token"]),
            json={"name": "Legacy", "mobile_required": False},
        ).json()
        assert client.portal is not None
        client.portal.call(
            seed_completed_review_metrics,
            app,
            summarized_task["id"],
            True,
        )
        client.portal.call(
            seed_completed_review_metrics,
            app,
            legacy_task["id"],
            False,
        )

        response = client.get("/api/v1/reviews", headers=bearer(login["token"]))

        assert response.status_code == 200
        reviews = {item["task_id"]: item for item in response.json()}
        assert reviews[summarized_task["id"]]["question_count"] == 1
        assert reviews[summarized_task["id"]]["avg_latency_ms"] == 1_234.5
        assert reviews[legacy_task["id"]]["avg_latency_ms"] == 1_500


def test_task_end_persists_one_latency_summary(tmp_path) -> None:
    app = create_app(cloud_settings(tmp_path))
    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "correct-horse-battery"},
        ).json()
        task = client.post(
            "/api/v1/tasks",
            headers=bearer(login["token"]),
            json={"name": "Metrics", "mobile_required": False},
        ).json()
        assert client.portal is not None
        client.portal.call(publish_task_latency, app, task["id"])

        ended = client.post(
            f"/api/v1/tasks/{task['id']}/end",
            headers=bearer(login["token"]),
        )
        events = client.get(
            f"/api/v1/tasks/{task['id']}/events?types=task.metrics",
            headers=bearer(login["token"]),
        ).json()

        assert ended.status_code == 200
        assert len(events) == 1
        assert events[0]["payload"] == {
            "asr_sample_count": 2,
            "asr_avg_ms": 200.0,
            "model_sample_count": 2,
            "model_avg_ms": 500.0,
            "end_to_end_sample_count": 2,
            "end_to_end_avg_ms": 1_000.0,
        }


def test_mobile_pairing_survives_server_restart_and_restores_snapshot(tmp_path) -> None:
    settings = cloud_settings(tmp_path)
    first_app = create_app(settings)
    with TestClient(first_app) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "correct-horse-battery"},
        ).json()
        task = client.post(
            "/api/v1/tasks",
            headers=bearer(login["token"]),
            json={"name": "Mobile restart", "mobile_required": False},
        ).json()
        assert client.portal is not None
        client.portal.call(seed_answer_cards, first_app, task["id"], 51)
        pairing = client.post(
            f"/api/v1/tasks/{task['id']}/pairing",
            headers=bearer(login["token"]),
        ).json()

    second_app = create_app(settings)
    with TestClient(second_app) as client:
        with client.websocket_connect(f"/ws/mobile/{pairing['token']}") as socket:
            paired = socket.receive_json()
            snapshot = socket.receive_json()

        assert paired["type"] == "mobile.paired"
        assert snapshot["type"] == "answer.snapshot"
        assert snapshot["payload"]["total_count"] == 51
        assert snapshot["payload"]["cards"][-1]["question"] == "问题 51"


def test_task_runtime_restores_focus_and_watermark_after_server_restart(tmp_path) -> None:
    settings = cloud_settings(tmp_path)
    first_app = create_app(settings)
    with TestClient(first_app) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "correct-horse-battery"},
        ).json()
        task = client.post(
            "/api/v1/tasks",
            headers=bearer(login["token"]),
            json={"name": "Runtime restore", "mobile_required": False},
        ).json()
        assert client.portal is not None
        client.portal.call(seed_runtime_checkpoint, first_app, task["id"])

    second_app = create_app(settings)
    with TestClient(second_app) as client:
        assert client.portal is not None
        restored = client.portal.call(runtime_summary, second_app, task["id"])

    assert restored == (1, "Redis 为什么快？", 1)


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

        audio_test = client.post(
            f"/api/v1/tasks/{task_id}/audio-test/start", headers=bearer(token)
        )
        assert audio_test.status_code == 409

        deleted = client.delete(f"/api/v1/tasks/{task_id}", headers=bearer(token))
        assert deleted.status_code == 200
        assert deleted.json()["deleted_at"] is not None
        assert client.get("/api/v1/tasks", headers=bearer(token)).json() == []
        assert client.get(
            f"/api/v1/tasks/{task_id}/events", headers=bearer(token)
        ).status_code == 404

        admin_tasks = client.get(
            "/api/v1/admin/tasks", headers=bearer(admin_token)
        ).json()
        assert admin_tasks[0]["deleted_at"] is not None
        full_record = client.get(
            f"/api/v1/admin/tasks/{task_id}/record", headers=bearer(admin_token)
        )
        assert full_record.status_code == 200
        assert full_record.json()["task"]["deleted_at"] is not None
        assert len(full_record.json()["events"]) >= 1
        restored = client.post(
            f"/api/v1/admin/tasks/{task_id}/restore", headers=bearer(admin_token)
        )
        assert restored.status_code == 200
        assert [item["id"] for item in client.get(
            "/api/v1/tasks", headers=bearer(token)
        ).json()] == [task_id]


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


def test_web_login_cookie_restores_session_and_logout_clears_it(tmp_path) -> None:
    app = create_app(cloud_settings(tmp_path))
    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "correct-horse-battery"},
        )
        assert login.status_code == 200
        assert "HttpOnly" in login.headers["set-cookie"]
        assert "SameSite=lax" in login.headers["set-cookie"]

        restored = client.get("/api/v1/auth/me")
        assert restored.status_code == 200
        assert restored.json()["username"] == "admin"

        logout = client.post("/api/v1/auth/logout")
        assert logout.status_code == 204
        assert client.get("/api/v1/auth/me").status_code == 401


def test_browser_authorization_issues_single_use_agent_login(tmp_path) -> None:
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
                "username": "browser.login",
                "password": "strong-password",
            },
        )
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "browser.login", "password": "strong-password"},
        )
        assert login.status_code == 200

        started = client.post("/api/v1/agent/authorizations")
        assert started.status_code == 200
        authorization = started.json()
        request_id = authorization["request_id"]
        secret = authorization["device_secret"]
        code = authorization["user_code"]
        assert f"code={code}" in authorization["verification_url"]

        wrong_secret = client.post(
            f"/api/v1/agent/authorizations/{request_id}/poll",
            json={"device_secret": "x" * 48},
        )
        assert wrong_secret.status_code == 404

        approved = client.post(
            f"/api/v1/agent/authorizations/code/{code}/approve"
        )
        assert approved.status_code == 200
        assert approved.json()["username"] == "browser.login"

        first_poll = client.post(
            f"/api/v1/agent/authorizations/{request_id}/poll",
            json={"device_secret": secret},
        )
        assert first_poll.status_code == 200
        assert first_poll.json()["status"] == "approved"
        assert first_poll.json()["username"] == "browser.login"
        agent_token = first_poll.json()["token"]
        assert agent_token.startswith("aba_")

        second_poll = client.post(
            f"/api/v1/agent/authorizations/{request_id}/poll",
            json={"device_secret": secret},
        )
        assert second_poll.status_code == 200
        assert second_poll.json()["status"] == "consumed"
        assert "token" not in second_poll.json()

        assert client.portal is not None
        agent_user = client.portal.call(resolve_agent_user, app, agent_token)
        assert agent_user is not None
        assert agent_user.username == "browser.login"


def test_browser_authorization_can_be_cancelled(tmp_path) -> None:
    app = create_app(cloud_settings(tmp_path))
    with TestClient(app) as client:
        authorization = client.post("/api/v1/agent/authorizations").json()
        unauthenticated = client.post(
            f"/api/v1/agent/authorizations/code/{authorization['user_code']}/approve"
        )
        assert unauthenticated.status_code == 401

        login = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "correct-horse-battery"},
        )
        assert login.status_code == 200

        cancelled = client.post(
            f"/api/v1/agent/authorizations/code/{authorization['user_code']}/cancel"
        )
        assert cancelled.status_code == 200
        polled = client.post(
            f"/api/v1/agent/authorizations/{authorization['request_id']}/poll",
            json={"device_secret": authorization["device_secret"]},
        )
        assert polled.status_code == 200
        assert polled.json()["status"] == "cancelled"


def test_model_credentials_are_configured_in_web_and_encrypted_at_rest(tmp_path) -> None:
    app = create_app(cloud_settings(tmp_path))
    with TestClient(app) as client:
        app.state.model_verifier = SuccessfulModelVerifier()
        admin = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "correct-horse-battery"},
        ).json()
        key = client.post(
            "/api/v1/admin/activation-keys",
            headers=bearer(admin["token"]),
            json={},
        ).json()["display_key"]
        registration = client.post(
            "/api/v1/auth/register",
            json={
                "activation_key": key,
                "username": "model.owner",
                "password": "strong-password",
            },
        ).json()
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "model.owner", "password": "strong-password"},
        ).json()

        initial = client.get("/api/v1/model-status", headers=bearer(login["token"]))
        assert initial.status_code == 200
        assert initial.json()["asr"]["configured"] is False
        assert initial.json()["llm"]["configured"] is False

        saved = client.put(
            "/api/v1/model-credentials",
            headers=bearer(login["token"]),
            json={
                "dashscope_api_key": "dashscope-secret-value",
                "deepseek_api_key": "deepseek-secret-value",
            },
        )
        assert saved.status_code == 200
        assert saved.json()["saved"] is True
        assert "secret-value" not in saved.text

        status = client.get("/api/v1/model-status", headers=bearer(login["token"]))
        assert status.json()["asr"]["configured"] is True
        assert status.json()["llm"]["configured"] is True
        assert status.json()["storage"] == "服务器加密保存"

        assert client.portal is not None
        ciphertext = client.portal.call(
            encrypted_credentials_payload, app, registration["id"]
        )
        assert "dashscope-secret-value" not in ciphertext
        assert "deepseek-secret-value" not in ciphertext
        assert (tmp_path / "credential-encryption.key").stat().st_mode & 0o777 == 0o600

        updated = client.put(
            "/api/v1/model-credentials",
            headers=bearer(login["token"]),
            json={"deepseek_api_key": "updated-deepseek-secret"},
        )
        assert updated.status_code == 200
        stored = client.portal.call(
            app.state.model_credential_service.get, registration["id"]
        )
        assert stored.dashscope_api_key == "dashscope-secret-value"
        assert stored.deepseek_api_key == "updated-deepseek-secret"


def test_preflight_requires_aec3_capable_agent(tmp_path) -> None:
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
        registration = client.post(
            "/api/v1/auth/register",
            json={
                "activation_key": key,
                "username": "aec.owner",
                "password": "strong-password",
            },
        ).json()
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "aec.owner", "password": "strong-password"},
        ).json()
        task = client.post(
            "/api/v1/tasks",
            headers=bearer(login["token"]),
            json={"name": "AEC3 检查", "mobile_required": False},
        ).json()

        assert client.portal is not None
        client.portal.call(
            app.state.model_credential_service.save,
            registration["id"],
            ModelCredentials(
                dashscope_api_key="dashscope-secret-value",
                deepseek_api_key="deepseek-secret-value",
            ),
        )
        app.state.task_service._verifier = SuccessfulModelVerifier()
        app.state.agent_hub.is_connected = lambda _: True

        async def old_agent_preflight(*_):
            return {
                "permissions": {"screen_capture": True, "microphone": True},
                "audio_processing": {},
            }

        app.state.agent_hub.request_preflight = old_agent_preflight
        rejected = client.post(
            f"/api/v1/tasks/{task['id']}/preflight",
            headers=bearer(login["token"]),
        ).json()
        aec_check = next(check for check in rejected["checks"] if check["key"] == "aec3")
        assert aec_check["ok"] is False
        assert rejected["ready"] is False

        async def new_agent_preflight(*_):
            return {
                "permissions": {"screen_capture": True, "microphone": True},
                "audio_processing": {"aec3": True},
            }

        app.state.agent_hub.request_preflight = new_agent_preflight
        accepted = client.post(
            f"/api/v1/tasks/{task['id']}/preflight",
            headers=bearer(login["token"]),
        ).json()
        aec_check = next(check for check in accepted["checks"] if check["key"] == "aec3")
        assert aec_check["ok"] is True
        assert accepted["ready"] is True

        client.portal.call(app.state.runtime_registry.release, task["id"])
        sent_commands: list[dict[str, str]] = []

        async def send_command(_: str, payload: dict[str, str]) -> None:
            sent_commands.append(payload)

        app.state.agent_hub.send = send_command
        started = client.post(
            f"/api/v1/tasks/{task['id']}/start",
            headers=bearer(login["token"]),
        )
        assert started.status_code == 200
        assert sent_commands == [{"type": "task.start", "task_id": task["id"]}]
        restored_runtime = client.portal.call(app.state.runtime_registry.get, task["id"])
        assert restored_runtime.configured is True

        app.state.agent_hub.get = lambda _: SimpleNamespace(connected_at=0.0)
        latest = client.get(
            f"/api/v1/tasks/{task['id']}/preflight",
            headers=bearer(login["token"]),
        ).json()
        assert latest["ready"] is True

        app.state.agent_hub.get = lambda _: None
        offline = client.get(
            f"/api/v1/tasks/{task['id']}/preflight",
            headers=bearer(login["token"]),
        ).json()
        assert offline["ready"] is False
        assert offline["checks"] == [
            {
                "key": "agent",
                "label": "桌面 Agent",
                "ok": False,
                "detail": "桌面 Agent 未连接",
                "latency_ms": None,
            }
        ]

        app.state.agent_hub.get = lambda _: SimpleNamespace(connected_at=10**12)
        stale = client.get(
            f"/api/v1/tasks/{task['id']}/preflight",
            headers=bearer(login["token"]),
        ).json()
        assert stale["ready"] is False
        assert stale["checks"][0]["ok"] is True
        assert len(stale["checks"]) == 1
