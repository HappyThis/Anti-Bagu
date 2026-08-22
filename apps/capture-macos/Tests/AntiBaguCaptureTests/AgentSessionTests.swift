import Foundation
import Testing
@testable import AntiBaguCapture

@Test
func agentSessionUsesOwnerOnlyFilePermissions() throws {
    let directory = FileManager.default.temporaryDirectory
        .appending(path: "anti-bagu-session-\(UUID().uuidString)")
    let file = directory.appending(path: "session.json")
    defer { try? FileManager.default.removeItem(at: directory) }

    let session = AgentSession(
        token: "test-agent-token",
        expiresAt: ISO8601DateFormatter().string(
            from: Date().addingTimeInterval(3_600)
        )
    )
    try session.save(to: file)
    let loaded = try AgentSession.load(from: file)

    #expect(loaded?.token == "test-agent-token")
    #expect(permissions(of: directory) == 0o700)
    #expect(permissions(of: file) == 0o600)
}

@Test
func expiredAgentSessionIsNotLoaded() throws {
    let directory = FileManager.default.temporaryDirectory
        .appending(path: "anti-bagu-expired-session-\(UUID().uuidString)")
    let file = directory.appending(path: "session.json")
    defer { try? FileManager.default.removeItem(at: directory) }

    try AgentSession(
        token: "expired-token",
        expiresAt: ISO8601DateFormatter().string(
            from: Date().addingTimeInterval(-60)
        )
    ).save(to: file)

    #expect(try AgentSession.load(from: file) == nil)
}

private func permissions(of url: URL) -> Int {
    let attributes = try? FileManager.default.attributesOfItem(atPath: url.path)
    return (attributes?[.posixPermissions] as? NSNumber)?.intValue ?? -1
}
