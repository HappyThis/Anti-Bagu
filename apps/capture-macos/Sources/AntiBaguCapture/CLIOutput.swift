import Darwin
import Foundation

enum CLITaskState: String {
    case idle = "IDLE"
    case running = "RUNNING"
    case paused = "PAUSED"
    case completed = "COMPLETED"
    case reconnecting = "RECONNECTING"
}

enum CLIScreenshotState: String {
    case capturing = "CAPTURING"
    case uploading = "UPLOADING"
    case analyzing = "ANALYZING"
    case completed = "COMPLETED"
    case noQuestion = "NO QUESTION"
    case timeout = "TIMEOUT"
    case failed = "FAILED"
}

enum CLIOutput {
    private enum Color: String {
        case reset = "\u{001B}[0m"
        case bold = "\u{001B}[1m"
        case dim = "\u{001B}[2m"
        case blue = "\u{001B}[34m"
        case green = "\u{001B}[32m"
        case yellow = "\u{001B}[33m"
        case red = "\u{001B}[31m"
        case cyan = "\u{001B}[36m"
    }

    private static var colorEnabled: Bool {
        guard ProcessInfo.processInfo.environment["NO_COLOR"] == nil,
              ProcessInfo.processInfo.environment["TERM"] != "dumb"
        else { return false }
        return isatty(STDOUT_FILENO) == 1
    }

    static var dynamicOutputEnabled: Bool {
        colorEnabled
    }

    static func banner() {
        write("")
        write(styled("Anti-Bagu Agent", .bold, .blue))
        write(styled("────────────────────────────────────────", .dim))
    }

    static func section(_ title: String) {
        write("")
        write(styled(title.uppercased(), .bold, .cyan))
    }

    static func row(_ label: String, _ value: String, healthy: Bool? = nil) {
        let paddedLabel = label.padding(toLength: 18, withPad: " ", startingAt: 0)
        let renderedValue: String
        if let healthy {
            renderedValue = styled(value, healthy ? .green : .yellow)
        } else {
            renderedValue = value
        }
        write("  \(styled(paddedLabel, .dim)) \(renderedValue)")
    }

    static func success(_ message: String) {
        write("\(styled("[OK]", .bold, .green)) \(message)")
    }

    static func info(_ message: String) {
        write("\(styled("[INFO]", .bold, .blue)) \(message)")
    }

    static func warning(_ message: String) {
        write("\(styled("[WARN]", .bold, .yellow)) \(message)", to: stderr)
    }

    static func error(_ message: String) {
        write("\(styled("[ERROR]", .bold, .red)) \(message)", to: stderr)
    }

    static func detail(_ message: String) {
        write("       \(styled(message, .dim))")
    }

    static func taskState(_ state: CLITaskState, taskID: String? = nil) {
        let color: Color = switch state {
        case .idle: .cyan
        case .running: .green
        case .paused, .reconnecting: .yellow
        case .completed: .blue
        }
        let suffix = taskID.map { "  \(styled(String($0.prefix(8)), .dim))" } ?? ""
        write("\(styled("[TASK]", .bold, color)) \(styled(state.rawValue, .bold, color))\(suffix)")
    }

    static func screenshotState(
        _ state: CLIScreenshotState,
        durationMilliseconds: Double? = nil
    ) {
        let color: Color = switch state {
        case .capturing, .uploading, .analyzing: .cyan
        case .completed: .green
        case .noQuestion, .timeout: .yellow
        case .failed: .red
        }
        let duration = durationMilliseconds.map {
            String(format: "  %.1fs", $0 / 1_000)
        } ?? ""
        write(
            "\(styled("[SCREENSHOT]", .bold, color)) "
                + "\(styled(state.rawValue, .bold, color))\(duration)"
        )
    }

    static func signal(interview: AudioSignalLevel, microphone: AudioSignalLevel) {
        guard dynamicOutputEnabled else { return }
        let line = "\(styled("[SIGNAL]", .bold, .cyan)) "
            + meter(label: "Interview", level: interview)
            + "   "
            + meter(label: "Microphone", level: microphone)
        writeLive(line)
    }

    static func finishSignal() {
        guard dynamicOutputEnabled else { return }
        flockfile(stdout)
        defer { funlockfile(stdout) }
        fputs("\r\u{001B}[2K", stdout)
        fflush(stdout)
    }

    private static func meter(label: String, level: AudioSignalLevel) -> String {
        let width = 12
        let filledCount = min(width, max(0, Int((level.normalized * Double(width)).rounded())))
        let filled = String(repeating: "█", count: filledCount)
        let empty = String(repeating: "░", count: width - filledCount)
        let color: Color
        if level.peak >= 0.95 {
            color = .red
        } else if level.normalized >= 0.72 {
            color = .yellow
        } else if level.normalized <= 0.08 {
            color = .dim
        } else {
            color = .green
        }
        let db = String(format: "%5.1f dB", level.decibels)
        return "\(styled(label.padding(toLength: 10, withPad: " ", startingAt: 0), .dim)) \(styled(filled, color))\(styled(empty, .dim)) \(styled(db, color))"
    }

    private static func styled(_ value: String, _ colors: Color...) -> String {
        guard colorEnabled else { return value }
        return colors.map(\.rawValue).joined() + value + Color.reset.rawValue
    }

    private static func write(_ value: String, to stream: UnsafeMutablePointer<FILE> = stdout) {
        flockfile(stream)
        defer { funlockfile(stream) }
        if isatty(fileno(stream)) == 1 {
            fputs("\r\u{001B}[2K", stream)
        }
        fputs(value + "\n", stream)
        fflush(stream)
    }

    private static func writeLive(_ value: String) {
        flockfile(stdout)
        defer { funlockfile(stdout) }
        fputs("\r\u{001B}[2K" + value, stdout)
        fflush(stdout)
    }
}
