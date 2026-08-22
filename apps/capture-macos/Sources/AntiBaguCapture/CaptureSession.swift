import Foundation

actor CaptureSession {
    private let serverURL: URL
    private let token: String
    private let permissions: CapturePermissions
    private var activeTaskID: String?
    private var interviewerSocket: AudioWebSocket?
    private var candidateSocket: AudioWebSocket?
    private var interviewerPump: AudioFramePump?
    private var candidatePump: AudioFramePump?
    private var systemAudio: SystemAudioCapture?
    private var microphone: MicrophoneCapture?

    init(serverURL: URL, token: String, permissions: CapturePermissions) {
        self.serverURL = serverURL
        self.token = token
        self.permissions = permissions
    }

    func start(taskID: String) async throws {
        if activeTaskID == taskID { return }
        await stop()
        let configuration = CaptureConfiguration(
            backendURL: websocketBaseURL(serverURL)
        )
        var startedChannel = false

        if permissions.microphoneGranted {
            let socket = AudioWebSocket(
                endpoint: configuration.endpoint(taskID: taskID, for: .candidate),
                metadata: configuration.metadata,
                authorizationToken: token
            )
            let pump = AudioFramePump(socket: socket, label: "Microphone")
            let encoder = PCMFrameEncoder { packet in pump.submit(packet) }
            let capture = MicrophoneCapture(encoder: encoder)
            pump.start()
            do {
                try await socket.connect()
                try capture.start()
                candidateSocket = socket
                candidatePump = pump
                microphone = capture
                startedChannel = true
            } catch {
                capture.stop()
                await pump.stop()
                await socket.close()
                throw error
            }
        }

        if permissions.screenCaptureGranted {
            let socket = AudioWebSocket(
                endpoint: configuration.endpoint(taskID: taskID, for: .interviewer),
                metadata: configuration.metadata,
                authorizationToken: token
            )
            let pump = AudioFramePump(socket: socket, label: "System audio")
            let encoder = PCMFrameEncoder { packet in pump.submit(packet) }
            let capture = SystemAudioCapture(encoder: encoder)
            pump.start()
            do {
                try await socket.connect()
                try await capture.start()
                interviewerSocket = socket
                interviewerPump = pump
                systemAudio = capture
                startedChannel = true
            } catch {
                await capture.stop()
                await pump.stop()
                await socket.close()
                await stop()
                throw error
            }
        }

        guard startedChannel else { throw CaptureSessionError.noAvailableChannel }
        activeTaskID = taskID
        print("任务 \(taskID) 已开始双路采集")
    }

    func stop() async {
        microphone?.stop()
        await systemAudio?.stop()
        await interviewerPump?.stop()
        await candidatePump?.stop()
        await interviewerSocket?.close()
        await candidateSocket?.close()
        microphone = nil
        systemAudio = nil
        interviewerPump = nil
        candidatePump = nil
        interviewerSocket = nil
        candidateSocket = nil
        activeTaskID = nil
    }

    private func websocketBaseURL(_ url: URL) -> URL {
        var components = URLComponents(url: url, resolvingAgainstBaseURL: false)!
        components.scheme = url.scheme == "https" ? "wss" : "ws"
        components.path = ""
        return components.url!
    }
}

enum CaptureSessionError: Error {
    case noAvailableChannel
}
