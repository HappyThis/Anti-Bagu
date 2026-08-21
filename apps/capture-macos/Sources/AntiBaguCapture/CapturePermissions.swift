import AVFoundation
import CoreGraphics

struct CapturePermissions: Sendable {
    let screenCaptureGranted: Bool
    let microphoneGranted: Bool

    static func current() -> CapturePermissions {
        CapturePermissions(
            screenCaptureGranted: CGPreflightScreenCaptureAccess(),
            microphoneGranted: AVCaptureDevice.authorizationStatus(for: .audio) == .authorized
        )
    }

    static func request() async -> CapturePermissions {
        let screenGranted = CGPreflightScreenCaptureAccess()
            || CGRequestScreenCaptureAccess()
        let microphoneGranted: Bool
        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .authorized:
            microphoneGranted = true
        case .notDetermined:
            microphoneGranted = await AVCaptureDevice.requestAccess(for: .audio)
        default:
            microphoneGranted = false
        }
        return CapturePermissions(
            screenCaptureGranted: screenGranted,
            microphoneGranted: microphoneGranted
        )
    }
}
