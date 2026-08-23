import AppKit
import Darwin
import Foundation

@main
struct AntiBaguCaptureApp {
    static func main() async {
        let arguments = Array(CommandLine.arguments.dropFirst())
        let command = arguments.first ?? "start"
        do {
            switch command {
            case "login":
                try await login(arguments: Array(arguments.dropFirst()))
            case "status":
                try showStatus()
            case "start":
                try await startAgent()
            case "help", "--help", "-h":
                printUsage()
            default:
                CLIOutput.error("Unknown command: \(command)")
                printUsage()
            }
        } catch {
            CLIOutput.error("Anti-Bagu Agent failed: \(error)")
            exit(1)
        }
    }

    private static func login(arguments: [String]) async throws {
        CLIOutput.banner()
        CLIOutput.section("Account")
        let options = parseOptions(arguments)
        let server = options["server"] ?? "https://101.42.92.125"
        guard let serverURL = URL(string: server) else {
            throw CLIError.usage("The server URL is invalid.")
        }
        let localHosts = Set(["127.0.0.1", "localhost", "::1"])
        if serverURL.scheme != "https", !localHosts.contains(serverURL.host ?? "") {
            throw CLIError.usage("Remote login requires HTTPS.")
        }
        _ = try await browserLogin(serverURL: serverURL)
    }

    private static func showStatus() throws {
        let configuration = try? AgentConfiguration.load()
        let session = try AgentSession.load()
        let permissions = CapturePermissions.current()
        CLIOutput.banner()
        CLIOutput.section("Account")
        CLIOutput.row("Server", configuration?.serverURL.absoluteString ?? "Not configured")
        CLIOutput.row("User", configuration?.username ?? "Not signed in")
        CLIOutput.row("Session", session == nil ? "Not signed in" : "Signed in", healthy: session != nil)
        CLIOutput.section("Audio")
        CLIOutput.row("Echo cancellation", AEC3NativeProcessor.isAvailable() ? "Ready" : "Component missing", healthy: AEC3NativeProcessor.isAvailable())
        CLIOutput.row("Interview audio", permissions.screenCaptureGranted ? "Allowed" : "Permission required", healthy: permissions.screenCaptureGranted)
        CLIOutput.row("Microphone", permissions.microphoneGranted ? "Allowed" : "Permission required", healthy: permissions.microphoneGranted)
    }

    private static func startAgent() async throws {
        CLIOutput.banner()
        let (configuration, token) = try await ensureAccount()
        let permissions = await CapturePermissions.request()
        CLIOutput.section("Permissions")
        CLIOutput.row("Interview audio", permissions.screenCaptureGranted ? "Allowed" : "Permission required", healthy: permissions.screenCaptureGranted)
        CLIOutput.row("Microphone", permissions.microphoneGranted ? "Allowed" : "Permission required", healthy: permissions.microphoneGranted)
        CLIOutput.row("Echo cancellation", AEC3NativeProcessor.isAvailable() ? "Ready" : "Component missing", healthy: AEC3NativeProcessor.isAvailable())
        if !permissions.screenCaptureGranted {
            let owner = CapturePermissions.permissionOwnerHint
            CLIOutput.warning("Screen & System Audio Recording permission is required.")
            CLIOutput.detail("Open System Settings > Privacy & Security > Screen & System Audio Recording.")
            CLIOutput.detail("Enable \(owner), then quit and restart the agent.")
            CLIOutput.detail("If it is not listed, close System Settings and run the agent again.")
            _ = await CapturePermissions.openScreenCaptureSettings()
        }
        if !permissions.microphoneGranted {
            let owner = CapturePermissions.permissionOwnerHint
            CLIOutput.warning("Microphone permission is required.")
            CLIOutput.detail("Open System Settings > Privacy & Security > Microphone.")
            CLIOutput.detail("Enable \(owner), then restart the agent.")
            if permissions.screenCaptureGranted {
                _ = await CapturePermissions.openMicrophoneSettings()
            }
        }
        let client = AgentControlClient(
            configuration: configuration,
            token: token,
            permissions: permissions
        )
        let _ = await MainActor.run {
            NSApplication.shared.setActivationPolicy(.accessory)
        }
        let screenshotHotKey = GlobalScreenshotHotKey {
            Task { await client.captureScreenshot() }
        }
        do {
            try screenshotHotKey.register()
        } catch {
            CLIOutput.warning("Screenshot shortcut unavailable: \(error)")
        }
        defer { screenshotHotKey.unregister() }
        let runner = Task {
            while !Task.isCancelled {
                do {
                    try await client.run()
                } catch {
                    if Task.isCancelled { return }
                    CLIOutput.taskState(.reconnecting)
                    CLIOutput.warning("Control channel disconnected; retrying in 1 second. \(error)")
                    try? await Task.sleep(for: .seconds(1))
                }
            }
        }
        CLIOutput.section("Agent")
        CLIOutput.success("Ready and waiting for an interview.")
        CLIOutput.row("Screenshot", "Option+Space")
        CLIOutput.detail("Press Ctrl+C to stop.")
        await waitForInterrupt()
        runner.cancel()
        await client.close()
        _ = await runner.result
    }

