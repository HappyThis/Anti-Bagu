import Foundation
import Security

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
        let directory = Self.fileURL.deletingLastPathComponent()
        try FileManager.default.createDirectory(
            at: directory,
            withIntermediateDirectories: true,
            attributes: [.posixPermissions: 0o700]
        )
        let data = try JSONEncoder().encode(self)
        try data.write(to: Self.fileURL, options: .atomic)
        try FileManager.default.setAttributes(
            [.posixPermissions: 0o600],
            ofItemAtPath: Self.fileURL.path
        )
    }
}

enum AgentSecret: String {
    case agentToken = "agent-token"
    case dashscopeAPIKey = "dashscope-api-key"
    case deepseekAPIKey = "deepseek-api-key"
}

enum KeychainStore {
    private static let service = "cn.anti-bagu.agent"

    static func save(_ value: String, for secret: AgentSecret) throws {
        let data = Data(value.utf8)
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: secret.rawValue,
        ]
        SecItemDelete(query as CFDictionary)
        var item = query
        item[kSecValueData as String] = data
        item[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        let status = SecItemAdd(item as CFDictionary, nil)
        guard status == errSecSuccess else {
            throw AgentCredentialError.keychain(status)
        }
    }

    static func load(_ secret: AgentSecret) throws -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: secret.rawValue,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var result: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        if status == errSecItemNotFound { return nil }
        guard status == errSecSuccess,
              let data = result as? Data,
              let value = String(data: data, encoding: .utf8)
        else {
            throw AgentCredentialError.keychain(status)
        }
        return value
    }
}

enum AgentCredentialError: Error {
    case keychain(OSStatus)
    case missingConfiguration
    case invalidServerURL
}
