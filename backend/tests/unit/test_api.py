from fastapi.testclient import TestClient

from anti_bagu.api.app import create_app
from anti_bagu.api.event_hub import EventHub
from anti_bagu.config import Settings
from anti_bagu.interview.events import RealtimeEvent


def test_health_starts_without_model_key(tmp_path) -> None:
    app = create_app(Settings(deepseek_api_key=None, audit_log_dir=tmp_path))
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["model_configured"] is False
    assert response.json()["audit_dropped_events"] == 0


def test_ui_websocket_removes_subscriber_after_disconnect(tmp_path) -> None:
    app = create_app(Settings(deepseek_api_key=None, audit_log_dir=tmp_path))
    with TestClient(app) as client:
        with client.websocket_connect("/ws/ui"):
            assert app.state.event_hub.subscriber_count == 1

        assert app.state.event_hub.subscriber_count == 0


def test_debug_events_returns_recent_redacted_audit_records(tmp_path) -> None:
    app = create_app(Settings(deepseek_api_key=None, audit_log_dir=tmp_path))
    with TestClient(app) as client:
        response = client.post(
            "/api/transcripts",
            json={
                "channel": "candidate",
                "phase": "final",
                "text": "我的回答",
            },
        )
        assert response.status_code == 202
        debug = client.get(
            "/api/debug/events", params={"event_prefix": "transcript."}
        )

    assert debug.status_code == 200
    body = debug.json()
    assert body["text_included"] is False
    assert [item["event"] for item in body["events"]] == [
        "transcript.final",
        "transcript.committed",
    ]
    assert body["events"][0]["payload"]["text"]["redacted"] is True


async def test_event_hub_replays_latest_audio_and_latency_state() -> None:
    hub = EventHub()
    await hub.publish(
        RealtimeEvent(
            type="audio.connected",
            session_id="session",
            conversation_revision=0,
            payload={"channel": "candidate"},
        )
    )
    await hub.publish(
        RealtimeEvent(
            type="latency.updated",
            session_id="session",
            conversation_revision=0,
            payload={"microphone": 1.2},
        )
    )

    async with hub.subscribe() as queue:
        audio = queue.get_nowait()
        latency = queue.get_nowait()

    assert audio.type == "audio.connected"
    assert latency.payload == {"microphone": 1.2}
