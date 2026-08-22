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
                fputs("未知命令：\(command)\n", stderr)
                printUsage()
            }
        } catch {
            fputs("Anti-Bagu Agent 错误：\(error)\n", stderr)
            exit(1)
        }
    }

    private static func login(arguments: [String]) async throws {
        let options = parseOptions(arguments)
        let server = options["server"] ?? "https://101.42.92.125"
        guard let serverURL = URL(string: server) else {
            throw CLIError.usage("服务地址无效")
        }
        let localHosts = Set(["127.0.0.1", "localhost", "::1"])
        if serverURL.scheme != "https", !localHosts.contains(serverURL.host ?? "") {
            throw CLIError.usage("远程登录必须使用 HTTPS")
        }
        _ = try await browserLogin(serverURL: serverURL)
    }

    private static func showStatus() throws {
        let configuration = try? AgentConfiguration.load()
        let session = try AgentSession.load()
        print("服务：\(configuration?.serverURL.absoluteString ?? "未配置")")
        print("用户：\(configuration?.username ?? "未登录")")
        print("登录状态：\(session == nil ? "未登录" : "已登录")")
        print("回声消除：\(AEC3NativeProcessor.isAvailable() ? "已准备" : "缺少组件")")
        let permissions = CapturePermissions.current()
        print("面试声音：\(permissions.screenCaptureGranted ? "已允许" : "需要允许")")
        print("我的声音：\(permissions.microphoneGranted ? "已允许" : "需要允许")")
    }

    private static func startAgent() async throws {
        let (configuration, token) = try await ensureAccount()
        let permissions = await CapturePermissions.request()
        if !permissions.screenCaptureGranted {
            let owner = CapturePermissions.permissionOwnerHint
            fputs("""

            尚未允许获取面试声音。
            已打开“系统设置 → 隐私与安全性 → 屏幕与系统音频录制”。
            请在列表中找到“\(owner)”并打开开关，然后完全退出电脑助手并重新打开。
            如果列表中没有它，请先关闭系统设置，再重新运行一次电脑助手。

            """, stderr)
            _ = await CapturePermissions.openScreenCaptureSettings()
        }
        if !permissions.microphoneGranted {
            let owner = CapturePermissions.permissionOwnerHint
            fputs("""

            尚未允许获取你的声音。
            请在“系统设置 → 隐私与安全性 → 麦克风”中找到“\(owner)”并打开开关，随后重新打开电脑助手。

            """, stderr)
            if permissions.screenCaptureGranted {
                _ = await CapturePermissions.openMicrophoneSettings()
            }
        }
        let client = AgentControlClient(
            configuration: configuration,
            token: token,
            permissions: permissions
        )
        let runner = Task {
            while !Task.isCancelled {
                do {
                    try await client.run()
                } catch {
                    if Task.isCancelled { return }
                    fputs("控制通道断开，1 秒后重连：\(error)\n", stderr)
                    try? await Task.sleep(for: .seconds(1))
                }
            }
        }
        print("Anti-Bagu 电脑助手已经打开，正在等待面试。按 Ctrl+C 停止。")
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

        print("""

        欢迎使用 Anti-Bagu 电脑助手
        即将打开网页登录。首次允许后，以后打开会自动连接。

        """)
        let serverURL = URL(string: "https://101.42.92.125")!
        return try await browserLogin(serverURL: serverURL)
    }

    private static func browserLogin(
        serverURL: URL
    ) async throws -> (AgentConfiguration, String) {
        let authorization = try await AgentAPI.beginBrowserAuthorization(serverURL: serverURL)
        guard let verificationURL = URL(string: authorization.verificationURL) else {
            throw CLIError.usage("服务返回了无效的登录地址")
        }
        let opened = await MainActor.run {
            NSWorkspace.shared.open(verificationURL)
        }
        guard opened else {
            throw CLIError.usage("无法打开浏览器，请手动访问：\(verificationURL.absoluteString)")
        }
        print("已打开浏览器，请在网页中确认登录。")

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
                    throw CLIError.usage("登录结果不完整，请重新登录")
                }
                let configuration = AgentConfiguration(serverURL: serverURL, username: username)
                let session = AgentSession(token: token, expiresAt: tokenExpiresAt)
                guard session.isValid else {
                    throw CLIError.usage("登录结果已过期，请重新登录")
                }
                try configuration.save()
                try session.save()
                print("登录成功，账号：\(username)。")
                return (configuration, token)
            case "expired":
                throw CLIError.usage("网页登录已超时，请重新运行电脑助手")
            case "cancelled":
                throw CLIError.usage("你已在网页中取消登录")
            case "consumed":
                throw CLIError.usage("这次登录已被使用，请重新运行电脑助手")
            default:
                continue
            }
        }
        throw CLIError.usage("网页登录已超时，请重新运行电脑助手")
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
        print("""
        Anti-Bagu 桌面 Agent

          anti-bagu-agent              首次使用会自动引导，之后直接启动
          anti-bagu-agent status       查看当前准备状态
          anti-bagu-agent login        更换登录账号

        登录凭据保存在 ~/.anti-bagu/session.json；模型服务密钥请在网页“设置”中管理。
        """)
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
