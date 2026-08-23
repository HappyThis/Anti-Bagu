import Darwin
import Foundation

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

    private static func styled(_ value: String, _ colors: Color...) -> String {
        guard colorEnabled else { return value }
        return colors.map(\.rawValue).joined() + value + Color.reset.rawValue
    }

    private static func write(_ value: String, to stream: UnsafeMutablePointer<FILE> = stdout) {
        fputs(value + "\n", stream)
        fflush(stream)
    }
}
