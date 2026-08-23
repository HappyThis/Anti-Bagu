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
    private var aecSynchronizer: AEC3AudioSynchronizer?
    private var signalMeter: TerminalSignalMeter?

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
        guard permissions.microphoneGranted, permissions.screenCaptureGranted else {
            throw CaptureSessionError.bothChannelsRequired
        }

        let interviewerSocket = AudioWebSocket(
            endpoint: configuration.endpoint(taskID: taskID, for: .interviewer),
            metadata: configuration.metadata,
            authorizationToken: token
        )
        let candidateSocket = AudioWebSocket(
            endpoint: configuration.endpoint(taskID: taskID, for: .candidate),
            metadata: configuration.metadata,
            authorizationToken: token
        )
        let interviewerPump = AudioFramePump(
            socket: interviewerSocket,
            label: "System audio"
        )
        let candidatePump = AudioFramePump(
            socket: candidateSocket,
            label: "AEC3 microphone"
        )
        let signalMeter = TerminalSignalMeter()
        let synchronizer = AEC3AudioSynchronizer(
            processor: try AEC3NativeProcessor()
        ) { packet in
            candidatePump.submit(packet)
            Task { await signalMeter.update(channel: .candidate, pcm: packet.pcm) }
        }
        let microphoneEncoder = PCMFrameEncoder { packet in
            synchronizer.submitCapture(packet)
        }
        let systemEncoder = PCMFrameEncoder { packet in
            interviewerPump.submit(packet)
            synchronizer.submitRender(packet)
            Task { await signalMeter.update(channel: .interviewer, pcm: packet.pcm) }
        }
        let microphone = MicrophoneCapture(encoder: microphoneEncoder)
        let systemAudio = SystemAudioCapture(encoder: systemEncoder)

        interviewerPump.start()
        candidatePump.start()
        await signalMeter.start()
        do {
            try await interviewerSocket.connect()
            try await candidateSocket.connect()
            try await systemAudio.start()
            try microphone.start()
        } catch {
            microphone.stop()
            await systemAudio.stop()
            synchronizer.flush()
            await interviewerSocket.close()
            await candidateSocket.close()
            await interviewerPump.stop()
            await candidatePump.stop()
            await signalMeter.stop()
            throw error
        }

        self.interviewerSocket = interviewerSocket
        self.candidateSocket = candidateSocket
        self.interviewerPump = interviewerPump
        self.candidatePump = candidatePump
        self.systemAudio = systemAudio
        self.microphone = microphone
        aecSynchronizer = synchronizer
        self.signalMeter = signalMeter
        activeTaskID = taskID
    }

    func stop() async {
        microphone?.stop()
        await systemAudio?.stop()
        aecSynchronizer?.flush()
        await signalMeter?.stop()
        await interviewerSocket?.close()
        await candidateSocket?.close()
        await interviewerPump?.stop()
        await candidatePump?.stop()
        microphone = nil
        systemAudio = nil
        aecSynchronizer = nil
        signalMeter = nil
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
    case bothChannelsRequired
}
