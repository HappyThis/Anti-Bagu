@preconcurrency import ScreenCaptureKit
import AVFoundation
import CoreMedia
import Foundation

final class SystemAudioCapture: NSObject, SCStreamOutput, SCStreamDelegate, @unchecked Sendable {
    private let encoder: PCMFrameEncoder
    private let sampleQueue = DispatchQueue(
        label: "anti-bagu.system-audio",
        qos: .userInteractive
    )
    private var stream: SCStream?

    init(encoder: PCMFrameEncoder) {
        self.encoder = encoder
    }

    func start() async throws {
        guard stream == nil else { return }
        let content = try await SCShareableContent.excludingDesktopWindows(
            false,
            onScreenWindowsOnly: true
        )
        guard let display = content.displays.first else {
            throw CaptureError.displayUnavailable
        }

        let filter = SCContentFilter(display: display, excludingWindows: [])
        let configuration = SCStreamConfiguration()
        configuration.width = 2
        configuration.height = 2
        configuration.minimumFrameInterval = CMTime(value: 1, timescale: 2)
        configuration.queueDepth = 3
        configuration.showsCursor = false
        configuration.capturesAudio = true
        configuration.excludesCurrentProcessAudio = true
        configuration.sampleRate = 48_000
        configuration.channelCount = 2

        let captureStream = SCStream(
            filter: filter,
            configuration: configuration,
            delegate: self
        )
        try captureStream.addStreamOutput(
            self,
            type: .audio,
            sampleHandlerQueue: sampleQueue
        )
        stream = captureStream
        try await withCheckedThrowingContinuation { continuation in
            let gate = CaptureStartGate(continuation: continuation)
            captureStream.startCapture { error in
                if let error {
                    gate.resume(throwing: error)
                } else {
                    gate.resume()
                }
            }
            DispatchQueue.global().asyncAfter(deadline: .now() + 5) {
                gate.resume(throwing: CaptureError.systemAudioStartTimedOut)
            }
        }
    }

    func stop() async {
        guard let stream else { return }
        self.stream = nil
        try? await stream.stopCapture()
    }

    func stream(
        _ stream: SCStream,
        didOutputSampleBuffer sampleBuffer: CMSampleBuffer,
        of outputType: SCStreamOutputType
    ) {
        guard outputType == .audio else { return }
        encoder.consume(sampleBuffer)
    }

    func stream(_ stream: SCStream, didStopWithError error: any Error) {
        CLIOutput.warning("System audio capture stopped: \(error)")
    }
}

private final class CaptureStartGate: @unchecked Sendable {
    private let lock = NSLock()
    private var continuation: CheckedContinuation<Void, any Error>?

    init(continuation: CheckedContinuation<Void, any Error>) {
        self.continuation = continuation
    }

    func resume() {
        finish(.success(()))
    }

    func resume(throwing error: any Error) {
        finish(.failure(error))
    }

    private func finish(_ result: Result<Void, any Error>) {
        let continuation: CheckedContinuation<Void, any Error>? = lock.withLock {
            defer { self.continuation = nil }
            return self.continuation
        }
        continuation?.resume(with: result)
    }
}
