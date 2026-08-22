import Darwin
import Foundation

@main
struct AntiBaguCaptureApp {
    static func main() async {
        let arguments = Array(CommandLine.arguments.dropFirst())
        let command = arguments.first ?? "help"
        do {
            switch command {
            case "login":
                try await login(arguments: Array(arguments.dropFirst()))
            case "configure-models":
                try configureModels()
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
        guard let server = options["server"],
              let serverURL = URL(string: server),
              let username = options["username"],
              !username.isEmpty
        else {
            throw CLIError.usage("login 需要 --server 和 --username")
        }
        let localHosts = Set(["127.0.0.1", "localhost", "::1"])
        if serverURL.scheme != "https", !localHosts.contains(serverURL.host ?? "") {
            throw CLIError.usage("远程登录必须使用 HTTPS，拒绝通过明文连接发送密码")
        }
        let password = try securePrompt("账户密码：")
        let response = try await AgentAPI.login(
            serverURL: serverURL,
            username: username,
            password: password
        )
        try AgentConfiguration(serverURL: serverURL, username: username).save()
        try KeychainStore.save(response.token, for: .agentToken)
        print("登录成功，Agent Token 已保存到系统钥匙串，有效期至 \(response.expiresAt)")
    }

    private static func configureModels() throws {
        let dashscope = try securePrompt("DashScope API Key：")
        let deepseek = try securePrompt("DeepSeek API Key：")
        guard !dashscope.isEmpty, !deepseek.isEmpty else {
            throw CLIError.usage("两个模型 Key 都不能为空")
        }
        try KeychainStore.save(dashscope, for: .dashscopeAPIKey)
        try KeychainStore.save(deepseek, for: .deepseekAPIKey)
        print("模型 Key 已保存到当前 Mac 的系统钥匙串。")
    }

    private static func showStatus() throws {
        let configuration = try? AgentConfiguration.load()
        let token = try KeychainStore.load(.agentToken)
        let dashscope = try KeychainStore.load(.dashscopeAPIKey)
        let deepseek = try KeychainStore.load(.deepseekAPIKey)
        print("服务：\(configuration?.serverURL.absoluteString ?? "未配置")")
        print("用户：\(configuration?.username ?? "未登录")")
        print("Agent Token：\(token == nil ? "未配置" : "已配置")")
        print("ASR 模型 Key：\(dashscope == nil ? "未配置" : "已配置")")
        print("LLM 模型 Key：\(deepseek == nil ? "未配置" : "已配置")")
        let permissions = CapturePermissions.current()
        print("系统音频权限：\(permissions.screenCaptureGranted ? "已授权" : "未授权")")
        print("麦克风权限：\(permissions.microphoneGranted ? "已授权" : "未授权")")
    }

    private static func startAgent() async throws {
        let configuration = try AgentConfiguration.load()
        guard let token = try KeychainStore.load(.agentToken) else {
            throw CLIError.usage("尚未登录，请先执行 anti-bagu-agent login")
        }
        let permissions = await CapturePermissions.request()
        if !permissions.screenCaptureGranted {
            fputs("系统音频未授权：请在“屏幕与系统音频录制”中允许当前终端。\n", stderr)
        }
        if !permissions.microphoneGranted {
            fputs("麦克风未授权：请在“麦克风”中允许当前终端。\n", stderr)
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
        print("Anti-Bagu Agent 正在等待任务。按 Ctrl+C 停止。")
        await waitForInterrupt()
        runner.cancel()
        await client.close()
        _ = await runner.result
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

    private static func securePrompt(_ prompt: String) throws -> String {
        guard let pointer = getpass(prompt) else { throw CLIError.inputUnavailable }
        return String(cString: pointer)
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

          anti-bagu-agent login --server https://example.com --username your-name
          anti-bagu-agent configure-models
          anti-bagu-agent status
          anti-bagu-agent start

        模型 Key 和 Agent Token 只保存在 macOS 系统钥匙串中。
        """)
    }
}

enum CLIError: Error, CustomStringConvertible {
    case usage(String)
    case inputUnavailable

    var description: String {
        switch self {
        case let .usage(message): message
        case .inputUnavailable: "无法读取终端输入"
        }
    }
}
