import Foundation

actor AgentControlClient {
    private let configuration: AgentConfiguration
    private let token: String
    private let permissions: CapturePermissions
    private let capture: CaptureSession
    private let session: URLSession
    private var socket: URLSessionWebSocketTask?
    private var heartbeat: Task<Void, Never>?
    private var audioTest: AudioTestSession?
    private var activeTaskID: String?
    private var screenshotSubmitting = false
    private var lastScreenshotAt: TimeInterval = 0

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
                "agent_version": "0.8.0",
                "capabilities": [
                    "preflight_audio_test_v1",
                    "terminal_signal_meter_v1",
                    "screenshot_focus_v1",
                    "global_hotkey_v1",
                ],
            ],
        ])
        heartbeat = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(20))
                try? await self?.send(["type": "agent.heartbeat", "at": Date().timeIntervalSince1970])
            }
        }
        CLIOutput.success("Control channel connected.")
        CLIOutput.taskState(.idle)
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
        await audioTest?.stop()
        audioTest = nil
        await capture.stop()
        activeTaskID = nil
        screenshotSubmitting = false
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
        case "preflight.audio_test.start":
            guard let taskID = payload["task_id"] as? String else { return }
            await audioTest?.stop()
            let session = AudioTestSession(permissions: permissions) { [weak self] taskID, channel, level in
                Task {
                    try? await self?.send([
                        "type": "preflight.audio.level",
                        "task_id": taskID,
                        "channel": channel.rawValue,
                        "rms": level.rms,
                        "peak": level.peak,
                    ])
                }
            }
            audioTest = session
            try await session.start(taskID: taskID)
        case "preflight.audio_test.stop":
            await audioTest?.stop()
            audioTest = nil
        case "task.start":
            if let taskID = payload["task_id"] as? String {
                await audioTest?.stop()
                audioTest = nil
                try await capture.start(taskID: taskID)
                activeTaskID = taskID
                CLIOutput.taskState(.running, taskID: taskID)
            }
        case "task.resume":
            if let taskID = payload["task_id"] as? String {
                try await capture.start(taskID: taskID)
                activeTaskID = taskID
                CLIOutput.taskState(.running, taskID: taskID)
            }
        case "task.pause":
            await capture.stop()
            activeTaskID = nil
            CLIOutput.taskState(.paused, taskID: payload["task_id"] as? String)
        case "task.end":
            await capture.stop()
            activeTaskID = nil
            CLIOutput.taskState(.completed, taskID: payload["task_id"] as? String)
            CLIOutput.taskState(.idle)
        case "screenshot.result":
            screenshotSubmitting = false
            let status = payload["status"] as? String ?? "rejected"
            let message = payload["message"] as? String ?? ""
            switch status {
            case "accepted":
                CLIOutput.screenshotState(.analyzing)
            case "busy":
                CLIOutput.warning("The previous screenshot is still being analyzed.")
            default:
                CLIOutput.screenshotState(.failed)
                if !message.isEmpty { CLIOutput.detail(message) }
            }
        case "screenshot.status":
            let status = payload["status"] as? String ?? "error"
            let duration = payload["duration_ms"] as? Double
            switch status {
            case "completed":
                CLIOutput.screenshotState(.completed, durationMilliseconds: duration)
            case "no_question":
                CLIOutput.screenshotState(.noQuestion, durationMilliseconds: duration)
            case "timeout":
                CLIOutput.screenshotState(.timeout, durationMilliseconds: duration)
            default:
                CLIOutput.screenshotState(.failed, durationMilliseconds: duration)
            }
        default:
            break
        }
    }

    func captureScreenshot() async {
        guard let taskID = activeTaskID else {
            CLIOutput.warning("Start an interview before using Option+Space.")
            return
        }
        let now = Date().timeIntervalSince1970
        guard now - lastScreenshotAt >= 0.8 else { return }
        guard !screenshotSubmitting else {
            CLIOutput.warning("A screenshot is already being submitted.")
            return
        }
        screenshotSubmitting = true
        lastScreenshotAt = now
        CLIOutput.screenshotState(.capturing)
        do {
            let data = try ScreenshotCapture.captureJPEG()
            CLIOutput.screenshotState(.uploading)
            try await send([
                "type": "screenshot.submit",
                "request_id": UUID().uuidString,
                "task_id": taskID,
                "mime_type": "image/jpeg",
                "image_base64": data.base64EncodedString(),
            ])
        } catch {
            screenshotSubmitting = false
            CLIOutput.screenshotState(.failed)
            CLIOutput.error("Screenshot failed: \(error)")
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
        case .invalidServerURL: "The server URL is invalid."
        case .insecureRemoteConnection: "Remote connections require HTTPS/WSS."
        case .notConnected: "The agent control channel is not connected."
        case .invalidMessage: "The agent message could not be encoded."
        }
    }
}
