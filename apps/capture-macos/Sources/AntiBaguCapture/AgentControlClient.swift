import Foundation

actor AgentControlClient {
    private let configuration: AgentConfiguration
    private let token: String
    private let permissions: CapturePermissions
    private let capture: CaptureSession
    private let session: URLSession
    private var socket: URLSessionWebSocketTask?
    private var heartbeat: Task<Void, Never>?

    init(
        configuration: AgentConfiguration,
        token: String,
        permissions: CapturePermissions,
        session: URLSession = .shared
    ) {
        self.configuration = configuration
        self.token = token
        self.permissions = permissions
        self.session = session
        self.capture = CaptureSession(
            serverURL: configuration.serverURL,
            token: token,
            permissions: permissions
        )
    }

    func run() async throws {
        let endpoint = try controlEndpoint(configuration.serverURL)
        try ensureSecureConnection(endpoint)
        var request = URLRequest(url: endpoint)
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        let task = session.webSocketTask(with: request)
        socket = task
        task.resume()
        try await send([
            "type": "agent.hello",
            "device": [
                "device_key": Host.current().localizedName ?? "macos-default",
                "name": Host.current().localizedName ?? "macOS Agent",
                "platform": "macOS \(ProcessInfo.processInfo.operatingSystemVersionString)",
                "agent_version": "0.5.0",
            ],
        ])
        heartbeat = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(20))
                try? await self?.send(["type": "agent.heartbeat", "at": Date().timeIntervalSince1970])
            }
        }
        print("电脑助手已连接。")
        do {
            while let message = try await receive() {
                try await handle(message)
            }
        } catch {
            await close()
            throw error
        }
    }

    func close() async {
        heartbeat?.cancel()
        heartbeat = nil
        await capture.stop()
        socket?.cancel(with: .normalClosure, reason: nil)
        socket = nil
    }

    private func handle(_ payload: [String: Any]) async throws {
        let type = payload["type"] as? String
        switch type {
        case "preflight.request":
            try await send([
                "type": "preflight.result",
                "request_id": payload["request_id"] as? String ?? "",
                "task_id": payload["task_id"] as? String ?? "",
                "permissions": [
                    "screen_capture": permissions.screenCaptureGranted,
                    "microphone": permissions.microphoneGranted,
                ],
                "audio_processing": [
                    "aec3": AEC3NativeProcessor.isAvailable(),
                ],
            ])
        case "task.start", "task.resume":
            if let taskID = payload["task_id"] as? String {
                try await capture.start(taskID: taskID)
            }
        case "task.pause", "task.end":
            await capture.stop()
        default:
            break
        }
    }

    private func send(_ payload: [String: Any]) async throws {
        guard let socket else { throw AgentControlError.notConnected }
        let data = try JSONSerialization.data(withJSONObject: payload)
        guard let text = String(data: data, encoding: .utf8) else {
            throw AgentControlError.invalidMessage
        }
        try await socket.send(.string(text))
    }

    private func receive() async throws -> [String: Any]? {
        guard let socket else { return nil }
        let message = try await socket.receive()
        let data: Data
        switch message {
        case let .string(text): data = Data(text.utf8)
        case let .data(value): data = value
        @unknown default: return nil
        }
        return try JSONSerialization.jsonObject(with: data) as? [String: Any]
    }

    private func controlEndpoint(_ url: URL) throws -> URL {
        guard var components = URLComponents(url: url, resolvingAgainstBaseURL: false) else {
            throw AgentControlError.invalidServerURL
        }
        components.scheme = url.scheme == "https" ? "wss" : "ws"
        components.path = "/ws/agent"
        guard let endpoint = components.url else {
            throw AgentControlError.invalidServerURL
        }
        return endpoint
    }

    private func ensureSecureConnection(_ endpoint: URL) throws {
        let localHosts = Set(["127.0.0.1", "localhost", "::1"])
        if endpoint.scheme != "wss", !localHosts.contains(endpoint.host ?? "") {
            throw AgentControlError.insecureRemoteConnection
        }
    }
}

enum AgentControlError: Error, CustomStringConvertible {
    case invalidServerURL
    case insecureRemoteConnection
    case notConnected
    case invalidMessage

    var description: String {
        switch self {
        case .invalidServerURL: "服务地址无效"
        case .insecureRemoteConnection: "远程连接必须使用 HTTPS/WSS"
        case .notConnected: "Agent 控制通道未连接"
        case .invalidMessage: "Agent 消息编码失败"
        }
    }
}
