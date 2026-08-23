import Foundation

actor AudioWebSocket {
    private let endpoint: URL
    private let metadata: AudioMetadata
    private let authorizationToken: String?
    private let session: URLSession
    private var task: URLSessionWebSocketTask?
    private var receiveTask: Task<Void, Never>?
    private var intentionallyClosed = false
    private var reconnectDelay: TimeInterval = 0.5
    private var reconnectAfter = Date.distantPast

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
        guard !intentionallyClosed else { throw AudioTransportError.closed }
        guard Date() >= reconnectAfter else { throw AudioTransportError.reconnecting }
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
        do {
            try await socket.send(.string(message))
        } catch {
            socket.cancel(with: .goingAway, reason: nil)
            reconnectAfter = Date().addingTimeInterval(reconnectDelay)
            reconnectDelay = min(5, reconnectDelay * 2)
            throw error
        }
        task = socket
        reconnectDelay = 0.5
        reconnectAfter = .distantPast
        startReceiving(from: socket)
    }

    func send(frame: Data) async throws {
        guard !Task.isCancelled else { throw CancellationError() }
        guard !intentionallyClosed else { throw AudioTransportError.closed }
        if task == nil {
            try await connect()
        }
        guard let task else { throw AudioTransportError.notConnected }
        do {
            try await task.send(.data(frame))
            reconnectDelay = 0.5
        } catch {
            scheduleReconnect(socket: task)
            throw error
        }
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
        reconnectAfter = .distantFuture
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
        scheduleReconnect(socket: socket)
        if !intentionallyClosed {
            CLIOutput.warning("Audio channel disconnected; retrying with backoff. \(error)")
        }
    }

    private func scheduleReconnect(socket: URLSessionWebSocketTask) {
        guard task === socket else { return }
        socket.cancel(with: .goingAway, reason: nil)
        task = nil
        reconnectAfter = Date().addingTimeInterval(reconnectDelay)
        reconnectDelay = min(5, reconnectDelay * 2)
    }
}

enum AudioTransportError: Error {
    case invalidMetadata
    case notConnected
    case reconnecting
    case closed
}
