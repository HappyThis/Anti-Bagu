import Foundation

actor AudioTestSession {
    typealias LevelHandler = @Sendable (String, AudioChannel, AudioSignalLevel) -> Void

    private let permissions: CapturePermissions
    private let levelHandler: LevelHandler
    private var systemAudio: SystemAudioCapture?
    private var microphone: MicrophoneCapture?
    private var synchronizer: AEC3AudioSynchronizer?

    init(permissions: CapturePermissions, levelHandler: @escaping LevelHandler) {
        self.permissions = permissions
        self.levelHandler = levelHandler
    }

    func start(taskID: String) async throws {
        await stop()
        guard permissions.microphoneGranted, permissions.screenCaptureGranted else {
            throw CaptureSessionError.bothChannelsRequired
        }
        let handler = levelHandler
        let synchronizer = AEC3AudioSynchronizer(
            processor: try AEC3NativeProcessor()
        ) { packet in
            handler(taskID, .candidate, AudioSignalLevel.measure(packet.pcm))
        }
        let microphoneEncoder = PCMFrameEncoder { packet in
            synchronizer.submitCapture(packet)
        }
        let systemEncoder = PCMFrameEncoder { packet in
            synchronizer.submitRender(packet)
            handler(taskID, .interviewer, AudioSignalLevel.measure(packet.pcm))
        }
        let microphone = MicrophoneCapture(encoder: microphoneEncoder)
        let systemAudio = SystemAudioCapture(encoder: systemEncoder)
        do {
            try await systemAudio.start()
            try microphone.start()
        } catch {
            microphone.stop()
            await systemAudio.stop()
            synchronizer.flush()
            throw error
        }
        self.systemAudio = systemAudio
        self.microphone = microphone
        self.synchronizer = synchronizer
        CLIOutput.info("Audio check started.")
    }

    func stop() async {
        microphone?.stop()
        await systemAudio?.stop()
        synchronizer?.flush()
        microphone = nil
        systemAudio = nil
        synchronizer = nil
    }
}
