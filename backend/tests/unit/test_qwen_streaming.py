from anti_bagu.asr.qwen_streaming import QwenStreamingASRSession
from anti_bagu.interview.events import Channel, TranscriptPhase


async def test_qwen_result_maps_to_timestamped_final_event() -> None:
    events = []

    async def collect(event):
        events.append(event)

    session = QwenStreamingASRSession(
        channel=Channel.INTERVIEWER,
        api_key="test",
        ws_url="wss://example.invalid",
        model="test-model",
        transcript_handler=collect,
    )
    session._audio_origin = 1_800_000_000.0

    await session._handle_result(
        {
            "payload": {
                "output": {
                    "sentence": {
                        "text": "Redis 为什么快？",
                        "sentence_end": True,
                        "begin_time": 500,
                        "end_time": 1800,
                    }
                }
            }
        }
    )

    assert len(events) == 1
    assert events[0].phase is TranscriptPhase.FINAL
    assert events[0].audio_started_at == 1_800_000_000.5
    assert events[0].audio_ended_at == 1_800_000_001.8
