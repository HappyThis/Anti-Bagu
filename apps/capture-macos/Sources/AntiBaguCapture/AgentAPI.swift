import Foundation

struct BrowserAuthorizationStart: Decodable {
    let requestID: String
    let deviceSecret: String
    let verificationURL: String
    let expiresAt: Double
    let pollIntervalSeconds: Double

    enum CodingKeys: String, CodingKey {
        case requestID = "request_id"
        case deviceSecret = "device_secret"
        case verificationURL = "verification_url"
        case expiresAt = "expires_at"
        case pollIntervalSeconds = "poll_interval_seconds"
    }
}

struct BrowserAuthorizationPoll: Decodable {
    let status: String
    let token: String?
    let tokenExpiresAt: String?
    let username: String?

    enum CodingKeys: String, CodingKey {
        case status
        case token
        case tokenExpiresAt = "token_expires_at"
        case username
    }
}

enum AgentAPI {
    static func beginBrowserAuthorization(
        serverURL: URL
    ) async throws -> BrowserAuthorizationStart {
        let url = serverURL
            .appending(path: "api")
            .appending(path: "v1")
            .appending(path: "agent")
            .appending(path: "authorizations")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        return try await perform(request, as: BrowserAuthorizationStart.self)
    }

    static func pollBrowserAuthorization(
        serverURL: URL,
        requestID: String,
        deviceSecret: String
    ) async throws -> BrowserAuthorizationPoll {
        let url = serverURL
            .appending(path: "api")
            .appending(path: "v1")
            .appending(path: "agent")
            .appending(path: "authorizations")
            .appending(path: requestID)
            .appending(path: "poll")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: [
            "device_secret": deviceSecret,
        ])
        return try await perform(request, as: BrowserAuthorizationPoll.self)
    }

    private static func perform<Response: Decodable>(
        _ request: URLRequest,
        as type: Response.Type
    ) async throws -> Response {
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse,
              (200 ..< 300).contains(http.statusCode)
        else {
            let detail = (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["detail"] as? String
            throw AgentAPIError.requestFailed(detail ?? "The sign-in request could not be completed.")
        }
        return try JSONDecoder().decode(type, from: data)
    }
}

enum AgentAPIError: Error, CustomStringConvertible {
    case requestFailed(String)

    var description: String {
        switch self {
        case let .requestFailed(message): message
        }
    }
}
