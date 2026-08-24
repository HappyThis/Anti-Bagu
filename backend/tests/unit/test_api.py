from fastapi.testclient import TestClient

from anti_bagu.agent.hub import AgentHub
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
    assert response.json()["model_mode"] == "per_user"
    assert response.json()["audit_dropped_events"] == 0


def test_legacy_global_realtime_endpoints_are_not_exposed(tmp_path) -> None:
    app = create_app(Settings(deepseek_api_key=None, audit_log_dir=tmp_path))
    with TestClient(app) as client:
        transcript = client.post(
            "/api/transcripts",
            json={
                "channel": "candidate",
                "phase": "final",
                "text": "我的回答",
            },
        )
        debug = client.get("/api/debug/events")

    assert transcript.status_code == 404
    assert debug.status_code == 404
    assert not any(
        getattr(route, "path", None) in {"/ws/ui", "/ws/audio/{channel}"}
        for route in app.routes
    )


def test_agent_hub_tracks_temporary_audio_test_levels() -> None:
    hub = AgentHub()
    hub.start_audio_test("user", "task")
    hub.handle_message(
        "user",
        {
            "type": "preflight.audio.level",
            "task_id": "task",
            "channel": "candidate",
            "rms": 0.12,
            "peak": 0.45,
        },
    )

    state = hub.audio_test_state("user", "task")
    assert state["active"] is True
    assert state["levels"]["candidate"]["rms"] == 0.12
    assert state["levels"]["candidate"]["peak"] == 0.45

    hub.stop_audio_test("user", "task")
    assert hub.audio_test_state("user", "task")["active"] is False


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


async def test_event_hub_aggregates_only_summary_latency_dimensions() -> None:
    hub = EventHub()
    for payload in (
        {"asr": 100.0, "microphone": 2.0},
        {"asr": 300.0, "model": 400.0, "endToEnd": 900.0},
        {"model": 600.0, "endToEnd": 1_100.0},
    ):
        await hub.publish(
            RealtimeEvent(
                type="latency.updated",
                session_id="session",
                conversation_revision=0,
                payload=payload,
            )
        )

    assert hub.latency_summary() == {
        "asr_sample_count": 2,
        "asr_avg_ms": 200.0,
        "model_sample_count": 2,
        "model_avg_ms": 500.0,
        "end_to_end_sample_count": 2,
        "end_to_end_avg_ms": 1_000.0,
    }


async def test_event_hub_replays_latest_screenshot_state() -> None:
    hub = EventHub()
    await hub.publish(
        RealtimeEvent(
            type="screenshot.accepted",
            session_id="session",
            conversation_revision=0,
            payload={"screenshot_id": "screen-1"},
        )
    )
    await hub.publish(
        RealtimeEvent(
            type="screenshot.focus.released",
            session_id="session",
            conversation_revision=0,
            payload={
                "screenshot_id": "screen-1",
                "outcome": "completed",
                "duration_ms": 21_630,
            },
        )
    )

    async with hub.subscribe() as queue:
        screenshot = queue.get_nowait()

    assert screenshot.type == "screenshot.focus.released"
    assert screenshot.payload["duration_ms"] == 21_630
