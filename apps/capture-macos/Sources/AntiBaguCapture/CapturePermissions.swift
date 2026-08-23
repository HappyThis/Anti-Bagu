import AppKit
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

    static func openScreenCaptureSettings() async -> Bool {
        await openSettings(
            "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
        )
    }

    static func openMicrophoneSettings() async -> Bool {
        await openSettings(
            "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone"
        )
    }

    static var permissionOwnerHint: String {
        switch ProcessInfo.processInfo.environment["TERM_PROGRAM"] {
        case "Apple_Terminal": "Terminal"
        case "iTerm.app": "iTerm"
        case "WarpTerminal": "Warp"
        default: "anti-bagu-agent or the terminal that launched it"
        }
    }

    @MainActor
    private static func openSettings(_ value: String) -> Bool {
        guard let url = URL(string: value) else { return false }
        return NSWorkspace.shared.open(url)
    }
}
