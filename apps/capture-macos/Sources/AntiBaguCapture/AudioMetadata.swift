import Foundation

enum AudioChannel: String, Codable, CaseIterable, Sendable {
    case interviewer
    case candidate
}

struct AudioMetadata: Codable, Equatable, Sendable {
    let sampleRate: Int
    let channels: Int
    let sampleFormat: String
    let frameDurationMs: Int

    init(
        sampleRate: Int = 16_000,
        channels: Int = 1,
        sampleFormat: String = "pcm_s16le",
        frameDurationMs: Int = 100
    ) {
        self.sampleRate = sampleRate
        self.channels = channels
        self.sampleFormat = sampleFormat
        self.frameDurationMs = frameDurationMs
    }

    enum CodingKeys: String, CodingKey {
        case sampleRate = "sample_rate"
        case channels
        case sampleFormat = "sample_format"
        case frameDurationMs = "frame_duration_ms"
    }

    var expectedFrameBytes: Int {
        sampleRate * channels * 2 * frameDurationMs / 1_000
    }
}
