import Foundation

actor AudioWebSocket {
    private let endpoint: URL
    private let metadata: AudioMetadata
    private let authorizationToken: String?
    private let session: URLSession
    private var task: URLSessionWebSocketTask?
    private var receiveTask: Task<Void, Never>?
    private var intentionallyClosed = false

    init(
        endpoint: URL,
        metadata: AudioMetadata,
        authorizationToken: String? = nil,
        session: URLSession = .shared
    ) {
        self.endpoint = endpoint
        self.metadata = metadata
        self.authorizationToken = authorizationToken
        self.session = session
    }

    func connect() async throws {
        guard task == nil else { return }
        intentionallyClosed = false
        var request = URLRequest(url: endpoint)
        if let authorizationToken {
            request.setValue("Bearer \(authorizationToken)", forHTTPHeaderField: "Authorization")
        }
        let socket = session.webSocketTask(with: request)
        socket.resume()
        let encoded = try JSONEncoder().encode(metadata)
        guard let message = String(data: encoded, encoding: .utf8) else {
            throw AudioTransportError.invalidMetadata
        }
        try await socket.send(.string(message))
        task = socket
        startReceiving(from: socket)
    }

    func send(frame: Data) async throws {
        var lastError: Error = AudioTransportError.notConnected
        for attempt in 1 ... 3 {
            do {
                if task == nil {
                    try await connect()
                }
                guard let task else { throw AudioTransportError.notConnected }
                try await task.send(.data(frame))
                return
            } catch {
                lastError = error
                task?.cancel(with: .goingAway, reason: nil)
                task = nil
                if attempt < 3 {
                    try? await Task.sleep(for: .milliseconds(200 * attempt))
                }
            }
        }
        throw lastError
    }

    func send(packet: AudioFramePacket) async throws {
        try await send(frame: packet.encoded)
    }

    func close() {
        intentionallyClosed = true
        receiveTask?.cancel()
        receiveTask = nil
        task?.cancel(with: .normalClosure, reason: nil)
        task = nil
    }

    private func startReceiving(from socket: URLSessionWebSocketTask) {
        receiveTask?.cancel()
        receiveTask = Task { [weak self] in
            do {
                while !Task.isCancelled {
                    _ = try await socket.receive()
                }
            } catch {
                await self?.didDisconnect(socket: socket, error: error)
            }
        }
    }

    private func didDisconnect(
        socket: URLSessionWebSocketTask,
        error: Error
    ) {
        guard task === socket else { return }
        task = nil
        if !intentionallyClosed {
            CLIOutput.warning("Audio channel disconnected; the next frame will retry. \(error)")
        }
    }
}

enum AudioTransportError: Error {
    case invalidMetadata
    case notConnected
}
