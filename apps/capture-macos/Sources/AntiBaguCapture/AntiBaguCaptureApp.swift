import Foundation
import Darwin

@main
struct AntiBaguCaptureApp {
    static func main() async {
        let configuration = CaptureConfiguration()
        let permissions = await CapturePermissions.request()
        if !permissions.screenCaptureGranted {
            fputs(
                "系统音频未授权：请在 屏幕与系统音频录制 中允许 Codex/终端。\n",
                stderr
            )
        }
        if !permissions.microphoneGranted {
            fputs(
                "麦克风未授权：请在 麦克风 中允许 Codex/终端。\n",
                stderr
            )
        }
        guard permissions.screenCaptureGranted || permissions.microphoneGranted else {
            return
        }

        var interviewerSocket: AudioWebSocket?
        var candidateSocket: AudioWebSocket?
        var interviewerPump: AudioFramePump?
        var candidatePump: AudioFramePump?
        var systemAudio: SystemAudioCapture?
        var microphone: MicrophoneCapture?
        var startedChannel = false

        if permissions.microphoneGranted {
            let socket = AudioWebSocket(
                endpoint: configuration.endpoint(for: .candidate),
                metadata: configuration.metadata
            )
            let pump = AudioFramePump(socket: socket, label: "Microphone")
            let encoder = PCMFrameEncoder { packet in
                pump.submit(packet)
            }
            let capture = MicrophoneCapture(encoder: encoder)
            do {
                pump.start()
                try await socket.connect()
                try capture.start()
                candidateSocket = socket
                candidatePump = pump
                microphone = capture
                startedChannel = true
                print("麦克风正在监听 → candidate")
            } catch {
                fputs("麦克风启动失败：\(error)\n", stderr)
                capture.stop()
                await pump.stop()
                await socket.close()
            }
        }

        if permissions.screenCaptureGranted {
            let socket = AudioWebSocket(
                endpoint: configuration.endpoint(for: .interviewer),
                metadata: configuration.metadata
            )
            let pump = AudioFramePump(socket: socket, label: "System audio")
            let encoder = PCMFrameEncoder { packet in
                pump.submit(packet)
            }
            let capture = SystemAudioCapture(encoder: encoder)
            do {
                pump.start()
                try await socket.connect()
                try await capture.start()
                interviewerSocket = socket
                interviewerPump = pump
                systemAudio = capture
                startedChannel = true
                print("系统音频正在监听 → interviewer")
            } catch {
                fputs("系统音频启动失败：\(error)\n", stderr)
                await capture.stop()
                await pump.stop()
                await socket.close()
            }
        }

        if startedChannel {
            print("Anti-Bagu 正在真实监听。按 Ctrl+C 停止。")
            await waitForInterrupt()
        }

        microphone?.stop()
        await systemAudio?.stop()
        await interviewerPump?.stop()
        await candidatePump?.stop()
        await interviewerSocket?.close()
        await candidateSocket?.close()
    }

    private static func waitForInterrupt() async {
        await withCheckedContinuation { continuation in
            signal(SIGINT, SIG_IGN)
            let source = DispatchSource.makeSignalSource(signal: SIGINT)
            source.setEventHandler {
                source.cancel()
                continuation.resume()
            }
            source.resume()
        }
    }
}