    private static func ensureAccount() async throws -> (AgentConfiguration, String) {
        if let configuration = try? AgentConfiguration.load(),
           let session = try AgentSession.load()
        {
            return (configuration, session.token)
        }

        CLIOutput.section("Sign in")
        CLIOutput.info("Opening the browser to connect your account.")
        CLIOutput.detail("After the first approval, future launches will connect automatically.")
        let serverURL = URL(string: "https://101.42.92.125")!
        return try await browserLogin(serverURL: serverURL)
    }

    private static func browserLogin(
        serverURL: URL
    ) async throws -> (AgentConfiguration, String) {
        let authorization = try await AgentAPI.beginBrowserAuthorization(serverURL: serverURL)
        guard let verificationURL = URL(string: authorization.verificationURL) else {
            throw CLIError.usage("The server returned an invalid login URL.")
        }
        let opened = await MainActor.run {
            NSWorkspace.shared.open(verificationURL)
        }
        guard opened else {
            throw CLIError.usage("Could not open the browser. Visit this URL manually: \(verificationURL.absoluteString)")
        }
        CLIOutput.info("Browser opened. Approve the sign-in request on the website.")

        let pollNanoseconds = UInt64(max(1, authorization.pollIntervalSeconds) * 1_000_000_000)
        while Date().timeIntervalSince1970 < authorization.expiresAt {
            try await Task.sleep(nanoseconds: pollNanoseconds)
            let result = try await AgentAPI.pollBrowserAuthorization(
                serverURL: serverURL,
                requestID: authorization.requestID,
                deviceSecret: authorization.deviceSecret
            )
            switch result.status {
            case "approved":
                guard let token = result.token,
                      let tokenExpiresAt = result.tokenExpiresAt,
                      let username = result.username,
                      !token.isEmpty,
                      !tokenExpiresAt.isEmpty,
                      !username.isEmpty
                else {
                    throw CLIError.usage("The login response was incomplete. Please sign in again.")
                }
                let configuration = AgentConfiguration(serverURL: serverURL, username: username)
                let session = AgentSession(token: token, expiresAt: tokenExpiresAt)
                guard session.isValid else {
                    throw CLIError.usage("The login session has expired. Please sign in again.")
                }
                try configuration.save()
                try session.save()
                CLIOutput.success("Signed in as \(username).")
                return (configuration, token)
            case "expired":
                throw CLIError.usage("Browser sign-in timed out. Run the agent again.")
            case "cancelled":
                throw CLIError.usage("The sign-in request was cancelled in the browser.")
            case "consumed":
                throw CLIError.usage("This sign-in request was already used. Run the agent again.")
            default:
                continue
            }
        }
        throw CLIError.usage("Browser sign-in timed out. Run the agent again.")
    }

    private static func parseOptions(_ arguments: [String]) -> [String: String] {
        var result: [String: String] = [:]
        var index = 0
        while index + 1 < arguments.count {
            let key = arguments[index]
            if key.hasPrefix("--") {
                result[String(key.dropFirst(2))] = arguments[index + 1]
                index += 2
            } else {
                index += 1
            }
        }
        return result
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

    private static func printUsage() {
        CLIOutput.banner()
        CLIOutput.section("Commands")
        CLIOutput.row("anti-bagu-agent", "Start the agent; first launch guides you through sign-in")
        CLIOutput.row("... status", "Show account, audio, and permission status")
        CLIOutput.row("... login", "Sign in with a different account")
        CLIOutput.section("Storage")
        CLIOutput.detail("Login session: ~/.anti-bagu/session.json")
        CLIOutput.detail("Model keys are managed on the website under Settings.")
    }
}

enum CLIError: Error, CustomStringConvertible {
    case usage(String)

    var description: String {
        switch self {
        case let .usage(message): message
        }
    }
}
