import Foundation

final class AudioFramePump: @unchecked Sendable {
    private let stream: AsyncStream<AudioFramePacket>
    private let continuation: AsyncStream<AudioFramePacket>.Continuation
    private let socket: AudioWebSocket
    private let label: String
    private var worker: Task<Void, Never>?

    init(socket: AudioWebSocket, label: String) {
        var capturedContinuation: AsyncStream<AudioFramePacket>.Continuation?
        stream = AsyncStream(bufferingPolicy: .bufferingNewest(30)) { continuation in
            capturedContinuation = continuation
        }
        continuation = capturedContinuation!
        self.socket = socket
        self.label = label
    }

    func start() {
        guard worker == nil else { return }
        worker = Task { [stream, socket, label] in
            for await packet in stream {
                do {
                    try await socket.send(packet: packet)
                } catch {
                    CLIOutput.error("\(label) transport unavailable after retries: \(error)")
                }
            }
        }
    }

    func submit(_ packet: AudioFramePacket) {
        continuation.yield(packet)
    }

    func stop() async {
        continuation.finish()
        await worker?.value
        worker = nil
    }
}
