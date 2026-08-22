import Foundation

struct AgentConfiguration: Codable, Sendable {
    let serverURL: URL
    let username: String

    static var fileURL: URL {
        FileManager.default.homeDirectoryForCurrentUser
            .appending(path: ".anti-bagu", directoryHint: .isDirectory)
            .appending(path: "config.json")
    }

    static func load() throws -> AgentConfiguration {
        try JSONDecoder().decode(
            AgentConfiguration.self,
            from: Data(contentsOf: fileURL)
        )
    }

    func save() throws {
        try SecureLocalFile.write(try JSONEncoder().encode(self), to: Self.fileURL)
    }
}

struct AgentSession: Codable, Sendable {
    let token: String
    let expiresAt: String

    enum CodingKeys: String, CodingKey {
        case token
        case expiresAt = "expires_at"
    }

    static var fileURL: URL {
        FileManager.default.homeDirectoryForCurrentUser
            .appending(path: ".anti-bagu", directoryHint: .isDirectory)
            .appending(path: "session.json")
    }

    static func load(from url: URL = fileURL) throws -> AgentSession? {
        guard FileManager.default.fileExists(atPath: url.path) else { return nil }
        let session = try JSONDecoder().decode(
            AgentSession.self,
            from: Data(contentsOf: url)
        )
        return session.isValid ? session : nil
    }

    func save(to url: URL = Self.fileURL) throws {
        try SecureLocalFile.write(try JSONEncoder().encode(self), to: url)
    }

    var isValid: Bool {
        !token.isEmpty && expirationDate.map { $0 > Date() } == true
    }

    private var expirationDate: Date? {
        let fractional = ISO8601DateFormatter()
        fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let value = fractional.date(from: expiresAt) { return value }
        return ISO8601DateFormatter().date(from: expiresAt)
    }
}

private enum SecureLocalFile {
    static func write(_ data: Data, to url: URL) throws {
        let fileManager = FileManager.default
        let directory = url.deletingLastPathComponent()
        try fileManager.createDirectory(
            at: directory,
            withIntermediateDirectories: true,
            attributes: [.posixPermissions: 0o700]
        )
        try fileManager.setAttributes(
            [.posixPermissions: 0o700],
            ofItemAtPath: directory.path
        )
        try data.write(to: url, options: .atomic)
        try fileManager.setAttributes(
            [.posixPermissions: 0o600],
            ofItemAtPath: url.path
        )
    }
}
