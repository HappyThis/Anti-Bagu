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
                if Task.isCancelled { return }
                do {
                    try await socket.send(packet: packet)
                } catch AudioTransportError.reconnecting {
                    continue
                } catch AudioTransportError.closed {
                    return
                } catch is CancellationError {
                    return
                } catch {
                    CLIOutput.warning("\(label) frame dropped while the channel reconnects: \(error)")
                }
            }
        }
    }

    func submit(_ packet: AudioFramePacket) {
        continuation.yield(packet)
    }

    func stop() async {
        worker?.cancel()
        continuation.finish()
        await worker?.value
        worker = nil
    }
}
