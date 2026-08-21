import AVFoundation
import Foundation

final class MicrophoneCapture: @unchecked Sendable {
    private let engine = AVAudioEngine()
    private let encoder: PCMFrameEncoder
    private var running = false

    init(encoder: PCMFrameEncoder) {
        self.encoder = encoder
    }

    func start() throws {
        guard !running else { return }
        let input = engine.inputNode
        let format = input.outputFormat(forBus: 0)
        guard format.channelCount > 0, format.sampleRate > 0 else {
            throw CaptureError.microphoneUnavailable
        }
        input.installTap(
            onBus: 0,
            bufferSize: 1_024,
            format: format
        ) { [encoder] buffer, _ in
            encoder.consume(buffer)
        }
        engine.prepare()
        try engine.start()
        running = true
    }

    func stop() {
        guard running else { return }
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
        running = false
    }
}

enum CaptureError: Error {
    case microphoneUnavailable
    case displayUnavailable
    case systemAudioStartTimedOut
}
